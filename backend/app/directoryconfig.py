"""Corporate directory configuration, stored in DB and edited in Administration.

One JSON blob, ``app_settings['directory']``, like the SMTP and SSO settings
(see smtpconfig). It describes two different things:

* **search sources**, which the application *calls* to find a person by name or
  email: Microsoft Entra ID (Microsoft Graph), LDAP / Active Directory, Google
  Workspace (Admin SDK Directory API). Several may be on at once; their answers
  are merged (see ``directory.search``).
* **SCIM 2.0 provisioning**, where the identity provider calls *us* to create,
  update and deactivate accounts (see ``routers/scim``). Only a hash of its bearer
  token is kept: the token is shown once, when it is generated.

Secrets (client secret, bind password, service account key) never leave the
server in clear: the admin screen gets a mask (``SECRETS``, routers/directory).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from sqlalchemy.orm import Session

from .models import AppSetting

DIRECTORY_KEY = "directory"

# Stored, used to call the directory, never shown.
SECRETS = ("entra_client_secret", "ldap_bind_password", "google_service_account_json")


def _defaults() -> dict:
    return {
        # Microsoft Entra ID (Azure AD), app registration with the
        # User.Read.All *application* permission, admin consent granted.
        "entra_enabled": False,
        "entra_tenant_id": "",
        "entra_client_id": "",
        "entra_client_secret": "",
        # National clouds (US Gov, China) answer on other hosts.
        "entra_login_host": "login.microsoftonline.com",
        "entra_graph_host": "graph.microsoft.com",
        # LDAP / LDAPS: Active Directory, OpenLDAP, FreeIPA...
        "ldap_enabled": False,
        "ldap_url": "ldaps://ldap.example.com:636",
        "ldap_start_tls": False,
        "ldap_bind_dn": "",
        "ldap_bind_password": "",
        "ldap_base_dn": "",
        "ldap_user_filter": "(&(objectClass=person)(mail=*))",
        # Attributes the typed text is looked for in (substring match).
        "ldap_search_attrs": "displayName,cn,mail,givenName,sn,sAMAccountName,uid",
        "ldap_attr_name": "displayName",
        "ldap_attr_first_name": "givenName",
        "ldap_attr_last_name": "sn",
        "ldap_attr_email": "mail",
        "ldap_attr_title": "title",
        "ldap_attr_department": "department",
        # Google Workspace: a service account with domain-wide delegation on the
        # admin.directory.user.readonly scope, acting as an administrator.
        "google_enabled": False,
        "google_service_account_json": "",
        "google_admin_subject": "",
        "google_customer": "my_customer",
        # SCIM 2.0 inbound provisioning.
        "scim_enabled": False,
        "scim_token_hash": "",
        "scim_token_hint": "",
        # The persona and tribe an account created by SCIM receives. Never admin:
        # a provisioning token must not be able to hand out administration.
        "scim_default_role": "member",
        "scim_default_tribe_id": None,
    }


KEYS = set(_defaults().keys())
_BOOLS = {"entra_enabled", "ldap_enabled", "ldap_start_tls", "google_enabled", "scim_enabled"}
# Written by the server only (token generation), never by a PUT.
_SERVER_ONLY = {"scim_token_hash", "scim_token_hint"}


def get_directory(db: Session) -> dict:
    """Effective config: defaults overlaid with the stored blob (unknown keys dropped)."""
    cfg = _defaults()
    row = db.get(AppSetting, DIRECTORY_KEY)
    if row:
        try:
            cfg.update({k: v for k, v in json.loads(row.value).items() if k in KEYS})
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    return cfg


def _store(db: Session, cfg: dict) -> None:
    payload = json.dumps({k: v for k, v in cfg.items() if k in KEYS})
    row = db.get(AppSetting, DIRECTORY_KEY)
    if row is None:
        db.add(AppSetting(key=DIRECTORY_KEY, value=payload))
    else:
        row.value = payload


def set_directory(db: Session, patch: dict) -> dict:
    """Apply a partial update from the admin screen and upsert the blob."""
    cfg = get_directory(db)
    for k, v in (patch or {}).items():
        if k in KEYS and k not in _SERVER_ONLY:
            cfg[k] = bool(v) if k in _BOOLS else v
    if cfg.get("scim_default_role") in (None, "", "admin"):
        cfg["scim_default_role"] = "member"
    tid = cfg.get("scim_default_tribe_id")
    try:
        cfg["scim_default_tribe_id"] = int(tid) if tid not in (None, "") else None
    except (TypeError, ValueError):
        cfg["scim_default_tribe_id"] = None
    _store(db, cfg)
    return cfg


def search_sources(cfg: dict) -> list[str]:
    """The search sources switched on, in a fixed order."""
    return [s for s in ("entra", "ldap", "google") if cfg.get(f"{s}_enabled")]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_scim_token(db: Session) -> str:
    """Generate a SCIM bearer token, keep only its hash, return it (shown once).

    256 random bits: a fast hash is enough, there is nothing to brute force."""
    token = "scim_" + secrets.token_urlsafe(32)
    cfg = get_directory(db)
    cfg["scim_token_hash"] = _hash(token)
    cfg["scim_token_hint"] = token[:9] + "..."
    _store(db, cfg)
    return token


def scim_token_ok(cfg: dict, presented: str | None) -> bool:
    """Constant-time check of a presented SCIM token against the stored hash."""
    stored = cfg.get("scim_token_hash") or ""
    if not stored or not presented:
        return False
    return hmac.compare_digest(stored, _hash(presented))
