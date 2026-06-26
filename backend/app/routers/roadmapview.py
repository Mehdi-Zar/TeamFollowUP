"""In-app global roadmap matrix (quarters × squads), the on-screen counterpart of
the roadmap export. Gated by the roadmap module + the 'roadmap' persona capability."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import get_current_user, require_capability, require_module
from ..models import User
from ..report import build_report_data

router = APIRouter(prefix="/api/roadmap", tags=["roadmap-view"],
                   dependencies=[Depends(require_module("squad_content", "roadmap")),
                                 Depends(require_capability("roadmap"))])


@router.get("/matrix")
def roadmap_matrix(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                   lang: str | None = Query(default=None),
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Roadmap matrix scoped to the caller's visibility (admin may target a tribe)."""
    year = year or st.current_year_quarter()[0]
    scope = tribe_id if user.role == "admin" else user.tribe_id
    data = build_report_data(db, scope, year, 7, lang=lang)
    tribes = [
        {
            "tribe_id": blk["tribe_id"],
            "tribe_name": blk["tribe_name"],
            "squads": [
                {
                    "squad_id": r["squad_id"],
                    "name": r["name"],
                    "annual_pct": r["annual_pct"],
                    "quarters": (r.get("detail") or {}).get("quarters", []),
                }
                for r in blk["squads"]
            ],
        }
        for blk in data["tribes"]
    ]
    return {"year": data["year"], "scope_name": data["scope_name"], "tribes": tribes}
