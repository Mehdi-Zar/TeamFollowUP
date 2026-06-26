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
        # 0 = Monday … 6 = Sunday (Python weekday()).
        "weekday": 0,
        # Hour of day (0-23, server/UTC) at/after which the send fires.
        "hour": 8,
        # Look-back window for the "changes this week" section.
        "since_days": 7,
        # Bookkeeping: ISO week already sent (e.g. "2026-W24"), set by scheduler.
        "last_sent_week": "",
    }


KEYS = set(_defaults().keys())


def get_report(db: Session) -> dict:
    cfg = _defaults()
    row = db.get(AppSetting, REPORT_KEY)
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


def set_report(db: Session, patch: dict) -> dict:
    cfg = get_report(db)
    for k, v in patch.items():
        if k in KEYS:
            cfg[k] = v
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["recipients"] = _clean_recipients(cfg.get("recipients"))
    try:
        cfg["weekday"] = max(0, min(6, int(cfg["weekday"])))
    except (TypeError, ValueError):
        cfg["weekday"] = 0
    try:
        cfg["hour"] = max(0, min(23, int(cfg["hour"])))
    except (TypeError, ValueError):
        cfg["hour"] = 8
    try:
        cfg["since_days"] = max(1, min(120, int(cfg["since_days"])))
    except (TypeError, ValueError):
        cfg["since_days"] = 7
    cfg["last_sent_week"] = str(cfg.get("last_sent_week") or "")

    row = db.get(AppSetting, REPORT_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=REPORT_KEY, value=payload))
    else:
        row.value = payload
    return cfg
