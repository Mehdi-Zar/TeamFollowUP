from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_can_edit_squad, record_audit, require_writer
from ..models import Member, Squad, User
from ..schemas import MemberCreate, MemberOut, MemberUpdate

router = APIRouter(prefix="/api/members", tags=["members"])


@router.post("", response_model=MemberOut, status_code=201)
def create_member(payload: MemberCreate, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    if db.get(Squad, payload.squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, payload.squad_id)
    member = Member(**payload.model_dump())
    db.add(member)
    db.flush()
    record_audit(db, user.id, "member.create", entity="member", entity_id=member.id,
                 detail={"squad_id": member.squad_id, "full_name": member.full_name})
    db.commit()
    db.refresh(member)
    return member


@router.put("/{member_id}", response_model=MemberOut)
def update_member(member_id: int, payload: MemberUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_writer)):
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    assert_can_edit_squad(db, user, member.squad_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(member, k, v)
    record_audit(db, user.id, "member.update", entity="member", entity_id=member.id, detail=data)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{member_id}", status_code=204)
def delete_member(member_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    assert_can_edit_squad(db, user, member.squad_id)
    record_audit(db, user.id, "member.delete", entity="member", entity_id=member.id,
                 detail={"squad_id": member.squad_id})
    db.delete(member)
    db.commit()
