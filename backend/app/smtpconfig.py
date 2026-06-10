"""SMTP configuration stored in DB, editable from the admin UI (like OIDC/SAML)."""
import json

from sqlalchemy.orm import Session

from .models import AppSetting

SMTP_KEY = "smtp"


def _defaults() -> dict:
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
    cfg = _defaults()
    row = db.get(AppSetting, SMTP_KEY)
    if row:
        try:
            cfg.update({k: v for k, v in json.loads(row.value).items() if k in KEYS})
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


def set_smtp(db: Session, patch: dict) -> dict:
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
