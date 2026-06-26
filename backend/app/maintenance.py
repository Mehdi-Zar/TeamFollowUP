"""Periodic data retention/cleanup, driven by the in-process scheduler.

Retention is opt-in (0 = keep forever). Progress purge keeps weekly/review points
(only the coalesced `auto` edits are pruned), so the review timeline stays meaningful.
"""
import logging
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .config import settings
from .models import AuditLog, ProgressUpdate, utcnow

logger = logging.getLogger("trt.maintenance")


def purge_old_records(db: Session) -> dict:
    out: dict[str, int] = {}
    now = utcnow()
    if settings.audit_retention_days > 0:
        cutoff = now - timedelta(days=settings.audit_retention_days)
        out["audit"] = db.execute(delete(AuditLog).where(AuditLog.timestamp < cutoff)).rowcount or 0
    if settings.progress_retention_days > 0:
        cutoff = now - timedelta(days=settings.progress_retention_days)
        out["progress_auto"] = db.execute(
            delete(ProgressUpdate).where(ProgressUpdate.created_at < cutoff,
                                         ProgressUpdate.kind == "auto")
        ).rowcount or 0
    if any(out.values()):
        db.commit()
        logger.info("retention purge: %s", out)
    return out
