from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import assert_can_edit_squad, get_current_user, record_audit, require_writer
from ..models import ReportSnapshot, Squad, User, utcnow
from ..schemas import SnapshotMeta, SnapshotOut, SubmitCycleIn

router = APIRouter(prefix="/api/squads/{squad_id}/snapshots", tags=["snapshots"])


def build_payload(squad: Squad, year: int) -> dict:
    progress = st.year_progress(squad, year)
    comments = st.quarter_comments(squad, year)
    return {
        "year": year,
        "objectives": [
            {"id": o.id, "title": o.title, "rag_status": o.rag_status, "weight": o.weight,
             "is_active": o.is_active, "target_date": o.target_date.isoformat() if o.target_date else None}
            for o in sorted(squad.objectives, key=lambda x: x.id) if o.year == year
        ],
        "roadmap_items": [
            {"id": r.id, "title": r.title, "quarter": r.quarter, "status": r.status}
            for r in sorted(squad.roadmap_items, key=lambda x: (x.quarter, x.display_order, x.id))
            if r.year == year
        ],
        "quarter_progress": {str(q): {"progress_pct": progress[q], "comment": comments[q]} for q in (1, 2, 3, 4)},
        "kpis": [
            {"id": k.id, "name": k.name, "unit": k.unit,
             "current_value": float(k.current_value) if k.current_value is not None else None,
             "target_value": float(k.target_value) if k.target_value is not None else None,
             "trend_status": k.trend_status, "comment": k.comment}
            for k in sorted(squad.kpis, key=lambda x: x.id)
        ],
    }


@router.post("", response_model=SnapshotOut, status_code=201)
def submit_cycle(squad_id: int, payload: SubmitCycleIn, db: Session = Depends(get_db),
                 user: User = Depends(require_writer)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    year = payload.year or st.current_year_quarter()[0]

    existing = db.scalars(select(ReportSnapshot).where(ReportSnapshot.squad_id == squad_id)).all()
    label = payload.cycle_label or f"Soumission {len(existing) + 1}"

    snap = ReportSnapshot(
        squad_id=squad_id, submitted_by_user_id=user.id, submitted_at=utcnow(),
        payload=build_payload(squad, year), cycle_label=label,
    )
    db.add(snap)
    db.flush()
    record_audit(db, user.id, "cycle.submit", entity="snapshot", entity_id=snap.id,
                 detail={"squad_id": squad_id, "year": year, "cycle_label": label})
    db.commit()
    db.refresh(snap)
    return snap


@router.get("", response_model=list[SnapshotMeta])
def list_snapshots(squad_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.get(Squad, squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    snaps = db.scalars(
        select(ReportSnapshot).where(ReportSnapshot.squad_id == squad_id)
        .order_by(ReportSnapshot.submitted_at.desc())
    ).all()
    return list(snaps)


@router.get("/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(squad_id: int, snapshot_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    snap = db.get(ReportSnapshot, snapshot_id)
    if snap is None or snap.squad_id != squad_id:
        raise HTTPException(status_code=404, detail="Snapshot introuvable")
    return snap


@router.get("/{snapshot_id}/compare", response_model=dict)
def compare_to_previous(squad_id: int, snapshot_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    snap = db.get(ReportSnapshot, snapshot_id)
    if snap is None or snap.squad_id != squad_id:
        raise HTTPException(status_code=404, detail="Snapshot introuvable")
    previous = db.scalars(
        select(ReportSnapshot)
        .where(ReportSnapshot.squad_id == squad_id, ReportSnapshot.submitted_at < snap.submitted_at)
        .order_by(ReportSnapshot.submitted_at.desc())
    ).first()
    return {
        "current": SnapshotOut.model_validate(snap).model_dump(),
        "previous": SnapshotOut.model_validate(previous).model_dump() if previous else None,
        "diff": _diff(previous.payload if previous else None, snap.payload),
    }


def _index(items):
    return {it["id"]: it for it in (items or [])}


def _diff(prev: dict | None, cur: dict) -> dict:
    result = {}
    for section in ("objectives", "roadmap_items", "kpis"):
        prev_idx = _index((prev or {}).get(section, []))
        cur_idx = _index(cur.get(section, []))
        changes = []
        for cid, citem in cur_idx.items():
            pitem = prev_idx.get(cid)
            if pitem is None:
                changes.append({"id": cid, "type": "added", "item": citem})
            else:
                fields = {k: {"from": pitem.get(k), "to": v} for k, v in citem.items() if pitem.get(k) != v}
                if fields:
                    changes.append({"id": cid, "type": "changed", "fields": fields, "item": citem})
        for pid, pitem in prev_idx.items():
            if pid not in cur_idx:
                changes.append({"id": pid, "type": "removed", "item": pitem})
        result[section] = changes
    return result
