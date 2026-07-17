"""Runtime auth configuration (OIDC / SAML) stored in DB, editable from the admin UI.

Values fall back to environment variables (settings) when not set in DB.
The single JSON blob lives in app_settings under key 'auth_config'.
"""
import json

from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

AUTH_KEY = "auth_config"

DEFAULTS_FROM_ENV = lambda: {
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


def get_auth_config(db: Session) -> dict:
    """Return the effective auth config: env defaults overlaid with DB overrides.

    Starts from the environment-derived defaults, then merges the DB blob on top,
    keeping only recognised keys (``EDITABLE_KEYS``) so a stale/garbage field can't
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
    return cfg


def set_auth_config(db: Session, patch: dict) -> dict:
    """Apply an admin patch to the auth config, sanitize it, and persist it.

    Only whitelisted keys are accepted. The group->role mappings, email-domain
    allowlist and the require_approval flag are all normalized before storage so
    downstream code can trust their shape (valid roles only, lowercase deduped
    domains, boolean flag). Returns the full, cleaned config.

    Note: stages the row on the session but does not commit — the caller controls
    the transaction boundary.
    """
    cfg = get_auth_config(db)
    for k, v in patch.items():
        if k in EDITABLE_KEYS:
            cfg[k] = v
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

    row = db.get(AppSetting, AUTH_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=AUTH_KEY, value=payload))
    else:
        row.value = payload
    return cfg


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
