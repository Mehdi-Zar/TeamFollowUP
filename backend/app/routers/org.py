"""Org-chart (organigramme) CRUD endpoints.

Manages the tree of OrgNode rows that make up a tribe's org chart. Reads are open
to any authenticated user (anyone may view any tribe's chart); writes require the
"org editor" role and stay within the caller's own tribe (admins may target any
tribe). The whole router is gated by the `org` module toggle and the `org`
persona capability.
"""
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
    """Map every squad id to its current-year RAG status, used to colour the nodes
    that are linked to a squad. Computed once per request to avoid N+1 lookups."""
    cur_year, _ = st.current_year_quarter()
    return {s.id: st.squad_status(s, cur_year, None) for s in db.scalars(select(Squad)).all()}


def _resolve_tribe(user: User, requested: int | None, db: Session) -> int | None:
    """Pick which tribe's chart to show. Also reused by the export router.

    Anyone may VIEW any tribe's org chart, so an explicit `requested` id wins;
    otherwise fall back to the user's own tribe, then to the first tribe by order.
    Returns None when there is no tribe at all.
    """
    if requested is not None:
        return requested
    if user.tribe_id is not None:
        return user.tribe_id
    first = db.scalar(select(Tribe).order_by(Tribe.display_order, Tribe.id))
    return first.id if first else None


@router.get("", response_model=list[OrgNodeTree])
def get_org(tribe_id: int | None = Query(default=None),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Return a tribe's org chart as a nested tree.

    GET /api/org?tribe_id=...
    Access: any authenticated user (viewing is unrestricted). Defaults the tribe
    via _resolve_tribe; returns an empty list when no tribe exists.
    """
    tid = _resolve_tribe(user, tribe_id, db)
    if tid is None:
        return []
    nodes = list(db.scalars(select(OrgNode).where(OrgNode.tribe_id == tid)).all())
    return build_org_tree(nodes, _squad_status_map(db))


@router.post("", response_model=OrgNodeTree, status_code=201)
def create_node(payload: OrgNodeCreate, db: Session = Depends(get_db), user: User = Depends(require_org_editor)):
    """Create an org-chart node.

    POST /api/org
    Access: org editor. Admins may target any tribe (payload.tribe_id); every other
    editor is forced onto their own tribe. assert_tribe_scope re-checks the result.
    Business rules: a parent, when given, must belong to the same tribe.
    Side effects: writes an "org.create" audit entry.
    """
    # Admins choose the target tribe; non-admin editors are pinned to their own.
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
    """Serialize one node (no children) into the tree schema, used by the create/
    update responses so the client gets the same shape as the full-tree read."""
    smap = _squad_status_map(db)
    return OrgNodeTree(
        id=node.id, parent_id=node.parent_id, title=node.title, person_name=node.person_name,
        squad_id=node.squad_id, squad_status=smap.get(node.squad_id) if node.squad_id else None,
        display_order=node.display_order, children=[],
    )


@router.put("/{node_id}", response_model=OrgNodeTree)
def update_node(node_id: int, payload: OrgNodeUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_org_editor)):
    """Partially update an org-chart node.

    PUT /api/org/{node_id}
    Access: org editor scoped to the node's tribe (assert_tribe_scope).
    Business rules: a node cannot be its own parent, and a new parent must be in
    the same tribe. Side effects: writes an "org.update" audit entry.
    """
    node = db.get(OrgNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Nœud introuvable")
    assert_tribe_scope(user, node.tribe_id)
    data = payload.model_dump(exclude_unset=True)
    # Guard against making a node its own parent (would create a broken cycle).
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
    """Delete an org-chart node, re-parenting its children.

    DELETE /api/org/{node_id} -> 204 No Content
    Access: org editor scoped to the node's tribe (assert_tribe_scope).
    Business rules: children are re-attached to the deleted node's parent so the
    tree stays connected. Side effects: writes an "org.delete" audit entry.
    """
    node = db.get(OrgNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Nœud introuvable")
    assert_tribe_scope(user, node.tribe_id)
    # Re-parent orphans onto the deleted node's parent instead of cascading.
    for child in db.scalars(select(OrgNode).where(OrgNode.parent_id == node_id)).all():
        child.parent_id = node.parent_id
    record_audit(db, user.id, "org.delete", entity="org_node", entity_id=node.id, detail={"title": node.title})
    db.delete(node)
    db.commit()
