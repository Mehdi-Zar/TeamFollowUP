"""Kubernetes test bench: drives the two SSO flows against the deployed app.

Runs from the host against the cluster's gateway. Two deliberate choices:

  * TLS is **verified** against the bench's internal CA, never disabled. A flow
    that only works with certificate checking turned off proves nothing.
  * DNS is redirected in-process (same idea as `curl --resolve`) rather than by
    editing the machine's hosts file, so the run leaves no trace on the system.

Each flow is played as a browser would: follow the redirects, fill in Keycloak's
login form, come back to the application, and check who we are afterwards.
"""
import http.cookiejar
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CA = HERE / "pki" / "ca.crt"
APP = "https://app.localtest.me"
IDP = "https://idp.localtest.me"
GATEWAY_IP = "127.0.0.1"          # where the port-forward listens
BENCH_HOSTS = {"app.localtest.me", "idp.localtest.me"}

results = []


def record(step, ok, detail=""):
    results.append({"step": step, "ok": bool(ok), "detail": str(detail)})
    print(f"  [{'OK ' if ok else 'FAIL'}] {step}" + (f"  ->  {detail}" if detail else ""), flush=True)
    return ok


# --- DNS redirection, the in-process equivalent of `curl --resolve` -----------
_real_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, port, *args, **kwargs):
    if host in BENCH_HOSTS:
        return _real_getaddrinfo(GATEWAY_IP, port, *args, **kwargs)
    return _real_getaddrinfo(host, port, *args, **kwargs)


socket.getaddrinfo = _patched_getaddrinfo

# TLS: trust the bench CA and nothing else beyond the defaults. Hostname
# verification stays ON, so the certificate really has to carry the right SANs.
CTX = ssl.create_default_context(cafile=str(CA))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Stop on 3xx so each hop can be inspected instead of silently followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def opener(jar, follow=True):
    handlers = [urllib.request.HTTPSHandler(context=CTX), urllib.request.HTTPCookieProcessor(jar)]
    if not follow:
        handlers.append(NoRedirect())
    return urllib.request.build_opener(*handlers)


def request(op, url, data=None, headers=None, method=None):
    """Return (status, final_url, body, headers); 3xx and 4xx come back as values."""
    if isinstance(data, (dict, list)):
        body, ctype = json.dumps(data).encode(), "application/json"
    elif isinstance(data, str):
        body, ctype = data.encode(), "application/x-www-form-urlencoded"
    else:
        body, ctype = data, None
    req = urllib.request.Request(url, data=body, method=method or ("POST" if body else "GET"))
    if ctype:
        req.add_header("Content-Type", ctype)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    # Header names are lowercased: uvicorn and Envoy emit them in lower case and a
    # case-sensitive lookup for "Location" would silently miss every redirect.
    try:
        r = op.open(req, timeout=45)
        return r.status, r.url, r.read().decode("utf-8", "replace"), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.url, e.read().decode("utf-8", "replace"), {k.lower(): v for k, v in e.headers.items()}


def admin_session():
    jar = http.cookiejar.CookieJar()
    op = opener(jar)
    st, _, body, _ = request(op, f"{APP}/api/auth/login",
                             {"email": "admin@local", "password": "bench-admin-pw"})
    if st != 200:
        raise SystemExit(f"break-glass login failed: {st} {body[:200]}")
    return op


def keycloak_login(op, html, page_url):
    """Submit Keycloak's username/password form and return the resulting hop."""
    m = re.search(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', html) or \
        re.search(r'<form[^>]+action="([^"]+)"[^>]*method="post"', html, re.I)
    if not m:
        return (0, page_url, "", {}), "no login form in the Keycloak page"
    action = m.group(1).replace("&amp;", "&")
    action = urllib.parse.urljoin(page_url, action)
    payload = urllib.parse.urlencode({"username": "alice", "password": "alice-pw", "credentialId": ""})
    return request(op, action, payload), None


def follow(op_nofollow, op_follow, url, max_hops=8):
    """Walk a redirect chain by hand, returning every hop for the report."""
    hops, current = [], url
    for _ in range(max_hops):
        st, final, body, hdrs = request(op_nofollow, current)
        hops.append((st, current))
        if st in (301, 302, 303, 307, 308) and hdrs.get("location"):
            current = urllib.parse.urljoin(current, hdrs["location"])
            continue
        return hops, st, current, body
    return hops, st, current, body


