from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_module
from ..models import Notification, User
from ..schemas import NotificationsResponse, PreferencesOut, PreferencesUpdate

router = APIRouter(prefix="/api", tags=["notifications"])

_inapp = Depends(require_module("notifications", "inapp"))


@router.get("/notifications", response_model=NotificationsResponse, dependencies=[_inapp])
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = db.scalars(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(40)
    ).all()
    unread = sum(1 for n in items if not n.is_read)
    return NotificationsResponse(unread_count=unread, items=list(items))


@router.post("/notifications/read-all", dependencies=[_inapp])
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False)).values(is_read=True))
    db.commit()
    return {"ok": True}


@router.post("/notifications/{notif_id}/read", dependencies=[_inapp])
def mark_read(notif_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, notif_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    n.is_read = True
    db.commit()
    return {"ok": True}


@router.get("/me/preferences", response_model=PreferencesOut)
def get_preferences(user: User = Depends(get_current_user)):
    return PreferencesOut(notify_tweets=user.notify_tweets, notify_replies=user.notify_replies,
                          email_notifications=user.email_notifications,
                          subscribe_weekly_report=user.subscribe_weekly_report)


@router.put("/me/preferences", response_model=PreferencesOut)
def update_preferences(payload: PreferencesUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = payload.model_dump(exclude_unset=True)
    # The weekly-report toggle drives the personal subscription cadence
    # (on = weekly / 7 days, off = unsubscribed); keep both representations aligned.
    if "subscribe_weekly_report" in data:
        on = bool(data["subscribe_weekly_report"])
        if on and user.report_interval_days == 0:
            user.report_interval_days = 7
            user.report_last_sent_at = None
        elif not on:
            user.report_interval_days = 0
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    return PreferencesOut(notify_tweets=user.notify_tweets, notify_replies=user.notify_replies,
                          email_notifications=user.email_notifications,
                          subscribe_weekly_report=user.subscribe_weekly_report)
