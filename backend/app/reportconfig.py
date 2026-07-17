"""Weekly-report scheduling configuration, stored in DB (like SMTP/general).

Stored as one JSON blob in app_settings['weekly_report']. Drives the automatic
weekly send of the combined dashboard + progress-review report.
"""
import json

from sqlalchemy.orm import Session

from .models import AppSetting

REPORT_KEY = "weekly_report"


def _defaults() -> dict:
    """Baseline weekly-report schedule (disabled; Monday 08:00 UTC, 7-day window).

    Also carries legacy single-`weekday`/`last_sent_week` fields kept only so old
    stored blobs still read cleanly and can be migrated to the `weekdays` list.
    """
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
        # When true, skip a scheduled send if nothing changed since the last one
        # (default false = always send, clearly badged "up to date").
        "only_when_changes": False,
        # Bookkeeping: ISO date already sent today (per-day idempotency).
        "last_sent_day": "",
        # --- legacy (kept for back-compat reads / migration) ---
        "weekday": 0,
        "last_sent_week": "",
    }


KEYS = set(_defaults().keys())


def get_report(db: Session) -> dict:
    """Effective schedule config, migrating the legacy single `weekday` on read.

    If a stored blob predates multi-day scheduling it only has `weekday`; we fold
    it into a one-element `weekdays` list so the rest of the code sees one shape.
    """
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
    """Normalize recipients (list or comma/semicolon/newline string) to unique
    addresses. Keeps only entries containing '@', de-duplicated case-insensitively
    while preserving original casing and order."""
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
    """Coerce to a sorted, de-duplicated list of valid weekday ints (0=Mon..6=Sun).
    Non-int and out-of-range entries are dropped; empty result defaults to [0]."""
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
    """Validate and persist a schedule update, clamping every field to its range.

    Accepts the legacy single `weekday` for back-compat and keeps `weekday` in sync
    with `weekdays[0]` on write, so old readers and new readers stay consistent.
    """
    cfg = get_report(db)
    for k, v in patch.items():
        if k in KEYS:
            cfg[k] = v
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["attach_pptx"] = bool(cfg.get("attach_pptx", True))
    cfg["tribe_leader_digest"] = bool(cfg.get("tribe_leader_digest", False))
    cfg["only_when_changes"] = bool(cfg.get("only_when_changes", False))
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
