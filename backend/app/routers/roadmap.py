from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_can_edit_squad, record_audit, require_writer
from ..models import RoadmapItem, Squad, User
from ..schemas import RoadmapItemCreate, RoadmapItemOut, RoadmapItemUpdate

router = APIRouter(prefix="/api/roadmap-items", tags=["roadmap"])


@router.post("", response_model=RoadmapItemOut, status_code=201)
def create_item(payload: RoadmapItemCreate, db: Session = Depends(get_db),
                user: User = Depends(require_writer)):
    if db.get(Squad, payload.squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, payload.squad_id)
    item = RoadmapItem(**payload.model_dump())
    db.add(item)
    db.flush()
    record_audit(db, user.id, "roadmap.create", entity="roadmap_item", entity_id=item.id,
                 detail={"squad_id": item.squad_id, "year": item.year, "quarter": item.quarter, "title": item.title})
    db.commit()
    db.refresh(item)
    return item


@router.put("/{item_id}", response_model=RoadmapItemOut)
def update_item(item_id: int, payload: RoadmapItemUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_writer)):
    item = db.get(RoadmapItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Jalon introuvable")
    assert_can_edit_squad(db, user, item.squad_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(item, k, v)
    record_audit(db, user.id, "roadmap.update", entity="roadmap_item", entity_id=item.id, detail=data)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    item = db.get(RoadmapItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Jalon introuvable")
    assert_can_edit_squad(db, user, item.squad_id)
    record_audit(db, user.id, "roadmap.delete", entity="roadmap_item", entity_id=item.id,
                 detail={"squad_id": item.squad_id})
    db.delete(item)
    db.commit()
