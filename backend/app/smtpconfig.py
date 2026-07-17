"""SMTP configuration stored in DB, editable from the admin UI (like OIDC/SAML).

Typed accessors over the single JSON blob app_settings['smtp']. `get_smtp`/
`set_smtp` overlay stored values on `_defaults()` and coerce fields (e.g. port to
int) so callers always get a well-formed config. The `password` is stored here
because outbound mail needs it; it is never surfaced by the public config
(see generalconfig.public_config, which exposes only `smtp_enabled`).
"""
import json

from sqlalchemy.orm import Session

from .models import AppSetting

SMTP_KEY = "smtp"


def _defaults() -> dict:
    """Baseline SMTP settings (disabled, TLS submission on port 587)."""
    return {
        "enabled": False,
        "host": "",
        "port": 587,
        "username": "",
        "password": "",
        "from_addr": "tribe-cockpit@local",
        "from_name": "Tribe Cockpit",
        "use_tls": True,
        "use_ssl": False,
    }


KEYS = set(_defaults().keys())


def get_smtp(db: Session) -> dict:
    """Effective SMTP config: defaults overlaid with the stored blob.

    Unknown keys are filtered out and a corrupt blob falls back to defaults.
    """
    cfg = _defaults()
    row = db.get(AppSetting, SMTP_KEY)
    if row:
        try:
            cfg.update({k: v for k, v in json.loads(row.value).items() if k in KEYS})
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


def set_smtp(db: Session, patch: dict) -> dict:
    """Apply a partial update, coerce `port` to int, and upsert the blob."""
    cfg = get_smtp(db)
    for k, v in patch.items():
        if k in KEYS:
            cfg[k] = v
    try:
        cfg["port"] = int(cfg["port"])
    except (TypeError, ValueError):
        cfg["port"] = 587
    row = db.get(AppSetting, SMTP_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=SMTP_KEY, value=payload))
    else:
        row.value = payload
    return cfg
