"""Server-side computation: per-quarter squad health, progress, freshness.

Statuses (jalons): on_track | at_risk | blocked | done.
There is no single all-time status for a whole squad - health is scoped to a
quarter (the current quarter by default), which is far less ambiguous.
"""
from datetime import date, datetime, timezone

from .config import settings
from .models import Squad


def _aware(dt: datetime | None) -> datetime | None:
    """Coerce a datetime to timezone-aware UTC (naive values are treated as UTC),
    so date arithmetic never mixes naive and aware datetimes."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def current_year_quarter(now: datetime | None = None) -> tuple[int, int]:
    """Return (year, quarter 1..4) for the given instant (default: now, UTC)."""
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


def annual_mean(pcts: dict[int, int], planned: set[int]) -> int:
    """Mean of the percentages of the PLANNED quarters (those with milestones), 0
    when none is. A quarter with nothing planned is neither late nor 0% done:
    counting it as 0 capped a squad whose work all sat in Q1-Q2, finished, at 50%,
    and turned its objectives red in the autumn."""
    if not planned:
        return 0
    return round(sum(pcts[q] for q in planned) / len(planned))


def annual_progress_pct(squad: Squad, year: int) -> int:
    """Annual progress (0..100): annual_mean of the quarters that have milestones.
    The single source for every screen and document (serializers.annual_progress)."""
    planned = {r.quarter for r in squad.roadmap_items if r.year == year}
    return annual_mean(year_progress(squad, year), planned)


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


def quarter_na(squad: Squad, year: int) -> set[int]:
    """The quarters the squad says do not concern it (it started in Q3, say),
    shown as N/A and never as 0 %. A quarter that has jalons is planned whatever
    the flag says: the flag only speaks for an empty quarter."""
    planned = {r.quarter for r in squad.roadmap_items if r.year == year}
    return {qp.quarter for qp in squad.quarter_progress
            if qp.year == year and qp.not_applicable and qp.quarter not in planned}


def quarter_comments(squad: Squad, year: int) -> dict[int, str | None]:
    """The free-text comment recorded for each quarter of the year (None if unset)."""
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
    """Number of blocked milestones in the year (or a single quarter if given)."""
    return sum(1 for r in squad.roadmap_items if r.year == year and r.status == "blocked" and (quarter is None or r.quarter == quarter))


def at_risk_count(squad: Squad, year: int, quarter: int | None = None) -> int:
    """Number of at-risk milestones in the year (or a single quarter if given)."""
    return sum(1 for r in squad.roadmap_items if r.year == year and r.status == "at_risk" and (quarter is None or r.quarter == quarter))


def counts(squad: Squad, year: int) -> dict:
    """Aggregate counters for a squad/year: its milestones by status. (The squad
    objectives, retired, are not counted: reading them cost one query per squad.)"""
    items = [r for r in squad.roadmap_items if r.year == year]
    return {
        "roadmap_total": len(items),
        "roadmap_done": sum(1 for r in items if r.status == "done"),
        "roadmap_blocked": sum(1 for r in items if r.status == "blocked"),
        "roadmap_at_risk": sum(1 for r in items if r.status == "at_risk"),
        "roadmap_on_track": sum(1 for r in items if r.status == "on_track"),
    }


def last_submission(squad: Squad) -> datetime | None:
    """Timestamp of the squad's most recent reporting snapshot, or None if it has
    never submitted."""
    if not squad.snapshots:
        return None
    return max(_aware(s.submitted_at) for s in squad.snapshots)


def freshness(squad: Squad, threshold: int | None = None, now: datetime | None = None) -> dict:
    """Reporting-freshness readout for a squad.

    Compares the last submission against `threshold` days (falling back to the
    configured default). A squad that never submitted is treated as stale. Returns
    last_submitted_at, age_days, is_stale, threshold_days and never_submitted -
    used to flag squads whose reporting is out of date."""
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
    """Numeric severity for sorting (blocked=3 > at_risk=2 > on_track=1 > 0)."""
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


# How many days before its committed date an unfinished OTD turns "at risk",
# even with no milestone blocked: the last fortnight is too late to recover.
OTD_DUE_SOON_DAYS = 15

# The statuses an OTD can have. The first four are computed, "unscoped" too; the
# others are facts: a delivery declared by hand, a cancellation, a carry-over.
OTD_STATUSES = ("on_track", "at_risk", "late", "delivered", "delivered_late",
                "not_delivered", "cancelled", "unscoped")


def quarter_end(year: int, quarter: int) -> date:
    """The last day of a quarter."""
    return date(year, 3 * quarter, 31 if quarter in (1, 4) else 30)


def day_of(dt) -> date | None:
    """The calendar day of a datetime (UTC) or a date."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return _aware(dt).date()
    return dt


