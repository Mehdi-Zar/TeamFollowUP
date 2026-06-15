from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_can_manage_objectives, get_current_user, record_audit, require_module
from ..models import Objective, Squad, User
from ..progress import capture_progress
from ..schemas import ObjectiveCreate, ObjectiveOut, ObjectiveUpdate

router = APIRouter(prefix="/api/objectives", tags=["objectives"],
                   dependencies=[Depends(require_module("squad_content", "objectives"))])


@router.post("", response_model=ObjectiveOut, status_code=201)
def create_objective(payload: ObjectiveCreate, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    squad = db.get(Squad, payload.squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_manage_objectives(user, squad)
    obj = Objective(**payload.model_dump())
    db.add(obj)
    db.flush()
    record_audit(db, user.id, "objective.create", entity="objective", entity_id=obj.id,
                 detail={"squad_id": obj.squad_id, "year": obj.year, "title": obj.title})
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/{objective_id}", response_model=ObjectiveOut)
def update_objective(objective_id: int, payload: ObjectiveUpdate, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    obj = db.get(Objective, objective_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Objectif introuvable")
    assert_can_manage_objectives(user, obj.squad)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    record_audit(db, user.id, "objective.update", entity="objective", entity_id=obj.id, detail=data)
    capture_progress(db, obj.squad_id, obj.year, user)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{objective_id}", status_code=204)
def delete_objective(objective_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.get(Objective, objective_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Objectif introuvable")
    assert_can_manage_objectives(user, obj.squad)
    record_audit(db, user.id, "objective.delete", entity="objective", entity_id=obj.id,
                 detail={"squad_id": obj.squad_id})
    db.delete(obj)
    db.commit()
