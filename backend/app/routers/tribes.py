"""Tribe endpoints (prefix ``/api/tribes``).

A tribe is the top-level org unit; each tribe owns squads, users, and an org
chart. This router covers listing tribes, the admin-only cross-tribe org
overview, and tribe CRUD.

Access model: listing is open to any authenticated user; the org overview and
create/delete are admin-only (``require_admin``); update is allowed for the
tribe's own leader (``can_edit_tribe``) with global-ordering fields reserved to
admins. Mutations are audited.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import get_current_user, record_audit, require_admin, update_data
from ..models import ApiKey, FeedPost, Initiative, Leave, OrgNode, Otd, RoadmapItem, Squad, Tribe, User
from ..schemas import TribeCreate, TribeOrg, TribeOut, TribeUpdate
from ..serializers import build_org_tree

router = APIRouter(prefix="/api/tribes", tags=["tribes"])


@router.get("", response_model=list[TribeOut])
def list_tribes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/tribes: list all tribes, ordered. Any authenticated user."""
    # All authenticated users can see the list of tribes (e.g. to browse org charts).
    from sqlalchemy import func
    counts = dict(db.execute(select(Squad.tribe_id, func.count(Squad.id)).group_by(Squad.tribe_id)).all())
    leaders: dict[int, list[str]] = {}
    for u in db.scalars(select(User).where(User.role == "tribe_leader").order_by(User.display_name)).all():
        if u.tribe_id is not None:
            leaders.setdefault(u.tribe_id, []).append(u.display_name)
    out = []
    for t in db.scalars(select(Tribe).order_by(Tribe.display_order, Tribe.id)).all():
        row = TribeOut.model_validate(t)
        row.squads_count = counts.get(t.id, 0)
        row.leaders = leaders.get(t.id, [])
        out.append(row)
    return out