def otd_state(jalons, committed_date, now: datetime | None = None, otd=None) -> dict:
    """The status of an OTD and why, as ``{"status", "reasons"}``.

    Facts written on the OTD come first, in this order:

      cancelled      : the OTD was cancelled (with a reason). Out of every count.
      declared       : a status declared by hand (delivered, delivered_late,
                       not_delivered), for an OTD whose story happened before the
                       tool: it wins over the milestones as long as it exists.
      not_delivered  : the OTD was not delivered by the end of its year and was
                       carried over to the next one, where its copy lives on.

    Otherwise the status is computed from the milestones linked to it and its
    committed date, first rule that matches:

      no milestone   : late once the date has passed, else unscoped (nothing to
                       judge it on yet).
      all done       : delivered, or delivered_late when the last milestone was
                       finished after the committed date.
      date passed    : late, from the day after the committed date.
      at_risk        : a milestone is blocked or at risk, the date is less than
                       OTD_DUE_SOON_DAYS days away, or an unfinished milestone is
                       planned in a quarter that ends after the date.
      on_track       : otherwise.
    """
    if otd is not None:
        if getattr(otd, "cancelled_at", None) is not None:
            return {"status": "cancelled", "reasons": ["cancelled"]}
        declared = getattr(otd, "declared_status", None)
        if declared:
            return {"status": declared, "reasons": ["declared"]}
        if getattr(otd, "carried_to", None):
            return {"status": "not_delivered", "reasons": ["carried_over"]}
    jalons = list(jalons)
    today = (_aware(now) or datetime.now(timezone.utc)).date()
    committed = day_of(committed_date)
    passed = committed is not None and today > committed
    if not jalons:
        return {"status": "late" if passed else "unscoped",
                "reasons": ["date_passed", "no_milestone"] if passed else ["no_milestone"]}
    if all(j.status == "done" for j in jalons):
        ends = [day_of(getattr(j, "done_at", None)) for j in jalons]
        last = max((d for d in ends if d is not None), default=None)
        if committed is not None and last is not None and last > committed:
            return {"status": "delivered_late", "reasons": ["done_after_date"]}
        return {"status": "delivered", "reasons": ["all_done"]}
    if passed:
        return {"status": "late", "reasons": ["date_passed"]}
    reasons = []
    if any(j.status == "blocked" for j in jalons):
        reasons.append("milestone_blocked")
    if any(j.status == "at_risk" for j in jalons):
        reasons.append("milestone_at_risk")
    if committed is not None and (committed - today).days <= OTD_DUE_SOON_DAYS:
        reasons.append("due_soon")
    if committed is not None and any(j.status != "done" and quarter_end(j.year, j.quarter) > committed
                                     for j in jalons):
        reasons.append("milestone_beyond_date")
    if reasons:
        return {"status": "at_risk", "reasons": reasons}
    return {"status": "on_track", "reasons": []}


def otd_status(jalons, committed_date, now: datetime | None = None, otd=None) -> str:
    """The status of an OTD (see ``otd_state`` for the rules)."""
    return otd_state(jalons, committed_date, now, otd)["status"]
