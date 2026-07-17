"""Access-request queue: validate SSO-provisioned accounts.

Available to managers (admin / tribe leader / squad leader). The queue is the set
of pending accounts; each approver can only grant within their delegation scope
(enforced in app.access). See docs/05-security.md.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import access as acc
from ..database import get_db
from ..deps import get_current_user
from ..models import Squad, Tribe, User
from ..rbac import ADMIN, TRIBE
from ..schemas import AccessApproveIn, AccessRequestOut, UserOut

router = APIRouter(prefix="/api/access-requests", tags=["access"])


def _require_reviewer(user: User = Depends(get_current_user)) -> User:
    """Router-wide guard: only managers (admin/tribe/squad leader) reach the queue.

    Coarse gate for *viewing* the queue; the finer per-request delegation limits
    live in ``app.access`` (approve/deny), so scope is always re-checked on the
    mutating action, never trusted from this guard alone.
    """
    if not acc.can_review_access(user):
        raise HTTPException(status_code=403, detail="Réservé aux managers.")
    return user


@router.get("")
def list_requests(db: Session = Depends(get_db), user: User = Depends(_require_reviewer)):
    """Pending requests + the options THIS reviewer may assign (roles, squads,
    tribes), so the SPA can render a correctly-scoped validation form."""
    squads = acc.led_squads(db, user)
    if user.role == ADMIN:
        tribes = list(db.scalars(select(Tribe).order_by(Tribe.display_order, Tribe.id)).all())
    elif user.role == TRIBE and user.tribe_id is not None:
        tribes = [t for t in [db.get(Tribe, user.tribe_id)] if t]
    else:
        tribes = []
    return {
        "requests": [AccessRequestOut.model_validate(u).model_dump() for u in acc.pending_users(db)],
        "roles": acc.approval_roles(user),
        "can_deny": user.role in (ADMIN, TRIBE),
        "tribe_locked": user.role != ADMIN,
        "squads": [{"id": s.id, "name": s.name, "tribe_id": s.tribe_id} for s in squads],
        "tribes": [{"id": t.id, "name": t.name} for t in tribes],
    }


def _target(db: Session, user_id: int) -> User:
    """Load the pending account being acted on, or 404 if it does not exist."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    return target


@router.post("/{user_id}/approve", response_model=UserOut)
def approve_request(user_id: int, payload: AccessApproveIn, db: Session = Depends(get_db),
                    user: User = Depends(_require_reviewer)):
    """Validate a pending account with the requested role/tribe/squad.

    Delegation limits (which roles/tribes/squads this reviewer may grant) are
    enforced inside ``acc.approve`` and surface as 4xx errors.
    """
    target = acc.approve(db, user, _target(db, user_id), role=payload.role,
                         tribe_id=payload.tribe_id, squad_id=payload.squad_id)
    db.commit()
    db.refresh(target)
    return target


@router.post("/{user_id}/deny", response_model=UserOut)
def deny_request(user_id: int, db: Session = Depends(get_db), user: User = Depends(_require_reviewer)):
    """Reject/revoke an account (disables it). Restricted to admin & tribe leaders
    inside ``acc.deny``; the break-glass account cannot be denied."""
    target = acc.deny(db, user, _target(db, user_id))
    db.commit()
    db.refresh(target)
    return target
