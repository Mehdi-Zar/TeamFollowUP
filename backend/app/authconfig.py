"""Runtime auth configuration (OIDC / SAML) stored in DB, editable from the admin UI.

Values fall back to environment variables (settings) when not set in DB.
The single JSON blob lives in app_settings under key 'auth_config'.

**One URL to configure.** The three SSO callback URLs an IdP needs (OIDC redirect
URI, SAML SP entity ID, SAML ACS URL) are all ``<public base URL> + <fixed path>``.
Rather than asking an admin to keep three absolute URLs in sync, only the public
base URL is configured, and the three are derived from it (:func:`derive_sso_urls`).
The base URL itself has three sources, most specific first:

1. ``public_base_url`` saved in the admin UI (DB);
2. the ``PUBLIC_BASE_URL`` environment variable;
3. the incoming request, honouring ``X-Forwarded-Proto`` / ``X-Forwarded-Host``
   (uvicorn runs with ``proxy_headers=True``), which covers local dev and any
   single-hostname deployment without configuring anything at all.

Each of the three URLs can still be overridden individually when an IdP
registration mandates a specific value; an override that merely restates what we
would derive is collapsed back to "empty" on save, so it keeps following the base
URL instead of silently freezing a hostname.
"""
import json

from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

AUTH_KEY = "auth_config"

# Fixed API paths behind each SSO URL. These are routes in routers/auth.py and are
# not configurable - only the base URL they hang off is.
SSO_URL_PATHS = {
    "oidc_redirect_uri": "/api/auth/oidc/callback",
    "saml_sp_entity_id": "/api/auth/saml/metadata",
    "saml_acs_url": "/api/auth/saml/acs",
}

DEFAULTS_FROM_ENV = lambda: {
    "public_base_url": settings.public_base_url,
    "oidc_enabled": settings.oidc_enabled,
    "oidc_issuer_url": settings.oidc_issuer_url,
    "oidc_client_id": settings.oidc_client_id,
    "oidc_client_secret": settings.oidc_client_secret,
    "oidc_redirect_uri": settings.oidc_redirect_uri,
    "oidc_scopes": settings.oidc_scopes,
    "oidc_groups_claim": "groups",
    "saml_enabled": settings.saml_enabled,
    "saml_idp_metadata_url": settings.saml_idp_metadata_url,
    "saml_idp_metadata_path": settings.saml_idp_metadata_path,
    "saml_sp_entity_id": settings.saml_sp_entity_id,
    "saml_acs_url": settings.saml_acs_url,
    "saml_sp_cert": settings.saml_sp_cert,
    "saml_sp_key": settings.saml_sp_key,
    "saml_groups_attr": "groups",
    "group_role_mappings": [],  # [{"group": "...", "role": "tribe_leader"}]
    # Access control for SSO provisioning:
    #  - allowed_email_domains: if non-empty, only these email domains may be
    #    provisioned at all (first gate). Empty = allow any authenticated identity.
    #  - require_approval: when True, new SSO users are created "pending" and must
    #    be validated by an admin / tribe leader / squad leader before access.
    "allowed_email_domains": [],
    "require_approval": True,
}

EDITABLE_KEYS = set(DEFAULTS_FROM_ENV().keys())
VALID_ROLES = {"admin", "tribe_leader", "squad_leader", "member"}


def normalize_base_url(value: str | None) -> str:
    """Reduce a user-typed public URL to ``scheme://host[:port]``.

    Tolerates the shapes people actually paste: a trailing slash, a trailing
    ``/api/...`` path, surrounding spaces, a bare hostname (assumed HTTPS, the
    only sane default for an SSO callback). Returns "" for empty input.
    """
    v = (value or "").strip()
    if not v:
        return ""
    if "://" not in v:
        v = "https://" + v
    scheme, _, rest = v.partition("://")
    # Keep the authority only: a path would break every derived callback URL.
    authority = rest.split("/", 1)[0]
    return f"{scheme.lower()}://{authority}".rstrip("/")


def base_url_from_request(request) -> str:
    """Public base URL as seen by the browser that issued ``request``.

    ``X-Forwarded-Proto`` / ``-Host`` (first hop) win, so a Gateway/ALB that
    terminates TLS still yields the external ``https://…`` URL rather than the
    pod's internal ``http://…:8000``. Reading them here rather than relying on
    uvicorn's ``proxy_headers`` keeps the behaviour identical under any ASGI
    server and testable. Falls back to the request URL when no proxy is involved.
    """
    if request is None:
        return ""
    headers = getattr(request, "headers", None) or {}
    first = lambda name: (headers.get(name) or "").split(",")[0].strip()
    proto, host = first("x-forwarded-proto"), first("x-forwarded-host")
    if host:
        return normalize_base_url(f"{proto or request.url.scheme}://{host}")
    if proto:
        return normalize_base_url(f"{proto}://{request.url.netloc}")
    return normalize_base_url(str(request.base_url))


def derive_sso_urls(base_url: str) -> dict[str, str]:
    """Map each SSO URL key to ``base_url`` + its fixed path (all "" if no base)."""
    base = normalize_base_url(base_url)
    if not base:
        return {k: "" for k in SSO_URL_PATHS}
    return {k: base + path for k, path in SSO_URL_PATHS.items()}


