from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import (
    ADMIN,
    TRIBE,
    assert_can_edit_squad,
    assert_tribe_scope,
    get_current_user,
    get_threshold,
    is_squad_privileged,
    record_audit,
    require_module,
    require_tribe_or_admin,
    visible_tribe_id,
)
from ..models import (
    FeedPost,
    KeyMessage,
    OrgNode,
    QuarterProgress,
    RoadmapItem,
    Squad,
    SquadBudget,
    User,
)
from ..changenotify import notify_change
from ..schemas import (
    DependentItemOut,
    KeyMessageCreate,
    KeyMessageOut,
    KeyMessageUpdate,
    QuarterProgressIn,
    QuarterProgressOut,
    SquadBudgetIn,
    SquadBudgetOut,
    SquadCreate,
    SquadDetail,
    SquadOut,
    SquadUpdate,
)
from ..serializers import budget_out, squad_detail

router = APIRouter(prefix="/api/squads", tags=["squads"])


@router.get("", response_model=list[SquadOut])
def list_squads(tribe_id: int | None = Query(default=None),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(Squad).order_by(Squad.display_order, Squad.id)
    scope = visible_tribe_id(user)
    if scope is not None:
        q = q.where(Squad.tribe_id == scope)
    elif tribe_id is not None:
        q = q.where(Squad.tribe_id == tribe_id)
    return list(db.scalars(q).all())


@router.get("/{squad_id}", response_model=SquadDetail)
def get_squad(squad_id: int, year: int | None = Query(default=None),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    if year is None:
        year = st.current_year_quarter()[0]
    return squad_detail(squad, year, get_threshold(db), privileged=is_squad_privileged(user, squad))


@router.get("/{squad_id}/dependents", response_model=list[DependentItemOut])
def squad_dependents(squad_id: int, year: int | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Milestones in *other* squads that declared a dependency on this squad.

    A dependency targets this squad directly, or this squad's tribe. This lets a
    squad surface what other teams are waiting on from them ("le faire apparaître").
    """
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    if year is None:
        year = st.current_year_quarter()[0]
    stmt = select(RoadmapItem).where(
        RoadmapItem.year == year,
        RoadmapItem.squad_id != squad_id,
        ((RoadmapItem.dependency_kind == "squad") & (RoadmapItem.dependency_squad_id == squad_id))
        | ((RoadmapItem.dependency_kind == "tribe") & (RoadmapItem.dependency_tribe_id == squad.tribe_id)),
    )
    out: list[DependentItemOut] = []
    for r in db.scalars(stmt).all():
        src = r.squad
        out.append(DependentItemOut(
            squad_id=r.squad_id,
            squad_name=src.name if src else "-",
            tribe_name=src.tribe.name if src and src.tribe else None,
            year=r.year, quarter=r.quarter, title=r.title, status=r.status,
            via="squad" if r.dependency_kind == "squad" else "tribe",
        ))
    out.sort(key=lambda d: (d.quarter, d.squad_name, d.title))
    return out


def _roadmap_data(db: Session, user: User, squad_id: int, year: int | None, lang: str | None):
    from ..report import build_report_data
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    if year is None:
        year = st.current_year_quarter()[0]
    return build_report_data(db, None, year, 7, squad_id=squad_id, lang=lang), year


@router.get("/{squad_id}/roadmap.pptx",
            dependencies=[Depends(require_module("squad_content", "roadmap"))])
def export_squad_roadmap_pptx(squad_id: int, year: int | None = Query(default=None),
                              lang: str | None = Query(default=None),
                              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Roadmap-only PowerPoint for a single squad (title slide + roadmap slide)."""
    from ..report import render_roadmap_pptx
    data, year = _roadmap_data(db, user, squad_id, year, lang)
    try:
        payload = render_roadmap_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="roadmap_{squad_id}_{year}.pptx"'},
    )


@router.get("/{squad_id}/roadmap.html",
            dependencies=[Depends(require_module("squad_content", "roadmap"))])
def export_squad_roadmap_html(squad_id: int, year: int | None = Query(default=None),
                              lang: str | None = Query(default=None),
                              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Roadmap-only web page for a single squad."""
    from fastapi.responses import HTMLResponse
    from ..report import render_roadmap_html
    data, _ = _roadmap_data(db, user, squad_id, year, lang)
    return HTMLResponse(render_roadmap_html(data, standalone=True))


@router.post("", response_model=SquadOut, status_code=201)
def create_squad(payload: SquadCreate, db: Session = Depends(get_db), user: User = Depends(require_tribe_or_admin)):
    # tribe leaders can only create squads in their own tribe
    tribe_id = payload.tribe_id if user.role == ADMIN else user.tribe_id
    if tribe_id is None:
        raise HTTPException(status_code=400, detail="Tribe requise")
    assert_tribe_scope(user, tribe_id)
    data = payload.model_dump()
    data["tribe_id"] = tribe_id
    squad = Squad(**data)
    db.add(squad)
    db.flush()
    record_audit(db, user.id, "squad.create", entity="squad", entity_id=squad.id, detail={"name": squad.name})
    db.commit()
    db.refresh(squad)
    return squad


@router.put("/{squad_id}", response_model=SquadOut)
def update_squad(squad_id: int, payload: SquadUpdate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    data = payload.model_dump(exclude_unset=True)
    if "tribe_id" in data and user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Seul l'administrateur peut déplacer une squad de tribe")
    # KPI / budget on/off is a tribe-leader decision (like leader assignment & ordering).
    structural = {"leader_user_id", "display_order", "kpis_enabled", "budget_enabled"}
    if user.role not in (ADMIN, TRIBE):
        assert_can_edit_squad(db, user, squad_id)
        if structural & data.keys():
            raise HTTPException(status_code=403, detail="Champs réservés au tribe leader")
    for k, v in data.items():
        setattr(squad, k, v)
    record_audit(db, user.id, "squad.update", entity="squad", entity_id=squad.id, detail=data)
    db.commit()
    db.refresh(squad)
    return squad


@router.delete("/{squad_id}", status_code=204)
def delete_squad(squad_id: int, db: Session = Depends(get_db), user: User = Depends(require_tribe_or_admin)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    # Detach references not owned by the squad (keep the org boxes and feed posts).
    for node in db.scalars(select(OrgNode).where(OrgNode.squad_id == squad_id)).all():
        node.squad_id = None
    for post in db.scalars(select(FeedPost).where(FeedPost.squad_id == squad_id)).all():
        post.squad_id = None
    record_audit(db, user.id, "squad.delete", entity="squad", entity_id=squad.id, detail={"name": squad.name})
    db.delete(squad)
    db.commit()


@router.put("/{squad_id}/quarter-progress", response_model=QuarterProgressOut)
def set_quarter_progress(squad_id: int, payload: QuarterProgressIn, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    row = db.scalar(
        select(QuarterProgress).where(
            QuarterProgress.squad_id == squad_id,
            QuarterProgress.year == payload.year,
            QuarterProgress.quarter == payload.quarter,
        )
    )
    if row is None:
        row = QuarterProgress(squad_id=squad_id, year=payload.year, quarter=payload.quarter,
                              progress_pct=payload.progress_pct, comment=payload.comment)
        db.add(row)
    else:
        row.progress_pct = payload.progress_pct
        row.comment = payload.comment
    record_audit(db, user.id, "quarter_progress.set", entity="squad", entity_id=squad_id,
                 detail={"year": payload.year, "quarter": payload.quarter, "progress_pct": payload.progress_pct})
    db.commit()
    db.refresh(row)
    notify_change(squad_id, "progress", user.display_name, payload.year)
    return row


# ---------- Budget (squad-leader reporting, privileged-visible) ----------
@router.put("/{squad_id}/budget", response_model=SquadBudgetOut)
def set_squad_budget(squad_id: int, payload: SquadBudgetIn, year: int | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    if not squad.budget_enabled:
        raise HTTPException(status_code=403, detail="Le budget n'est pas activé pour cette squad")
    if year is None:
        year = st.current_year_quarter()[0]
    row = db.scalar(select(SquadBudget).where(SquadBudget.squad_id == squad_id, SquadBudget.year == year))
    if row is None:
        row = SquadBudget(squad_id=squad_id, year=year)
        db.add(row)
    # The total envelope is a tribe-leader (or admin) decision; a squad leader only
    # reports where the squad stands (spent / forecast) and comments. Ignore an
    # incoming total from a squad leader so they can't move the envelope.
    if user.role in (ADMIN, TRIBE):
        row.total = payload.total
    row.spent = payload.spent
    row.forecast = payload.forecast
    row.comment = payload.comment
    record_audit(db, user.id, "squad_budget.set", entity="squad", entity_id=squad_id,
                 detail={"year": year, "total": float(row.total) if row.total is not None else None,
                         "spent": payload.spent, "forecast": payload.forecast})
    db.commit()
    notify_change(squad_id, "budget", user.display_name, year)
    return budget_out(squad, year)


# ---------- Key messages (curated success / alert / risk) ----------
def _get_key_message(db: Session, user: User, squad_id: int, msg_id: int) -> KeyMessage:
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    km = db.get(KeyMessage, msg_id)
    if km is None or km.squad_id != squad_id:
        raise HTTPException(status_code=404, detail="Message introuvable")
    return km


@router.post("/{squad_id}/key-messages", response_model=KeyMessageOut, status_code=201)
def create_key_message(squad_id: int, payload: KeyMessageCreate, year: int | None = Query(default=None),
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    if year is None:
        year = st.current_year_quarter()[0]
    km = KeyMessage(squad_id=squad_id, year=year, kind=payload.kind, text=payload.text,
                    display_order=payload.display_order, created_by_user_id=user.id)
    db.add(km)
    record_audit(db, user.id, "key_message.create", entity="squad", entity_id=squad_id,
                 detail={"year": year, "kind": payload.kind})
    db.commit()
    db.refresh(km)
    notify_change(squad_id, "key_message", user.display_name, year)
    return km


@router.put("/{squad_id}/key-messages/{msg_id}", response_model=KeyMessageOut)
def update_key_message(squad_id: int, msg_id: int, payload: KeyMessageUpdate,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    km = _get_key_message(db, user, squad_id, msg_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(km, k, v)
    record_audit(db, user.id, "key_message.update", entity="squad", entity_id=squad_id, detail={"id": msg_id})
    km_year = km.year
    db.commit()
    db.refresh(km)
    notify_change(squad_id, "key_message", user.display_name, km_year)
    return km


@router.delete("/{squad_id}/key-messages/{msg_id}", status_code=204)
def delete_key_message(squad_id: int, msg_id: int,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    km = _get_key_message(db, user, squad_id, msg_id)
    km_year = km.year
    record_audit(db, user.id, "key_message.delete", entity="squad", entity_id=squad_id, detail={"id": msg_id})
    db.delete(km)
    db.commit()
    notify_change(squad_id, "key_message", user.display_name, km_year)