def main():
    print("\n=== 1. Transport: internal CA, verified ===", flush=True)
    jar = http.cookiejar.CookieJar()
    op = opener(jar)
    st, _, body, _ = request(op, f"{APP}/api/health")
    record("app reachable through the gateway over verified TLS", st == 200, f"HTTP {st} {body[:40]}")
    st, _, body, _ = request(op, f"{IDP}/realms/tribe/.well-known/openid-configuration")
    issuer = json.loads(body)["issuer"] if st == 200 else "?"
    record("Keycloak reachable on the same certificate", st == 200 and issuer == f"{IDP}/realms/tribe", issuer)

    print("\n=== 2. Deployment: derived SSO URLs ===", flush=True)
    admin = admin_session()
    st, _, body, _ = request(admin, f"{APP}/api/admin/auth-config")
    cfg = json.loads(body)
    record("public base URL taken from PUBLIC_BASE_URL", cfg["base_url_source"] == "configured", cfg["base_url_effective"])
    record("OIDC redirect URI derived", cfg["oidc_redirect_uri"] == f"{APP}/api/auth/oidc/callback", cfg["oidc_redirect_uri"])
    record("SAML entity ID derived", cfg["saml_sp_entity_id"] == f"{APP}/api/auth/saml/metadata", cfg["saml_sp_entity_id"])
    record("SAML ACS URL derived", cfg["saml_acs_url"] == f"{APP}/api/auth/saml/acs", cfg["saml_acs_url"])

    print("\n=== 3. OIDC login, end to end ===", flush=True)
    request(admin, f"{APP}/api/admin/auth-config", {
        "oidc_enabled": True,
        "oidc_issuer_url": f"{IDP}/realms/tribe",
        "oidc_client_id": "teamfollowup",
        "oidc_client_secret": "teamfollowup-oidc-secret",
        "oidc_scopes": "openid email profile",
        "oidc_groups_claim": "groups",
        "require_approval": False,
        "group_role_mappings": [{"group": "tribe-leads", "role": "tribe_leader"}],
    }, method="PUT")

    ujar = http.cookiejar.CookieJar()
    u_follow, u_nofollow = opener(ujar), opener(ujar, follow=False)
    hops, st, url, html = follow(u_nofollow, u_follow, f"{APP}/api/auth/oidc/login")
    record("app redirects the user to Keycloak", any("/protocol/openid-connect/auth" in u for _, u in hops),
           " -> ".join(u.split("?")[0].replace(IDP, "IdP").replace(APP, "APP") for _, u in hops))
    (st2, url2, html2, hdrs2), err = keycloak_login(u_nofollow, html, url)
    record("Keycloak accepts the credentials", st2 in (302, 200) and not err, err or f"HTTP {st2}")
    loc = hdrs2.get("location", "")
    record("Keycloak calls back the DERIVED redirect URI", loc.startswith(f"{APP}/api/auth/oidc/callback"),
           loc.split("?")[0] or "(no Location)")
    hops2, st3, url3, _ = follow(u_nofollow, u_follow, loc) if loc else ([], 0, "", "")
    st4, _, body4, _ = request(u_follow, f"{APP}/api/auth/me")
    me = json.loads(body4) if st4 == 200 else {}
    record("OIDC session established", st4 == 200, f"{me.get('email')} / {me.get('status')}")
    record("IdP group mapped to an application role", me.get("role") == "tribe_leader", me.get("role"))
    oidc_me = me

    print("\n=== 4. SAML 2.0 login, end to end ===", flush=True)
    request(admin, f"{APP}/api/admin/auth-config", {
        "oidc_enabled": False,
        "saml_enabled": True,
        "saml_idp_metadata_url": f"{IDP}/realms/tribe/protocol/saml/descriptor",
        "saml_groups_attr": "groups",
        "require_approval": False,
        "group_role_mappings": [{"group": "tribe-leads", "role": "tribe_leader"}],
    }, method="PUT")

    st, _, md, _ = request(admin, f"{APP}/api/auth/saml/metadata")
    ent = re.search(r'entityID="([^"]+)"', md)
    acs = re.search(r'Location="([^"]+)"', md)
    record("SP metadata published with the derived URLs",
           st == 200 and ent and ent.group(1) == f"{APP}/api/auth/saml/metadata",
           f"entityID={ent.group(1) if ent else '?'} acs={acs.group(1) if acs else '?'}")

    sjar = http.cookiejar.CookieJar()          # fresh jar: force a real login
    s_follow, s_nofollow = opener(sjar), opener(sjar, follow=False)
    hops, st, url, html = follow(s_nofollow, s_follow, f"{APP}/api/auth/saml/login")
    record("app issues a SAML AuthnRequest to Keycloak", any("/protocol/saml" in u for _, u in hops),
           " -> ".join(u.split("?")[0].replace(IDP, "IdP").replace(APP, "APP") for _, u in hops))
    (st2, url2, html2, hdrs2), err = keycloak_login(s_nofollow, html, url)
    record("Keycloak authenticates the SAML user", st2 == 200 and not err, err or f"HTTP {st2}")

    # Keycloak answers with a self-posting form carrying the signed assertion.
    action = re.search(r'<form[^>]+action="([^"]+)"', html2 or "")
    saml_resp = re.search(r'name="SAMLResponse" value="([^"]+)"', html2 or "")
    rstate = re.search(r'name="RelayState" value="([^"]*)"', html2 or "")
    record("Keycloak posts the assertion to the ACS URL",
           bool(action) and action.group(1).replace("&amp;", "&") == f"{APP}/api/auth/saml/acs",
           action.group(1) if action else "(no form)")
    if saml_resp:
        import html as htmlmod
        payload = {"SAMLResponse": htmlmod.unescape(saml_resp.group(1))}
        if rstate:
            payload["RelayState"] = htmlmod.unescape(rstate.group(1))
        st3, _, body3, hdrs3 = request(s_nofollow, f"{APP}/api/auth/saml/acs", urllib.parse.urlencode(payload))
        record("app accepts the signed assertion (strict mode)", st3 in (302, 303),
               f"HTTP {st3}" + ("" if st3 in (302, 303) else f" {body3[:160]}"))
    st4, _, body4, _ = request(s_follow, f"{APP}/api/auth/me")
    me = json.loads(body4) if st4 == 200 else {}
    record("SAML session established", st4 == 200, f"{me.get('email')} / {me.get('status')}")
    record("same identity as the OIDC flow", me.get("email") == oidc_me.get("email"),
           f"{me.get('email')} (role {me.get('role')})")

    print("\n=== 5. Reset ===", flush=True)
    request(admin, f"{APP}/api/admin/auth-config",
            {"oidc_enabled": False, "saml_enabled": False}, method="PUT")

    passed = sum(1 for r in results if r["ok"])
    print(f"\n{passed}/{len(results)} verifications passed", flush=True)
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