def _stored_auth_config(db: Session) -> dict:
    """Raw config as persisted: env defaults overlaid with the DB blob, no derivation.

    Keeps only recognised keys (``EDITABLE_KEYS``) so a stale/garbage field can't
    leak in. A missing or corrupt blob silently falls back to the env defaults so
    auth never breaks on bad stored JSON.
    """
    cfg = DEFAULTS_FROM_ENV()
    row = db.get(AppSetting, AUTH_KEY)
    if row:
        try:
            stored = json.loads(row.value)
            cfg.update({k: v for k, v in stored.items() if k in EDITABLE_KEYS})
        except (json.JSONDecodeError, TypeError):
            pass
    cfg["public_base_url"] = normalize_base_url(cfg.get("public_base_url"))
    return cfg


def _resolve(cfg: dict, request) -> dict:
    """Fill the empty SSO URLs from the effective base URL.

    Two read-only keys are added for the admin UI, and dropped again on the next
    read since they are not in ``EDITABLE_KEYS``:

      * ``base_url_effective`` - the base URL actually in use;
      * ``base_url_source`` - ``configured``, ``request`` or ``unset``.
    """
    configured = cfg["public_base_url"]
    base = configured or base_url_from_request(request)
    out = dict(cfg)
    out["base_url_effective"] = base
    out["base_url_source"] = "configured" if configured else ("request" if base else "unset")
    for key, derived in derive_sso_urls(base).items():
        if not (out.get(key) or "").strip():
            out[key] = derived
    return out


def get_auth_config(db: Session, request=None) -> dict:
    """Return the effective auth config: stored values with the SSO URLs resolved."""
    return _resolve(_stored_auth_config(db), request)


def set_auth_config(db: Session, patch: dict, request=None) -> dict:
    """Apply an admin patch to the auth config, sanitize it, and persist it.

    Only whitelisted keys are accepted. The public base URL is normalized, the
    group->role mappings, email-domain allowlist and the require_approval flag are
    all normalized before storage so downstream code can trust their shape (valid
    roles only, lowercase deduped domains, boolean flag).

    An SSO URL submitted with exactly the value we would derive is stored empty,
    so the admin UI can round-trip the resolved URLs it displays without turning
    them into frozen overrides. Returns the effective config (derivation applied).

    Note: stages the row on the session but does not commit — the caller controls
    the transaction boundary.
    """
    cfg = _stored_auth_config(db)
    for k, v in patch.items():
        if k in EDITABLE_KEYS:
            cfg[k] = v
    cfg["public_base_url"] = normalize_base_url(cfg.get("public_base_url"))
    # Collapse "overrides" that merely restate the derivation back to empty, so
    # they keep tracking the base URL instead of freezing today's hostname.
    base = cfg["public_base_url"] or base_url_from_request(request)
    for key, derived in derive_sso_urls(base).items():
        if derived and (cfg.get(key) or "").strip() == derived:
            cfg[key] = ""
        else:
            cfg[key] = (cfg.get(key) or "").strip()
    # sanitize mappings: drop entries with a blank group or an unknown role so a
    # malformed mapping can never grant an unexpected privilege.
    mappings = []
    for m in cfg.get("group_role_mappings") or []:
        group = (m.get("group") or "").strip()
        role = m.get("role")
        if group and role in VALID_ROLES:
            mappings.append({"group": group, "role": role})
    cfg["group_role_mappings"] = mappings
    # Normalize the email-domain allowlist (lowercase, no leading '@', deduped).
    domains = []
    for d in cfg.get("allowed_email_domains") or []:
        d = str(d).strip().lower().lstrip("@")
        if d and d not in domains:
            domains.append(d)
    cfg["allowed_email_domains"] = domains
    cfg["require_approval"] = bool(cfg.get("require_approval", True))

    stored = {k: v for k, v in cfg.items() if k in EDITABLE_KEYS}
    # Saving the admin page must not silently freeze the deployment's
    # PUBLIC_BASE_URL into the database. The value is only persisted when it
    # actually differs from the environment; otherwise it is omitted, so the env
    # var keeps winning and changing it in the manifest still takes effect. Note
    # this omits rather than stores "", because a stored "" would override a
    # non-empty environment default (see _stored_auth_config).
    if stored.get("public_base_url") == normalize_base_url(settings.public_base_url):
        stored.pop("public_base_url", None)

    row = db.get(AppSetting, AUTH_KEY)
    payload = json.dumps(stored)
    if row is None:
        db.add(AppSetting(key=AUTH_KEY, value=payload))
    else:
        row.value = payload
    # Resolve from the in-memory config: the row above is staged, not flushed, so
    # re-reading it through the session would miss a first-time insert.
    return _resolve({**DEFAULTS_FROM_ENV(), **stored}, request)


def email_domain_allowed(cfg: dict, email: str) -> bool:
    """First access gate: is this email's domain permitted to be provisioned?
    An empty allowlist permits any authenticated identity (approval still applies)."""
    domains = cfg.get("allowed_email_domains") or []
    if not domains:
        return True
    email = (email or "").lower().strip()
    return "@" in email and email.rsplit("@", 1)[1] in domains


def role_from_groups(cfg: dict, groups) -> str | None:
    """Return the highest-priority role mapped from the user's IdP groups, if any."""
    if not groups:
        return None
    if isinstance(groups, str):
        groups = [groups]
    groups = set(str(g) for g in groups)
    # When a user is in several mapped groups, the most privileged role wins.
    priority = {"admin": 3, "tribe_leader": 2, "squad_leader": 1, "member": 0}
    best = None
    for m in cfg.get("group_role_mappings") or []:
        if m["group"] in groups:
            if best is None or priority.get(m["role"], -1) > priority.get(best, -1):
                best = m["role"]
    return best
