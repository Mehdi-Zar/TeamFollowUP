"""Helpers for per-user report subscriptions (global or per-squad)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ReportSubscription, Squad, User


def user_can_see_squad(db: Session, user: User, squad_id: int) -> bool:
    """Whether `user` may subscribe to a squad: admins see all, others only squads
    in their own tribe. Used to authorize per-squad subscription requests."""
    sq = db.get(Squad, squad_id)
    if sq is None:
        return False
    from .deps import can_read_squad
    return can_read_squad(user, sq)  # its tribe, or leading / contributing to it
