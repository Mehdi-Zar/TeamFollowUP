"""General app configuration stored in DB (branding, default language/year, feed),
editable from the admin Settings. Stored as one JSON blob in app_settings['general'].
"""
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

GENERAL_KEY = "general"


def _defaults() -> dict:
    return {
        "app_name": settings.app_name,
        "app_subtitle": "Pilotage de la tribe",
        "default_lang": "fr",
        "default_year": datetime.now(timezone.utc).year,
        "staleness_threshold_days": settings.staleness_threshold_days,
        "feed_post_scope": "leaders",   # leaders | everyone
        "feed_retention_days": 0,        # 0 = keep all
        "feed_kinds": ["incident", "info", "success"],
    }


KEYS = set(_defaults().keys())


def get_general(db: Session) -> dict:
    cfg = _defaults()
    row = db.get(AppSetting, GENERAL_KEY)
    if row:
        try:
            stored = json.loads(row.value)
            cfg.update({k: v for k, v in stored.items() if k in KEYS})
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


def set_general(db: Session, patch: dict) -> dict:
    cfg = get_general(db)
    for k, v in patch.items():
        if k in KEYS:
            cfg[k] = v
    # sanitize
    try:
        cfg["staleness_threshold_days"] = max(1, min(365, int(cfg["staleness_threshold_days"])))
    except (TypeError, ValueError):
        cfg["staleness_threshold_days"] = settings.staleness_threshold_days
    if cfg.get("default_lang") not in ("fr", "en"):
        cfg["default_lang"] = "fr"
    if cfg.get("feed_post_scope") not in ("leaders", "everyone"):
        cfg["feed_post_scope"] = "leaders"
    try:
        cfg["feed_retention_days"] = max(0, int(cfg["feed_retention_days"]))
    except (TypeError, ValueError):
        cfg["feed_retention_days"] = 0
    if not isinstance(cfg.get("feed_kinds"), list) or not cfg["feed_kinds"]:
        cfg["feed_kinds"] = ["incident", "info", "success"]

    row = db.get(AppSetting, GENERAL_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=GENERAL_KEY, value=payload))
    else:
        row.value = payload
    return cfg


def public_config(db: Session) -> dict:
    from .smtpconfig import get_smtp
    cfg = get_general(db)
    return {
        "app_name": cfg["app_name"],
        "app_subtitle": cfg["app_subtitle"],
        "default_lang": cfg["default_lang"],
        "default_year": cfg["default_year"],
        "feed_post_scope": cfg["feed_post_scope"],
        "feed_kinds": cfg["feed_kinds"],
        "smtp_enabled": bool(get_smtp(db).get("enabled")),
    }
