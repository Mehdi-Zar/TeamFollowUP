"""Who runs, fills in and reads the Customer Success projects (ADR 0020).

The same three levels as the Steerco (app/steercoaccess.py), on another topic:

* **run** (create and delete projects, name their contributors, set the stages and
  the offers, copy the recap): the administrator on every tribe; a tribe leader on
  their own tribe, by default; any user designated CS leader of a tribe
  (``cs_leaders``), whatever their role.
* **contribute**: fill in the projects a CS leader named you on (``cs_contributors``):
  their card, their journal, their points to follow. Only those projects are visible.
* **read**: whoever runs it, and the personas the administrator granted the
  ``customer_success`` capability, on their own tribe.

Only the administrator and the tribe leader designate CS leaders, and only the
administrator takes a tribe leader's default designation away.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import CsContributor, CsLeader, CsProject, Tribe, User

ADMIN = "admin"
TRIBE = "tribe_leader"


def _rows(db: Session, user: User) -> list[CsLeader]:
    if user.id is None:
        return []
    return db.query(CsLeader).filter(CsLeader.user_id == user.id).all()


def led_tribe_ids(db: Session, user: User) -> set[int] | None:
    """The tribes whose CS projects ``user`` runs; None means every tribe (admin)."""
    if user.role == ADMIN:
        return None
    rows = _rows(db, user)
    out = {r.tribe_id for r in rows if not r.excluded}
    if user.role == TRIBE and user.tribe_id is not None:
        if not any(r.tribe_id == user.tribe_id and r.excluded for r in rows):
            out.add(user.tribe_id)
    return out


def runs(db: Session, user: User, tribe_id: int | None) -> bool:
    ids = led_tribe_ids(db, user)
    return ids is None or (tribe_id is not None and tribe_id in ids)


def runs_any(db: Session, user: User) -> bool:
    ids = led_tribe_ids(db, user)
    return ids is None or bool(ids)


def has_read_capability(db: Session, user: User) -> bool:
    from .personasconfig import can
    return can(db, user, "customer_success")


def readable_tribe_ids(db: Session, user: User) -> set[int] | None:
    """Tribes whose whole CS list ``user`` may read; None means every tribe."""
    ids = led_tribe_ids(db, user)
    if ids is None:
        return None
    out = set(ids)
    if user.tribe_id is not None and has_read_capability(db, user):
        out.add(user.tribe_id)
    return out


def reads_tribe(db: Session, user: User, tribe_id: int) -> bool:
    ids = readable_tribe_ids(db, user)
    return ids is None or tribe_id in ids


def contributed_project_ids(db: Session, user: User) -> set[int]:
    if user.id is None:
        return set()
    return {r.project_id for r in
            db.query(CsContributor).filter(CsContributor.user_id == user.id).all()}


def can_see(db: Session, user: User, project: CsProject) -> bool:
    return reads_tribe(db, user, project.tribe_id) or project.id in contributed_project_ids(db, user)


def can_edit(db: Session, user: User, project: CsProject) -> bool:
    """A CS leader of its tribe, or one of its contributors."""
    return runs(db, user, project.tribe_id) or project.id in contributed_project_ids(db, user)


def opens_menu(db: Session, user: User) -> bool:
    ids = readable_tribe_ids(db, user)
    return (ids is None or bool(ids) or bool(contributed_project_ids(db, user))
            or bool(designate_tribe_ids(db, user)))


def ensure_runs(db: Session, user: User, tribe_id: int | None) -> None:
    if not runs(db, user, tribe_id):
        raise HTTPException(status_code=403, detail="Réservé aux responsables Customer Success de cette tribe")


def ensure_edit(db: Session, user: User, project: CsProject) -> None:
    if not can_see(db, user, project):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if not can_edit(db, user, project):
        raise HTTPException(status_code=403, detail="Ce projet ne vous est ouvert qu'en lecture")


def can_designate(user: User, tribe_id: int) -> bool:
    return user.role == ADMIN or (user.role == TRIBE and user.tribe_id == tribe_id)


def designate_tribe_ids(db: Session, user: User) -> list[int]:
    if user.role == ADMIN:
        return sorted(t.id for t in db.query(Tribe).all())
    return [user.tribe_id] if user.role == TRIBE and user.tribe_id else []


def leaders_of(db: Session, tribe_id: int) -> list[dict]:
    """The tribe's CS leaders: its tribe leaders (by default, unless excluded) then
    the designated users, each with how they hold it."""
    rows = {r.user_id: r for r in db.query(CsLeader).filter(CsLeader.tribe_id == tribe_id)}
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


def contributors_of(project: CsProject) -> list[dict]:
    out = [{"id": r.user_id, "name": r.user.display_name or r.user.email, "email": r.user.email}
           for r in project.contributors if r.user is not None]
    return sorted(out, key=lambda x: (x["name"] or "").lower())


def summary(db: Session, user: User) -> dict:
    """What the SPA needs to build the Customer Success menu."""
    led = led_tribe_ids(db, user)
    read = readable_tribe_ids(db, user)
    names = sorted(t.id for t in db.query(Tribe).all())
    contrib = sorted(contributed_project_ids(db, user))
    contrib_tribes = sorted({p.tribe_id for p in
                             db.query(CsProject).filter(CsProject.id.in_(contrib or [-1]))})
    return {
        "contribute": bool(contrib),
        "contribute_project_ids": contrib,
        "contribute_tribe_ids": contrib_tribes,
        "read": read is None or bool(read),
        "run": led is None or bool(led),
        "all_tribes": led is None,
        "run_tribe_ids": names if led is None else sorted(led),
        "read_tribe_ids": names if read is None else sorted(read),
        "designate_tribe_ids": designate_tribe_ids(db, user),
    }
