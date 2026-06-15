"""On-demand weekly-report downloads (HTML / PPTX) and manual email send.

The automatic weekly send lives in app.report.send_due_weekly_reports, driven by
the in-process scheduler in main.py.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import get_current_user, require_module
from ..models import User
from ..report import build_report_data, render_html, render_pptx

router = APIRouter(prefix="/api/reports", tags=["reports"],
                   dependencies=[Depends(require_module("review", "weekly_report"))])


def _resolve_scope(user: User, tribe_id: int | None) -> int | None:
    """Weekly report is a leader/admin artifact, scoped to visibility."""
    if user.role == "admin":
        return tribe_id
    if user.role == "tribe_leader":
        return user.tribe_id
    raise HTTPException(status_code=403, detail="Réservé aux tribe leaders et administrateurs")


def _data(db: Session, user: User, tribe_id: int | None, year: int | None, since_days: int) -> dict:
    scope = _resolve_scope(user, tribe_id)
    year = year or st.current_year_quarter()[0]
    return build_report_data(db, scope, year, since_days)


@router.get("/weekly.html", response_class=HTMLResponse)
def weekly_html(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                since_days: int = Query(default=7, ge=1, le=120),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = _data(db, user, tribe_id, year, since_days)
    return HTMLResponse(render_html(data, standalone=True))


@router.get("/weekly.pptx")
def weekly_pptx(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                since_days: int = Query(default=7, ge=1, le=120),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = _data(db, user, tribe_id, year, since_days)
    try:
        payload = render_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    filename = f"rapport_hebdo_{data['year']}.pptx"
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/weekly/email")
def weekly_email(payload: dict = Body(default=None), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Send the report now to a chosen address (HTML body + PPTX attachment)."""
    from ..smtpconfig import get_smtp
    from ..mail import send_email

    payload = payload or {}
    to = (payload.get("to") or user.email or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="Adresse destinataire requise")
    tribe_id = payload.get("tribe_id")
    year = payload.get("year")
    since_days = int(payload.get("since_days") or 7)

    cfg = get_smtp(db)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="SMTP non configuré (activez-le dans l'Administration)")

    data = _data(db, user, tribe_id, year, since_days)
    html_body = render_html(data, standalone=True)
    attachment = None
    try:
        pptx_bytes = render_pptx(data)
        attachment = (f"rapport_hebdo_{data['year']}.pptx", pptx_bytes,
                      "application", "vnd.openxmlformats-officedocument.presentationml.presentation")
    except ImportError:
        pass  # send HTML-only if PPTX backend unavailable

    subject = f"{data['app_name']} — Rapport hebdomadaire"
    ok = send_email(cfg, to, subject, html_body, attachment=attachment, html=True)
    if not ok:
        raise HTTPException(status_code=502, detail="L'envoi de l'email a échoué (vérifiez la configuration SMTP)")
    return {"ok": True, "to": to}
