"""On site or remote: the team's week, and the recap (ADR 0021).

Part of the leaves menu, in its own view: everyone sees where the people of their
tribe work (admins: every tribe, or the one they choose). A person sets their own
usual remote week and changes one day; whoever manages their absences (their squad
leader, their tribe leader, an admin) can do it for them. No approval.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (ADMIN, can_manage_leave, get_current_user, record_audit,
                    require_capability, require_module, scoped_tribe_id)
from ..models import Member, RemoteDay, RemotePattern, Squad, User
from ..presence import WORKDAYS, clean_weekdays, day_range, statuses

router = APIRouter(prefix="/api/presence", tags=["leaves"],
                   dependencies=[Depends(require_module("leaves", "remote")),
                                 Depends(require_capability("leaves"))])

MAX_DAYS = 93  # a quarter: enough for the monthly recap, small enough to stay fast


class WeekIn(BaseModel):
    weekdays: list[int]


class DayIn(BaseModel):
    day: date
    # remote | onsite, or null to go back to the usual week.
    location: str | None = None


def _target(db: Session, viewer: User, user_id: int) -> User:
    """The person whose remote days are changed: oneself, or someone whose
    absences the viewer manages. 404 for an unknown account, 403 otherwise."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if target.id != viewer.id and not can_manage_leave(db, viewer, target.id):
        raise HTTPException(status_code=403, detail="Vous ne gérez pas le télétravail de cette personne")
    return target


@router.get("")
def team_presence(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    squad_id: int | None = Query(default=None),
    tribe_id: int | None = Query(default=None),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Where each person of the tribe works, day by day, over [from, to].

    GET /api/presence?from=&to=&squad_id=&tribe_id=
    Access: anyone with the leaves menu, within their tribe (admins: every tribe,
    or ``tribe_id``). At most 93 days. Each person comes with ``can_edit`` (self or
    managed) and the status of each day: onsite, remote, leave or off (weekend).
    """
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="La date de fin précède la date de début")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail="Période trop longue (93 jours au plus)")
    scope = scoped_tribe_id(user, tribe_id)
    q = select(User).where(User.status == "active", User.is_break_glass.is_(False))
    if scope is not None:
        q = q.where(User.tribe_id == scope)
    people = db.scalars(q.order_by(User.display_name)).all()

    # Squads of each person, from the org chart (members linked to an account).
    sq_q = select(Squad)
    if scope is not None:
        sq_q = sq_q.where(Squad.tribe_id == scope)
    squads = db.scalars(sq_q.order_by(Squad.display_order, Squad.name)).all()
    squad_ids = {s.id for s in squads}
    of: dict[int, list[int]] = {}
    for m in db.scalars(select(Member).where(Member.user_id.isnot(None),
                                             Member.squad_id.in_(squad_ids or {-1}))).all():
        if m.squad_id not in of.setdefault(m.user_id, []):
            of[m.user_id].append(m.squad_id)
    if squad_id is not None:
        people = [p for p in people if squad_id in of.get(p.id, [])]

    st = statuses(db, [p.id for p in people], date_from, date_to)
    manage_all = user.role == ADMIN
    return {
        "days": [d.isoformat() for d in day_range(date_from, date_to)],
        "squads": [{"id": s.id, "name": s.name} for s in squads],
        "people": [{
            "user_id": p.id, "name": p.display_name, "squad_ids": of.get(p.id, []),
            "can_edit": p.id == user.id or manage_all or can_manage_leave(db, user, p.id),
            **st[p.id],
        } for p in people],
    }


@router.put("/week/{user_id}")
def set_week(user_id: int, payload: WeekIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Set the usual remote weekdays of a person (0 = Monday .. 4 = Friday).

    PUT /api/presence/week/{user_id}  {"weekdays": [0, 4]}
    Access: the person, or whoever manages their absences. An empty list means
    always on site. Audited.
    """
    target = _target(db, user, user_id)
    days = clean_weekdays(payload.weekdays)
    row = db.scalar(select(RemotePattern).where(RemotePattern.user_id == target.id))
    if row is None:
        row = RemotePattern(user_id=target.id, weekdays=days, updated_by_user_id=user.id)
        db.add(row)
    else:
        row.weekdays = days
        row.updated_by_user_id = user.id
    record_audit(db, user.id, "remote.week", entity="user", entity_id=target.id,
                 detail={"weekdays": days})
    db.commit()
    return {"user_id": target.id, "weekdays": days}


@router.put("/day/{user_id}")
def set_day(user_id: int, payload: DayIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """Change where a person works on one day, or go back to their usual week.

    PUT /api/presence/day/{user_id}  {"day": "2026-12-01", "location": "remote"}
    ``location`` is remote, onsite, or null (back to the usual week). A change
    equal to the usual week is not stored. Weekends are refused (422).
    Access: the person, or whoever manages their absences. Audited.
    """
    target = _target(db, user, user_id)
    if payload.location not in (None, "remote", "onsite"):
        raise HTTPException(status_code=422, detail="Lieu inconnu (remote ou onsite)")
    if payload.day.weekday() not in WORKDAYS:
        raise HTTPException(status_code=422, detail="Le samedi et le dimanche ne se planifient pas")
    pat = db.scalar(select(RemotePattern).where(RemotePattern.user_id == target.id))
    usual = "remote" if payload.day.weekday() in clean_weekdays(pat.weekdays if pat else []) else "onsite"
    row = db.scalar(select(RemoteDay).where(RemoteDay.user_id == target.id, RemoteDay.day == payload.day))
    keep = payload.location is not None and payload.location != usual
    if not keep:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(RemoteDay(user_id=target.id, day=payload.day, location=payload.location,
                         created_by_user_id=user.id))
    else:
        row.location = payload.location
        row.created_by_user_id = user.id
    record_audit(db, user.id, "remote.day", entity="user", entity_id=target.id,
                 detail={"day": payload.day.isoformat(), "location": payload.location or usual})
    db.commit()
    return {"user_id": target.id, "day": payload.day.isoformat(), "location": payload.location or usual,
            "changed": keep}
