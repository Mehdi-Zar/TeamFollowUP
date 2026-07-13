"""On-demand weekly-report downloads (HTML / PPTX) and manual email send.

The automatic weekly send lives in app.report.send_due_weekly_reports, driven by
the in-process scheduler in main.py.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..deps import (caller, caller_has_scope, get_current_user, is_api_caller,
                    require_capability, require_module)
from ..models import User
from ..report import (build_dependencies_data, build_report_data, render_dependencies_html,
                      render_dependencies_pptx, render_html, render_pptx, render_roadmap_html,
                      render_roadmap_pptx, rt)
from ..schemas import ReportSubscriptionIn, ReportSubscriptionOut

router = APIRouter(prefix="/api/reports", tags=["reports"])

# Two orthogonal gates on every export, and both are needed:
#   * require_module  - is the feature switched on at all (admin toggles)?
#   * require_capability - may THIS persona reach the section being exported?
# An export is a copy of a section's data, so it must demand the very capability
# that section demands. Without this, a persona denied "dashboard" could still
# pull the whole dashboard as PPTX (the SPA hides the button; the API did not).
_report_gate = Depends(require_module("review", "weekly_report"))
_roadmap_gate = Depends(require_module("squad_content", "roadmap"))
_dashboard_gate = Depends(require_module("dashboard"))

# The weekly report aggregates the dashboard/review data, so it rides on the
# dashboard capability (every built-in persona has it; a persona denied the
# dashboard has no business receiving the same content by mail).
_report_cap = Depends(require_capability("dashboard"))

# The document routes are the read-only API surface open to machines: a human is
# gated by the persona capability, an API key by its scope (deps.caller). The
# subscription/e-mail routes below are NOT - they belong to a user, so they stay
# cookie-only with the capability gate.
_weekly_caller = caller("reports:read", capability="dashboard")
_dashboard_caller = caller("dashboard:read", capability="dashboard")
_roadmap_caller = caller("roadmap:read", capability="roadmap")


def _data(request: Request, db: Session, user: User, tribe_id: int | None, year: int | None,
          since_days: int, squad_id: int | None = None, lang: str | None = None,
          squad_ids: list[int] | None = None) -> dict:
    """Build the report scoped to the caller's visibility (or a single squad).

    lang follows the caller's UI language. squad_ids, when set, restricts the
    report to that subset (within the caller's tribe scope).

    `viewer` is what lets the renderer decide whether budget figures belong in the
    document. For a human it is themselves (is_squad_privileged decides). For an
    API key it is themselves ONLY if the key carries budget:read - otherwise we
    pass None, which strips every budget from the payload. Without this, a
    tribe-less key (which reads across tribes) would collect every squad's budget
    for free.
    """
    viewer = user
    if is_api_caller(request) and not caller_has_scope(request, "budget:read"):
        viewer = None

    year = year or st.current_year_quarter()[0]
    if squad_id is not None:
        from ..subscriptions import user_can_see_squad
        if not user_can_see_squad(db, user, squad_id):
            raise HTTPException(status_code=404, detail="Squad introuvable")
        return build_report_data(db, None, year, since_days, squad_id=squad_id, lang=lang, viewer=viewer)
    # Admin may target a tribe; everyone else is scoped to their own tribe.
    scope = tribe_id if user.role == "admin" else user.tribe_id
    return build_report_data(db, scope, year, since_days, lang=lang, squad_ids=squad_ids, viewer=viewer)


@router.get("/weekly.html", response_class=HTMLResponse, dependencies=[_report_gate])
def weekly_html(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                lang: str | None = Query(default=None),
                db: Session = Depends(get_db), user: User = Depends(_weekly_caller)):
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang)
    return HTMLResponse(render_html(data, standalone=True))


@router.get("/weekly.pptx", dependencies=[_report_gate])
def weekly_pptx(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                lang: str | None = Query(default=None),
                db: Session = Depends(get_db), user: User = Depends(_weekly_caller)):
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang)
    try:
        payload = render_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    filename = f"rapport_{data['year']}.pptx"
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard.html", response_class=HTMLResponse, dependencies=[_dashboard_gate])
def dashboard_html(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                   since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                   squad_ids: list[int] | None = Query(default=None),
                   lang: str | None = Query(default=None),
                   db: Session = Depends(get_db), user: User = Depends(_dashboard_caller)):
    """Dashboard view as a page: the overview the user sees (summary + squads +
    per-squad detail), optionally restricted to a chosen set of squads."""
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, squad_ids)
    return HTMLResponse(render_html(data, standalone=True))


@router.get("/dashboard.pptx", dependencies=[_dashboard_gate])
def dashboard_pptx(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                   since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                   squad_ids: list[int] | None = Query(default=None),
                   lang: str | None = Query(default=None),
                   db: Session = Depends(get_db), user: User = Depends(_dashboard_caller)):
    """Dashboard view as a branded deck, optionally restricted to chosen squads."""
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, squad_ids)
    try:
        payload = render_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    filename = f"dashboard_{data['year']}.pptx"
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/roadmap.html", response_class=HTMLResponse, dependencies=[_roadmap_gate])
def roadmap_html(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                 since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                 squad_ids: list[int] | None = Query(default=None),
                 lang: str | None = Query(default=None),
                 db: Session = Depends(get_db), user: User = Depends(_roadmap_caller)):
    """Roadmap web page scoped to the caller (optionally restricted to chosen squads)."""
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, squad_ids)
    return HTMLResponse(render_roadmap_html(data, standalone=True))


@router.get("/roadmap.pptx", dependencies=[_roadmap_gate])
def roadmap_pptx(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                 since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                 squad_ids: list[int] | None = Query(default=None),
                 lang: str | None = Query(default=None),
                 db: Session = Depends(get_db), user: User = Depends(_roadmap_caller)):
    """Roadmap deck scoped to the caller (optionally restricted to chosen squads)."""
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, squad_ids)
    try:
        payload = render_roadmap_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    filename = f"roadmap_{data['year']}.pptx"
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _dep_data(request: Request, db: Session, user: User, tribe_id: int | None, year: int | None,
              squad_ids: list[int] | None, lang: str | None, mode: str) -> dict:
    """Milestone-dependency data, scoped like the other exports (admin may target a
    tribe; everyone else is scoped to their own tribe). Budgets are stripped for an
    API key without budget:read, exactly as in _data()."""
    viewer = user
    if is_api_caller(request) and not caller_has_scope(request, "budget:read"):
        viewer = None
    year = year or st.current_year_quarter()[0]
    scope = tribe_id if user.role == "admin" else user.tribe_id
    return build_dependencies_data(db, scope, year, squad_ids=squad_ids, viewer=viewer, lang=lang, mode=mode)


@router.get("/dependencies.html", response_class=HTMLResponse, dependencies=[_roadmap_gate])
def dependencies_html(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                      squad_ids: list[int] | None = Query(default=None), lang: str | None = Query(default=None),
                      mode: str = Query(default="cross_tribe"),
                      db: Session = Depends(get_db), user: User = Depends(_roadmap_caller)):
    """Milestone dependencies as a page (grouped by the entity waited on)."""
    data = _dep_data(request, db, user, tribe_id, year, squad_ids, lang, mode)
    return HTMLResponse(render_dependencies_html(data, standalone=True))


@router.get("/dependencies.pptx", dependencies=[_roadmap_gate])
def dependencies_pptx(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                      squad_ids: list[int] | None = Query(default=None), lang: str | None = Query(default=None),
                      mode: str = Query(default="cross_tribe"),
                      db: Session = Depends(get_db), user: User = Depends(_roadmap_caller)):
    """Milestone-dependency deck (paginated table grouped by the entity waited on)."""
    data = _dep_data(request, db, user, tribe_id, year, squad_ids, lang, mode)
    try:
        payload = render_dependencies_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    filename = f"dependances_{data['year']}.pptx"
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _sub_out(db: Session, sub, squad_id: int | None) -> ReportSubscriptionOut:
    from ..models import Squad
    name = None
    if squad_id is not None:
        sq = db.get(Squad, squad_id)
        name = sq.name if sq else None
    return ReportSubscriptionOut(
        squad_id=squad_id, squad_name=name,
        interval_days=sub.interval_days if sub else 0,
        weekdays=(sub.weekdays or []) if sub else [],
        hour=sub.hour if sub else 8,
        last_sent_at=sub.last_sent_at if sub else None,
    )


@router.get("/subscriptions", response_model=list[ReportSubscriptionOut], dependencies=[_report_gate, _report_cap])
def list_my_subscriptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..subscriptions import list_subscriptions
    return [_sub_out(db, s, s.squad_id) for s in list_subscriptions(db, user)]


@router.get("/subscription", response_model=ReportSubscriptionOut, dependencies=[_report_gate, _report_cap])
def get_my_subscription(squad_id: int | None = Query(default=None),
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..subscriptions import get_subscription
    return _sub_out(db, get_subscription(db, user.id, squad_id), squad_id)


@router.put("/subscription", response_model=ReportSubscriptionOut, dependencies=[_report_gate, _report_cap])
def set_my_subscription(payload: ReportSubscriptionIn, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    from ..subscriptions import set_subscription, user_can_see_squad
    if payload.squad_id is not None and not user_can_see_squad(db, user, payload.squad_id):
        raise HTTPException(status_code=404, detail="Squad introuvable")
    sub = set_subscription(db, user, payload.squad_id, payload.interval_days, payload.weekdays, payload.hour)
    # Keep the legacy global flags in sync (dashboard subscription only).
    if payload.squad_id is None:
        active = bool(payload.weekdays) or payload.interval_days > 0
        user.report_interval_days = payload.interval_days
        user.subscribe_weekly_report = active
        if not active:
            user.report_last_sent_at = None
    db.commit()
    return _sub_out(db, sub, payload.squad_id)


@router.post("/weekly/email", dependencies=[_report_gate, _report_cap])
def weekly_email(request: Request, payload: dict = Body(default=None), db: Session = Depends(get_db),
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
    squad_id = payload.get("squad_id")
    lang = payload.get("lang")

    cfg = get_smtp(db)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="SMTP non configuré (activez-le dans l'Administration)")

    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang)
    html_body = render_html(data, standalone=True)
    attachment = None
    try:
        pptx_bytes = render_pptx(data)
        attachment = (f"rapport_hebdo_{data['year']}.pptx", pptx_bytes,
                      "application", "vnd.openxmlformats-officedocument.presentationml.presentation")
    except ImportError:
        pass  # send HTML-only if PPTX backend unavailable

    subject = f"{data['app_name']} - {rt(data['lang'], 'report')}"
    ok = send_email(cfg, to, subject, html_body, attachment=attachment, html=True)
    if not ok:
        raise HTTPException(status_code=502, detail="L'envoi de l'email a échoué (vérifiez la configuration SMTP)")
    return {"ok": True, "to": to}
