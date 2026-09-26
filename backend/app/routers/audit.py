"""Audit-log read endpoint.

Exposes the append-only AuditLog written across the app by record_audit. Read-only
and admin-only - there is no route to create or mutate entries here.

The endpoint is paginated and filterable rather than "the last N rows". On an
instance that has been running for a year the table holds hundreds of thousands of
entries, and the screen's real job is answering a question ("who disabled this
account", "what happened on the 12th"), which a truncated list of the most recent
rows cannot do. Ordering and the date filters ride the index on ``timestamp``.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import AuditLog, User
from ..schemas import AuditOut, AuditPage

router = APIRouter(prefix="/api/audit-log", tags=["audit"])

# Bounds the response whatever the caller asks for. 500 is already more than a
# person reads; the UI defaults to 50.
MAX_LIMIT = 500


@router.get("", response_model=AuditPage)
def list_audit(
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    action: str | None = Query(None, description="Case-insensitive substring of the action name."),
    entity: str | None = Query(None, description="Exact entity type, e.g. 'user' or 'squad'."),
    user_id: int | None = Query(None, description="Only entries recorded for this acting user."),
    since: datetime | None = Query(None, description="Inclusive lower bound on the timestamp."),
    until: datetime | None = Query(None, description="Inclusive upper bound on the timestamp."),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return one page of audit entries, newest first, with the total that matched.

    GET /api/audit-log?limit=&offset=&action=&entity=&user_id=&since=&until=
    Access: admin only (require_admin).

    ``total`` is the count for the filters, not the page, so the UI can say
    "showing 50 of 12480" and know whether a next page exists.
    """
    filters = []
    if action:
        filters.append(AuditLog.action.ilike(f"%{action.strip()}%"))
    if entity:
        filters.append(AuditLog.entity == entity.strip())
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if since is not None:
        filters.append(AuditLog.timestamp >= since)
    if until is not None:
        filters.append(AuditLog.timestamp <= until)

    total = db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0

    # The acting user is resolved here rather than by the UI: user_id alone is
    # unreadable, and the row must survive the deletion of that user (the FK is
    # nullable on purpose), so an outer join is the only correct shape.
    rows = db.execute(
        select(AuditLog, User.email, User.display_name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(*filters)
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    items = []
    for entry, email, display_name in rows:
        out = AuditOut.model_validate(entry).model_dump()
        out["user_email"] = email
        out["user_name"] = display_name
        items.append(out)

    return {"items": items, "total": total, "limit": limit, "offset": offset}
