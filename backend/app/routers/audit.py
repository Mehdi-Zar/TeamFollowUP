"""Audit-log read endpoint.

Exposes the append-only AuditLog written across the app by record_audit. Read-only
and admin-only - there is no route to create or mutate entries here.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import AuditLog, User
from ..schemas import AuditOut

router = APIRouter(prefix="/api/audit-log", tags=["audit"])


@router.get("", response_model=list[AuditOut])
def list_audit(limit: int = 200, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Return the most recent audit-log entries, newest first.

    GET /api/audit-log?limit=...
    Access: admin only (require_admin). The limit is clamped to 1..1000 to bound
    the response regardless of the value requested.
    """
    limit = max(1, min(limit, 1000))
    rows = db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)).all()
    return list(rows)
