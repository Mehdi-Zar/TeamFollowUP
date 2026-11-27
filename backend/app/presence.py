"""Who is on site and who works remotely, day by day (ADR 0021).

Remote work is not an absence: the person works, only somewhere else. So it is
kept apart from the leaves (Leave, LeaveType), and it needs no approval.

Two sources say where a person is on a working day:

  * the **usual week** (RemotePattern.weekdays): the weekdays the person usually
    works remotely, for example Monday and Friday;
  * a **change for one day** (RemoteDay): remote on a day of the usual week where
    they are normally on site, or on site on a usual remote day.

The status of one day, from the strongest rule to the weakest:

  1. Saturday and Sunday: ``off`` (not counted);
  2. an absence in progress (pending or approved leave) covering the day: ``leave``;
  3. a change for that day: ``remote`` or ``onsite``;
  4. the usual week: ``remote`` if the weekday is in it;
  5. otherwise ``onsite``.

Full days only: a half-day of remote work is recorded as a full day, which is how
most remote work agreements count it.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .leavesconfig import ACTIVE_STATUSES
from .models import Leave, RemoteDay, RemotePattern

STATUSES = ("onsite", "remote", "leave", "off")
WORKDAYS = (0, 1, 2, 3, 4)  # Monday .. Friday


def clean_weekdays(values) -> list[int]:
    """The usual remote weekdays, deduplicated, sorted, Monday to Friday only."""
    return sorted({int(v) for v in values or [] if int(v) in WORKDAYS})


def day_range(start: date, end: date) -> list[date]:
    """Every calendar day from start to end, both included."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def statuses(db: Session, user_ids: list[int], start: date, end: date) -> dict:
    """Status of each person on each day of [start, end].

    Returns ``{user_id: {"weekdays": [...], "days": {iso: status}, "changes":
    {iso: "remote"|"onsite"}, "leaves": {iso: {"label", "color", "half"}}}}``.
    """
    ids = list(user_ids) or [-1]
    patterns = {p.user_id: clean_weekdays(p.weekdays) for p in
                db.scalars(select(RemotePattern).where(RemotePattern.user_id.in_(ids))).all()}
    changes: dict[int, dict[date, str]] = {}
    for c in db.scalars(select(RemoteDay).where(
            RemoteDay.user_id.in_(ids), RemoteDay.day >= start, RemoteDay.day <= end)).all():
        changes.setdefault(c.user_id, {})[c.day] = c.location
    leaves: dict[int, list[Leave]] = {}
    for lv in db.scalars(select(Leave).where(
            Leave.user_id.in_(ids), Leave.status.in_(ACTIVE_STATUSES),
            Leave.end_date >= start, Leave.start_date <= end)).all():
        leaves.setdefault(lv.user_id, []).append(lv)

    days = day_range(start, end)
    out: dict[int, dict] = {}
    for uid in user_ids:
        week = patterns.get(uid, [])
        mine = changes.get(uid, {})
        cells: dict[str, str] = {}
        away: dict[str, dict] = {}
        for d in days:
            k = d.isoformat()
            if d.weekday() not in WORKDAYS:
                cells[k] = "off"
                continue
            lv = next((x for x in leaves.get(uid, []) if x.start_date <= d <= x.end_date), None)
            if lv is not None:
                cells[k] = "leave"
                half = (d == lv.start_date and lv.start_half) or (d == lv.end_date and lv.end_half)
                away[k] = {"label": lv.type.label if lv.type else "", "detail": lv.detail,
                           "color": lv.type.color if lv.type else "#6B7280", "half": bool(half),
                           "pending": lv.status == "pending"}
            elif d in mine:
                cells[k] = mine[d]
            else:
                cells[k] = "remote" if d.weekday() in week else "onsite"
        out[uid] = {"weekdays": week, "days": cells,
                    "changes": {d.isoformat(): v for d, v in mine.items()}, "leaves": away}
    return out
