"""Helpers for per-user report subscriptions (global or per-squad)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import visible_tribe_id
from .models import ReportSubscription, Squad, User


def user_can_see_squad(db: Session, user: User, squad_id: int) -> bool:
    sq = db.get(Squad, squad_id)
    if sq is None:
        return False
    scope = visible_tribe_id(user)  # None = admin (all tribes)
    return scope is None or sq.tribe_id == scope


def get_subscription(db: Session, user_id: int, squad_id: int | None) -> ReportSubscription | None:
    stmt = select(ReportSubscription).where(ReportSubscription.user_id == user_id)
    stmt = stmt.where(ReportSubscription.squad_id.is_(None) if squad_id is None
                      else ReportSubscription.squad_id == squad_id)
    return db.scalar(stmt)


def set_subscription(db: Session, user: User, squad_id: int | None, interval_days: int) -> ReportSubscription | None:
    """Upsert a subscription. interval_days <= 0 removes it. Does not commit."""
    row = get_subscription(db, user.id, squad_id)
    if interval_days <= 0:
        if row is not None:
            db.delete(row)
        return None
    if row is None:
        row = ReportSubscription(user_id=user.id, squad_id=squad_id, interval_days=interval_days)
        db.add(row)
    else:
        if row.interval_days != interval_days:
            row.last_sent_at = None  # restart the clock on a cadence change
        row.interval_days = interval_days
    return row


def list_subscriptions(db: Session, user: User) -> list[ReportSubscription]:
    return list(db.scalars(
        select(ReportSubscription).where(ReportSubscription.user_id == user.id)
        .order_by(ReportSubscription.squad_id.is_(None).desc(), ReportSubscription.squad_id)
    ).all())
