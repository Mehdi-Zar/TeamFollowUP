"""OTD (On-Time Delivery / budget) commitments, fixed by the tribe leader / admin.

An OTD groups milestones (set from here, never from the milestone editor) and
carries a single committed date. Its on-time status is derived from its milestones.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .. import status as st
from ..database import get_db
from ..deps import (ADMIN, SQUAD, TRIBE, assert_can_manage_tribe_reporting,
                    get_current_user, record_audit, require_tribe_or_admin)
from ..models import Otd, RoadmapItem, Squad, Tribe, User
from ..schemas import OtdCreate, OtdMembers, OtdOut, OtdUpdate

router = APIRouter(prefix="/api/otds", tags=["otds"])


def _scope_tribe(user: User, tribe_id: int | None) -> int | None:
    """Resolve which tribe to read: admins may pass any ``tribe_id``; others are
    pinned to their own tribe."""
    return tribe_id if user.role == "admin" else user.tribe_id


def _jalon_brief(j) -> dict:
    """Compact milestone view embedded in an OTD payload."""
    return {"id": j.id, "title": j.title, "quarter": j.quarter, "stage": j.release_stage,
            "status": j.status, "squad_id": j.squad_id, "squad_name": j.squad.name if j.squad else ""}


def _otd_payload(otd: Otd) -> dict:
    """Serialize an OTD with its derived on-time status, member-milestone counts,
    and the milestone briefs. The status is computed from the milestones and the
    committed date (``st.otd_status``), not stored."""
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
    """GET /api/otds/candidate-jalons — milestones of the scope's squads, for
    assigning them to an OTD. Tribe leader or admin.

    Scope: an admin may target any ``tribe_id``; a tribe leader is pinned to their
    tribe. Each row carries its current ``otd_id`` so the UI can show what is
    already assigned. ``year`` defaults to current."""
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
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """OTDs with their derived on-time status and member milestones.

    Visibility (rule #4): managed by the tribe leader (or admin); a squad leader
    sees ONLY the OTDs that include a milestone of a squad they lead; anyone else
    sees none.
    """
    year = year or st.current_year_quarter()[0]
    q = (select(Otd).where(Otd.year == year).order_by(Otd.display_order, Otd.id)
         .options(selectinload(Otd.roadmap_items)))
    if user.role == ADMIN:
        if tribe_id is not None:
            q = q.where(Otd.tribe_id == tribe_id)
    elif user.role == TRIBE:
        q = q.where(Otd.tribe_id == user.tribe_id)
    elif user.role == SQUAD:
        # A squad leader sees the OTDs assigned to them (owner_user_id), plus any
        # that group a milestone of a squad they lead.
        led_squads = select(Squad.id).where(Squad.leader_user_id == user.id)
        concerned = (select(RoadmapItem.otd_id)
                     .where(RoadmapItem.squad_id.in_(led_squads), RoadmapItem.otd_id.is_not(None)))
        q = q.where(or_(Otd.owner_user_id == user.id, Otd.id.in_(concerned)))
    else:
        return []  # members and custom personas do not see OTDs
    return [_otd_payload(o) for o in db.scalars(q).all()]


def _validate_owner(db: Session, tribe_id: int, owner_user_id: int | None) -> None:
    """The assigned owner must be a squad leader of THIS OTD's tribe. Without this
    a tribe leader could assign a squad leader of another tribe, who would then
    see this tribe's OTD (title, committed date, budget ref, milestones) via the
    owner-based visibility rule - a cross-tribe disclosure."""
    if owner_user_id is None:
        return
    owner = db.get(User, owner_user_id)
    if owner is None or owner.role != SQUAD or owner.tribe_id != tribe_id:
        raise HTTPException(status_code=400,
                            detail="L'owner doit être un squad leader de cette tribe")


@router.post("", status_code=201)
def create_otd(payload: OtdCreate, db: Session = Depends(get_db),
               user: User = Depends(require_tribe_or_admin)):
    """POST /api/otds — create an OTD (201). Tribe leader or admin.

    Requires ``assert_can_manage_tribe_reporting`` for the target tribe (404 if
    unknown). Any assigned owner must be a squad leader of that tribe
    (``_validate_owner``, a cross-tribe-disclosure guard). Audited."""
    if db.get(Tribe, payload.tribe_id) is None:
        raise HTTPException(status_code=404, detail="Tribe introuvable")
    assert_can_manage_tribe_reporting(user, payload.tribe_id)
    _validate_owner(db, payload.tribe_id, payload.owner_user_id)
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
    """PUT /api/otds/{otd_id} — update an OTD. Tribe leader or admin.

    Requires ``assert_can_manage_tribe_reporting`` for the OTD's tribe; a changed
    owner is re-validated (``_validate_owner``). Audited."""
    otd = db.get(Otd, otd_id)
    if otd is None:
        raise HTTPException(status_code=404, detail="OTD introuvable")
    assert_can_manage_tribe_reporting(user, otd.tribe_id)
    data = payload.model_dump(exclude_unset=True)
    if "owner_user_id" in data:
        _validate_owner(db, otd.tribe_id, data["owner_user_id"])
    for k, v in data.items():
        setattr(otd, k, v)
    record_audit(db, user.id, "otd.update", entity="otd", entity_id=otd.id, detail=list(data.keys()))
    db.commit()
    db.refresh(otd)
    return _otd_payload(otd)


@router.put("/{otd_id}/jalons")
def set_otd_jalons(otd_id: int, payload: OtdMembers, db: Session = Depends(get_db),
                   user: User = Depends(require_tribe_or_admin)):
    """PUT /api/otds/{otd_id}/jalons — set the milestones that make up this OTD
    (replaces the current set). Tribe leader or admin.

    Requires ``assert_can_manage_tribe_reporting``. Only milestones from the OTD's
    tribe are accepted (400 otherwise); this is the ONLY place the milestone<->OTD
    link is managed (squad leaders never touch it). Audited."""
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
    """DELETE /api/otds/{otd_id} — delete an OTD (204). Tribe leader or admin,
    requires ``assert_can_manage_tribe_reporting``.

    Side effect: member milestones keep existing; only their ``otd_id`` link is
    cleared. Audited."""
    otd = db.get(Otd, otd_id)
    if otd is None:
        raise HTTPException(status_code=404, detail="OTD introuvable")
    assert_can_manage_tribe_reporting(user, otd.tribe_id)
    record_audit(db, user.id, "otd.delete", entity="otd", entity_id=otd.id,
                 detail={"tribe_id": otd.tribe_id})
    db.delete(otd)  # milestones keep existing; their otd_id is set NULL
    db.commit()
