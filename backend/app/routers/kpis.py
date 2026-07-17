"""Squad KPI CRUD endpoints.

Manages the key performance indicators attached to a squad (create/update/delete).
Every route is gated by the `squad_content > kpis` module toggle at the router
level, and writes additionally require the "writer" role plus edit rights on the
target squad. Reads of KPIs happen through the squad endpoints, not here.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_can_edit_squad, record_audit, require_module, require_writer
from ..models import Kpi, Squad, User
from ..schemas import KpiCreate, KpiOut, KpiUpdate

# Router-level dependency: the KPIs sub-module must be enabled (admin toggle).
router = APIRouter(prefix="/api/kpis", tags=["kpis"],
                   dependencies=[Depends(require_module("squad_content", "kpis"))])


@router.post("", response_model=KpiOut, status_code=201)
def create_kpi(payload: KpiCreate, db: Session = Depends(get_db),
               user: User = Depends(require_writer)):
    """Create a KPI on a squad.

    POST /api/kpis
    Access: writer role + edit rights on the target squad (assert_can_edit_squad).
    Side effects: writes a "kpi.create" audit entry.
    Returns 404 if the referenced squad does not exist.
    """
    if db.get(Squad, payload.squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, payload.squad_id)
    item = Kpi(**payload.model_dump())
    db.add(item)
    db.flush()
    record_audit(db, user.id, "kpi.create", entity="kpi", entity_id=item.id,
                 detail={"squad_id": item.squad_id, "name": item.name})
    db.commit()
    db.refresh(item)
    return item


@router.put("/{kpi_id}", response_model=KpiOut)
def update_kpi(kpi_id: int, payload: KpiUpdate, db: Session = Depends(get_db),
               user: User = Depends(require_writer)):
    """Partially update a KPI.

    PUT /api/kpis/{kpi_id}
    Access: writer role + edit rights on the KPI's squad.
    Side effects: writes a "kpi.update" audit entry (with the changed fields).
    Only fields present in the payload are applied (exclude_unset). 404 if unknown.
    """
    item = db.get(Kpi, kpi_id)
    if item is None:
        raise HTTPException(status_code=404, detail="KPI introuvable")
    assert_can_edit_squad(db, user, item.squad_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(item, k, v)
    record_audit(db, user.id, "kpi.update", entity="kpi", entity_id=item.id, detail=data)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{kpi_id}", status_code=204)
def delete_kpi(kpi_id: int, db: Session = Depends(get_db),
               user: User = Depends(require_writer)):
    """Delete a KPI.

    DELETE /api/kpis/{kpi_id} -> 204 No Content
    Access: writer role + edit rights on the KPI's squad.
    Side effects: writes a "kpi.delete" audit entry. 404 if unknown.
    """
    item = db.get(Kpi, kpi_id)
    if item is None:
        raise HTTPException(status_code=404, detail="KPI introuvable")
    assert_can_edit_squad(db, user, item.squad_id)
    record_audit(db, user.id, "kpi.delete", entity="kpi", entity_id=item.id, detail={"squad_id": item.squad_id})
    db.delete(item)
    db.commit()
