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
ALL_EVENTS = ["submission", "progress", "roadmap", "budget", "key_message",
              "otd", "kpi", "committee", "team", "mood"]
# By default only the submission notifies: it is the moment the squad says its
# reporting is ready. The editing events fire while it is being filled in.
DEFAULT_EVENTS = ["submission"]
# The kinds that existed before the last five were added. A config that had all of
# them on meant "every change": it gets the new ones too (see get_change_notify).
_FIRST_EVENTS = {"progress", "roadmap", "budget", "key_message"}


def _defaults() -> dict:
    """Baseline change-notification config (disabled; all event kinds, no debounce)."""
    return {
        "enabled": False,
        # Explicit recipient emails (who gets the change export).
        "recipients": [],
        # Which modifications trigger an email (the "conditions").
        "events": list(DEFAULT_EVENTS),
        # Attach the PPTX export in addition to the HTML body.
        "attach_pptx": True,
        # Grouping window: changes to a squad are gathered and sent as ONE mail
        # once the squad has been quiet this many minutes (0 = one mail per change).
        "min_interval_minutes": 15,
        # Restrict to these squad ids (empty = all squads).
        "scope_squads": [],
        # Only notify on changes for the current year.
        "current_year_only": True,
        # Also email the tribe leader(s) of the squad's tribe, on top of the list.
        "tribe_leaders": False,
        # Also email the squad's own leader and co-leaders (except the author).
        "squad_leaders": False,
        # Bumped when ALL_EVENTS grows (see get_change_notify).
        "events_version": 3,
    }


KEYS = set(_defaults().keys())


def get_change_notify(db: Session) -> dict:
    """Effective change-notify config: defaults overlaid with the stored blob."""
    cfg = _defaults()
    row = db.get(AppSetting, CHANGE_KEY)
    if row:
        try:
            stored = json.loads(row.value)
            cfg.update({k: v for k, v in stored.items() if k in KEYS})
            if "events_version" not in stored:
                # Saved before the new kinds existed: "all on" keeps meaning all.
                cfg["events_version"] = 2
                if _FIRST_EVENTS <= set(cfg.get("events") or []):
                    cfg["events"] = list(ALL_EVENTS)
            if int(cfg.get("events_version") or 0) < 3:
                # Saved before "submission" existed: whoever wanted notices of the
                # edits gets the submission too.
                cfg["events_version"] = 3
                if cfg.get("events") and "submission" not in cfg["events"]:
                    cfg["events"] = ["submission"] + list(cfg["events"])
        except (json.JSONDecodeError, TypeError):
            pass
    return cfg


def _clean_recipients(value) -> list[str]:
    """Normalize recipients (list or delimited string) to unique '@' addresses,
    de-duplicated case-insensitively while preserving original casing/order."""
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
    """Coerce an iterable to a sorted, de-duplicated list of ints (used for squad
    ids in `scope_squads`); non-int entries are dropped."""
    out = []
    for x in value or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return sorted(set(out))


def set_change_notify(db: Session, patch: dict) -> dict:
    """Validate and persist a change-notify update.

    Coerces booleans, cleans recipients/squad scope, keeps only known event kinds,
    and clamps the debounce interval to [0, 1440] minutes.
    """
    cfg = get_change_notify(db)
    for k, v in patch.items():
        if k in KEYS:
            cfg[k] = v
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["attach_pptx"] = bool(cfg["attach_pptx"])
    cfg["current_year_only"] = bool(cfg["current_year_only"])
    cfg["tribe_leaders"] = bool(cfg.get("tribe_leaders"))
    cfg["squad_leaders"] = bool(cfg.get("squad_leaders"))
    cfg["events_version"] = 2
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
    """Read the per-squad last-sent timestamps used to enforce the debounce.

    Stored separately from the config (STATE_KEY) because it is runtime bookkeeping,
    not admin-editable settings. Missing/corrupt state reads as an empty map.
    """
    row = db.get(AppSetting, STATE_KEY)
    if row:
        try:
            return json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def set_state(db: Session, state: dict) -> None:
    """Upsert the per-squad debounce state (last-sent timestamps)."""
    payload = json.dumps(state)
    row = db.get(AppSetting, STATE_KEY)
    if row is None:
        db.add(AppSetting(key=STATE_KEY, value=payload))
    else:
        row.value = payload
