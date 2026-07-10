"""Feature/module on-off switches, stored in DB (app_settings['modules']).

Two levels: each *module* (service) has an `enabled` flag, and may carry
sub-*feature* booleans. A feature is "active" only when its module is enabled
AND the feature flag is true. Editable from the admin Modules tab; surfaced to
the SPA via /api/config and enforced server-side via deps.require_module.
"""
import json

from sqlalchemy.orm import Session

from .models import AppSetting

MODULES_KEY = "modules"


def _defaults() -> dict:
    return {
        "dashboard": {"enabled": True},
        "org": {"enabled": True},
        "reporting": {"enabled": True},
        "feed": {"enabled": True, "reactions": True, "replies": True, "pin": True, "kinds": True},
        "review": {"enabled": True, "weekly_report": True},
        "squad_content": {"enabled": True, "objectives": True, "roadmap": True, "kpis": False},
        # Optional governance section ("comitologie"): squad leaders declare their
        # recurring committees, tribe leaders get oversight. Off by default.
        "committees": {"enabled": False},
        "notifications": {"enabled": True, "inapp": True, "email": True},
        "getting_started": {"enabled": True},
        "leaves": {"enabled": True, "overlap_alert": True},
    }


# Allowed (module -> set of feature keys, excluding "enabled").
_SCHEMA = {m: {k for k in feats if k != "enabled"} for m, feats in _defaults().items()}


def get_modules(db: Session) -> dict:
    cfg = _defaults()
    row = db.get(AppSetting, MODULES_KEY)
    if row:
        try:
            stored = json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            stored = {}
        for module, feats in stored.items():
            if module not in cfg or not isinstance(feats, dict):
                continue
            if "enabled" in feats:
                cfg[module]["enabled"] = bool(feats["enabled"])
            for fk, fv in feats.items():
                if fk in _SCHEMA[module]:
                    cfg[module][fk] = bool(fv)
    return cfg


def set_modules(db: Session, patch: dict) -> dict:
    cfg = get_modules(db)
    if isinstance(patch, dict):
        for module, feats in patch.items():
            if module not in cfg or not isinstance(feats, dict):
                continue
            if "enabled" in feats:
                cfg[module]["enabled"] = bool(feats["enabled"])
            for fk, fv in feats.items():
                if fk in _SCHEMA[module]:
                    cfg[module][fk] = bool(fv)
    row = db.get(AppSetting, MODULES_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=MODULES_KEY, value=payload))
    else:
        row.value = payload
    return cfg


def is_active(cfg: dict, module: str, feature: str | None = None) -> bool:
    """True if the module is enabled (and the optional feature flag is on)."""
    m = cfg.get(module) or {}
    if not m.get("enabled", True):
        return False
    if feature is None:
        return True
    return bool(m.get(feature, True))
