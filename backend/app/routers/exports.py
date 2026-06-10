import csv
import io

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import assert_tribe_scope, get_current_user, get_threshold, visible_tribe_id
from ..models import Squad, User
from ..schemas import EmailExportIn

router = APIRouter(prefix="/api/exports", tags=["exports"])


def _to_csv(header, rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _dashboard_csv(db: Session, user: User, year: int | None) -> tuple[str, str]:
    threshold = get_threshold(db)
    cur_year, cur_q = st.current_year_quarter()
    year = year or cur_year
    q = select(Squad).order_by(Squad.display_order, Squad.id)
    scope = visible_tribe_id(user)
    if scope is not None:
        q = q.where(Squad.tribe_id == scope)
    squads = db.scalars(q).all()
    ref_q = cur_q if year == cur_year else None
    rows = []
    for s in squads:
        c = st.counts(s, year)
        f = st.freshness(s, threshold)
        p = st.year_progress(s, year)
        rows.append([
            s.name, s.leader.display_name if s.leader else "", st.squad_status(s, year, ref_q),
            p[1], p[2], p[3], p[4], c["roadmap_blocked"], c["roadmap_at_risk"], c["objectives_red"],
            f.get("age_days") if f.get("age_days") is not None else "", "oui" if f.get("is_stale") else "non",
        ])
    header = ["squad", "responsable", "statut", "q1_pct", "q2_pct", "q3_pct", "q4_pct",
              "jalons_bloques", "jalons_a_risque", "objectifs_rouges", "fraicheur_jours", "perime"]
    return f"dashboard_{year}.csv", _to_csv(header, rows)


def _squad_csv(squad: Squad, year: int | None) -> tuple[str, str]:
    year = year or st.current_year_quarter()[0]
    rows = []
    for o in squad.objectives:
        if o.year == year:
            rows.append(["objectif", "", o.title, o.rag_status, o.target_date.date().isoformat() if o.target_date else "", "", ""])
    for r in sorted(squad.roadmap_items, key=lambda x: (x.quarter, x.display_order, x.id)):
        if r.year == year:
            rows.append(["jalon", f"Q{r.quarter}", r.title, r.status, r.owner or "", "", ""])
    for k in squad.kpis:
        rows.append(["kpi", "", k.name, k.trend_status, "",
                     k.current_value if k.current_value is not None else "",
                     k.target_value if k.target_value is not None else ""])
    header = ["type", "quarter", "intitule", "statut", "owner_echeance", "valeur", "cible"]
    safe = "".join(ch if ch.isalnum() else "_" for ch in squad.name).lower()
    return f"squad_{safe}_{year}.csv", _to_csv(header, rows)


def _csv_response(filename: str, text: str) -> StreamingResponse:
    return StreamingResponse(iter([text]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _email_csv(db: Session, to: str, subject: str, filename: str, text: str) -> bool:
    from ..smtpconfig import get_smtp
    from ..mail import send_email
    cfg = get_smtp(db)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="SMTP non configuré (activez-le dans l'Administration)")
    body = f"Bonjour,\n\nVous trouverez en pièce jointe l'export demandé depuis Tribe Cockpit.\n\n— Tribe Cockpit"
    ok = send_email(cfg, to, subject, body, attachment=(filename, text.encode("utf-8"), "text", "csv"))
    if not ok:
        raise HTTPException(status_code=502, detail="L'envoi de l'email a échoué (vérifiez la configuration SMTP)")
    return ok


@router.get("/dashboard.csv")
def export_dashboard_csv(year: int | None = Query(default=None),
                         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    filename, text = _dashboard_csv(db, user, year)
    return _csv_response(filename, text)


@router.post("/dashboard/email")
def email_dashboard_csv(payload: EmailExportIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    filename, text = _dashboard_csv(db, user, payload.year)
    _email_csv(db, payload.to, "Tribe Cockpit — export du dashboard", filename, text)
    return {"ok": True, "to": payload.to}


@router.get("/squad/{squad_id}.csv")
def export_squad_csv(squad_id: int, year: int | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    filename, text = _squad_csv(squad, year)
    return _csv_response(filename, text)


@router.post("/squad/{squad_id}/email")
def email_squad_csv(squad_id: int, payload: EmailExportIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    filename, text = _squad_csv(squad, payload.year)
    _email_csv(db, payload.to, f"Tribe Cockpit — rapport {squad.name}", filename, text)
    return {"ok": True, "to": payload.to}
