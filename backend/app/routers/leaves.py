"""Team leave / absence management.

Everyone (within their tribe scope) can see who is away and declare their own
absences; squad/tribe leaders manage (approve/edit/cancel) absences of people in
their scope; admins configure the leave types. Approval is required or not per
tribe (Tribe.leaves_require_approval). The free-text motif is visible only to the
person, their leader and admins; the type is visible to everyone.
"""
import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (ADMIN, SQUAD, TRIBE, can_manage_leave, can_see_leaves_of,
                    get_current_user, record_audit, require_admin, require_module)
from ..leavesconfig import ACTIVE_STATUSES, leave_days
from ..models import Leave, LeaveType, Member, Squad, Tribe, User, utcnow
from ..schemas import (LeaveConfigIn, LeaveConfigOut, LeaveDecisionIn, LeaveIn,
                       LeaveOut, LeaveOverlapDay, LeaveTypeIn, LeaveTypeOut, LeaveUpdate)

router = APIRouter(prefix="/api/leaves", tags=["leaves"],
                   dependencies=[Depends(require_module("leaves"))])


# ----- helpers -------------------------------------------------------------------

def _scope_tribe(user: User) -> int | None:
    """None = all tribes (admin); otherwise the caller's own tribe."""
    return None if user.role == ADMIN else user.tribe_id


def _name(db: Session, uid: int | None, cache: dict) -> str | None:
    if uid is None:
        return None
    if uid not in cache:
        u = db.get(User, uid)
        cache[uid] = u.display_name if u else f"#{uid}"
    return cache[uid]


def _serialize(db: Session, lv: Leave, viewer: User, cache: dict) -> LeaveOut:
    is_owner = lv.user_id == viewer.id
    manages = can_manage_leave(db, viewer, lv.user_id)
    may_see_comment = is_owner or manages
    can_edit = (is_owner and lv.status in ("pending", "approved")) or manages
    can_decide = manages and lv.status == "pending"
    return LeaveOut(
        id=lv.id, user_id=lv.user_id, user_name=_name(db, lv.user_id, cache) or "",
        tribe_id=lv.tribe_id, type_id=lv.type_id,
        type_label=lv.type.label if lv.type else "", type_color=lv.type.color if lv.type else "#6B7280",
        type_requires_detail=bool(lv.type.requires_detail) if lv.type else False,
        start_date=lv.start_date, end_date=lv.end_date,
        start_half=lv.start_half, end_half=lv.end_half, days=leave_days(lv),
        status=lv.status, detail=(lv.detail or None), comment=(lv.comment if may_see_comment else None),
        created_at=lv.created_at,
        decided_by_name=_name(db, lv.decided_by_user_id, cache), decided_at=lv.decided_at,
        decision_comment=(lv.decision_comment if may_see_comment else None),
        can_edit=can_edit, can_decide=can_decide,
    )


def _validate_range(start: date, end: date, start_half: bool, end_half: bool) -> None:
    if end < start:
        raise HTTPException(status_code=422, detail="La date de fin précède la date de début")
    if start == end and start_half and end_half:
        raise HTTPException(status_code=422, detail="Une journée ne peut pas être demi le matin ET l'après-midi")


def _get_type(db: Session, type_id: int) -> LeaveType:
    lt = db.get(LeaveType, type_id)
    if lt is None or not lt.is_active:
        raise HTTPException(status_code=404, detail="Type d'absence introuvable")
    return lt


def _require_detail(lt: LeaveType, detail: str | None) -> None:
    if lt.requires_detail and not (detail or "").strip():
        raise HTTPException(status_code=422, detail="Une précision est requise pour ce type d'absence")


def _users_in_squad(db: Session, squad_id: int) -> list[int]:
    return list(db.scalars(select(Member.user_id).where(
        Member.squad_id == squad_id, Member.user_id.isnot(None))).all())


# ----- leave types (admin) -------------------------------------------------------

