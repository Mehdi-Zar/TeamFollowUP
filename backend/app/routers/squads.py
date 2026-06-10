from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import (
    ADMIN,
    TRIBE,
    assert_can_edit_squad,
    assert_tribe_scope,
    get_current_user,
    get_threshold,
    record_audit,
    require_tribe_or_admin,
    visible_tribe_id,
)
from ..models import FeedPost, OrgNode, QuarterProgress, Squad, User
from ..progress import capture_progress
from ..schemas import (
    QuarterProgressIn,
    QuarterProgressOut,
    SquadCreate,
    SquadDetail,
    SquadOut,
    SquadUpdate,
)
from ..serializers import squad_detail

router = APIRouter(prefix="/api/squads", tags=["squads"])


@router.get("", response_model=list[SquadOut])
def list_squads(tribe_id: int | None = Query(default=None),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(Squad).order_by(Squad.display_order, Squad.id)
    scope = visible_tribe_id(user)
    if scope is not None:
        q = q.where(Squad.tribe_id == scope)
    elif tribe_id is not None:
        q = q.where(Squad.tribe_id == tribe_id)
    return list(db.scalars(q).all())


@router.get("/{squad_id}", response_model=SquadDetail)
def get_squad(squad_id: int, year: int | None = Query(default=None),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    if year is None:
        year = st.current_year_quarter()[0]
    return squad_detail(squad, year, get_threshold(db))


@router.post("", response_model=SquadOut, status_code=201)
def create_squad(payload: SquadCreate, db: Session = Depends(get_db), user: User = Depends(require_tribe_or_admin)):
    # tribe leaders can only create squads in their own tribe
    tribe_id = payload.tribe_id if user.role == ADMIN else user.tribe_id
    if tribe_id is None:
        raise HTTPException(status_code=400, detail="Tribu requise")
    assert_tribe_scope(user, tribe_id)
    data = payload.model_dump()
    data["tribe_id"] = tribe_id
    squad = Squad(**data)
    db.add(squad)
    db.flush()
    record_audit(db, user.id, "squad.create", entity="squad", entity_id=squad.id, detail={"name": squad.name})
    db.commit()
    db.refresh(squad)
    return squad


@router.put("/{squad_id}", response_model=SquadOut)
def update_squad(squad_id: int, payload: SquadUpdate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    data = payload.model_dump(exclude_unset=True)
    if "tribe_id" in data and user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Seul l'administrateur peut déplacer une squad de tribu")
    structural = {"leader_user_id", "display_order"}
    if user.role not in (ADMIN, TRIBE):
        assert_can_edit_squad(db, user, squad_id)
        if structural & data.keys():
            raise HTTPException(status_code=403, detail="Champs structurels réservés au tribe leader")
    for k, v in data.items():
        setattr(squad, k, v)
    record_audit(db, user.id, "squad.update", entity="squad", entity_id=squad.id, detail=data)
    db.commit()
    db.refresh(squad)
    return squad


@router.delete("/{squad_id}", status_code=204)
def delete_squad(squad_id: int, db: Session = Depends(get_db), user: User = Depends(require_tribe_or_admin)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    # Detach references not owned by the squad (keep the org boxes and feed posts).
    for node in db.scalars(select(OrgNode).where(OrgNode.squad_id == squad_id)).all():
        node.squad_id = None
    for post in db.scalars(select(FeedPost).where(FeedPost.squad_id == squad_id)).all():
        post.squad_id = None
    record_audit(db, user.id, "squad.delete", entity="squad", entity_id=squad.id, detail={"name": squad.name})
    db.delete(squad)
    db.commit()


@router.put("/{squad_id}/quarter-progress", response_model=QuarterProgressOut)
def set_quarter_progress(squad_id: int, payload: QuarterProgressIn, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    row = db.scalar(
        select(QuarterProgress).where(
            QuarterProgress.squad_id == squad_id,
            QuarterProgress.year == payload.year,
            QuarterProgress.quarter == payload.quarter,
        )
    )
    if row is None:
        row = QuarterProgress(squad_id=squad_id, year=payload.year, quarter=payload.quarter,
                              progress_pct=payload.progress_pct, comment=payload.comment)
        db.add(row)
    else:
        row.progress_pct = payload.progress_pct
        row.comment = payload.comment
    record_audit(db, user.id, "quarter_progress.set", entity="squad", entity_id=squad_id,
                 detail={"year": payload.year, "quarter": payload.quarter, "progress_pct": payload.progress_pct})
    capture_progress(db, squad_id, payload.year, user)
    db.commit()
    db.refresh(row)
    return row
