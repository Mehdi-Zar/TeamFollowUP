"""Find a person in the corporate directory: Entra ID, LDAP / AD, Google Workspace.

``search(cfg, q)`` asks every source switched on in Administration (directoryconfig)
in parallel, with short timeouts, and merges their answers, deduplicated by
email. A source that fails does not hide the others: its error is reported next
to the results, so a screen can say "LDAP did not answer" and still show what
Entra found.

Every call out verifies the server certificate against the application's trust
store (trust.context / trust.ca_file), the one the admin fills in Administration.
Nothing here can turn verification off.

A person is returned as a plain dict:
``{name, first_name, last_name, email, title, department, source}``.
Entries without an email are dropped: the email is what links a person to an
account and to a team member.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import urlsplit

from . import trust
from .netguard import BlockedURL, check_outbound_host, guarded_client

log = logging.getLogger("trt.directory")

TIMEOUT = 6.0          # per HTTP / LDAP call
OVERALL_TIMEOUT = 8.0  # the whole search, all sources together
MAX_RESULTS = 20

# Tests swap these for an httpx.MockTransport / an ldap3 MOCK_SYNC connection.
_transport = None
_ldap_connection_factory = None


class DirectoryError(Exception):
    """A source could not answer; the message is shown to the administrator."""


def _client():
    kw = {"timeout": TIMEOUT, "verify": trust.context()}
    if _transport is not None:
        kw["transport"] = _transport
    return guarded_client(**kw)


def _clean(q: str) -> str:
    """The typed text, trimmed, without the quotes and backslashes the query
    languages below would read as syntax."""
    return " ".join((q or "").replace('"', " ").replace("\\", " ").replace("'", " ").split())[:64]


def _person(source: str, *, name=None, first=None, last=None, email=None, title=None, dept=None) -> dict | None:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return None
    name = (name or " ".join(x for x in (first, last) if x) or email.split("@")[0]).strip()
    return {"name": name, "first_name": (first or "").strip() or None, "last_name": (last or "").strip() or None,
            "email": email, "title": (title or "").strip() or None, "department": (dept or "").strip() or None,
            "source": source}


def _http_error(resp, what: str) -> DirectoryError:
    msg = None
    try:
        body = resp.json()
        err = body.get("error")
        msg = err.get("message") if isinstance(err, dict) else (body.get("error_description") or err)
    except Exception:
        pass
    return DirectoryError(f"{what} : HTTP {resp.status_code}" + (f" ({str(msg)[:200]})" if msg else ""))


# ---------- Microsoft Entra ID (Microsoft Graph) ----------
_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()


def _cached(key: str):
    with _token_lock:
        hit = _token_cache.get(key)
        return hit[0] if hit and hit[1] > time.time() + 60 else None


def _remember(key: str, token: str, ttl: int) -> None:
    with _token_lock:
        _token_cache[key] = (token, time.time() + max(60, int(ttl or 3600)))


def _entra_token(cfg: dict, client) -> str:
    tenant = (cfg.get("entra_tenant_id") or "").strip()
    cid = (cfg.get("entra_client_id") or "").strip()
    secret = cfg.get("entra_client_secret") or ""
    if not (tenant and cid and secret):
        raise DirectoryError("Entra ID : tenant, client id et secret client sont requis")
    graph = (cfg.get("entra_graph_host") or "graph.microsoft.com").strip()
    key = f"entra:{tenant}:{cid}:{hash(secret)}"
    tok = _cached(key)
    if tok:
        return tok
    host = (cfg.get("entra_login_host") or "login.microsoftonline.com").strip()
    r = client.post(f"https://{host}/{tenant}/oauth2/v2.0/token",
                    data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret,
                          "scope": f"https://{graph}/.default"})
    if r.status_code != 200:
        raise _http_error(r, "Entra ID (jeton)")
    body = r.json()
    _remember(key, body["access_token"], body.get("expires_in", 3600))
    return body["access_token"]


def search_entra(cfg: dict, q: str, limit: int = MAX_RESULTS) -> list[dict]:
    term = _clean(q)
    with _client() as client:
        token = _entra_token(cfg, client)
        graph = (cfg.get("entra_graph_host") or "graph.microsoft.com").strip()
        search = " OR ".join(f'"{f}:{term}"' for f in ("displayName", "mail", "userPrincipalName"))
        r = client.get(f"https://{graph}/v1.0/users",
                       params={"$search": search, "$filter": "accountEnabled eq true",
                               "$select": "displayName,givenName,surname,mail,userPrincipalName,jobTitle,department",
                               "$top": str(limit), "$count": "true"},
                       headers={"Authorization": f"Bearer {token}", "ConsistencyLevel": "eventual"})
        if r.status_code != 200:
            raise _http_error(r, "Entra ID")
        out = []
        for u in r.json().get("value") or []:
            upn = u.get("userPrincipalName") or ""
            email = u.get("mail") or (upn if "@" in upn and "#EXT#" not in upn else None)
            p = _person("entra", name=u.get("displayName"), first=u.get("givenName"), last=u.get("surname"),
                        email=email, title=u.get("jobTitle"), dept=u.get("department"))
            if p:
                out.append(p)
        return out


# ---------- Google Workspace (Admin SDK Directory API) ----------
_GOOGLE_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"


def _google_token(cfg: dict, client) -> str:
    raw = cfg.get("google_service_account_json") or ""
    subject = (cfg.get("google_admin_subject") or "").strip()
    try:
        info = json.loads(raw) if isinstance(raw, str) else dict(raw)
        email, pkey = info["client_email"], info["private_key"]
    except Exception:
        raise DirectoryError("Google Workspace : clé du compte de service (JSON) absente ou invalide")
    if not subject:
        raise DirectoryError("Google Workspace : l'administrateur à emprunter est requis")
    key = f"google:{email}:{subject}"
    tok = _cached(key)
    if tok:
        return tok
    import jwt
    token_uri = info.get("token_uri") or "https://oauth2.googleapis.com/token"
    now = int(time.time())
    assertion = jwt.encode({"iss": email, "sub": subject, "scope": _GOOGLE_SCOPE, "aud": token_uri,
                            "iat": now, "exp": now + 3600}, pkey, algorithm="RS256")
    r = client.post(token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                     "assertion": assertion})
    if r.status_code != 200:
        raise _http_error(r, "Google Workspace (jeton)")
    body = r.json()
    _remember(key, body["access_token"], body.get("expires_in", 3600))
    return body["access_token"]


def search_google(cfg: dict, q: str, limit: int = MAX_RESULTS) -> list[dict]:
    term = _clean(q)
    with _client() as client:
        token = _google_token(cfg, client)
        # A bare term matches name and email fields; quoted, it may hold spaces.
        query = f"'{term}'" if " " in term else term
        r = client.get("https://admin.googleapis.com/admin/directory/v1/users",
                       params={"customer": (cfg.get("google_customer") or "my_customer").strip(),
                               "query": query, "maxResults": str(limit), "viewType": "domain_public"},
                       headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            raise _http_error(r, "Google Workspace")
        out = []
        for u in r.json().get("users") or []:
            if u.get("suspended") or u.get("archived"):
                continue
            n = u.get("name") or {}
            org = next(iter(u.get("organizations") or []), {}) or {}
            p = _person("google", name=n.get("fullName"), first=n.get("givenName"), last=n.get("familyName"),
                        email=u.get("primaryEmail"), title=org.get("title"), dept=org.get("department"))
            if p:
                out.append(p)
        return out


# ---------- LDAP / Active Directory ----------
def _ldap_connection(cfg: dict):
    """A bound ldap3 connection, certificate verified against the trust store."""
    if _ldap_connection_factory is not None:
        return _ldap_connection_factory(cfg)
    import ssl

    from ldap3 import Connection, Server, Tls

    url = (cfg.get("ldap_url") or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("ldap", "ldaps") or not parts.hostname:
        raise DirectoryError("LDAP : l'URL doit être ldap://hôte[:port] ou ldaps://hôte[:port]")
    use_ssl = parts.scheme == "ldaps"
    port = parts.port or (636 if use_ssl else 389)
    try:
        check_outbound_host(parts.hostname, port)
    except BlockedURL as exc:
        raise DirectoryError(f"LDAP : {exc}")
    tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=trust.ca_file())
    server = Server(parts.hostname, port=port, use_ssl=use_ssl, tls=tls, connect_timeout=TIMEOUT, get_info=None)
    conn = Connection(server, user=cfg.get("ldap_bind_dn") or None, password=cfg.get("ldap_bind_password") or None,
                      receive_timeout=TIMEOUT, raise_exceptions=False, auto_bind=False, read_only=True)
    if not conn.open():
        raise DirectoryError("LDAP : serveur injoignable")
    if cfg.get("ldap_start_tls") and not use_ssl and not conn.start_tls():
        raise DirectoryError("LDAP : StartTLS refusé")
    if not use_ssl and not cfg.get("ldap_start_tls") and cfg.get("ldap_bind_password"):
        # A password is never sent in clear.
        raise DirectoryError("LDAP : utilisez ldaps:// ou StartTLS pour envoyer le mot de passe")
    return conn


def _attr(entry: dict, name: str):
    if not name:
        return None
    v = entry.get(name)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    return str(v) if v not in (None, "") else None


def search_ldap(cfg: dict, q: str, limit: int = MAX_RESULTS) -> list[dict]:
    from ldap3 import SUBTREE
    from ldap3.utils.conv import escape_filter_chars

    term = escape_filter_chars(_clean(q))
    base = (cfg.get("ldap_base_dn") or "").strip()
    if not base:
        raise DirectoryError("LDAP : la base DN est requise")
    attrs = [a.strip() for a in (cfg.get("ldap_search_attrs") or "").split(",") if a.strip()] or ["cn", "mail"]
    any_of = "".join(f"({a}=*{term}*)" for a in attrs)
    user_filter = (cfg.get("ldap_user_filter") or "(objectClass=person)").strip()
    if not user_filter.startswith("("):
        user_filter = f"({user_filter})"
    flt = f"(&{user_filter}(|{any_of}))"
    keys = {k: cfg.get(f"ldap_attr_{k}") for k in ("name", "first_name", "last_name", "email", "title", "department")}
    wanted = sorted({v for v in keys.values() if v})
    conn = _ldap_connection(cfg)
    try:
        if not conn.bound and not conn.bind():
            raise DirectoryError(f"LDAP : authentification refusée ({(conn.result or {}).get('description', 'invalidCredentials')})")
        conn.search(base, flt, SUBTREE, attributes=wanted, size_limit=limit, time_limit=int(TIMEOUT))
        out = []
        for e in conn.entries:
            d = e.entry_attributes_as_dict
            p = _person("ldap", name=_attr(d, keys["name"]), first=_attr(d, keys["first_name"]),
                        last=_attr(d, keys["last_name"]), email=_attr(d, keys["email"]),
                        title=_attr(d, keys["title"]), dept=_attr(d, keys["department"]))
            if p:
                out.append(p)
        return out
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


_SOURCES = {"entra": search_entra, "ldap": search_ldap, "google": search_google}


def search_one(source: str, cfg: dict, q: str, limit: int = MAX_RESULTS) -> list[dict]:
    """One source, errors raised (the admin's test button wants them)."""
    try:
        return _SOURCES[source](cfg, q, limit)
    except DirectoryError:
        raise
    except Exception as exc:  # network, TLS, malformed answer
        raise DirectoryError(f"{source} : {type(exc).__name__} : {str(exc)[:200]}")


def search(cfg: dict, q: str, sources: list[str], limit: int = MAX_RESULTS) -> dict:
    """Every source in parallel; ``{"results": [...], "sources": {name: {ok, count|error}}}``.

    Merged by email: the first source to name a person wins, the others only fill
    the fields it left empty (an LDAP title completes an Entra entry)."""
    status: dict[str, dict] = {}
    found: dict[str, list[dict]] = {}
    if not sources:
        return {"results": [], "sources": status}
    pool = ThreadPoolExecutor(max_workers=len(sources))
    futures = {pool.submit(search_one, s, cfg, q, limit): s for s in sources}
    done, pending = wait(futures, timeout=OVERALL_TIMEOUT)
    for f in done:
        s = futures[f]
        try:
            found[s] = f.result()
            status[s] = {"ok": True, "count": len(found[s])}
        except Exception as exc:
            log.warning("directory search failed on %s: %s", s, exc)
            status[s] = {"ok": False, "error": str(exc)}
    for f in pending:
        status[futures[f]] = {"ok": False, "error": "pas de réponse dans le délai"}
    pool.shutdown(wait=False, cancel_futures=True)
    merged: dict[str, dict] = {}
    for s in sources:
        for p in found.get(s, []):
            cur = merged.get(p["email"])
            if cur is None:
                merged[p["email"]] = dict(p)
            else:
                for k, v in p.items():
                    if v and not cur.get(k):
                        cur[k] = v
    results = sorted(merged.values(), key=lambda p: (p["name"] or "").lower())[:limit]
    return {"results": results, "sources": status}
