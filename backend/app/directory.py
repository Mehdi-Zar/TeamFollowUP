"""Find a person in the corporate directory: Entra ID, Active Directory, LDAP, Google Workspace.

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

``diagnose(source, cfg, q)`` is what the administrator's test button runs: the same
calls, one step at a time (configuration, connection, authentication, query,
attributes), each with its outcome, its duration and a sentence saying what to
change when it fails. A bare "HTTP 403" tells nobody which of four settings is wrong.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import urlsplit

from . import trust
from .directoryconfig import as_ldap
from .netguard import BlockedURL, check_outbound_host, guarded_client

log = logging.getLogger("trt.directory")

TIMEOUT = 6.0          # per HTTP / LDAP call
OVERALL_TIMEOUT = 8.0  # the whole search, all sources together
MAX_RESULTS = 20

# Tests swap these for an httpx.MockTransport / an ldap3 MOCK_SYNC connection.
_transport = None
_ldap_connection_factory = None


LABELS = {"entra": "Entra ID", "ad": "Active Directory", "ldap": "LDAP", "google": "Google Workspace"}


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


def _entra_check(cfg: dict) -> tuple[str, str, str]:
    tenant = (cfg.get("entra_tenant_id") or "").strip()
    cid = (cfg.get("entra_client_id") or "").strip()
    secret = cfg.get("entra_client_secret") or ""
    missing = [n for n, v in (("ID du tenant", tenant), ("ID client", cid), ("secret client", secret)) if not v]
    if missing:
        raise DirectoryError("Entra ID : à renseigner : " + ", ".join(missing))
    return tenant, cid, secret


def _entra_token(cfg: dict, client, use_cache: bool = True) -> str:
    tenant, cid, secret = _entra_check(cfg)
    graph = (cfg.get("entra_graph_host") or "graph.microsoft.com").strip()
    key = f"entra:{tenant}:{cid}:{hash(secret)}"
    tok = _cached(key) if use_cache else None
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


def _entra_query(cfg: dict, client, token: str, q: str, limit: int) -> tuple[list[dict], int]:
    """People found, and how many entries came back (with or without an email)."""
    term = _clean(q)
    graph = (cfg.get("entra_graph_host") or "graph.microsoft.com").strip()
    search = " OR ".join(f'"{f}:{term}"' for f in ("displayName", "mail", "userPrincipalName"))
    r = client.get(f"https://{graph}/v1.0/users",
                   params={"$search": search, "$filter": "accountEnabled eq true",
                           "$select": "displayName,givenName,surname,mail,userPrincipalName,jobTitle,department",
                           "$top": str(limit), "$count": "true"},
                   headers={"Authorization": f"Bearer {token}", "ConsistencyLevel": "eventual"})
    if r.status_code != 200:
        raise _http_error(r, "Entra ID")
    rows = r.json().get("value") or []
    out = []
    for u in rows:
        upn = u.get("userPrincipalName") or ""
        email = u.get("mail") or (upn if "@" in upn and "#EXT#" not in upn else None)
        p = _person("entra", name=u.get("displayName"), first=u.get("givenName"), last=u.get("surname"),
                    email=email, title=u.get("jobTitle"), dept=u.get("department"))
        if p:
            out.append(p)
    return out, len(rows)


def search_entra(cfg: dict, q: str, limit: int = MAX_RESULTS) -> list[dict]:
    with _client() as client:
        return _entra_query(cfg, client, _entra_token(cfg, client), q, limit)[0]


# ---------- Google Workspace (Admin SDK Directory API) ----------
_GOOGLE_SCOPE = "https://www.googleapis.com/auth/admin.directory.user.readonly"


def _google_key(cfg: dict) -> dict:
    raw = cfg.get("google_service_account_json") or ""
    try:
        info = json.loads(raw) if isinstance(raw, str) else dict(raw)
        info["client_email"], info["private_key"]
    except Exception:
        raise DirectoryError("Google Workspace : clé du compte de service (JSON) absente ou invalide. "
                             "Collez le fichier JSON entier téléchargé depuis la console Google Cloud.")
    return info


def _google_subject(cfg: dict) -> str:
    subject = (cfg.get("google_admin_subject") or "").strip()
    if not subject:
        raise DirectoryError("Google Workspace : l'administrateur à emprunter est requis")
    return subject


def _google_token(cfg: dict, client, use_cache: bool = True, scope: str = _GOOGLE_SCOPE) -> str:
    info = _google_key(cfg)
    email, pkey = info["client_email"], info["private_key"]
    subject = _google_subject(cfg)
    key = f"google:{email}:{subject}:{scope}"
    tok = _cached(key) if use_cache else None
    if tok:
        return tok
    import jwt
    token_uri = info.get("token_uri") or "https://oauth2.googleapis.com/token"
    now = int(time.time())
    assertion = jwt.encode({"iss": email, "sub": subject, "scope": scope, "aud": token_uri,
                            "iat": now, "exp": now + 3600}, pkey, algorithm="RS256")
    r = client.post(token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                     "assertion": assertion})
    if r.status_code != 200:
        raise _http_error(r, "Google Workspace (jeton)")
    body = r.json()
    _remember(key, body["access_token"], body.get("expires_in", 3600))
    return body["access_token"]


def _google_query(cfg: dict, client, token: str, q: str, limit: int) -> tuple[list[dict], int]:
    term = _clean(q)
    # A bare term matches name and email fields; quoted, it may hold spaces.
    query = f"'{term}'" if " " in term else term
    r = client.get("https://admin.googleapis.com/admin/directory/v1/users",
                   params={"customer": (cfg.get("google_customer") or "my_customer").strip(),
                           "query": query, "maxResults": str(limit), "viewType": "domain_public"},
                   headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise _http_error(r, "Google Workspace")
    rows = r.json().get("users") or []
    out = []
    for u in rows:
        if u.get("suspended") or u.get("archived"):
            continue
        n = u.get("name") or {}
        org = next(iter(u.get("organizations") or []), {}) or {}
        p = _person("google", name=n.get("fullName"), first=n.get("givenName"), last=n.get("familyName"),
                    email=u.get("primaryEmail"), title=org.get("title"), dept=org.get("department"))
        if p:
            out.append(p)
    return out, len(rows)


def search_google(cfg: dict, q: str, limit: int = MAX_RESULTS) -> list[dict]:
    with _client() as client:
        return _google_query(cfg, client, _google_token(cfg, client), q, limit)[0]


# ---------- LDAP and Active Directory ----------
# Active Directory answers a refused bind with a sub-code buried in the message
# ("... AcceptSecurityContext error, data 52e, v4563"). It is the only place that
# says whether the password is wrong, the account locked or the password expired.
_AD_BIND_CODES = {
    "525": "compte introuvable : vérifiez le bind DN (forme svc@domaine.local ou CN=...,OU=...,DC=...)",
    "52e": "mot de passe ou identifiant incorrect",
    "530": "connexion interdite à cette heure pour ce compte",
    "531": "connexion interdite depuis ce poste pour ce compte",
    "532": "mot de passe expiré",
    "533": "compte désactivé",
    "568": "trop de groupes dans le jeton de sécurité du compte",
    "701": "compte expiré",
    "773": "le mot de passe doit être changé avant la première connexion",
    "775": "compte verrouillé après trop d'essais",
}


def _url_parts(cfg: dict, label: str):
    url = (cfg.get("ldap_url") or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("ldap", "ldaps") or not parts.hostname:
        raise DirectoryError(f"{label} : l'URL doit être ldap://hôte[:port] ou ldaps://hôte[:port]")
    use_ssl = parts.scheme == "ldaps"
    return parts.hostname, parts.port or (636 if use_ssl else 389), use_ssl


def _ldap_connection(cfg: dict, label: str = "LDAP"):
    """An opened (not yet bound) ldap3 connection, certificate verified against the trust store."""
    if _ldap_connection_factory is not None:
        return _ldap_connection_factory(cfg)
    import ssl

    from ldap3 import Connection, Server, Tls

    host, port, use_ssl = _url_parts(cfg, label)
    try:
        check_outbound_host(host, port)
    except BlockedURL as exc:
        raise DirectoryError(f"{label} : {exc}")
    tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=trust.ca_file())
    server = Server(host, port=port, use_ssl=use_ssl, tls=tls, connect_timeout=TIMEOUT, get_info=None)
    conn = Connection(server, user=cfg.get("ldap_bind_dn") or None, password=cfg.get("ldap_bind_password") or None,
                      receive_timeout=TIMEOUT, raise_exceptions=False, auto_bind=False, read_only=True)
    try:
        opened = conn.open()
    except Exception as exc:  # TLS handshake and socket errors surface here
        raise DirectoryError(f"{label} : connexion à {host}:{port} impossible ({type(exc).__name__} : {str(exc)[:200]})")
    if opened is False:
        raise DirectoryError(f"{label} : serveur {host}:{port} injoignable")
    if cfg.get("ldap_start_tls") and not use_ssl and not conn.start_tls():
        raise DirectoryError(f"{label} : StartTLS refusé par le serveur")
    if not use_ssl and not cfg.get("ldap_start_tls") and cfg.get("ldap_bind_password"):
        # A password is never sent in clear.
        raise DirectoryError(f"{label} : utilisez ldaps:// ou StartTLS pour envoyer le mot de passe")
    return conn


def _bind_error(conn, label: str) -> DirectoryError:
    res = conn.result or {}
    desc, msg = res.get("description") or "invalidCredentials", res.get("message") or ""
    sub = re.search(r"data ([0-9a-f]{3})", msg)
    why = _AD_BIND_CODES.get(sub.group(1)) if sub else None
    return DirectoryError(f"{label} : authentification refusée ({desc}" + (f", {why}" if why else "") + ")"
                          + (f". Réponse du serveur : {msg[:160]}" if msg and not why else ""))


def _attr(entry: dict, name: str):
    if not name:
        return None
    v = entry.get(name)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    return str(v) if v not in (None, "") else None


def _ldap_plan(cfg: dict, q: str, label: str):
    """Base, filter, attributes asked and the mapping, or the setting that is missing."""
    from ldap3.utils.conv import escape_filter_chars

    base = (cfg.get("ldap_base_dn") or "").strip()
    if not base:
        raise DirectoryError(f"{label} : la base de recherche (base DN) est requise, par exemple DC=entreprise,DC=local")
    term = escape_filter_chars(_clean(q))
    attrs = [a.strip() for a in (cfg.get("ldap_search_attrs") or "").split(",") if a.strip()] or ["cn", "mail"]
    any_of = "".join(f"({a}=*{term}*)" for a in attrs)
    user_filter = (cfg.get("ldap_user_filter") or "(objectClass=person)").strip()
    if not user_filter.startswith("("):
        user_filter = f"({user_filter})"
    keys = {k: cfg.get(f"ldap_attr_{k}") for k in ("name", "first_name", "last_name", "email", "title", "department")}
    return base, f"(&{user_filter}(|{any_of}))", keys, sorted({v for v in keys.values() if v})


def _ldap_people(conn, source: str, keys: dict) -> list[dict]:
    out = []
    for e in conn.entries:
        d = e.entry_attributes_as_dict
        p = _person(source, name=_attr(d, keys["name"]), first=_attr(d, keys["first_name"]),
                    last=_attr(d, keys["last_name"]), email=_attr(d, keys["email"]),
                    title=_attr(d, keys["title"]), dept=_attr(d, keys["department"]))
        if p:
            out.append(p)
    return out


def search_ldap(cfg: dict, q: str, limit: int = MAX_RESULTS, source: str = "ldap") -> list[dict]:
    from ldap3 import SUBTREE

    label = LABELS[source]
    base, flt, keys, wanted = _ldap_plan(cfg, q, label)
    conn = _ldap_connection(cfg, label)
    try:
        if not conn.bound and not conn.bind():
            raise _bind_error(conn, label)
        conn.search(base, flt, SUBTREE, attributes=wanted, size_limit=limit, time_limit=int(TIMEOUT))
        return _ldap_people(conn, source, keys)
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


def search_ad(cfg: dict, q: str, limit: int = MAX_RESULTS) -> list[dict]:
    return search_ldap(as_ldap(cfg, "ad"), q, limit, source="ad")


_SOURCES = {"entra": search_entra, "ad": search_ad, "ldap": search_ldap, "google": search_google}


def search_one(source: str, cfg: dict, q: str, limit: int = MAX_RESULTS) -> list[dict]:
    """One source, errors raised (the admin's test button wants them)."""
    try:
        return _SOURCES[source](cfg, q, limit)
    except DirectoryError:
        raise
    except Exception as exc:  # network, TLS, malformed answer
        raise DirectoryError(f"{LABELS.get(source, source)} : {type(exc).__name__} : {str(exc)[:200]}")


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


# ---------- Diagnostic (the administrator's test button) ----------
# Three kinds of test, the same steps before the query:
#   * user: the people search the screens run;
#   * group: a group search, which needs its own permission (Group.Read.All in
#     Entra, the group scope in Google) and its own filter (AD, LDAP);
#   * custom: the administrator's own query, read-only, against the configured
#     server only: an LDAP filter, a Graph path, an Admin SDK path. What comes
#     back is shown raw, which is what one wants when a mapping or a permission
#     does not behave.
MODES = ("user", "group", "custom")
CUSTOM_MAX = 50
RAW_MAX = 20000


class _Trace:
    """The steps of one test, in order. A step is ``{key, status, detail, ms}``:
    ``key`` names it for the screen (translated there), ``status`` is ok, warn,
    fail or skip, ``detail`` says what was seen and, on failure, what to change.
    ``out`` collects what the query returned, kept even when a later step fails."""

    def __init__(self):
        self.steps: list[dict] = []
        self.out: dict = {}

    @contextmanager
    def step(self, key: str):
        rec = {"key": key, "status": "ok", "detail": "", "ms": None}
        self.steps.append(rec)
        t0 = time.monotonic()
        try:
            yield rec
        except DirectoryError as exc:
            rec["status"], rec["detail"] = "fail", str(exc)
            raise
        except Exception as exc:  # network, TLS, malformed answer, invalid filter
            rec["status"], rec["detail"] = "fail", f"{type(exc).__name__} : {str(exc)[:300]}"
            raise DirectoryError(rec["detail"])
        finally:
            rec["ms"] = int((time.monotonic() - t0) * 1000)


def _jwt_claims(token: str) -> dict:
    """The claims of an access token, read without checking it: only to show the
    administrator which permissions the identity provider actually granted."""
    import jwt
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return {}


def _http_body(r) -> dict:
    """An HTTP answer as shown to the administrator: status and body, cut short."""
    try:
        text = json.dumps(r.json(), indent=2, ensure_ascii=False)
    except Exception:
        text = r.text
    return {"status": r.status_code, "text": text[:RAW_MAX] + ("\n..." if len(text) > RAW_MAX else "")}


def _safe_path(path: str, what: str, example: str) -> str:
    """A path on the configured host, never another host: a custom test is a
    read on the directory, not a way to make the server call anywhere."""
    p = (path or "").strip()
    if not p or "://" in p or ".." in p or p.startswith("//") or any(c in p for c in "\r\n\t "):
        raise DirectoryError(f"{what} : chemin invalide, par exemple {example}")
    return p


# The permissions that let an Entra application read users, or groups.
_ENTRA_NEEDS = {
    "user": ({"User.Read.All", "Directory.Read.All"}, "User.Read.All"),
    "group": ({"Group.Read.All", "GroupMember.Read.All", "Directory.Read.All"}, "Group.Read.All"),
}


def _diag_entra(cfg: dict, q: str, tr: _Trace, limit: int, mode: str, custom: dict):
    with tr.step("config") as st:
        tenant, cid, _ = _entra_check(cfg)
        graph = (cfg.get("entra_graph_host") or "graph.microsoft.com").strip()
        st["detail"] = f"tenant {tenant}, application {cid}, hôtes {cfg.get('entra_login_host')} et {graph}"
    with _client() as client:
        with tr.step("token") as st:
            token = _entra_token(cfg, client, use_cache=False)
            claims = _jwt_claims(token)
            roles = claims.get("roles") or []
            st["detail"] = "jeton obtenu" + (f", permissions : {', '.join(roles)}" if roles else "")
            if claims and mode in _ENTRA_NEEDS and not (_ENTRA_NEEDS[mode][0] & set(roles)):
                need = _ENTRA_NEEDS[mode][1]
                st["status"] = "warn"
                st["detail"] += (f". Le jeton ne porte pas {need} : ajoutez cette permission d'application "
                                 "(pas déléguée) et accordez le consentement administrateur, sinon Graph "
                                 "répondra 403.")
        with tr.step("query") as st:
            if mode == "user":
                people, rows = _entra_query(cfg, client, token, q, limit)
                tr.out["sample"] = people
                st["detail"] = f"recherche « {_clean(q)} » : {rows} compte(s) actif(s) renvoyé(s)"
                if rows > len(people):
                    st["status"] = "warn"
                    st["detail"] += f", dont {rows - len(people)} sans email (ignorés)"
            elif mode == "group":
                term = _clean(q)
                r = client.get(f"https://{graph}/v1.0/groups",
                               params={"$search": f'"displayName:{term}"', "$top": str(limit), "$count": "true",
                                       "$select": "id,displayName,mail,description,groupTypes,securityEnabled"},
                               headers={"Authorization": f"Bearer {token}", "ConsistencyLevel": "eventual"})
                if r.status_code != 200:
                    raise _http_error(r, "Entra ID (groupes)")
                groups = []
                for g in r.json().get("value") or []:
                    kind = ("Microsoft 365" if "Unified" in (g.get("groupTypes") or [])
                            else "sécurité" if g.get("securityEnabled") else "distribution")
                    groups.append({"name": g.get("displayName") or "", "email": g.get("mail"),
                                   "description": g.get("description"), "kind": kind, "id": g.get("id")})
                tr.out["groups"] = groups
                st["detail"] = f"groupes « {term} » : {len(groups)} trouvé(s)"
            else:
                path = _safe_path(custom.get("path"), "Entra ID", "/v1.0/groups?$top=5")
                if not re.match(r"^/(v1\.0|beta)/", path):
                    raise DirectoryError("Entra ID : le chemin commence par /v1.0/ ou /beta/, "
                                         "par exemple /v1.0/users?$top=5")
                r = client.get(f"https://{graph}{path}",
                               headers={"Authorization": f"Bearer {token}", "ConsistencyLevel": "eventual"})
                tr.out["body"] = _http_body(r)
                st["detail"] = f"GET https://{graph}{path} : HTTP {r.status_code}"
                if r.status_code >= 400:
                    raise _http_error(r, f"Entra ID (GET {path})")
    return None


_GOOGLE_GROUP_SCOPE = "https://www.googleapis.com/auth/admin.directory.group.readonly"


def _diag_google(cfg: dict, q: str, tr: _Trace, limit: int, mode: str, custom: dict):
    with tr.step("key") as st:
        info = _google_key(cfg)
        st["detail"] = f"compte de service {info['client_email']}" + (
            f", projet {info['project_id']}" if info.get("project_id") else "")
    with tr.step("subject") as st:
        st["detail"] = f"agit au nom de {_google_subject(cfg)}, client {cfg.get('google_customer') or 'my_customer'}"
    groups_api = mode == "group" or (mode == "custom" and custom.get("scope") == "group")
    scope = _GOOGLE_GROUP_SCOPE if groups_api else _GOOGLE_SCOPE
    customer = (cfg.get("google_customer") or "my_customer").strip()
    with _client() as client:
        with tr.step("token") as st:
            try:
                token = _google_token(cfg, client, use_cache=False, scope=scope)
            except DirectoryError as exc:
                raise DirectoryError(f"{exc}. Vérifiez la délégation au niveau du domaine (console "
                                     "d'administration Workspace > Sécurité > Contrôles des API) pour l'ID "
                                     f"client du compte de service et le scope {scope}.")
            st["detail"] = f"jeton obtenu pour le scope {scope}"
        with tr.step("query") as st:
            auth = {"Authorization": f"Bearer {token}"}
            if mode == "user":
                people, rows = _google_query(cfg, client, token, q, limit)
                tr.out["sample"] = people
                st["detail"] = f"recherche « {_clean(q)} » : {rows} compte(s) renvoyé(s)"
                if rows > len(people):
                    st["status"] = "warn"
                    st["detail"] += f", dont {rows - len(people)} suspendu(s), archivé(s) ou sans email (ignorés)"
            elif mode == "group":
                term = _clean(q)
                r = client.get("https://admin.googleapis.com/admin/directory/v1/groups",
                               params={"customer": customer, "query": f"name:{term}*", "maxResults": str(limit)},
                               headers=auth)
                if r.status_code != 200:
                    raise _http_error(r, "Google Workspace (groupes)")
                groups = [{"name": g.get("name") or "", "email": g.get("email"), "description": g.get("description"),
                           "members": int(g["directMembersCount"]) if str(g.get("directMembersCount", "")).isdigit() else None,
                           "id": g.get("id")} for g in r.json().get("groups") or []]
                tr.out["groups"] = groups
                st["detail"] = f"groupes « {term} » : {len(groups)} trouvé(s)"
            else:
                path = _safe_path(custom.get("path"), "Google Workspace", "users?customer=my_customer&maxResults=5")
                path = path.lstrip("/")
                url = f"https://admin.googleapis.com/admin/directory/v1/{path}"
                r = client.get(url, headers=auth)
                tr.out["body"] = _http_body(r)
                st["detail"] = f"GET {url} : HTTP {r.status_code}"
                if r.status_code >= 400:
                    raise _http_error(r, f"Google Workspace (GET {path})")
    return None


# Attributes never worth showing as a sample: binary, or noise for a mapping.
_RAW_SKIP = {"objectsid", "objectguid", "thumbnailphoto", "jpegphoto", "usercertificate", "msexchmailboxguid",
             "msexchmailboxsecuritydescriptor", "logonhours", "usersmimecertificate", "userpassword"}


def _raw_entry(e) -> dict:
    d = e.entry_attributes_as_dict
    return {"dn": e.entry_dn,
            "attributes": {k: ", ".join(str(x) for x in (v if isinstance(v, list) else [v]))[:160]
                           for k, v in sorted(d.items()) if k.lower() not in _RAW_SKIP}}


# A group, in each dialect: AD knows it by its category, the others by one of the
# usual object classes. Searched by its name, its account name or its address.
_GROUP_FILTER = {
    "ad": ("(objectCategory=group)", ("cn", "name", "sAMAccountName", "mail")),
    "ldap": ("(|(objectClass=groupOfNames)(objectClass=groupOfUniqueNames)(objectClass=posixGroup)"
             "(objectClass=groupOfMembers))", ("cn", "description")),
}


def _diag_ldap(cfg: dict, q: str, tr: _Trace, limit: int, source: str, mode: str, custom: dict):
    from ldap3 import BASE, LEVEL, SUBTREE
    from ldap3.utils.conv import escape_filter_chars

    label = LABELS[source]
    with tr.step("config") as st:
        if _ldap_connection_factory is None:
            host, port, use_ssl = _url_parts(cfg, label)
            enc = "LDAPS" if use_ssl else ("StartTLS" if cfg.get("ldap_start_tls") else "sans chiffrement")
            st["detail"] = f"{host}:{port}, {enc}"
            if not use_ssl and not cfg.get("ldap_start_tls"):
                st["status"] = "warn"
                st["detail"] += ". Sans chiffrement, aucun mot de passe ne peut être envoyé : préférez ldaps://"
        if mode == "custom":
            base = (custom.get("base") or cfg.get("ldap_base_dn") or "").strip()
            if not base:
                raise DirectoryError(f"{label} : indiquez une base de recherche pour le test personnalisé")
            keys = {}
        else:
            base, flt, keys, _wanted = _ldap_plan(cfg, q, label)
    with tr.step("connect") as st:
        conn = _ldap_connection(cfg, label)
        st["detail"] = "connexion ouverte, certificat vérifié" if _ldap_connection_factory is None else "connexion ouverte"
    try:
        with tr.step("bind") as st:
            dn = cfg.get("ldap_bind_dn") or ""
            if not conn.bound and not conn.bind():
                raise _bind_error(conn, label)
            st["detail"] = f"authentifié en tant que {dn}" if dn else "connexion anonyme"
            if source == "ad" and not dn:
                st["status"] = "warn"
                st["detail"] += ". Active Directory refuse en général les recherches anonymes : renseignez un compte de service."
        with tr.step("base") as st:
            conn.search(base, "(objectClass=*)", BASE, attributes=[], size_limit=1, time_limit=int(TIMEOUT))
            if (conn.result or {}).get("description") not in (None, "success"):
                raise DirectoryError(f"{label} : base « {base} » introuvable ou illisible "
                                     f"({(conn.result or {}).get('description')}). Vérifiez son orthographe "
                                     "et les droits de lecture du compte de service.")
            st["detail"] = f"« {base} » existe"

        def run(flt: str, scope, attrs, size: int):
            conn.search(base, flt, scope, attributes=attrs, size_limit=size, time_limit=int(TIMEOUT))
            desc = (conn.result or {}).get("description")
            if desc not in (None, "success", "sizeLimitExceeded"):
                raise DirectoryError(f"{label} : recherche refusée ({desc} : {(conn.result or {}).get('message', '')[:160]})")
            return list(conn.entries), desc == "sizeLimitExceeded"

        if mode == "user":
            with tr.step("query") as st:
                entries, cut = run(flt, SUBTREE, ["*"], limit)
                people = _ldap_people(conn, source, keys)
                tr.out["sample"] = people
                st["detail"] = f"filtre {flt} : {len(entries)} entrée(s)" + (f" (limitée à {limit})" if cut else "")
                if len(entries) > len(people):
                    st["status"] = "warn"
                    st["detail"] += (f", dont {len(entries) - len(people)} sans email dans l'attribut "
                                     f"« {keys['email']} » (ignorées)")
            with tr.step("attributes") as st:
                if not entries:
                    st["status"] = "skip"
                    st["detail"] = "aucune entrée à examiner : essayez un autre texte de recherche"
                else:
                    # The first entry with an email, the kind the mapping is for.
                    first = next((e for e in entries if _attr(e.entry_attributes_as_dict, keys["email"])), entries[0])
                    present = {k.lower() for k in first.entry_attributes_as_dict}
                    missing = [f"{k} ({v})" for k, v in keys.items() if v and v.lower() not in present]
                    tr.out["raw"] = _raw_entry(first)
                    st["detail"] = f"entrée examinée : {first.entry_dn}"
                    if missing:
                        st["status"] = "warn"
                        st["detail"] += ". Attribut(s) de correspondance absent(s) : " + ", ".join(missing)
        elif mode == "group":
            with tr.step("query") as st:
                term = escape_filter_chars(_clean(q))
                kind, attrs = _GROUP_FILTER[source]
                gflt = f"(&{kind}(|" + "".join(f"({a}=*{term}*)" for a in attrs) + "))"
                entries, cut = run(gflt, SUBTREE, ["cn", "name", "mail", "description", "member",
                                                    "uniqueMember", "memberUid"], limit)
                groups = []
                for e in entries:
                    d = e.entry_attributes_as_dict
                    members = sum(len(d.get(k) or []) for k in ("member", "uniqueMember", "memberUid"))
                    groups.append({"name": _attr(d, "cn") or _attr(d, "name") or e.entry_dn, "email": _attr(d, "mail"),
                                   "description": _attr(d, "description"), "members": members, "id": e.entry_dn})
                tr.out["groups"] = groups
                st["detail"] = f"filtre {gflt} : {len(groups)} groupe(s)" + (f" (limité à {limit})" if cut else "")
        else:
            with tr.step("query") as st:
                flt = (custom.get("filter") or "(objectClass=*)").strip()
                if not flt.startswith("("):
                    flt = f"({flt})"
                scope = {"base": BASE, "one": LEVEL}.get(custom.get("scope"), SUBTREE)
                attrs = [a.strip() for a in (custom.get("attributes") or "*").split(",") if a.strip()] or ["*"]
                try:
                    size = max(1, min(CUSTOM_MAX, int(custom.get("limit") or 10)))
                except (TypeError, ValueError):
                    size = 10
                entries, cut = run(flt, scope, attrs, size)
                tr.out["entries"] = [_raw_entry(e) for e in entries]
                st["detail"] = (f"base {base}, portée {custom.get('scope') or 'sub'}, filtre {flt} : "
                                f"{len(entries)} entrée(s)" + (f" (limitée à {size})" if cut else ""))
    finally:
        try:
            conn.unbind()
        except Exception:
            pass
    return None


def diagnose(source: str, cfg: dict, q: str, limit: int = 5, mode: str = "user", custom: dict | None = None) -> dict:
    """Run one source step by step. Never raises: the outcome is in the result.

    ``{"ok", "error", "mode", "steps": [...], "count", "sample", "groups",
    "entries", "raw", "body"}``: ``sample`` the people found, ``groups`` the
    groups, ``entries`` the raw LDAP entries of a custom test, ``raw`` the first
    entry of a people search with all its attributes (LDAP, AD), ``body`` the
    HTTP answer of a custom test (Entra, Google)."""
    tr = _Trace()
    mode = mode if mode in MODES else "user"
    custom = custom or {}
    q = _clean(q) or "a"
    if mode == "group":
        limit = max(limit, 10)
    try:
        if source == "entra":
            _diag_entra(cfg, q, tr, limit, mode, custom)
        elif source == "google":
            _diag_google(cfg, q, tr, limit, mode, custom)
        elif source in ("ad", "ldap"):
            _diag_ldap(as_ldap(cfg, source), q, tr, limit, source, mode, custom)
        else:
            raise DirectoryError(f"source inconnue : {source}")
        ok, error = True, None
    except DirectoryError as exc:
        ok, error = False, str(exc)
    out = tr.out
    sample = out.get("sample") or []
    groups = out.get("groups")
    entries = out.get("entries")
    count = len(groups) if groups is not None else len(entries) if entries is not None else len(sample)
    return {"ok": ok, "error": error, "mode": mode, "steps": tr.steps, "count": count,
            "sample": sample[:limit], "groups": groups, "entries": entries,
            "raw": out.get("raw"), "body": out.get("body")}
