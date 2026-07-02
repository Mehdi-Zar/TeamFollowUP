"""Squad governance meetings ("comitologie").

A squad leader declares the recurring committees their squad runs; the tribe
leader (and admin) get read/edit oversight. Standing entities (not year-scoped).
Gated by the optional `committees` module.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_can_edit_squad, record_audit, require_module, require_writer
from ..models import Committee, Squad, User
from ..schemas import CommitteeCreate, CommitteeOut, CommitteeUpdate

router = APIRouter(prefix="/api/committees", tags=["committees"],
                   dependencies=[Depends(require_module("committees"))])


@router.post("", response_model=CommitteeOut, status_code=201)
def create_committee(payload: CommitteeCreate, db: Session = Depends(get_db),
                     user: User = Depends(require_writer)):
    if db.get(Squad, payload.squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, payload.squad_id)
    item = Committee(**payload.model_dump(), created_by_user_id=user.id)
    db.add(item)
    db.flush()
    record_audit(db, user.id, "committee.create", entity="committee", entity_id=item.id,
                 detail={"squad_id": item.squad_id, "name": item.name})
    db.commit()
    db.refresh(item)
    return item


@router.put("/{committee_id}", response_model=CommitteeOut)
def update_committee(committee_id: int, payload: CommitteeUpdate, db: Session = Depends(get_db),
                     user: User = Depends(require_writer)):
    item = db.get(Committee, committee_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Comité introuvable")
    assert_can_edit_squad(db, user, item.squad_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(item, k, v)
    record_audit(db, user.id, "committee.update", entity="committee", entity_id=item.id, detail=data)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{committee_id}", status_code=204)
def delete_committee(committee_id: int, db: Session = Depends(get_db),
                     user: User = Depends(require_writer)):
    item = db.get(Committee, committee_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Comité introuvable")
    assert_can_edit_squad(db, user, item.squad_id)
    record_audit(db, user.id, "committee.delete", entity="committee", entity_id=item.id,
                 detail={"squad_id": item.squad_id})
    db.delete(item)
    db.commit()