@router.get("/org-overview", response_model=list[TribeOrg])
def org_overview(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/tribes/org-overview: read-only org charts of ALL tribes (one per
    tribe). Admin only.

    Builds a per-squad status map for the current year and a per-tribe squad count,
    then assembles each tribe's org tree from its ``OrgNode`` rows."""
    # The instance's year (as the Organisation page), and the milestones loaded
    # in one query instead of one per squad.
    from ..generalconfig import reference_year
    from sqlalchemy.orm import selectinload
    cur_year = reference_year(db)
    squads = db.scalars(select(Squad).options(selectinload(Squad.roadmap_items))).all()
    from .org import _with_unreported
    status_map = _with_unreported(db, {s.id: st.squad_status(s, cur_year, None) for s in squads})
    count_by_tribe: dict[int, int] = {}
    for s in squads:
        count_by_tribe[s.tribe_id] = count_by_tribe.get(s.tribe_id, 0) + 1
    nodes = list(db.scalars(select(OrgNode)).all())
    out = []
    tq = select(Tribe).order_by(Tribe.display_order, Tribe.id)
    if admin.role != "admin":  # a delegate of the Tribes tab: their own tribe only
        tq = tq.where(Tribe.id == admin.tribe_id)
    for t in db.scalars(tq).all():
        tribe_nodes = [n for n in nodes if n.tribe_id == t.id]
        out.append(TribeOrg(
            tribe_id=t.id, tribe_name=t.name,
            squads_count=count_by_tribe.get(t.id, 0),
            tree=build_org_tree(tribe_nodes, status_map),
        ))
    return out


@router.post("", response_model=TribeOut, status_code=201)
def create_tribe(payload: TribeCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """POST /api/tribes: create a tribe (201). Admin only.

    Optional ``leader_user_id`` promotes an existing user to tribe leader of the
    new tribe (404 if unknown; the break-glass account cannot be made a tribe
    leader). Audited."""
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
        # An administrator stays one (the role is not lowered), and the leader of
        # another tribe is not moved away from it without a word.
        if leader.role == "admin":
            raise HTTPException(status_code=400, detail="Un administrateur ne peut pas être nommé tribe leader")
        if leader.role == "tribe_leader" and leader.tribe_id not in (None, tribe.id):
            raise HTTPException(status_code=400, detail=f"{leader.display_name} est déjà tribe leader d'une autre tribe")
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
    """PUT /api/tribes/{tribe_id}: update a tribe.

    Allowed for an admin or the tribe's own leader (``can_edit_tribe``); 403
    otherwise. ``display_order`` is a global ordering concern, so it is dropped
    from the payload for non-admins. Audited."""
    from ..rbac import can_edit_tribe
    from ..tabaccess import acting_manager
    tribe = db.get(Tribe, tribe_id)
    if tribe is None:
        raise HTTPException(status_code=404, detail="Tribe introuvable")
    # "Tribes" edits every tribe; "My tribe" one's own, as its tribe leader.
    # A delegate (either tab) edits their own tribe only.
    from ..tabaccess import has_tab
    if user.role != "admin":
        if not has_tab(db, user, "tribes"):
            user = acting_manager(db, user, "tribe")
        if user.tribe_id != tribe_id or not (has_tab(db, user, "tribes") or can_edit_tribe(user, tribe_id)):
            raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que votre tribe")
    data = update_data(payload, Tribe)
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
    """DELETE /api/tribes/{tribe_id}: delete a tribe (204). Admin only.

    Refuses with 409 while the tribe still has squads, initiatives or OTDs (they
    must be moved or deleted first: that is content, not bookkeeping). Side
    effects: users and leaves of the tribe are detached (``tribe_id`` cleared),
    other tribes' milestones that depended on it keep the dependency as free text,
    and the tribe's org-chart nodes, feed posts and API keys are deleted. A post
    or a key left without a tribe would read as global, hence deleted. Audited."""
    tribe = db.get(Tribe, tribe_id)
    if tribe is None:
        raise HTTPException(status_code=404, detail="Tribe introuvable")
    if admin.role != "admin" and tribe_id != admin.tribe_id:  # a delegate: their own tribe only
        raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que votre tribe")
    if db.scalar(select(Squad).where(Squad.tribe_id == tribe_id)) is not None:
        raise HTTPException(status_code=409, detail="Supprimez ou déplacez d'abord les squads de cette tribe")
    if db.scalar(select(Initiative.id).where(Initiative.tribe_id == tribe_id)) is not None:
        raise HTTPException(status_code=409, detail="Supprimez d'abord les initiatives de cette tribe")
    if db.scalar(select(Otd.id).where(Otd.tribe_id == tribe_id)) is not None:
        raise HTTPException(status_code=409, detail="Supprimez d'abord les OTD de cette tribe")
    # detach users and leaves, clean org/feed/keys of this tribe. Its tribe
    # leaders become members: a tribe leader without a tribe had nothing to lead.
    for u in db.scalars(select(User).where(User.tribe_id == tribe_id)).all():
        u.tribe_id = None
        if u.role == "tribe_leader":
            u.role = "member"
    for lv in db.scalars(select(Leave).where(Leave.tribe_id == tribe_id)).all():
        lv.tribe_id = None
    for item in db.scalars(select(RoadmapItem).where(RoadmapItem.dependency_tribe_id == tribe_id)).all():
        item.dependency_to_text(tribe.name)
    # Org boxes point at their parent: unlink them first, the delete has no order.
    db.execute(update(OrgNode).where(OrgNode.tribe_id == tribe_id).values(parent_id=None))
    for row in db.scalars(select(OrgNode).where(OrgNode.tribe_id == tribe_id)).all():
        db.delete(row)
    for row in db.scalars(select(FeedPost).where(FeedPost.tribe_id == tribe_id)).all():
        db.delete(row)
    for row in db.scalars(select(ApiKey).where(ApiKey.tribe_id == tribe_id)).all():
        db.delete(row)
    # Nothing links these rows to the tribe in the ORM, so the unit of work could
    # delete the tribe before writing them: flush them first.
    db.flush()
    record_audit(db, admin.id, "tribe.delete", entity="tribe", entity_id=tribe.id, detail={"name": tribe.name})
    db.delete(tribe)
    db.commit()
