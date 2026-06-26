from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import (ADMIN, assert_tribe_scope, get_current_user, record_audit,
                    require_capability, require_module, require_org_editor, visible_tribe_id)
from ..models import OrgNode, Squad, Tribe, User
from ..schemas import OrgNodeCreate, OrgNodeTree, OrgNodeUpdate
from ..serializers import build_org_tree

router = APIRouter(prefix="/api/org", tags=["org"],
                   dependencies=[Depends(require_module("org")),
                                 Depends(require_capability("org"))])


def _squad_status_map(db: Session) -> dict[int, str]:
    cur_year, _ = st.current_year_quarter()
    return {s.id: st.squad_status(s, cur_year, None) for s in db.scalars(select(Squad)).all()}


def _resolve_tribe(user: User, requested: int | None, db: Session) -> int | None:
    # Anyone may VIEW any tribe's org chart. Default to the requested tribe,
    # else the user's own tribe, else the first tribe.
    if requested is not None:
        return requested
    if user.tribe_id is not None:
        return user.tribe_id
    first = db.scalar(select(Tribe).order_by(Tribe.display_order, Tribe.id))
    return first.id if first else None


@router.get("", response_model=list[OrgNodeTree])
def get_org(tribe_id: int | None = Query(default=None),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tid = _resolve_tribe(user, tribe_id, db)
    if tid is None:
        return []
    nodes = list(db.scalars(select(OrgNode).where(OrgNode.tribe_id == tid)).all())
    return build_org_tree(nodes, _squad_status_map(db))


@router.post("", response_model=OrgNodeTree, status_code=201)
def create_node(payload: OrgNodeCreate, db: Session = Depends(get_db), user: User = Depends(require_org_editor)):
    tid = payload.tribe_id if user.role == ADMIN else user.tribe_id
    if tid is None:
        raise HTTPException(status_code=400, detail="Tribe requise")
    assert_tribe_scope(user, tid)
    if payload.parent_id is not None:
        parent = db.get(OrgNode, payload.parent_id)
        if parent is None or parent.tribe_id != tid:
            raise HTTPException(status_code=400, detail="Nœud parent invalide")
    data = payload.model_dump()
    data["tribe_id"] = tid
    node = OrgNode(**data)
    db.add(node)
    db.flush()
    record_audit(db, user.id, "org.create", entity="org_node", entity_id=node.id, detail={"title": node.title})
    db.commit()
    db.refresh(node)
    return _single(node, db)


def _single(node: OrgNode, db: Session) -> OrgNodeTree:
    smap = _squad_status_map(db)
    return OrgNodeTree(
        id=node.id, parent_id=node.parent_id, title=node.title, person_name=node.person_name,
        squad_id=node.squad_id, squad_status=smap.get(node.squad_id) if node.squad_id else None,
        display_order=node.display_order, children=[],
    )


@router.put("/{node_id}", response_model=OrgNodeTree)
def update_node(node_id: int, payload: OrgNodeUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_org_editor)):
    node = db.get(OrgNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Nœud introuvable")
    assert_tribe_scope(user, node.tribe_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("parent_id") == node_id:
        raise HTTPException(status_code=400, detail="Un nœud ne peut pas être son propre parent")
    if data.get("parent_id") is not None:
        parent = db.get(OrgNode, data["parent_id"])
        if parent is None or parent.tribe_id != node.tribe_id:
            raise HTTPException(status_code=400, detail="Nœud parent invalide")
    for k, v in data.items():
        setattr(node, k, v)
    record_audit(db, user.id, "org.update", entity="org_node", entity_id=node.id, detail=data)
    db.commit()
    db.refresh(node)
    return _single(node, db)


@router.delete("/{node_id}", status_code=204)
def delete_node(node_id: int, db: Session = Depends(get_db), user: User = Depends(require_org_editor)):
    node = db.get(OrgNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Nœud introuvable")
    assert_tribe_scope(user, node.tribe_id)
    for child in db.scalars(select(OrgNode).where(OrgNode.parent_id == node_id)).all():
        child.parent_id = node.parent_id
    record_audit(db, user.id, "org.delete", entity="org_node", entity_id=node.id, detail={"title": node.title})
    db.delete(node)
    db.commit()
