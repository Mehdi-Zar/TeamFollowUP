from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import get_current_user, get_threshold, visible_tribe_id
from ..models import Squad, User
from ..schemas import DashboardOut, DashboardSummary
from ..serializers import squad_card

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def get_dashboard(year: int | None = Query(default=None), tribe_id: int | None = Query(default=None),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    threshold = get_threshold(db)
    cur_year, cur_q = st.current_year_quarter()
    if year is None:
        year = cur_year
    q = select(Squad).order_by(Squad.display_order, Squad.id)
    scope = visible_tribe_id(user)
    if scope is not None:
        q = q.where(Squad.tribe_id == scope)
    elif tribe_id is not None:
        q = q.where(Squad.tribe_id == tribe_id)
    squads = db.scalars(q).all()
    cards = [squad_card(s, year, threshold) for s in squads]
    cards.sort(key=lambda c: (-c.risk_rank, -c.blocked_count, c.name.lower()))

    avg = round(sum(c.annual_progress for c in cards) / len(cards)) if cards else 0
    summary = DashboardSummary(
        squads_total=len(cards),
        blocked_jalons=sum(c.blocked_count for c in cards),
        at_risk_jalons=sum(c.at_risk_count for c in cards),
        squads_stale=sum(1 for c in cards if c.freshness.get("is_stale")),
        avg_progress=avg,
    )
    return DashboardOut(year=year, current_year=cur_year, current_quarter=cur_q, summary=summary, cards=cards)
