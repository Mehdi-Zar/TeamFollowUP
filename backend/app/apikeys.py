"""API keys: machine credentials for the read-only API.

Design (see docs/adr/0011-api-keys-and-scopes.md):

* A key is a *service* credential, not a user. It belongs to the organisation and
  outlives whoever created it.
* The secret is generated once, shown once, and stored only as an argon2 hash.
  What we keep in clear is the `prefix` - the non-secret head of the key - which
  is what the admin UI displays and what we look the key up by. Looking a key up
  by prefix means one hash verification per call, not one per row.
* Authority is the intersection of two things: the *scopes* (which resources) and
  the *tribe* (whose data). Neither is a persona: personas gate humans navigating
  sections, scopes gate a credential reading resources.

Only read scopes exist today - keys cannot write. Adding a write scope means
deliberately opening a write route to machines, which is a decision, not an
accident.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ApiKey, User, utcnow
from .security import hash_password, verify_password

# Every key looks like:  trt_<8 hex>_<43 url-safe chars>
#                        └── prefix ──┘ └──── secret ────┘
KEY_PREFIX = "trt"
_PREFIX_BYTES = 4
_SECRET_BYTES = 32


# The catalog. `key` is what is stored on the credential and checked on a route;
# `label` is what the admin UI shows. Read-only by construction.
SCOPES: list[dict] = [
    {"key": "dashboard:read", "label": "Dashboard (lecture)",
     "desc": "Lire le dashboard et l'exporter (HTML/PPTX)."},
    {"key": "roadmap:read", "label": "Roadmap (lecture)",
     "desc": "Lire la roadmap, les dépendances, et les exporter."},
    {"key": "reports:read", "label": "Rapport hebdomadaire (lecture)",
     "desc": "Télécharger le rapport hebdomadaire (HTML/PPTX)."},
    {"key": "org:read", "label": "Organigramme (lecture)",
     "desc": "Lire l'organigramme et l'exporter."},
    {"key": "budget:read", "label": "Budgets (lecture)",
     "desc": "Inclure les montants de budget dans les rapports. Sans ce scope, "
             "les budgets sont retirés des documents servis à la clé."},
]
SCOPE_KEYS = {s["key"] for s in SCOPES}


def normalize_scopes(raw) -> list[str]:
    """Keep only known scopes, deduplicated, in catalog order (unknown → dropped)."""
    asked = set(raw or [])
    return [s["key"] for s in SCOPES if s["key"] in asked]


def generate_key() -> tuple[str, str]:
    """Return (full_secret_shown_once, prefix). The secret is never stored."""
    prefix = f"{KEY_PREFIX}_{secrets.token_hex(_PREFIX_BYTES)}"
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    return f"{prefix}_{secret}", prefix


def split_key(presented: str) -> tuple[str, str] | None:
    """Split 'trt_ab12cd34_<secret>' into (prefix, secret); None if malformed.

    maxsplit=2 matters: token_urlsafe() draws from the base64url alphabet, which
    contains '_', so the secret itself may hold underscores. Splitting greedily
    would mangle every key that happens to contain one.
    """
    parts = (presented or "").strip().split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_PREFIX or not parts[1] or not parts[2]:
        return None
    return f"{parts[0]}_{parts[1]}", parts[2]


def hash_key(secret: str) -> str:
    return hash_password(secret)


def is_live(key: ApiKey, now: datetime | None = None) -> bool:
    now = now or utcnow()
    if key.revoked_at is not None:
        return False
    if key.expires_at is not None:
        exp = key.expires_at
        # Rows read back from SQLite come out naive; compare on equal footing.
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= now:
            return False
    return True


def resolve(db: Session, presented: str) -> ApiKey | None:
    """The presented secret → the live ApiKey it authenticates, or None.

    Constant-time-ish: we find the row by its (public) prefix, then verify the
    secret against the stored argon2 hash. A wrong prefix and a wrong secret are
    both simply "no key".
    """
    split = split_key(presented)
    if split is None:
        return None
    prefix, secret = split
    key = db.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if key is None or not is_live(key):
        return None
    if not verify_password(secret, key.key_hash):
        return None
    return key


def touch(db: Session, key: ApiKey) -> None:
    """Record that the key was just used (the admin UI shows 'last used')."""
    key.last_used_at = utcnow()


def principal(key: ApiKey) -> User:
    """The caller identity a key acts as, for the existing data-scoping helpers.

    A transient (never persisted) User carrying just what visible_tribe_id() and
    the squad-visibility helpers read. Role is derived from the key's tribe scope:
    a key bound to a tribe sees that tribe only ("member" scoping); a key with no
    tribe reads across tribes ("admin" scoping). Budget figures do NOT ride on
    this role - they require the explicit budget:read scope (see reports.py).
    """
    return User(
        id=None,
        email=f"apikey:{key.prefix}",
        display_name=f"API · {key.name}",
        role="admin" if key.tribe_id is None else "member",
        status="active",
        tribe_id=key.tribe_id,
    )


def public(key: ApiKey) -> dict:
    """The safe representation for the admin UI - never the secret."""
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "scopes": list(key.scopes or []),
        "tribe_id": key.tribe_id,
        "created_at": key.created_at,
        "expires_at": key.expires_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
        "live": is_live(key),
    }
