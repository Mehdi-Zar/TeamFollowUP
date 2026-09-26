"""Leave/absence helpers: default types seed + day counting.

The French default leave types are seeded by migration 0019; ensure_default_leave_types
re-seeds them on a fresh DB built via create_all (tests) or any environment whose
table ended up empty, so the feature is never blank out of the box.
"""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Leave, LeaveType

# (label, color, display_order) - the runtime seed for an empty table (tests /
# fresh create_all). Migration 0019 seeded these + "Télétravail", which 0020 then
# removed; this list is the current canonical default set.
DEFAULT_LEAVE_TYPES = [
    ("Congés payés", "#2563EB", 1),
    ("RTT", "#7C3AED", 2),
    ("Maladie", "#DC2626", 3),
    ("Formation", "#16A34A", 5),
    ("Autre", "#6B7280", 6),
]

# Workflow statuses.
STATUSES = ("pending", "approved", "rejected", "cancelled")
# Statuses that count as "the person is actually away" (calendar + reports).
ACTIVE_STATUSES = ("pending", "approved")


def ensure_default_leave_types(db: Session) -> None:
    """Seed the French default leave types if none exist yet (idempotent)."""
    if db.scalar(select(func.count()).select_from(LeaveType)):
        return
    for label, color, order in DEFAULT_LEAVE_TYPES:
        db.add(LeaveType(label=label, color=color, display_order=order, is_active=True,
                         requires_detail=(label == "Autre")))
    db.commit()


def leave_days(lv: Leave) -> float:
    """Number of days an absence spans, adjusted for half-days at the edges.

    Counts calendar days (weekends/holidays are NOT excluded, by product choice).
    A single-day absence with a half flag counts as 0.5."""
    if lv.start_date == lv.end_date:
        return 0.5 if (lv.start_half or lv.end_half) else 1.0
    total = (lv.end_date - lv.start_date).days + 1
    if lv.start_half:
        total -= 0.5
    if lv.end_half:
        total -= 0.5
    return float(total)


def overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    """True if two inclusive [start, end] date ranges intersect.

    Used by the overlap-alert feature to flag concurrent absences in a squad.
    Ranges are inclusive on both ends (touching endpoints count as overlapping).
    """
    return a_start <= b_end and b_start <= a_end
