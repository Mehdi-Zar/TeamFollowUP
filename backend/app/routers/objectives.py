"""Squad objective endpoints (prefix ``/api/objectives``).

Objectives are a squad's yearly goals; milestones link up to them. This router
provides objective CRUD and is gated by the ``squad_content``/``objectives``
module.

Access model: every mutation requires ``assert_can_manage_objectives`` for the
owning squad (squad leader, tribe leader, or admin). Mutations are audited and
emit ``notify_change(..., "objectives", ...)``.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_can_manage_objectives, get_current_user, record_audit, require_module
from ..changenotify import notify_change
from ..models import Objective, Squad, User
from ..schemas import ObjectiveCreate, ObjectiveOut, ObjectiveUpdate
from ..serializers import objective_out

router = APIRouter(prefix="/api/objectives", tags=["objectives"],
                   dependencies=[Depends(require_module("squad_content", "objectives"))])


@router.post("", response_model=ObjectiveOut, status_code=201)
def create_objective(payload: ObjectiveCreate, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """POST /api/objectives — create an objective for a squad (201).

    Requires ``assert_can_manage_objectives`` on the target squad. Audited, then
    ``notify_change(..., "objectives", ...)``."""
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
    notify_change(obj.squad_id, "objectives", user.display_name, obj.year)
    return objective_out(obj, obj.squad)


@router.put("/{objective_id}", response_model=ObjectiveOut)
def update_objective(objective_id: int, payload: ObjectiveUpdate, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """PUT /api/objectives/{objective_id} — update an objective.

    Requires ``assert_can_manage_objectives`` on the objective's squad. Audited,
    then ``notify_change(..., "objectives", ...)``."""
    obj = db.get(Objective, objective_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Objectif introuvable")
    assert_can_manage_objectives(user, obj.squad)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    record_audit(db, user.id, "objective.update", entity="objective", entity_id=obj.id, detail=data)
    db.commit()
    db.refresh(obj)
    notify_change(obj.squad_id, "objectives", user.display_name, obj.year)
    return objective_out(obj, obj.squad)


@router.delete("/{objective_id}", status_code=204)
def delete_objective(objective_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """DELETE /api/objectives/{objective_id} — delete an objective (204).

    Requires ``assert_can_manage_objectives`` on the objective's squad. Audited,
    then ``notify_change(..., "objectives", ...)``."""
    obj = db.get(Objective, objective_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Objectif introuvable")
    assert_can_manage_objectives(user, obj.squad)
    sq_id, yr = obj.squad_id, obj.year
    record_audit(db, user.id, "objective.delete", entity="objective", entity_id=obj.id,
                 detail={"squad_id": obj.squad_id})
    db.delete(obj)
    db.commit()
    notify_change(sq_id, "objectives", user.display_name, yr)
