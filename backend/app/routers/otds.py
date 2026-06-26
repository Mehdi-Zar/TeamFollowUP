"""OTD (On-Time Delivery / budget) commitments, fixed by the tribe leader / admin.

An OTD groups milestones (set from here, never from the milestone editor) and
carries a single committed date. Its on-time status is derived from its milestones.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import status as st
from ..database import get_db
from ..deps import (assert_can_manage_tribe_reporting, record_audit, require_tribe_or_admin)
from ..models import Otd, RoadmapItem, Squad, Tribe, User
from ..schemas import OtdCreate, OtdMembers, OtdOut, OtdUpdate

router = APIRouter(prefix="/api/otds", tags=["otds"])


def _scope_tribe(user: User, tribe_id: int | None) -> int | None:
    return tribe_id if user.role == "admin" else user.tribe_id


def _jalon_brief(j) -> dict:
    return {"id": j.id, "title": j.title, "quarter": j.quarter, "stage": j.release_stage,
            "status": j.status, "squad_id": j.squad_id, "squad_name": j.squad.name if j.squad else ""}


def _otd_payload(otd: Otd) -> dict:
    jalons = sorted(otd.roadmap_items, key=lambda x: (x.squad_id, x.quarter, x.id))
    return {
        **OtdOut.model_validate(otd).model_dump(),
        "owner_name": otd.owner.display_name if otd.owner else None,
        "status": st.otd_status(jalons, otd.committed_date),
        "counts": {"total": len(jalons),
                   "done": sum(1 for j in jalons if j.status == "done"),
                   "blocked": sum(1 for j in jalons if j.status == "blocked"),
                   "at_risk": sum(1 for j in jalons if j.status == "at_risk")},
        "jalons": [_jalon_brief(j) for j in jalons],
    }


@router.get("/candidate-jalons")
def candidate_jalons(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(require_tribe_or_admin)):
    """Milestones of the scope's squads, for assigning them to an OTD."""
    year = year or st.current_year_quarter()[0]
    scope = _scope_tribe(user, tribe_id)
    q = (select(RoadmapItem).join(Squad, Squad.id == RoadmapItem.squad_id)
         .where(RoadmapItem.year == year)
         .order_by(Squad.display_order, RoadmapItem.quarter, RoadmapItem.id))
    if scope is not None:
        q = q.where(Squad.tribe_id == scope)
    return [{"id": j.id, "title": j.title, "quarter": j.quarter, "theme": j.theme,
             "squad_id": j.squad_id, "squad_name": j.squad.name if j.squad else "",
             "otd_id": j.otd_id} for j in db.scalars(q).all()]


@router.get("")
def list_otds(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
              db: Session = Depends(get_db), user: User = Depends(require_tribe_or_admin)):
    """OTDs in scope with their derived on-time status and member milestones."""
    year = year or st.current_year_quarter()[0]
    scope = _scope_tribe(user, tribe_id)
    q = (select(Otd).where(Otd.year == year).order_by(Otd.display_order, Otd.id)
         .options(selectinload(Otd.roadmap_items)))
    if scope is not None:
        q = q.where(Otd.tribe_id == scope)
    return [_otd_payload(o) for o in db.scalars(q).all()]


@router.post("", status_code=201)
def create_otd(payload: OtdCreate, db: Session = Depends(get_db),
               user: User = Depends(require_tribe_or_admin)):
    if db.get(Tribe, payload.tribe_id) is None:
        raise HTTPException(status_code=404, detail="Tribe introuvable")
    assert_can_manage_tribe_reporting(user, payload.tribe_id)
    otd = Otd(**payload.model_dump())
    db.add(otd)
    db.flush()
    record_audit(db, user.id, "otd.create", entity="otd", entity_id=otd.id,
                 detail={"tribe_id": otd.tribe_id, "title": otd.title})
    db.commit()
    db.refresh(otd)
    return _otd_payload(otd)


@router.put("/{otd_id}")
def update_otd(otd_id: int, payload: OtdUpdate, db: Session = Depends(get_db),
               user: User = Depends(require_tribe_or_admin)):
    otd = db.get(Otd, otd_id)
    if otd is None:
        raise HTTPException(status_code=404, detail="OTD introuvable")
    assert_can_manage_tribe_reporting(user, otd.tribe_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(otd, k, v)
    record_audit(db, user.id, "otd.update", entity="otd", entity_id=otd.id, detail=list(data.keys()))
    db.commit()
    db.refresh(otd)
    return _otd_payload(otd)


@router.put("/{otd_id}/jalons")
def set_otd_jalons(otd_id: int, payload: OtdMembers, db: Session = Depends(get_db),
                   user: User = Depends(require_tribe_or_admin)):
    """Set the milestones that make up this OTD (replaces the current set). Only
    milestones from the OTD's tribe are accepted; this is the only place the
    milestone<->OTD link is managed (squad leaders never touch it)."""
    otd = db.get(Otd, otd_id)
    if otd is None:
        raise HTTPException(status_code=404, detail="OTD introuvable")
    assert_can_manage_tribe_reporting(user, otd.tribe_id)
    wanted = set(payload.jalon_ids)
    # Validate every requested milestone belongs to a squad of this OTD's tribe.
    if wanted:
        rows = db.execute(
            select(RoadmapItem).join(Squad, Squad.id == RoadmapItem.squad_id)
            .where(RoadmapItem.id.in_(wanted), Squad.tribe_id == otd.tribe_id)
        ).scalars().all()
        if len(rows) != len(wanted):
            raise HTTPException(status_code=400, detail="Un jalon n'appartient pas à cette tribe")
    # Clear the previous set, then assign the new one.
    for j in list(otd.roadmap_items):
        j.otd_id = None
    for j in db.scalars(select(RoadmapItem).where(RoadmapItem.id.in_(wanted))).all() if wanted else []:
        j.otd_id = otd.id
    record_audit(db, user.id, "otd.set_jalons", entity="otd", entity_id=otd.id,
                 detail={"jalon_ids": sorted(wanted)})
    db.commit()
    db.refresh(otd)
    return _otd_payload(otd)


@router.delete("/{otd_id}", status_code=204)
def delete_otd(otd_id: int, db: Session = Depends(get_db),
               user: User = Depends(require_tribe_or_admin)):
    otd = db.get(Otd, otd_id)
    if otd is None:
        raise HTTPException(status_code=404, detail="OTD introuvable")
    assert_can_manage_tribe_reporting(user, otd.tribe_id)
    record_audit(db, user.id, "otd.delete", entity="otd", entity_id=otd.id,
                 detail={"tribe_id": otd.tribe_id})
    db.delete(otd)  # milestones keep existing; their otd_id is set NULL
    db.commit()
