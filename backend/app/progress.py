"""Progress-review timeline: capture and aggregation.

A ProgressUpdate is recorded:
  - automatically on each meaningful reporting write (kind="auto", coalesced
    within a short window so a single editing session = one point),
  - on a weekly cadence (kind="weekly"),
  - when a leader posts a review note + confidence (kind="review").

Each point stores the metrics of the moment (for the evolution curve), a light
state snapshot used to compute human-readable `changes` vs the previous point.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger("trt.progress")

from . import status as st
from .models import ProgressUpdate, Squad, User, utcnow
from .serializers import annual_progress

COALESCE_MINUTES = 30


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_state(squad: Squad, year: int) -> dict:
    """Light snapshot used both for metrics and for diffing into `changes`."""
    progress = st.year_progress(squad, year)
    comments = st.quarter_comments(squad, year)
    items = [r for r in squad.roadmap_items if r.year == year]
    return {
        "roadmap": {
            str(r.id): {"title": r.title, "quarter": r.quarter, "status": r.status}
            for r in items
        },
        "quarters": {str(q): {"pct": progress[q], "comment": comments[q]} for q in (1, 2, 3, 4)},
        "objectives": {
            str(o.id): {"title": o.title, "rag": st.objective_status(o, squad)}
            for o in squad.objectives if o.year == year
        },
        "kpis": {
            str(k.id): {"name": k.name, "trend": k.trend_status}
            for k in squad.kpis
        },
    }


def compute_metrics(squad: Squad, year: int) -> dict:
    items = [r for r in squad.roadmap_items if r.year == year]
    return {
        "progress_pct": annual_progress(squad, year),
        "blocked_count": sum(1 for r in items if r.status == "blocked"),
        "at_risk_count": sum(1 for r in items if r.status == "at_risk"),
        "done_count": sum(1 for r in items if r.status == "done"),
        "total_count": len(items),
    }


def diff_state(prev: dict | None, cur: dict) -> list[dict]:
    """Human-oriented list of changes between two states."""
    changes: list[dict] = []
    prev = prev or {}

    # Roadmap milestone status changes (and new milestones)
    p_road = prev.get("roadmap", {})
    for rid, item in cur.get("roadmap", {}).items():
        before = p_road.get(rid)
        if before is None:
            changes.append({"kind": "jalon_added", "label": item["title"], "to": item["status"]})
        elif before.get("status") != item["status"]:
            changes.append({"kind": "jalon_status", "label": item["title"],
                            "from": before.get("status"), "to": item["status"]})

    # Quarter progress %
    p_q = prev.get("quarters", {})
    for q, cell in cur.get("quarters", {}).items():
        before = p_q.get(q, {}).get("pct")
        if before is not None and before != cell["pct"]:
            changes.append({"kind": "quarter_pct", "label": f"Q{q}", "from": before, "to": cell["pct"]})

    # Objective RAG changes
    p_obj = prev.get("objectives", {})
    for oid, o in cur.get("objectives", {}).items():
        before = p_obj.get(oid)
        if before is not None and before.get("rag") != o["rag"]:
            changes.append({"kind": "objective_rag", "label": o["title"],
                            "from": before.get("rag"), "to": o["rag"]})

    # KPI trend changes
    p_kpi = prev.get("kpis", {})
    for kid, k in cur.get("kpis", {}).items():
        before = p_kpi.get(kid)
        if before is not None and before.get("trend") != k["trend"]:
            changes.append({"kind": "kpi_trend", "label": k["name"],
                            "from": before.get("trend"), "to": k["trend"]})

    return changes


def _last_update(db: Session, squad_id: int, year: int, before: datetime | None = None):
    stmt = select(ProgressUpdate).where(
        ProgressUpdate.squad_id == squad_id, ProgressUpdate.year == year
    )
    if before is not None:
        stmt = stmt.where(ProgressUpdate.created_at < before)
    return db.scalars(stmt.order_by(ProgressUpdate.created_at.desc())).first()


def record_progress(
    db: Session,
    squad: Squad,
    year: int,
    user: User | None,
    *,
    kind: str = "auto",
    note: str | None = None,
    confidence: int | None = None,
) -> ProgressUpdate:
    """Create (or coalesce into) a progress-review point. Does not commit."""
    state = compute_state(squad, year)
    metrics = compute_metrics(squad, year)
    last = _last_update(db, squad.id, year)

    # Coalesce rapid auto-edits from the same user into the most recent point.
    if (
        kind == "auto"
        and note is None
        and confidence is None
        and last is not None
        and last.kind == "auto"
        and last.created_by_user_id == (user.id if user else None)
        and _aware(last.created_at) is not None
        and (utcnow() - _aware(last.created_at)) < timedelta(minutes=COALESCE_MINUTES)
    ):
        baseline = _last_update(db, squad.id, year, before=_aware(last.created_at))
        last.state = state
        last.changes = diff_state(baseline.state if baseline else None, state)
        last.created_at = utcnow()
        for k, v in metrics.items():
            setattr(last, k, v)
        return last

    pu = ProgressUpdate(
        squad_id=squad.id,
        year=year,
        created_by_user_id=user.id if user else None,
        kind=kind,
        note=note,
        confidence=confidence,
        state=state,
        changes=diff_state(last.state if last else None, state),
        created_at=utcnow(),
        **metrics,
    )
    db.add(pu)
    return pu


def capture_progress(db: Session, squad_id: int, year: int, user: User | None,
                     *, kind: str = "auto", note: str | None = None,
                     confidence: int | None = None) -> None:
    """Record a progress point from a router; never let capture break the write."""
    try:
        squad = db.get(Squad, squad_id)
        if squad is not None:
            record_progress(db, squad, year, user, kind=kind, note=note, confidence=confidence)
    except Exception:
        # Never let progress capture break the main write, but don't lose the signal.
        logger.exception("capture_progress failed for squad_id=%s year=%s", squad_id, year)


def ensure_weekly(db: Session, now: datetime | None = None) -> int:
    """Create a weekly point for every squad whose last weekly is >= 7 days old.

    Returns the number of points created. Safe to call repeatedly (idempotent
    within a week).
    """
    now = now or utcnow()
    created = 0
    for squad in db.scalars(select(Squad)).all():
        year = st.current_year_quarter(now)[0]
        last_weekly = db.scalars(
            select(ProgressUpdate).where(
                ProgressUpdate.squad_id == squad.id,
                ProgressUpdate.kind == "weekly",
            ).order_by(ProgressUpdate.created_at.desc())
        ).first()
        if last_weekly is not None and _aware(last_weekly.created_at) is not None:
            if (now - _aware(last_weekly.created_at)) < timedelta(days=7):
                continue
        record_progress(db, squad, year, None, kind="weekly")
        created += 1
    if created:
        db.commit()
    return created
