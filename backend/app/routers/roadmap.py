"""Roadmap milestone (jalon) endpoints (prefix ``/api/roadmap-items``).

Milestones are the quarter-level deliverables a squad tracks. This router covers
theme autocomplete and milestone CRUD. The whole router is gated by the
``squad_content``/``roadmap`` module.

Access model: all mutations require ``require_writer`` and, per milestone, that
the caller reports for the owning squad (``assert_reports_for_squad``: leader,
admin). On write, the dependency reference is normalized to match the chosen
kind, and a milestone moved to another year leaves the commitments and the
initiative of the old one. Mutations are audited and emit ``notify_change(..., "roadmap",
...)``.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_reports_for_squad, record_audit, require_module, require_writer, update_data
from ..changenotify import notify_change
from ..models import RoadmapItem, Squad, User
from ..schemas import RoadmapItemCreate, RoadmapItemOut, RoadmapItemUpdate
from ..serializers import roadmap_item_out

router = APIRouter(prefix="/api/roadmap-items", tags=["roadmap"],
                   dependencies=[Depends(require_module("squad_content", "roadmap"))])


@router.get("/themes", response_model=list[str])
def list_themes(db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """GET /api/roadmap-items/themes: distinct existing milestone themes,
    most-used first, for reuse/autocomplete.

    Requires ``require_writer``. Scoped to the writer's visibility: admins see
    every theme, others see the themes used across their own tribe's squads."""
    q = (select(RoadmapItem.theme, func.count(RoadmapItem.id).label("n"))
         .where(RoadmapItem.theme.is_not(None), func.trim(RoadmapItem.theme) != "")
         .group_by(RoadmapItem.theme))
    if user.role != "admin":
        q = q.join(Squad, Squad.id == RoadmapItem.squad_id).where(Squad.tribe_id == user.tribe_id)
    rows = db.execute(q.order_by(func.count(RoadmapItem.id).desc())).all()
    return [theme for theme, _ in rows]


def _check_dependency_target(db: Session, item: RoadmapItem) -> None:
    """The squad or tribe a milestone depends on must exist (the foreign key
    otherwise failed as a 500). Called after _normalize_dependency."""
    from ..models import Tribe
    # No autoflush: on an update the item is already dirty with the unknown id.
    with db.no_autoflush:
        if item.dependency_squad_id is not None and db.get(Squad, item.dependency_squad_id) is None:
            raise HTTPException(status_code=400, detail="Squad de dépendance introuvable")
        if item.dependency_tribe_id is not None and db.get(Tribe, item.dependency_tribe_id) is None:
            raise HTTPException(status_code=400, detail="Tribe de dépendance introuvable")


def _normalize_dependency(item: RoadmapItem) -> None:
    """Keep only the reference matching the chosen dependency kind (clear the others)."""
    kind = item.dependency_kind
    if kind == "squad":
        item.dependency_tribe_id = None
    elif kind == "tribe":
        item.dependency_squad_id = None
    else:  # text or none
        item.dependency_squad_id = None
        item.dependency_tribe_id = None
        if kind not in ("text", None):
            item.dependency_kind = None


@router.post("", response_model=RoadmapItemOut, status_code=201)
def create_item(payload: RoadmapItemCreate, db: Session = Depends(get_db),
                user: User = Depends(require_writer)):
    """POST /api/roadmap-items: create a milestone (201).

    Writer who reports for the target squad (``assert_reports_for_squad``). The
    dependency reference is normalized before insert. Audited, then ``notify_change(..., "roadmap", ...)``."""
    if db.get(Squad, payload.squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_reports_for_squad(db, user, payload.squad_id)
    item = RoadmapItem(**payload.model_dump())
    _normalize_dependency(item)
    _check_dependency_target(db, item)
    db.add(item)
    db.flush()
    record_audit(db, user.id, "roadmap.create", entity="roadmap_item", entity_id=item.id,
                 detail={"squad_id": item.squad_id, "year": item.year, "quarter": item.quarter, "title": item.title})
    db.commit()
    db.refresh(item)
    notify_change(item.squad_id, "roadmap", user, item.year)
    return roadmap_item_out(item)


@router.put("/{item_id}", response_model=RoadmapItemOut)
def update_item(item_id: int, payload: RoadmapItemUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_writer)):
    """PUT /api/roadmap-items/{item_id}: update a milestone.

    Writer who leads the milestone's squad only. Dependency fields are re-
    normalized when they are part of the update. Audited, then ``notify_change(..., "roadmap", ...)``."""
    item = db.get(RoadmapItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Jalon introuvable")
    assert_reports_for_squad(db, user, item.squad_id)
    data = update_data(payload, RoadmapItem)
    for k, v in data.items():
        setattr(item, k, v)
    if "dependency_kind" in data or "dependency_squad_id" in data or "dependency_tribe_id" in data:
        _normalize_dependency(item)
        _check_dependency_target(db, item)
    # Moved to another year: the commitments and the initiative of the old year
    # no longer count it (set_otd_jalons refuses a milestone of another year).
    if "year" in data:
        from ..models import Initiative, Otd
        for col, model in (("otd_id", Otd), ("squad_otd_id", Otd), ("initiative_id", Initiative)):
            ref = getattr(item, col)
            if ref is None or col in data:
                continue
            target = db.get(model, ref)
            if target is not None and target.year != item.year:
                setattr(item, col, None)
    record_audit(db, user.id, "roadmap.update", entity="roadmap_item", entity_id=item.id, detail=data)
    db.commit()
    db.refresh(item)
    notify_change(item.squad_id, "roadmap", user, item.year)
    return roadmap_item_out(item)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """DELETE /api/roadmap-items/{item_id}: delete a milestone (204).

    Writer who leads the milestone's squad only. Audited, then
    ``notify_change(..., "roadmap", ...)``."""
    item = db.get(RoadmapItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Jalon introuvable")
    assert_reports_for_squad(db, user, item.squad_id)
    sq_id, yr = item.squad_id, item.year
    record_audit(db, user.id, "roadmap.delete", entity="roadmap_item", entity_id=item.id,
                 detail={"squad_id": item.squad_id})
    db.delete(item)
    db.commit()
    notify_change(sq_id, "roadmap", user, yr)
