"""Who runs and who reads the Steerco (ADR 0018).

Two levels, nothing in between:

* **run** (enter the figures, validate and reopen months, declare platforms, import,
  send the pack, design the platform slides in the Studio): the administrator on
  every tribe; a tribe leader on their own tribe, by default; any user designated
  Steerco leader of a tribe (``steerco_leaders``), whatever their role.
* **read** (open the Steerco menu, preview any month, export): whoever runs it, and
  the personas the administrator granted the ``steerco`` capability, on their own
  tribe. Closed by default: the slide shows degraded SLAs and risks before the
  committee has seen them.

A tribe leader's default designation is a real one: the administrator can take it
away (an ``excluded`` row), for a tribe that hands its Steerco entirely to a PMO.
Only the administrator and the tribe leader designate; a Steerco leader cannot
designate another one, so access to the committee's figures never spreads past the
person accountable for the tribe.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import SteercoLeader, Tribe, User

ADMIN = "admin"
TRIBE = "tribe_leader"


def _rows(db: Session, user: User) -> list[SteercoLeader]:
    if user.id is None:
        return []
    return db.query(SteercoLeader).filter(SteercoLeader.user_id == user.id).all()


def led_tribe_ids(db: Session, user: User) -> set[int] | None:
    """The tribes whose Steerco ``user`` runs; None means every tribe (admin)."""
    if user.role == ADMIN:
        return None
    rows = _rows(db, user)
    out = {r.tribe_id for r in rows if not r.excluded}
    if user.role == TRIBE and user.tribe_id is not None:
        if not any(r.tribe_id == user.tribe_id and r.excluded for r in rows):
            out.add(user.tribe_id)
    return out


def runs(db: Session, user: User, tribe_id: int | None) -> bool:
    """May ``user`` run the Steerco of ``tribe_id``."""
    ids = led_tribe_ids(db, user)
    return ids is None or (tribe_id is not None and tribe_id in ids)


def runs_any(db: Session, user: User) -> bool:
    ids = led_tribe_ids(db, user)
    return ids is None or bool(ids)


def has_read_capability(db: Session, user: User) -> bool:
    from .personasconfig import can
    return can(db, user, "steerco")


def readable_tribe_ids(db: Session, user: User) -> set[int] | None:
    """Tribes whose Steerco ``user`` may read; None means every tribe."""
    ids = led_tribe_ids(db, user)
    if ids is None:
        return None
    out = set(ids)
    if user.tribe_id is not None and has_read_capability(db, user):
        out.add(user.tribe_id)
    return out


def can_read(db: Session, user: User) -> bool:
    ids = readable_tribe_ids(db, user)
    return ids is None or bool(ids)


def _current_user_dep():
    from .deps import get_current_user
    return get_current_user


def reader_dep():
    """Route guard: anyone who may read some tribe's Steerco. 403 otherwise."""
    get_current_user = _current_user_dep()

    def dep(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
        if not can_read(db, user):
            raise HTTPException(status_code=403, detail="Le Steerco ne vous est pas ouvert")
        return user
    return dep


def runner_dep():
    """Route guard: anyone who runs some tribe's Steerco. Each route then checks
    the tribe of what it touches with :func:`ensure_runs`."""
    get_current_user = _current_user_dep()

    def dep(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
        if not runs_any(db, user):
            raise HTTPException(status_code=403, detail="Réservé aux Steerco leaders")
        return user
    return dep


def ensure_runs(db: Session, user: User, tribe_id: int | None) -> None:
    if not runs(db, user, tribe_id):
        raise HTTPException(status_code=403, detail="Réservé aux Steerco leaders de cette tribe")


def can_designate(user: User, tribe_id: int) -> bool:
    """The administrator anywhere, the tribe leader on their own tribe."""
    return user.role == ADMIN or (user.role == TRIBE and user.tribe_id == tribe_id)


def leaders_of(db: Session, tribe_id: int) -> list[dict]:
    """The tribe's Steerco leaders: its tribe leaders (by default, unless excluded)
    then the designated users, each with how they hold it."""
    rows = {r.user_id: r for r in db.query(SteercoLeader).filter(SteercoLeader.tribe_id == tribe_id)}
    out = []
    tls = (db.query(User).filter(User.role == TRIBE, User.tribe_id == tribe_id)
           .order_by(User.display_name).all())
    for u in tls:
        r = rows.get(u.id)
        out.append({"user_id": u.id, "display_name": u.display_name, "email": u.email,
                    "role": u.role, "by_default": True, "active": not (r and r.excluded)})
    tl_ids = {u.id for u in tls}
    designated = [r for r in rows.values() if r.user_id not in tl_ids and not r.excluded]
    for r in sorted(designated, key=lambda r: (r.user.display_name or "").lower()):
        out.append({"user_id": r.user_id, "display_name": r.user.display_name,
                    "email": r.user.email, "role": r.user.role, "by_default": False,
                    "active": True})
    return out


def leader_emails(db: Session, tribe_id: int) -> list[str]:
    """Addresses of the tribe's active Steerco leaders (for the monthly reminder)."""
    ids = [x["user_id"] for x in leaders_of(db, tribe_id) if x["active"]]
    if not ids:
        return []
    users = db.query(User).filter(User.id.in_(ids)).all()
    return sorted({u.email for u in users if u.email and (u.status or "active") == "active"})


def summary(db: Session, user: User) -> dict:
    """What the SPA needs to build the Steerco menu."""
    led = led_tribe_ids(db, user)
    read = readable_tribe_ids(db, user)
    names = {t.id: t.name for t in db.query(Tribe).all()}
    return {
        "read": read is None or bool(read),
        "run": led is None or bool(led),
        "all_tribes": led is None,
        "run_tribe_ids": sorted(names) if led is None else sorted(led),
        "read_tribe_ids": sorted(names) if read is None else sorted(read),
        "designate_tribe_ids": sorted(names) if user.role == ADMIN
        else ([user.tribe_id] if user.role == TRIBE and user.tribe_id else []),
    }
