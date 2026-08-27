"""Populate the bench with a real access history, through the real flows.

Nothing is fabricated in the database: two people actually sign in through the
IdP (one over OIDC, one over SAML), land in the pending queue because approval is
required, and are then validated or refused by the administrator. The history
screen therefore shows genuine audit entries.
"""
import html as htmlmod
import http.cookiejar
import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP, IDP = "https://app.localtest.me", "https://idp.localtest.me"
CTX = ssl.create_default_context(cafile=str(HERE / "pki" / "ca.crt"))

_real = socket.getaddrinfo
socket.getaddrinfo = lambda h, p, *a, **k: (
    _real("127.0.0.1", p, *a, **k) if h.endswith("localtest.me") else _real(h, p, *a, **k))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a):
        return None


def opener(jar, follow=True):
    hs = [urllib.request.HTTPSHandler(context=CTX), urllib.request.HTTPCookieProcessor(jar)]
    if not follow:
        hs.append(NoRedirect())
    return urllib.request.build_opener(*hs)


def req(op, url, data=None, method=None):
    if isinstance(data, (dict, list)):
        body, ctype = json.dumps(data).encode(), "application/json"
    elif isinstance(data, str):
        body, ctype = data.encode(), "application/x-www-form-urlencoded"
    else:
        body, ctype = None, None
    r = urllib.request.Request(url, data=body, method=method or ("POST" if body else "GET"))
    if ctype:
        r.add_header("Content-Type", ctype)
    try:
        resp = op.open(r, timeout=45)
        return resp.status, resp.read().decode("utf-8", "replace"), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), {k.lower(): v for k, v in e.headers.items()}


def hop(op, url, limit=8):
    """Follow a redirect chain by hand and return the last body reached."""
    for _ in range(limit):
        st, body, h = req(op, url)
        if st in (301, 302, 303, 307, 308) and h.get("location"):
            url = urllib.parse.urljoin(url, h["location"])
            continue
        return st, body, url
    return st, body, url


def keycloak_login(op, page, url, user, pw):
    m = re.search(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', page)
    action = urllib.parse.urljoin(url, m.group(1).replace("&amp;", "&"))
    return req(op, action, urllib.parse.urlencode({"username": user, "password": pw, "credentialId": ""}))


def sign_in_oidc(user, pw):
    jar = http.cookiejar.CookieJar()
    nf = opener(jar, follow=False)
    _, page, url = hop(nf, f"{APP}/api/auth/oidc/login")
    _, _, h = keycloak_login(nf, page, url, user, pw)
    if h.get("location"):
        hop(nf, h["location"])


def sign_in_saml(user, pw):
    jar = http.cookiejar.CookieJar()
    nf = opener(jar, follow=False)
    _, page, url = hop(nf, f"{APP}/api/auth/saml/login")
    _, page2, _ = keycloak_login(nf, page, url, user, pw)
    resp = re.search(r'name="SAMLResponse" value="([^"]+)"', page2 or "")
    if resp:
        req(nf, f"{APP}/api/auth/saml/acs",
            urllib.parse.urlencode({"SAMLResponse": htmlmod.unescape(resp.group(1))}))


def main():
    admin = opener(http.cookiejar.CookieJar())
    req(admin, f"{APP}/api/auth/login", {"email": "admin@local", "password": "bench-admin-pw"})
    req(admin, f"{APP}/api/admin/auth-config", {
        "oidc_enabled": True,
        "oidc_issuer_url": f"{IDP}/realms/tribe",
        "oidc_client_id": "teamfollowup",
        "oidc_client_secret": "teamfollowup-oidc-secret",
        "oidc_groups_claim": "groups",
        "saml_enabled": True,
        "saml_idp_metadata_url": f"{IDP}/realms/tribe/protocol/saml/descriptor",
        "saml_groups_attr": "groups",
        "require_approval": True,          # so both arrivals land in the queue
        "group_role_mappings": [{"group": "tribe-leads", "role": "tribe_leader"}],
    }, method="PUT")

    print("  Alice se connecte via OIDC...", flush=True)
    sign_in_oidc("alice", "alice-pw")
    print("  Bob se connecte via SAML...", flush=True)
    sign_in_saml("bob", "bob-pw")

    st, body, _ = req(admin, f"{APP}/api/access-requests")
    pending = {r["email"]: r["id"] for r in json.loads(body)["requests"]}
    print(f"  file d'attente : {list(pending)}", flush=True)

    if "alice@exemple.com" in pending:
        st, b, _ = req(admin, f"{APP}/api/access-requests/{pending['alice@exemple.com']}/approve",
                       {"role": "tribe_leader"})
        print(f"  validation d'Alice : HTTP {st}", flush=True)
    if "bob@exemple.com" in pending:
        st, b, _ = req(admin, f"{APP}/api/access-requests/{pending['bob@exemple.com']}/deny", {})
        print(f"  refus de Bob       : HTTP {st}", flush=True)

    st, body, _ = req(admin, f"{APP}/api/access-requests/history")
    print("\n  --- historique tel que l'ecran l'affichera ---", flush=True)
    for e in json.loads(body)["entries"]:
        who = f" par {e['actor']}" if e.get("actor") else ""
        extra = f" ({e['role']})" if e.get("role") else ""
        print(f"    {e['action']:24} {e['email']}{extra}{who}", flush=True)


if __name__ == "__main__":
    main()
