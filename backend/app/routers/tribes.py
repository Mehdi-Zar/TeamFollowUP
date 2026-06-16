from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import get_current_user, record_audit, require_admin
from ..models import OrgNode, Squad, Tribe, User
from ..schemas import TribeCreate, TribeOrg, TribeOut, TribeUpdate
from ..serializers import build_org_tree

router = APIRouter(prefix="/api/tribes", tags=["tribes"])


@router.get("", response_model=list[TribeOut])
def list_tribes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # All authenticated users can see the list of tribes (e.g. to browse org charts).
    return list(db.scalars(select(Tribe).order_by(Tribe.display_order, Tribe.id)).all())


@router.get("/org-overview", response_model=list[TribeOrg])
def org_overview(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Read-only org charts of ALL tribes (one per tribe). Admin only."""
    cur_year, _ = st.current_year_quarter()
    squads = db.scalars(select(Squad)).all()
    status_map = {s.id: st.squad_status(s, cur_year, None) for s in squads}
    count_by_tribe: dict[int, int] = {}
    for s in squads:
        count_by_tribe[s.tribe_id] = count_by_tribe.get(s.tribe_id, 0) + 1
    nodes = list(db.scalars(select(OrgNode)).all())
    out = []
    for t in db.scalars(select(Tribe).order_by(Tribe.display_order, Tribe.id)).all():
        tribe_nodes = [n for n in nodes if n.tribe_id == t.id]
        out.append(TribeOrg(
            tribe_id=t.id, tribe_name=t.name,
            squads_count=count_by_tribe.get(t.id, 0),
            tree=build_org_tree(tribe_nodes, status_map),
        ))
    return out


@router.post("", response_model=TribeOut, status_code=201)
def create_tribe(payload: TribeCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    data = payload.model_dump()
    leader_user_id = data.pop("leader_user_id", None)
    tribe = Tribe(**data)
    db.add(tribe)
    db.flush()
    # Optionally promote a chosen user to tribe leader of this new tribe.
    if leader_user_id is not None:
        leader = db.get(User, leader_user_id)
        if leader is None:
            raise HTTPException(status_code=404, detail="Utilisateur (tribe leader) introuvable")
        if leader.is_break_glass:
            raise HTTPException(status_code=400, detail="Le compte de secours ne peut pas être tribe leader")
        leader.role = "tribe_leader"
        leader.tribe_id = tribe.id
    record_audit(db, admin.id, "tribe.create", entity="tribe", entity_id=tribe.id,
                 detail={"name": tribe.name, "leader_user_id": leader_user_id})
    db.commit()
    db.refresh(tribe)
    return tribe


@router.put("/{tribe_id}", response_model=TribeOut)
def update_tribe(tribe_id: int, payload: TribeUpdate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    from ..rbac import can_edit_tribe
    tribe = db.get(Tribe, tribe_id)
    if tribe is None:
        raise HTTPException(status_code=404, detail="Tribu introuvable")
    if not can_edit_tribe(user, tribe_id):
        raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que votre tribu")
    data = payload.model_dump(exclude_unset=True)
    # display_order is a global ordering concern → admin only.
    if "display_order" in data and user.role != "admin":
        data.pop("display_order")
    for k, v in data.items():
        setattr(tribe, k, v)
    record_audit(db, user.id, "tribe.update", entity="tribe", entity_id=tribe.id)
    db.commit()
    db.refresh(tribe)
    return tribe


@router.delete("/{tribe_id}", status_code=204)
def delete_tribe(tribe_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    tribe = db.get(Tribe, tribe_id)
    if tribe is None:
        raise HTTPException(status_code=404, detail="Tribu introuvable")
    if db.scalar(select(Squad).where(Squad.tribe_id == tribe_id)) is not None:
        raise HTTPException(status_code=409, detail="Supprimez ou déplacez d'abord les squads de cette tribu")
    # detach users and clean org/feed of this tribe
    for u in db.scalars(select(User).where(User.tribe_id == tribe_id)).all():
        u.tribe_id = None
    for n in db.scalars(select(OrgNode).where(OrgNode.tribe_id == tribe_id)).all():
        db.delete(n)
    record_audit(db, admin.id, "tribe.delete", entity="tribe", entity_id=tribe.id, detail={"name": tribe.name})
    db.delete(tribe)
    db.commit()
