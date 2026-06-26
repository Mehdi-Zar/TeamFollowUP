"""Initiatives: a simple flat list (initiative / owner / squad / deadline) set by
the tribe leader and visible to everyone. Each initiative is assigned to one squad,
so it surfaces in that squad's report + dashboard. No milestones, no OTD here."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import (assert_can_manage_tribe_reporting, get_current_user, record_audit,
                    require_tribe_or_admin, visible_tribe_id)
from ..models import Initiative, Squad, Tribe, User
from ..schemas import InitiativeCreate, InitiativeOut, InitiativeUpdate

router = APIRouter(prefix="/api/initiatives", tags=["initiatives"])


def _scope_tribe(user: User, tribe_id: int | None) -> int | None:
    """Resolve which tribe to read: admins may pass any; others are pinned."""
    if user.role == "admin":
        return tribe_id
    return user.tribe_id


def _out(init: Initiative) -> InitiativeOut:
    out = InitiativeOut.model_validate(init)
    out.squad_name = init.squad.name if init.squad else None
    return out


def _validate_squad(db: Session, tribe_id: int, squad_id: int | None) -> None:
    if squad_id is None:
        return
    sq = db.get(Squad, squad_id)
    if sq is None or sq.tribe_id != tribe_id:
        raise HTTPException(status_code=400, detail="La squad choisie n'appartient pas à cette tribe")


@router.get("", response_model=list[InitiativeOut])
def list_initiatives(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                     squad_id: int | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Flat list of initiatives, visible to everyone in scope (read-only for non
    tribe-leaders). Optionally filtered to a single squad (for that squad's report)."""
    year = year or st.current_year_quarter()[0]
    scope = _scope_tribe(user, tribe_id) if user.role == "admin" else visible_tribe_id(user)
    q = select(Initiative).where(Initiative.year == year).order_by(Initiative.display_order, Initiative.id)
    if scope is not None:
        q = q.where(Initiative.tribe_id == scope)
    if squad_id is not None:
        q = q.where(Initiative.squad_id == squad_id)
    return [_out(i) for i in db.scalars(q).all()]


@router.post("", response_model=InitiativeOut, status_code=201)
def create_initiative(payload: InitiativeCreate, db: Session = Depends(get_db),
                      user: User = Depends(require_tribe_or_admin)):
    if db.get(Tribe, payload.tribe_id) is None:
        raise HTTPException(status_code=404, detail="Tribe introuvable")
    assert_can_manage_tribe_reporting(user, payload.tribe_id)
    _validate_squad(db, payload.tribe_id, payload.squad_id)
    init = Initiative(**payload.model_dump())
    db.add(init)
    db.flush()
    record_audit(db, user.id, "initiative.create", entity="initiative", entity_id=init.id,
                 detail={"tribe_id": init.tribe_id, "title": init.title, "squad_id": init.squad_id})
    db.commit()
    db.refresh(init)
    return _out(init)


@router.put("/{initiative_id}", response_model=InitiativeOut)
def update_initiative(initiative_id: int, payload: InitiativeUpdate, db: Session = Depends(get_db),
                      user: User = Depends(require_tribe_or_admin)):
    init = db.get(Initiative, initiative_id)
    if init is None:
        raise HTTPException(status_code=404, detail="Initiative introuvable")
    assert_can_manage_tribe_reporting(user, init.tribe_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(init, k, v)
    _validate_squad(db, init.tribe_id, init.squad_id)
    record_audit(db, user.id, "initiative.update", entity="initiative", entity_id=init.id, detail=list(data.keys()))
    db.commit()
    db.refresh(init)
    return _out(init)


@router.delete("/{initiative_id}", status_code=204)
def delete_initiative(initiative_id: int, db: Session = Depends(get_db),
                      user: User = Depends(require_tribe_or_admin)):
    init = db.get(Initiative, initiative_id)
    if init is None:
        raise HTTPException(status_code=404, detail="Initiative introuvable")
    assert_can_manage_tribe_reporting(user, init.tribe_id)
    record_audit(db, user.id, "initiative.delete", entity="initiative", entity_id=init.id,
                 detail={"tribe_id": init.tribe_id})
    db.delete(init)
    db.commit()


@router.get("/report.html", response_class=HTMLResponse)
def initiatives_html(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                     lang: str | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Flat initiatives list as a standalone page."""
    from ..report import build_initiative_list, render_initiatives_html
    year = year or st.current_year_quarter()[0]
    scope = _scope_tribe(user, tribe_id) if user.role == "admin" else visible_tribe_id(user)
    data = build_initiative_list(db, scope, year)
    return HTMLResponse(render_initiatives_html(data, lang=lang or "fr", standalone=True))


@router.get("/report.pptx")
def initiatives_pptx(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                     lang: str | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Flat initiatives list as a branded deck."""
    from ..report import build_initiative_list, render_initiatives_pptx
    year = year or st.current_year_quarter()[0]
    scope = _scope_tribe(user, tribe_id) if user.role == "admin" else visible_tribe_id(user)
    data = build_initiative_list(db, scope, year)
    try:
        payload = render_initiatives_pptx(data, lang=lang or "fr")
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="initiatives_{data["year"]}.pptx"'},
    )
