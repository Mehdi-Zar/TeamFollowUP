"""Server-side computation: per-quarter squad health, progress, freshness.

Statuses (jalons): on_track | at_risk | blocked | done.
There is no single all-time status for a whole squad — health is scoped to a
quarter (the current quarter by default), which is far less ambiguous.
"""
from datetime import datetime, timezone

from .config import settings
from .models import Squad


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def current_year_quarter(now: datetime | None = None) -> tuple[int, int]:
    now = now or datetime.now(timezone.utc)
    return now.year, (now.month - 1) // 3 + 1


def squad_status(squad: Squad, year: int, quarter: int | None = None) -> str:
    """'blocked' | 'at_risk' | 'on_track' for a squad, scoped to a quarter.

    quarter=None aggregates over the whole year.
    """
    items = [r for r in squad.roadmap_items if r.year == year and (quarter is None or r.quarter == quarter)]
    if any(r.status == "blocked" for r in items):
        return "blocked"
    if any(r.status == "at_risk" for r in items):
        return "at_risk"
    return "on_track"


def year_progress(squad: Squad, year: int) -> dict[int, int]:
    out = {q: 0 for q in (1, 2, 3, 4)}
    for qp in squad.quarter_progress:
        if qp.year == year and qp.quarter in out:
            out[qp.quarter] = max(0, min(100, qp.progress_pct))
    return out


def quarter_comments(squad: Squad, year: int) -> dict[int, str | None]:
    out = {q: None for q in (1, 2, 3, 4)}
    for qp in squad.quarter_progress:
        if qp.year == year and qp.quarter in out:
            out[qp.quarter] = qp.comment
    return out


def quarter_breakdown(squad: Squad, year: int, quarter: int | None) -> dict:
    """Count jalons by status for the given quarter (or whole year if None)."""
    items = [r for r in squad.roadmap_items if r.year == year and (quarter is None or r.quarter == quarter)]
    return {
        "total": len(items),
        "on_track": sum(1 for r in items if r.status == "on_track"),
        "at_risk": sum(1 for r in items if r.status == "at_risk"),
        "blocked": sum(1 for r in items if r.status == "blocked"),
        "done": sum(1 for r in items if r.status == "done"),
    }


def blocked_count(squad: Squad, year: int, quarter: int | None = None) -> int:
    return sum(1 for r in squad.roadmap_items if r.year == year and r.status == "blocked" and (quarter is None or r.quarter == quarter))


def at_risk_count(squad: Squad, year: int, quarter: int | None = None) -> int:
    return sum(1 for r in squad.roadmap_items if r.year == year and r.status == "at_risk" and (quarter is None or r.quarter == quarter))


def counts(squad: Squad, year: int) -> dict:
    objectives = [o for o in squad.objectives if o.is_active and o.year == year]
    items = [r for r in squad.roadmap_items if r.year == year]
    return {
        "objectives_total": len(objectives),
        "objectives_red": sum(1 for o in objectives if o.rag_status == "red"),
        "objectives_amber": sum(1 for o in objectives if o.rag_status == "amber"),
        "objectives_green": sum(1 for o in objectives if o.rag_status == "green"),
        "roadmap_total": len(items),
        "roadmap_done": sum(1 for r in items if r.status == "done"),
        "roadmap_blocked": sum(1 for r in items if r.status == "blocked"),
        "roadmap_at_risk": sum(1 for r in items if r.status == "at_risk"),
        "roadmap_on_track": sum(1 for r in items if r.status == "on_track"),
    }


def last_submission(squad: Squad) -> datetime | None:
    if not squad.snapshots:
        return None
    return max(_aware(s.submitted_at) for s in squad.snapshots)


def freshness(squad: Squad, threshold: int | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    last = last_submission(squad)
    threshold = threshold if threshold is not None else settings.staleness_threshold_days
    if last is None:
        return {"last_submitted_at": None, "age_days": None, "is_stale": True,
                "threshold_days": threshold, "never_submitted": True}
    age_days = (now - last).days
    return {"last_submitted_at": last.isoformat(), "age_days": age_days,
            "is_stale": age_days > threshold, "threshold_days": threshold, "never_submitted": False}


def risk_rank(status: str) -> int:
    return {"blocked": 3, "at_risk": 2, "on_track": 1}.get(status, 0)
