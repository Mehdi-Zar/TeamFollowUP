"""Configuration for change-notification emails (granular).

When a squad's reporting changes, an email containing **only that squad's export**
is sent to the configured recipients. Admins control *when* and *under which
conditions* this fires. Stored as one JSON blob in app_settings['change_notify'].
"""
import json

from sqlalchemy.orm import Session

from .models import AppSetting

CHANGE_KEY = "change_notify"
STATE_KEY = "change_notify_state"   # per-squad last-sent timestamps (debounce)

# Modification kinds the admin can switch on/off as trigger conditions.
ALL_EVENTS = ["progress", "roadmap", "objectives", "budget", "key_message"]


def _defaults() -> dict:
    return {
        "enabled": False,
        # Explicit recipient emails (who gets the change export).
        "recipients": [],
        # Which modifications trigger an email (the "conditions").
        "events": list(ALL_EVENTS),
        # Attach the PPTX export in addition to the HTML body.
        "attach_pptx": True,
        # Per-squad debounce: don't re-send within this many minutes (0 = every change).
        "min_interval_minutes": 0,
        # Restrict to these squad ids (empty = all squads).
        "scope_squads": [],
        # Only notify on changes for the current year.
        "current_year_only": True,
    }


KEYS = set(_defaults().keys())


def get_change_notify(db: Session) -> dict:
    cfg = _defaults()
    row = db.get(AppSetting, CHANGE_KEY)
    if row:
        try:
            cfg.update({k: v for k, v in json.loads(row.value).items() if k in KEYS})
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


def _clean_recipients(value) -> list[str]:
    if isinstance(value, str):
        parts = value.replace(",", "\n").replace(";", "\n").splitlines()
    elif isinstance(value, list):
        parts = value
    else:
        return []
    seen, out = set(), []
    for p in parts:
        addr = str(p).strip()
        if addr and "@" in addr and addr.lower() not in seen:
            seen.add(addr.lower())
            out.append(addr)
    return out


def _clean_int_list(value) -> list[int]:
    out = []
    for x in value or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return sorted(set(out))


def set_change_notify(db: Session, patch: dict) -> dict:
    cfg = get_change_notify(db)
    for k, v in patch.items():
        if k in KEYS:
            cfg[k] = v
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["attach_pptx"] = bool(cfg["attach_pptx"])
    cfg["current_year_only"] = bool(cfg["current_year_only"])
    cfg["recipients"] = _clean_recipients(cfg.get("recipients"))
    cfg["events"] = [e for e in (cfg.get("events") or []) if e in ALL_EVENTS] or []
    cfg["scope_squads"] = _clean_int_list(cfg.get("scope_squads"))
    try:
        cfg["min_interval_minutes"] = max(0, min(1440, int(cfg["min_interval_minutes"])))
    except (TypeError, ValueError):
        cfg["min_interval_minutes"] = 0

    row = db.get(AppSetting, CHANGE_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=CHANGE_KEY, value=payload))
    else:
        row.value = payload
    return cfg


def get_state(db: Session) -> dict:
    row = db.get(AppSetting, STATE_KEY)
    if row:
        try:
            return json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def set_state(db: Session, state: dict) -> None:
    payload = json.dumps(state)
    row = db.get(AppSetting, STATE_KEY)
    if row is None:
        db.add(AppSetting(key=STATE_KEY, value=payload))
    else:
        row.value = payload
