"""Helpers for per-user report subscriptions (global or per-squad)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import visible_tribe_id
from .models import ReportSubscription, Squad, User


def user_can_see_squad(db: Session, user: User, squad_id: int) -> bool:
    """Whether `user` may subscribe to a squad: admins see all, others only squads
    in their own tribe. Used to authorize per-squad subscription requests."""
    sq = db.get(Squad, squad_id)
    if sq is None:
        return False
    scope = visible_tribe_id(user)  # None = admin (all tribes)
    return scope is None or sq.tribe_id == scope


def get_subscription(db: Session, user_id: int, squad_id: int | None) -> ReportSubscription | None:
    """Fetch a user's subscription for a scope. squad_id=None is the global
    (all-visible-tribes) subscription; a squad id targets that single squad."""
    stmt = select(ReportSubscription).where(ReportSubscription.user_id == user_id)
    stmt = stmt.where(ReportSubscription.squad_id.is_(None) if squad_id is None
                      else ReportSubscription.squad_id == squad_id)
    return db.scalar(stmt)


def set_subscription(db: Session, user: User, squad_id: int | None, interval_days: int = 0,
                     weekdays: list[int] | None = None, hour: int | None = None) -> ReportSubscription | None:
    """Upsert a subscription. A subscription is active if it has weekdays (the new
    schedule) OR a positive interval (legacy). Empty/none of both removes it.
    Does not commit."""
    wd = sorted({int(d) for d in (weekdays or []) if 0 <= int(d) <= 6})
    hr = max(0, min(23, int(hour))) if hour is not None else None
    active = bool(wd) or interval_days > 0
    row = get_subscription(db, user.id, squad_id)
    if not active:
        if row is not None:
            db.delete(row)
        return None
    if row is None:
        row = ReportSubscription(user_id=user.id, squad_id=squad_id)
        db.add(row)
    # Reset the send clock when the schedule changes.
    if row.interval_days != interval_days or row.weekdays != wd or (hr is not None and row.hour != hr):
        row.last_sent_at = None
    row.interval_days = interval_days
    row.weekdays = wd
    if hr is not None:
        row.hour = hr
    return row


def list_subscriptions(db: Session, user: User) -> list[ReportSubscription]:
    """All of a user's subscriptions, global one first then per-squad by squad id."""
    return list(db.scalars(
        select(ReportSubscription).where(ReportSubscription.user_id == user.id)
        .order_by(ReportSubscription.squad_id.is_(None).desc(), ReportSubscription.squad_id)
    ).all())
