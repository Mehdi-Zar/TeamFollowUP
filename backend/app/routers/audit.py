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
    limit = max(1, min(limit, 1000))
    rows = db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)).all()
    return list(rows)
