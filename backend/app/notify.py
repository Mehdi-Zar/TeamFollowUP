"""Create in-app notifications (and optional emails) for feed events."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .mail import send_async
from .models import FeedPost, FeedReply, Notification, User
from .modulesconfig import get_modules, is_active
from .smtpconfig import get_smtp


def _excerpt(text: str, n: int = 140) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def _emit(db: Session, smtp: dict, mods: dict, user: User, kind: str, actor: str,
          excerpt: str, link: str, subject: str) -> None:
    if is_active(mods, "notifications", "inapp"):
        db.add(Notification(user_id=user.id, kind=kind, actor_name=actor, excerpt=excerpt, link=link))
    email_on = is_active(mods, "notifications", "email")
    if email_on and user.email_notifications and user.email and smtp.get("enabled"):
        body = f"{actor} - {excerpt}\n\nOuvrir : (votre instance Tribe Cockpit){link}"
        send_async(smtp, user.email, subject, body)


def notify_new_post(db: Session, post: FeedPost) -> None:
    mods = get_modules(db)
    if not is_active(mods, "notifications"):
        return
    smtp = get_smtp(db)
    actor = post.author.display_name if post.author else "Quelqu'un"
    excerpt = _excerpt(post.content)
    q = select(User).where(User.notify_tweets.is_(True), User.id != post.author_user_id)
    if post.tribe_id is not None:
        q = q.where(User.tribe_id == post.tribe_id)
    for user in db.scalars(q).all():
        _emit(db, smtp, mods, user, "tweet", actor, excerpt, "/fil", f"Nouveau message - {actor}")


def notify_reply(db: Session, post: FeedPost, reply: FeedReply) -> None:
    if post.author_user_id is None or post.author_user_id == reply.author_user_id:
        return
    mods = get_modules(db)
    if not is_active(mods, "notifications"):
        return
    target = db.get(User, post.author_user_id)
    if target is None or not target.notify_replies:
        return
    smtp = get_smtp(db)
    actor = reply.author.display_name if reply.author else "Quelqu'un"
    _emit(db, smtp, mods, target, "reply", actor, _excerpt(reply.content), "/fil", f"Réponse à votre message - {actor}")
