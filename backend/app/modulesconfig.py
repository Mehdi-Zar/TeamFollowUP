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
    """The default module/feature switch map (everything on except `committees`).

    Each entry is a module; `enabled` gates the whole module and every other key is
    a sub-feature boolean. This dict is also the schema source of truth: `_SCHEMA`
    is derived from it, so a module/feature only exists if it is listed here.
    """
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
        # Steering-committee inputs (squad leaders) + consolidated document. Off by default.
        "steerco": {"enabled": False},
        "notifications": {"enabled": True, "inapp": True, "email": True},
        "getting_started": {"enabled": True},
        "leaves": {"enabled": True, "overlap_alert": True},
    }


# Allowed (module -> set of feature keys, excluding "enabled").
_SCHEMA = {m: {k for k in feats if k != "enabled"} for m, feats in _defaults().items()}


def get_modules(db: Session) -> dict:
    """Return the effective module map: defaults overlaid with stored overrides.

    Stored values are applied defensively - unknown modules/features are skipped
    and every flag is coerced to bool - so the returned shape always matches the
    schema regardless of what was persisted.
    """
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
    """Merge a partial switch update into the stored map and persist it.

    Same validation as reads (unknown keys ignored, values coerced to bool), so an
    admin can send only the modules/features they changed. Returns the new map.
    """
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
    # Fail-open on unknown module/feature (default True): a switch that predates a
    # rename must not silently hide an existing section. Access control proper is
    # done by personas/scopes elsewhere; this only toggles optional features.
    m = cfg.get(module) or {}
    if not m.get("enabled", True):
        return False
    if feature is None:
        return True
    return bool(m.get(feature, True))
