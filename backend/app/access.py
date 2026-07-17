"""SSO access-approval workflow.

SSO authenticates *who* a user is; this module governs *whether* they may enter.
New SSO accounts are provisioned "pending" and must be validated by a manager:

  - admin        : validate anyone, any role / tribe (full rights);
  - tribe_leader : validate into their own tribe as squad_leader / member;
  - squad_leader : validate a person into one of their own squads (as member).

Denial disables the account (kept for audit). Visibility of the pending queue is
intentionally broad (a brand-new account has no tribe yet), but the *action* is
strictly scoped to what the approver may grant.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .deps import record_audit
from .models import Notification, Squad, User
from .rbac import ADMIN, MEMBER, SQUAD, TRIBE


def can_review_access(user: User) -> bool:
    """Who may open the access-request queue at all."""
    return user.role in (ADMIN, TRIBE, SQUAD)


def approval_roles(actor: User) -> list[str]:
    """Roles an approver may grant when validating a pending account."""
    if actor.role == ADMIN:
        return [ADMIN, TRIBE, SQUAD, MEMBER]
    if actor.role == TRIBE:
        return [SQUAD, MEMBER]
    if actor.role == SQUAD:
        return [MEMBER]
    return []


def pending_users(db: Session) -> list[User]:
    """All accounts awaiting validation (oldest first)."""
    return list(db.scalars(
        select(User).where(User.status == "pending").order_by(User.created_at.asc())
    ).all())


def pending_count(db: Session, reviewer: User) -> int:
    """Badge count of pending requests, or 0 for a viewer who can't review any.

    Returns the global pending total (the queue is intentionally broad — a
    brand-new account has no tribe yet), but only to actual reviewers so a plain
    member never sees a nonzero badge.
    """
    if not can_review_access(reviewer):
        return 0
    return int(db.scalar(select(func.count()).select_from(User).where(User.status == "pending")) or 0)


def led_squads(db: Session, actor: User) -> list[Squad]:
    """Squads an actor may validate someone into."""
    if actor.role == ADMIN:
        return list(db.scalars(select(Squad).order_by(Squad.display_order, Squad.id)).all())
    if actor.role == TRIBE:
        return list(db.scalars(select(Squad).where(Squad.tribe_id == actor.tribe_id)
                               .order_by(Squad.display_order, Squad.id)).all())
    if actor.role == SQUAD:
        return list(db.scalars(select(Squad).where(Squad.leader_user_id == actor.id)
                               .order_by(Squad.display_order, Squad.id)).all())
    return []


def approve(db: Session, actor: User, target: User, *, role: str,
            tribe_id: int | None, squad_id: int | None) -> User:
    """Validate a pending account: set role + tribe scope and activate it.
    Raises 4xx HTTPException when the actor exceeds their delegation scope."""
    if target.status != "pending":
        raise HTTPException(status_code=409, detail="Cette demande a déjà été traitée.")
    if role not in approval_roles(actor):
        raise HTTPException(status_code=403, detail="Vous ne pouvez pas attribuer ce rôle.")

    if actor.role == ADMIN:
        scope_tribe = tribe_id
        if squad_id is not None:
            sq = db.get(Squad, squad_id)
            if sq is None:
                raise HTTPException(status_code=404, detail="Squad introuvable")
            scope_tribe = sq.tribe_id
    elif actor.role == TRIBE:
        scope_tribe = actor.tribe_id
        if squad_id is not None:
            sq = db.get(Squad, squad_id)
            if sq is None or sq.tribe_id != actor.tribe_id:
                raise HTTPException(status_code=403, detail="Cette squad n'est pas dans votre tribe.")
    else:  # SQUAD leader: must place the person into one of their own squads.
        if squad_id is None:
            raise HTTPException(status_code=400, detail="Choisissez la squad d'accueil.")
        sq = db.get(Squad, squad_id)
        if sq is None or sq.leader_user_id != actor.id:
            raise HTTPException(status_code=403, detail="Vous ne pouvez valider que pour vos squads.")
        scope_tribe = sq.tribe_id

    target.status = "active"
    target.role = role
    target.tribe_id = scope_tribe
    record_audit(db, actor.id, "access.approve", entity="user", entity_id=target.id,
                 detail={"email": target.email, "role": role, "tribe_id": scope_tribe, "squad_id": squad_id})
    _notify_user_granted(db, target, actor)
    return target


def deny(db: Session, actor: User, target: User) -> User:
    """Reject / revoke an account. Reserved to admin & tribe leaders (gatekeepers)."""
    if actor.role not in (ADMIN, TRIBE):
        raise HTTPException(status_code=403, detail="Seuls un admin ou un tribe leader peuvent refuser un accès.")
    if target.is_break_glass:
        raise HTTPException(status_code=403, detail="Le compte de secours ne peut pas être désactivé.")
    target.status = "disabled"
    record_audit(db, actor.id, "access.deny", entity="user", entity_id=target.id,
                 detail={"email": target.email})
    return target


# ----- notifications ----------------------------------------------------------

def _reviewers(db: Session) -> list[User]:
    """Accounts that should hear about a new access request: active admins and
    tribe leaders (the gatekeepers)."""
    return list(db.scalars(
        select(User).where(User.status == "active", User.role.in_([ADMIN, TRIBE]))
    ).all())


def notify_access_request(db: Session, requester: User) -> None:
    """Ping the gatekeepers (in-app, best-effort email) about a pending request.
    Never let a notification failure break the login/provisioning path."""
    try:
        for r in _reviewers(db):
            db.add(Notification(user_id=r.id, kind="access_request", actor_name=requester.display_name,
                                excerpt=f"Demande d'accès : {requester.email}", link="/acces"))
        db.flush()
        _email_reviewers(db, requester)
    except Exception:
        pass


def _notify_user_granted(db: Session, target: User, actor: User) -> None:
    """In-app "welcome, your access is validated" notice for the approved user.
    Best-effort: never let a notification failure roll back the approval."""
    try:
        db.add(Notification(user_id=target.id, kind="access_granted", actor_name=actor.display_name,
                            excerpt="Votre accès a été validé. Bienvenue !", link="/"))
    except Exception:
        pass


def _email_reviewers(db: Session, requester: User) -> None:
    """Best-effort email to gatekeepers when SMTP is configured."""
    try:
        from .smtpconfig import get_smtp
        from .mail import send_email
        cfg = get_smtp(db)
        if not cfg.get("enabled"):
            return
        subject = f"Nouvelle demande d'accès : {requester.email}"
        body = (f"{requester.display_name} ({requester.email}) a été authentifié via SSO et "
                f"attend la validation de son accès.\n\nValidez ou refusez dans l'application "
                f"(menu « Accès »).")
        for r in _reviewers(db):
            if r.email:
                send_email(cfg, r.email, subject, body)
    except Exception:
        pass
