"""Server-side computation: per-quarter squad health, progress, freshness.

Statuses (jalons): on_track | at_risk | blocked | done.
There is no single all-time status for a whole squad - health is scoped to a
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
    """Per-quarter advancement (0..100), AUTO-DERIVED from the quarter's milestones:
    the share of that quarter's jalons that are done. Not hand-entered."""
    out = {q: 0 for q in (1, 2, 3, 4)}
    for q in (1, 2, 3, 4):
        items = [r for r in squad.roadmap_items if r.year == year and r.quarter == q]
        if items:
            out[q] = round(100 * sum(1 for r in items if r.status == "done") / len(items))
    return out


def annual_progress_pct(squad: Squad, year: int) -> int:
    """Mean of the four quarter percentages (0..100). Mirrors serializers.annual_progress."""
    p = year_progress(squad, year)
    return round(sum(p.values()) / 4)


def objective_status(obj, squad: Squad, now: datetime | None = None) -> str:
    """Derive an objective's RAG ('green'|'amber'|'red') from the squad's advancement.

    The status is no longer entered by hand: it is deduced from whether the squad's
    annual progress keeps pace with the calendar, measured against the objective's
    optional deadline (target_date) - or the end of the year when none is set.

      green  : on/ahead of pace (or already at 100%).
      amber  : slipping 10-25 points behind the expected pace.
      red    : badly behind (>25 pts) or the deadline has passed without completion.
    """
    now = _aware(now) or datetime.now(timezone.utc)
    actual = annual_progress_pct(squad, obj.year)
    if actual >= 100:
        return "green"
    start = datetime(obj.year, 1, 1, tzinfo=timezone.utc)
    end = _aware(getattr(obj, "target_date", None)) or datetime(obj.year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    if now >= end:
        return "red"  # deadline reached and not complete
    if end <= start or now <= start:
        expected = 0.0
    else:
        expected = 100.0 * (now - start).total_seconds() / (end - start).total_seconds()
    gap = expected - actual
    if gap > 25:
        return "red"
    if gap > 10:
        return "amber"
    return "green"


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
    obj_rags = [objective_status(o, squad) for o in objectives]
    return {
        "objectives_total": len(objectives),
        "objectives_red": sum(1 for r in obj_rags if r == "red"),
        "objectives_amber": sum(1 for r in obj_rags if r == "amber"),
        "objectives_green": sum(1 for r in obj_rags if r == "green"),
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


# ----- Initiative / OTD roll-ups (derived from milestone statuses) ---------------

def rollup_status(jalons) -> str:
    """Worst-of roll-up for a set of milestones: blocked > at_risk > done(all) > on_track."""
    statuses = [j.status for j in jalons]
    if not statuses:
        return "on_track"
    if any(s == "blocked" for s in statuses):
        return "blocked"
    if any(s == "at_risk" for s in statuses):
        return "at_risk"
    if all(s == "done" for s in statuses):
        return "done"
    return "on_track"


def rollup_progress(jalons) -> int:
    """Percentage of milestones marked done (0..100)."""
    jalons = list(jalons)
    if not jalons:
        return 0
    return round(100 * sum(1 for j in jalons if j.status == "done") / len(jalons))


def otd_status(jalons, committed_date, now: datetime | None = None) -> str:
    """On-time delivery status of an OTD from its milestones + committed date:

      delivered : every milestone is done.
      late      : the committed date has passed and not everything is done.
      at_risk   : a milestone is blocked or at risk (and not yet late).
      on_track  : otherwise.
    """
    jalons = list(jalons)
    now = _aware(now) or datetime.now(timezone.utc)
    if jalons and all(j.status == "done" for j in jalons):
        return "delivered"
    committed = _aware(committed_date)
    if committed is not None and now > committed:
        return "late"
    if any(j.status in ("blocked", "at_risk") for j in jalons):
        return "at_risk"
    return "on_track"
