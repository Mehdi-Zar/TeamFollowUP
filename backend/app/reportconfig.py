"""Weekly-report scheduling configuration, stored in DB (like SMTP/general).

Stored as one JSON blob in app_settings['weekly_report']. Drives the automatic
weekly send of the combined dashboard + progress-review report.
"""
import json

from sqlalchemy.orm import Session

from .models import AppSetting

REPORT_KEY = "weekly_report"


def _defaults() -> dict:
    return {
        "enabled": False,
        # Fixed recipients (admins set these) - they receive the GLOBAL report.
        "recipients": [],
        # Days of the week to send on (0 = Monday … 6 = Sunday). Multiple allowed.
        "weekdays": [0],
        # Hour of day (0-23, server/UTC) at/after which the send fires.
        "hour": 8,
        # Look-back window for the "changes this week" section.
        "since_days": 7,
        # Attach the PPTX deck (HTML is always the email body).
        "attach_pptx": True,
        # When true, also email each tribe leader their OWN tribe-scoped report,
        # with that tribe's squad leaders in CC. Independent of `recipients`.
        "tribe_leader_digest": False,
        # Bookkeeping: ISO date already sent today (per-day idempotency).
        "last_sent_day": "",
        # --- legacy (kept for back-compat reads / migration) ---
        "weekday": 0,
        "last_sent_week": "",
    }


KEYS = set(_defaults().keys())


def get_report(db: Session) -> dict:
    cfg = _defaults()
    row = db.get(AppSetting, REPORT_KEY)
    if row:
        try:
            stored = {k: v for k, v in json.loads(row.value).items() if k in KEYS}
            cfg.update(stored)
            # Migrate a single legacy weekday → weekdays list.
            if "weekdays" not in stored and "weekday" in stored:
                cfg["weekdays"] = [stored["weekday"]]
        except (json.JSONDecodeError, TypeError):
            pass
    if not cfg.get("weekdays"):
        cfg["weekdays"] = [cfg.get("weekday", 0)]
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


def _clean_weekdays(value) -> list[int]:
    out = []
    for x in value or []:
        try:
            d = int(x)
        except (TypeError, ValueError):
            continue
        if 0 <= d <= 6:
            out.append(d)
    return sorted(set(out)) or [0]


def set_report(db: Session, patch: dict) -> dict:
    cfg = get_report(db)
    for k, v in patch.items():
        if k in KEYS:
            cfg[k] = v
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["attach_pptx"] = bool(cfg.get("attach_pptx", True))
    cfg["tribe_leader_digest"] = bool(cfg.get("tribe_leader_digest", False))
    cfg["recipients"] = _clean_recipients(cfg.get("recipients"))
    # Back-compat: a caller may still send a single `weekday` → fold into weekdays.
    if "weekday" in patch and "weekdays" not in patch:
        try:
            cfg["weekdays"] = [max(0, min(6, int(patch["weekday"])))]
        except (TypeError, ValueError):
            cfg["weekdays"] = [0]
    cfg["weekdays"] = _clean_weekdays(cfg.get("weekdays"))
    cfg["weekday"] = cfg["weekdays"][0]  # keep legacy field consistent
    try:
        cfg["hour"] = max(0, min(23, int(cfg["hour"])))
    except (TypeError, ValueError):
        cfg["hour"] = 8
    try:
        cfg["since_days"] = max(1, min(120, int(cfg["since_days"])))
    except (TypeError, ValueError):
        cfg["since_days"] = 7
    cfg["last_sent_day"] = str(cfg.get("last_sent_day") or "")
    cfg["last_sent_week"] = str(cfg.get("last_sent_week") or "")

    row = db.get(AppSetting, REPORT_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=REPORT_KEY, value=payload))
    else:
        row.value = payload
    return cfg
