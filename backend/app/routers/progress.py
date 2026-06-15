from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import (assert_can_edit_squad, get_current_user, record_audit,
                    require_admin, require_module, require_writer)
from ..models import ProgressUpdate, Squad, Tribe, User, utcnow
from ..progress import compute_metrics, ensure_weekly, record_progress
from ..schemas import ProgressNoteIn, ProgressPointOut, ProgressReviewRow

router = APIRouter(tags=["progress"])


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _point_out(pu: ProgressUpdate, author: str | None) -> ProgressPointOut:
    return ProgressPointOut(
        id=pu.id, squad_id=pu.squad_id, year=pu.year, created_at=pu.created_at,
        kind=pu.kind, author_name=author, note=pu.note, confidence=pu.confidence,
        progress_pct=pu.progress_pct, blocked_count=pu.blocked_count,
        at_risk_count=pu.at_risk_count, done_count=pu.done_count,
        total_count=pu.total_count, changes=pu.changes or [],
    )


@router.get("/api/squads/{squad_id}/progress", response_model=list[ProgressPointOut],
            dependencies=[Depends(require_module("review"))])
def squad_progress(squad_id: int, year: int | None = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    if db.get(Squad, squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    stmt = select(ProgressUpdate).where(ProgressUpdate.squad_id == squad_id)
    if year:
        stmt = stmt.where(ProgressUpdate.year == year)
    rows = db.scalars(stmt.order_by(ProgressUpdate.created_at.asc())).all()
    names = {u.id: u.display_name for u in db.scalars(select(User)).all()}
    return [_point_out(r, names.get(r.created_by_user_id)) for r in rows]


@router.post("/api/squads/{squad_id}/progress", response_model=ProgressPointOut, status_code=201,
             dependencies=[Depends(require_module("review", "notes"))])
def add_review_note(squad_id: int, payload: ProgressNoteIn, db: Session = Depends(get_db),
                    user: User = Depends(require_writer)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    if not (payload.note or payload.confidence):
        raise HTTPException(status_code=400, detail="Note ou indice de confiance requis")
    year = payload.year or st.current_year_quarter()[0]
    pu = record_progress(db, squad, year, user, kind="review",
                         note=payload.note, confidence=payload.confidence)
    record_audit(db, user.id, "progress.review", entity="squad", entity_id=squad_id,
                 detail={"confidence": payload.confidence})
    db.commit()
    db.refresh(pu)
    return _point_out(pu, user.display_name)


def aggregate_review(db: Session, scope_tribe: int | None, since_days: int = 7,
                     year: int | None = None) -> list[ProgressReviewRow]:
    """Build the weekly-review rows for every squad in scope (None = all tribes).

    Shared by the API endpoint and the HTML/PPTX report generator.
    """
    cutoff = utcnow() - timedelta(days=since_days)
    year = year or st.current_year_quarter()[0]
    tribes = {t.id: t.name for t in db.scalars(select(Tribe)).all()}
    rows: list[ProgressReviewRow] = []

    for sq in db.scalars(select(Squad)).all():
        if scope_tribe and sq.tribe_id != scope_tribe:
            continue
        pts = db.scalars(
            select(ProgressUpdate).where(
                ProgressUpdate.squad_id == sq.id, ProgressUpdate.year == year
            ).order_by(ProgressUpdate.created_at.asc())
        ).all()

        latest = pts[-1] if pts else None
        in_period = [p for p in pts if _aware(p.created_at) and _aware(p.created_at) >= cutoff]
        before = [p for p in pts if _aware(p.created_at) and _aware(p.created_at) < cutoff]
        baseline = before[-1] if before else (pts[0] if pts else None)

        if latest is not None:
            progress_pct = latest.progress_pct
            blocked = latest.blocked_count
            at_risk = latest.at_risk_count
        else:
            m = compute_metrics(sq, year)
            progress_pct, blocked, at_risk = m["progress_pct"], m["blocked_count"], m["at_risk_count"]

        delta = (latest.progress_pct - baseline.progress_pct) if (latest and baseline) else 0

        changes: list = []
        for p in in_period:
            changes.extend(p.changes or [])

        note = None
        confidence = None
        for p in reversed(in_period):
            if note is None and p.note:
                note = p.note
            if confidence is None and p.confidence:
                confidence = p.confidence

        rows.append(ProgressReviewRow(
            squad_id=sq.id, squad_name=sq.name, tribe_id=sq.tribe_id,
            tribe_name=tribes.get(sq.tribe_id), progress_pct=progress_pct,
            progress_delta=delta, blocked_count=blocked, at_risk_count=at_risk,
            confidence=confidence, note=note,
            last_update_at=latest.created_at if latest else None,
            points_in_period=len(in_period), changes=changes,
        ))

    # Worst movers / most blocked first — most useful for the ceremony.
    rows.sort(key=lambda r: (-r.blocked_count, r.progress_delta, r.squad_name))
    return rows


@router.get("/api/progress/review", response_model=list[ProgressReviewRow],
            dependencies=[Depends(require_module("review"))])
def aggregated_review(since_days: int = Query(7, ge=1, le=365), tribe_id: int | None = None,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # The weekly ceremony is for leaders: admins see everything, tribe leaders
    # see their own tribe.
    if user.role == "admin":
        scope_tribe = tribe_id
    elif user.role == "tribe_leader":
        scope_tribe = user.tribe_id
    else:
        raise HTTPException(status_code=403, detail="Réservé aux tribe leaders et administrateurs")
    return aggregate_review(db, scope_tribe, since_days)


@router.post("/api/admin/progress/run-weekly")
def run_weekly(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    n = ensure_weekly(db)
    record_audit(db, admin.id, "progress.run_weekly", entity="progress", detail={"created": n})
    db.commit()
    return {"created": n}