@router.get("/types", response_model=list[LeaveTypeOut])
def list_types(include_inactive: bool = Query(default=False),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(LeaveType)
    if not include_inactive:
        stmt = stmt.where(LeaveType.is_active.is_(True))
    return db.scalars(stmt.order_by(LeaveType.display_order, LeaveType.id)).all()


@router.post("/types", response_model=LeaveTypeOut, status_code=201)
def create_type(payload: LeaveTypeIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    lt = LeaveType(label=payload.label.strip(), color=payload.color, is_active=payload.is_active,
                   display_order=payload.display_order)
    db.add(lt)
    db.flush()
    record_audit(db, user.id, "leave_type.create", entity="leave_type", entity_id=lt.id)
    db.commit()
    db.refresh(lt)
    return lt


@router.put("/types/{type_id}", response_model=LeaveTypeOut)
def update_type(type_id: int, payload: LeaveTypeIn, db: Session = Depends(get_db),
                user: User = Depends(require_admin)):
    lt = db.get(LeaveType, type_id)
    if lt is None:
        raise HTTPException(status_code=404, detail="Type d'absence introuvable")
    lt.label = payload.label.strip()
    lt.color = payload.color
    lt.display_order = payload.display_order
    lt.is_active = payload.is_active
    db.commit()
    db.refresh(lt)
    return lt


@router.delete("/types/{type_id}", status_code=204)
def delete_type(type_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    lt = db.get(LeaveType, type_id)
    if lt is None:
        raise HTTPException(status_code=404, detail="Type d'absence introuvable")
    used = db.scalar(select(Leave.id).where(Leave.type_id == type_id).limit(1))
    if used:  # keep referential integrity: deactivate instead of deleting
        lt.is_active = False
    else:
        db.delete(lt)
    db.commit()


# ----- per-tribe configuration ---------------------------------------------------

def _resolve_tribe(db: Session, user: User, tribe_id: int | None) -> Tribe:
    if tribe_id is None:
        tribe_id = user.tribe_id
    if tribe_id is None:
        raise HTTPException(status_code=400, detail="Aucune tribe à configurer")
    tribe = db.get(Tribe, tribe_id)
    if tribe is None:
        raise HTTPException(status_code=404, detail="Tribe introuvable")
    return tribe


@router.get("/config", response_model=LeaveConfigOut)
def get_config(tribe_id: int | None = Query(default=None),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tribe = _resolve_tribe(db, user, tribe_id)
    if not can_see_leaves_of(user, tribe.id):
        raise HTTPException(status_code=403, detail="Hors de votre périmètre")
    return LeaveConfigOut(tribe_id=tribe.id, tribe_name=tribe.name,
                          require_approval=tribe.leaves_require_approval,
                          overlap_threshold=tribe.leaves_overlap_threshold)


@router.put("/config", response_model=LeaveConfigOut)
def set_config(payload: LeaveConfigIn, tribe_id: int | None = Query(default=None),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (ADMIN, TRIBE):
        raise HTTPException(status_code=403, detail="Réservé au tribe leader")
    tribe = _resolve_tribe(db, user, tribe_id)
    if user.role == TRIBE and tribe.id != user.tribe_id:
        raise HTTPException(status_code=403, detail="Hors de votre périmètre")
    if payload.require_approval is not None:
        tribe.leaves_require_approval = payload.require_approval
    if payload.overlap_threshold is not None:
        tribe.leaves_overlap_threshold = payload.overlap_threshold
    record_audit(db, user.id, "leave_config.update", entity="tribe", entity_id=tribe.id)
    db.commit()
    return LeaveConfigOut(tribe_id=tribe.id, tribe_name=tribe.name,
                          require_approval=tribe.leaves_require_approval,
                          overlap_threshold=tribe.leaves_overlap_threshold)


# ----- leaves --------------------------------------------------------------------

@router.get("/people")
def fileable_people(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """People the caller may file an absence for: themselves plus, for leaders,
    everyone in their manageable scope. Used to populate the person picker."""
    people: dict[int, str] = {user.id: user.display_name}
    if user.role == ADMIN:
        for u in db.scalars(select(User).where(User.status == "active")).all():
            people[u.id] = u.display_name
    elif user.role == TRIBE:
        for u in db.scalars(select(User).where(User.tribe_id == user.tribe_id,
                                               User.status == "active")).all():
            people[u.id] = u.display_name
    elif user.role == SQUAD:
        led = db.scalars(select(Squad.id).where(Squad.leader_user_id == user.id)).all()
        if led:
            for uid in db.scalars(select(Member.user_id).where(
                    Member.squad_id.in_(led), Member.user_id.isnot(None))).all():
                u = db.get(User, uid)
                if u:
                    people[u.id] = u.display_name
    return [{"user_id": uid, "name": name} for uid, name in
            sorted(people.items(), key=lambda kv: kv[1].lower())]


@router.get("", response_model=list[LeaveOut])
def list_leaves(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    user_id: int | None = Query(default=None),
    squad_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    mine: bool = Query(default=False),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    stmt = select(Leave)
    scope = _scope_tribe(user)
    if scope is not None:
        stmt = stmt.where(Leave.tribe_id == scope)
    if mine:
        stmt = stmt.where(Leave.user_id == user.id)
    elif user_id is not None:
        stmt = stmt.where(Leave.user_id == user_id)
    if squad_id is not None:
        ids = _users_in_squad(db, squad_id)
        stmt = stmt.where(Leave.user_id.in_(ids or [-1]))
    if status:
        stmt = stmt.where(Leave.status == status)
    if date_from is not None:
        stmt = stmt.where(Leave.end_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Leave.start_date <= date_to)
    rows = db.scalars(stmt.order_by(Leave.start_date.desc(), Leave.id.desc())).all()
    cache: dict = {}
    return [_serialize(db, lv, user, cache) for lv in rows]


@router.post("", response_model=LeaveOut, status_code=201)
def create_leave(payload: LeaveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target_id = payload.user_id or user.id
    target = db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    on_behalf = target_id != user.id
    if on_behalf and not can_manage_leave(db, user, target_id):
        raise HTTPException(status_code=403, detail="Vous ne pouvez saisir que pour votre périmètre")
    lt = _get_type(db, payload.type_id)
    _require_detail(lt, payload.detail)
    _validate_range(payload.start_date, payload.end_date, payload.start_half, payload.end_half)

    tribe = db.get(Tribe, target.tribe_id) if target.tribe_id else None
    require_approval = bool(tribe.leaves_require_approval) if tribe else True
    # A manager filing (for self or others) is an approver → auto-approved.
    manager = can_manage_leave(db, user, target_id)
    approved = manager or not require_approval

    lv = Leave(
        user_id=target_id, tribe_id=target.tribe_id, type_id=payload.type_id,
        start_date=payload.start_date, end_date=payload.end_date,
        start_half=payload.start_half, end_half=payload.end_half,
        detail=(payload.detail or None), comment=(payload.comment or None), created_by_user_id=user.id,
        status="approved" if approved else "pending",
    )
    if approved:
        lv.decided_by_user_id = user.id
        lv.decided_at = utcnow()
    db.add(lv)
    db.flush()
    record_audit(db, user.id, "leave.create", entity="leave", entity_id=lv.id,
                 detail={"user_id": target_id, "status": lv.status})
    db.commit()
    db.refresh(lv)
    return _serialize(db, lv, user, {})


@router.put("/{leave_id}", response_model=LeaveOut)
def update_leave(leave_id: int, payload: LeaveUpdate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    lv = db.get(Leave, leave_id)
    if lv is None:
        raise HTTPException(status_code=404, detail="Absence introuvable")
    is_owner = lv.user_id == user.id
    manages = can_manage_leave(db, user, lv.user_id)
    if not (manages or (is_owner and lv.status in ("pending", "approved"))):
        raise HTTPException(status_code=403, detail="Modification non autorisée")

    data = payload.model_dump(exclude_unset=True)
    new_type_id = data.get("type_id") or lv.type_id
    lt = _get_type(db, new_type_id)
    _require_detail(lt, data.get("detail", lv.detail))
    new_start = data.get("start_date", lv.start_date)
    new_end = data.get("end_date", lv.end_date)
    new_sh = data.get("start_half", lv.start_half)
    new_eh = data.get("end_half", lv.end_half)
    _validate_range(new_start, new_end, new_sh, new_eh)
    for k, v in data.items():
        setattr(lv, k, v)

    # If the owner edits an approved leave where approval is required, it must be
    # re-approved. A manager's edit keeps the current status.
    if is_owner and not manages and lv.status == "approved":
        tribe = db.get(Tribe, lv.tribe_id) if lv.tribe_id else None
        if not tribe or tribe.leaves_require_approval:
            lv.status = "pending"
            lv.decided_by_user_id = None
            lv.decided_at = None
            lv.decision_comment = None
    db.commit()
    db.refresh(lv)
    return _serialize(db, lv, user, {})


@router.post("/{leave_id}/decision", response_model=LeaveOut)
def decide_leave(leave_id: int, payload: LeaveDecisionIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    lv = db.get(Leave, leave_id)
    if lv is None:
        raise HTTPException(status_code=404, detail="Absence introuvable")
    if not can_manage_leave(db, user, lv.user_id):
        raise HTTPException(status_code=403, detail="Vous ne gérez pas cette personne")
    lv.status = "approved" if payload.action == "approve" else "rejected"
    lv.decided_by_user_id = user.id
    lv.decided_at = utcnow()
    lv.decision_comment = (payload.comment or None)
    record_audit(db, user.id, "leave.decision", entity="leave", entity_id=lv.id,
                 detail={"action": payload.action})
    db.commit()
    db.refresh(lv)
    return _serialize(db, lv, user, {})


@router.delete("/{leave_id}", status_code=204)
def delete_leave(leave_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lv = db.get(Leave, leave_id)
    if lv is None:
        raise HTTPException(status_code=404, detail="Absence introuvable")
    if not (lv.user_id == user.id or can_manage_leave(db, user, lv.user_id)):
        raise HTTPException(status_code=403, detail="Suppression non autorisée")
    record_audit(db, user.id, "leave.delete", entity="leave", entity_id=lv.id)
    db.delete(lv)
    db.commit()


# ----- overlap alert (leaders) ---------------------------------------------------

@router.get("/overlaps", response_model=list[LeaveOverlapDay],
            dependencies=[Depends(require_module("leaves", "overlap_alert"))])
def overlaps(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Days where a squad has at least `overlap_threshold` people away at once,
    restricted to the squads the caller can manage."""
    if user.role == ADMIN:
        squads = db.scalars(select(Squad)).all()
    elif user.role == TRIBE:
        squads = db.scalars(select(Squad).where(Squad.tribe_id == user.tribe_id)).all()
    elif user.role == SQUAD:
        squads = db.scalars(select(Squad).where(Squad.leader_user_id == user.id)).all()
    else:
        return []
    if (date_to - date_from).days > 366:
        raise HTTPException(status_code=422, detail="Plage trop large (max 1 an)")

    out: list[LeaveOverlapDay] = []
    cache: dict = {}
    for sq in squads:
        member_ids = _users_in_squad(db, sq.id)
        if not member_ids:
            continue
        threshold = db.get(Tribe, sq.tribe_id).leaves_overlap_threshold if sq.tribe_id else 3
        rows = db.scalars(select(Leave).where(
            Leave.user_id.in_(member_ids), Leave.status.in_(ACTIVE_STATUSES),
            Leave.end_date >= date_from, Leave.start_date <= date_to)).all()
        if not rows:
            continue
        day = date_from
        while day <= date_to:
            present = [r for r in rows if r.start_date <= day <= r.end_date]
            if len(present) >= threshold:
                out.append(LeaveOverlapDay(
                    squad_id=sq.id, squad_name=sq.name, day=day, count=len(present),
                    names=[_name(db, r.user_id, cache) or "" for r in present]))
            day = date.fromordinal(day.toordinal() + 1)
    return out


# ----- CSV export ----------------------------------------------------------------

@router.get("/export.csv")
def export_csv(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    stmt = select(Leave)
    scope = _scope_tribe(user)
    if scope is not None:
        stmt = stmt.where(Leave.tribe_id == scope)
    if date_from is not None:
        stmt = stmt.where(Leave.end_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Leave.start_date <= date_to)
    rows = db.scalars(stmt.order_by(Leave.start_date.desc())).all()
    cache: dict = {}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Personne", "Type", "Précision", "Début", "Fin", "Jours", "Statut", "Motif"])
    for lv in rows:
        out = _serialize(db, lv, user, cache)
        w.writerow([out.user_name, out.type_label, out.detail or "", out.start_date.isoformat(),
                    out.end_date.isoformat(), out.days, out.status, out.comment or ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="absences.csv"'})
