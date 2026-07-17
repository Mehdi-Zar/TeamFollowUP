from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_leads_squad, record_audit, require_module, require_writer
from ..changenotify import notify_change
from ..models import RoadmapItem, Squad, User
from ..schemas import RoadmapItemCreate, RoadmapItemOut, RoadmapItemUpdate
from ..serializers import roadmap_item_out

router = APIRouter(prefix="/api/roadmap-items", tags=["roadmap"],
                   dependencies=[Depends(require_module("squad_content", "roadmap"))])


@router.get("/themes", response_model=list[str])
def list_themes(db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Distinct existing milestone themes, most-used first, for reuse/autocomplete.

    Scoped to the writer's visibility: admins see every theme, others see the
    themes used across their own tribe's squads."""
    q = (select(RoadmapItem.theme, func.count(RoadmapItem.id).label("n"))
         .where(RoadmapItem.theme.is_not(None), func.trim(RoadmapItem.theme) != "")
         .group_by(RoadmapItem.theme))
    if user.role != "admin":
        q = q.join(Squad, Squad.id == RoadmapItem.squad_id).where(Squad.tribe_id == user.tribe_id)
    rows = db.execute(q.order_by(func.count(RoadmapItem.id).desc())).all()
    return [theme for theme, _ in rows]


def _validate_objective(db: Session, item: RoadmapItem) -> None:
    """A milestone may only link to an objective of its own squad."""
    if item.objective_id is None:
        return
    from ..models import Objective
    obj = db.get(Objective, item.objective_id)
    if obj is None or obj.squad_id != item.squad_id:
        raise HTTPException(status_code=400, detail="L'objectif choisi n'appartient pas à cette squad")


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
    if db.get(Squad, payload.squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_leads_squad(db, user, payload.squad_id)
    item = RoadmapItem(**payload.model_dump())
    _normalize_dependency(item)
    _validate_objective(db, item)
    db.add(item)
    db.flush()
    record_audit(db, user.id, "roadmap.create", entity="roadmap_item", entity_id=item.id,
                 detail={"squad_id": item.squad_id, "year": item.year, "quarter": item.quarter, "title": item.title})
    db.commit()
    db.refresh(item)
    notify_change(item.squad_id, "roadmap", user.display_name, item.year)
    return roadmap_item_out(item)


@router.put("/{item_id}", response_model=RoadmapItemOut)
def update_item(item_id: int, payload: RoadmapItemUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_writer)):
    item = db.get(RoadmapItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Jalon introuvable")
    assert_leads_squad(db, user, item.squad_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(item, k, v)
    if "dependency_kind" in data or "dependency_squad_id" in data or "dependency_tribe_id" in data:
        _normalize_dependency(item)
    if "objective_id" in data:
        _validate_objective(db, item)
    record_audit(db, user.id, "roadmap.update", entity="roadmap_item", entity_id=item.id, detail=data)
    db.commit()
    db.refresh(item)
    notify_change(item.squad_id, "roadmap", user.display_name, item.year)
    return roadmap_item_out(item)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    item = db.get(RoadmapItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Jalon introuvable")
    assert_leads_squad(db, user, item.squad_id)
    sq_id, yr = item.squad_id, item.year
    record_audit(db, user.id, "roadmap.delete", entity="roadmap_item", entity_id=item.id,
                 detail={"squad_id": item.squad_id})
    db.delete(item)
    db.commit()
    notify_change(sq_id, "roadmap", user.display_name, yr)
