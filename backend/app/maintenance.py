"""Periodic data retention/cleanup, driven by the in-process scheduler.

Retention is opt-in (0 = keep forever) and applies to the two kinds of record
that accumulate without anyone deciding to keep them: the audit trail, and the
feed. Everything else in this application is content somebody entered on purpose
and expects to find again.

The feed purge exists because the setting was lying. "Message retention (days)"
only ever *hid* old posts from the listing endpoint: they stayed in the database
and in every backup, forever. An administrator who set it to satisfy a retention
policy had not satisfied anything.
"""
import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .generalconfig import get_general
from .models import AuditLog, FeedPost, utcnow

logger = logging.getLogger("trt.maintenance")


def purge_old_records(db: Session) -> dict:
    """Delete records older than their configured retention window.

    Prunes the audit log past ``audit_retention_days`` (environment) and feed
    posts past ``feed_retention_days`` (Administration > Settings). Both are
    opt-in: 0 means "keep forever" and is skipped. Commits only when something
    was actually deleted. Returns per-table deleted-row counts.
    """
    out: dict[str, int] = {}
    now = utcnow()

    if settings.audit_retention_days > 0:
        cutoff = now - timedelta(days=settings.audit_retention_days)
        out["audit"] = db.execute(delete(AuditLog).where(AuditLog.timestamp < cutoff)).rowcount or 0

    feed_days = int(get_general(db).get("feed_retention_days") or 0)
    if feed_days > 0:
        cutoff = now - timedelta(days=feed_days)
        # Pinned posts are exempt: pinning is somebody deciding this one stays,
        # and the listing already treats them that way.
        stale = db.scalars(select(FeedPost).where(
            FeedPost.is_pinned.is_(False), FeedPost.created_at < cutoff)).all()
        # Deleted through the ORM, one by one, so the cascade declared on
        # FeedPost.replies / .reactions actually runs. A bulk delete() would skip
        # it and fail on the foreign keys, which have no ON DELETE CASCADE.
        for post in stale:
            db.delete(post)
        out["feed"] = len(stale)

    if any(out.values()):
        db.commit()
        logger.info("retention purge: %s", out)
    return out
