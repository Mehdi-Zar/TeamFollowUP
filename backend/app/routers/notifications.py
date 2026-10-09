"""In-app notifications and per-user notification preferences.

The /notifications/* routes serve the current user's own notification inbox and are
gated by the `notifications > inapp` sub-module. The /me/preferences routes let a
user tune what they get notified about; they
are always available (no module gate) since they are personal settings.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_module, update_data
from ..models import Notification, User
from ..schemas import NotificationsResponse, PreferencesOut, PreferencesUpdate

router = APIRouter(prefix="/api", tags=["notifications"])

# Shared gate: the in-app notification sub-module must be enabled (admin toggle).
_inapp = Depends(require_module("notifications", "inapp"))


@router.get("/notifications", response_model=NotificationsResponse, dependencies=[_inapp])
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Return the caller's 40 most recent notifications plus an unread count.

    GET /api/notifications
    Access: any authenticated user (own inbox only); gated by `notifications > inapp`.
    """
    items = db.scalars(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(40)
    ).all()
    unread = sum(1 for n in items if not n.is_read)
    return NotificationsResponse(unread_count=unread, items=list(items))


@router.post("/notifications/read-all", dependencies=[_inapp])
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Mark all of the caller's unread notifications as read.

    POST /api/notifications/read-all
    Access: any authenticated user (own inbox only); gated by `notifications > inapp`.
    """
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False)).values(is_read=True))
    db.commit()
    return {"ok": True}


@router.post("/notifications/{notif_id}/read", dependencies=[_inapp])
def mark_read(notif_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Mark a single notification as read.

    POST /api/notifications/{notif_id}/read
    Access: any authenticated user; gated by `notifications > inapp`.
    Returns 404 when the notification does not exist or belongs to someone else
    (ownership check doubles as the access guard).
    """
    n = db.get(Notification, notif_id)
    # 404 (not 403) when it isn't the caller's own, to avoid leaking existence.
    if n is None or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    n.is_read = True
    db.commit()
    return {"ok": True}


@router.get("/me/preferences", response_model=PreferencesOut)
def get_preferences(user: User = Depends(get_current_user)):
    """Return the caller's notification preferences.

    GET /api/me/preferences
    Access: any authenticated user (own settings). No module gate.
    """
    return PreferencesOut(notify_tweets=user.notify_tweets, notify_replies=user.notify_replies,
                          email_notifications=user.email_notifications)


@router.put("/me/preferences", response_model=PreferencesOut)
def update_preferences(payload: PreferencesUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Update the caller's notification preferences.

    PUT /api/me/preferences
    Access: any authenticated user (own settings). No module gate.
    """
    data = update_data(payload, User)
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    return PreferencesOut(notify_tweets=user.notify_tweets, notify_replies=user.notify_replies,
                          email_notifications=user.email_notifications)
