"""On-demand weekly-report downloads (HTML / PPTX) and manual email send.

The automatic weekly send lives in app.report.send_due_weekly_reports, driven by
the in-process scheduler in main.py.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import pptxtpl
from ..database import get_db
from ..generalconfig import reference_year
from ..deps import (caller, caller_has_scope, get_current_user, is_api_caller, scoped_tribe_id,
                    require_capability, require_module)
from ..models import User, utcnow
from ..report import (build_dependencies_data, build_report_data, render_dependencies_html,
                      render_dependencies_pptx, render_html, render_pptx, render_roadmap_html,
                      render_roadmap_pptx, rt)
from ..reportasof import freeze_report_data, list_versions
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
          squad_ids: list[int] | None = None, as_of: str | None = None) -> dict:
    """Build the report scoped to the caller's visibility (or a single squad).

    lang follows the caller's UI language. squad_ids, when set, restricts the
    report to that subset (within the caller's tribe scope).

    as_of ("AAAA-MM-JJ"), when set, rejoue le document a cette date depuis les
    saisies figees (voir ``reportasof``). Le calcul de visibilite reste celui du
    jour, et c'est voulu: une version passee ne doit pas ouvrir a un lecteur des
    squads qu'il n'a pas le droit de voir aujourd'hui.

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

    year = year or reference_year(db)
    if squad_id is not None:
        from ..subscriptions import user_can_see_squad
        if not user_can_see_squad(db, user, squad_id):
            raise HTTPException(status_code=404, detail="Squad introuvable")
        data = build_report_data(db, None, year, since_days, squad_id=squad_id, lang=lang, viewer=viewer)
    else:
        # Admin may target a tribe; everyone else is scoped to their own tribe.
        scope = scoped_tribe_id(user, tribe_id)
        data = build_report_data(db, scope, year, since_days, lang=lang, squad_ids=squad_ids,
                                 viewer=viewer, led_by=user)
    if as_of:
        try:
            data = freeze_report_data(db, data, as_of)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    return data


@router.get("/weekly.html", response_class=HTMLResponse, dependencies=[_report_gate])
def weekly_html(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                lang: str | None = Query(default=None),
                 as_of: str | None = Query(default=None),
                db: Session = Depends(get_db), user: User = Depends(_weekly_caller)):
    """Weekly report as a standalone HTML page.

    GET /api/reports/weekly.html
    Access: human via `dashboard` capability, or API key with `reports:read` scope
    (the _weekly_caller); gated by the `review > weekly_report` module. squad_id
    narrows to one squad, else the caller's tribe scope (admins may target a tribe).
    """
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, as_of=as_of)
    return HTMLResponse(render_html(data, standalone=True))


@router.get("/weekly.pptx", dependencies=[_report_gate])
def weekly_pptx(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                lang: str | None = Query(default=None),
                 as_of: str | None = Query(default=None),
                db: Session = Depends(get_db), user: User = Depends(_weekly_caller)):
    """Weekly report as a PPTX download.

    GET /api/reports/weekly.pptx
    Access/scoping identical to weekly_html. Returns 501 when the python-pptx
    backend is not installed.
    """
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, as_of=as_of)
    try:
        pptxtpl.use(pptxtpl.get(db))
        payload = render_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    filename = f"rapport_{data['year']}.pptx"
    # Fully buffered artifact → a plain Response so Starlette sets Content-Length
    # (not chunked). Without it the browser can't detect a truncated download and
    # shows "check your connection" on any mid-transfer TLS blip. See ADR/CHANGELOG.
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard.html", response_class=HTMLResponse, dependencies=[_dashboard_gate])
def dashboard_html(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                   since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                   squad_ids: list[int] | None = Query(default=None),
                   lang: str | None = Query(default=None),
                 as_of: str | None = Query(default=None),
                   db: Session = Depends(get_db), user: User = Depends(_dashboard_caller)):
    """Dashboard view as a page: the overview the user sees (summary + squads +
    per-squad detail), optionally restricted to a chosen set of squads."""
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, squad_ids, as_of)
    data["doc"] = "dashboard"  # its own title: it used to read "Weekly report"
    return HTMLResponse(render_html(data, standalone=True))


@router.get("/dashboard.pptx", dependencies=[_dashboard_gate])
def dashboard_pptx(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                   since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                   squad_ids: list[int] | None = Query(default=None),
                   lang: str | None = Query(default=None),
                 as_of: str | None = Query(default=None),
                   db: Session = Depends(get_db), user: User = Depends(_dashboard_caller)):
    """Dashboard view as a branded deck, optionally restricted to chosen squads."""
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, squad_ids, as_of)
    data["doc"] = "dashboard"
    try:
        pptxtpl.use(pptxtpl.get(db))
        payload = render_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    filename = f"dashboard_{data['year']}.pptx"
    # Fully buffered artifact → a plain Response so Starlette sets Content-Length
    # (not chunked). Without it the browser can't detect a truncated download and
    # shows "check your connection" on any mid-transfer TLS blip. See ADR/CHANGELOG.
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/roadmap.html", response_class=HTMLResponse, dependencies=[_roadmap_gate])
def roadmap_html(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                 since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                 squad_ids: list[int] | None = Query(default=None),
                 lang: str | None = Query(default=None),
                 as_of: str | None = Query(default=None),
                 db: Session = Depends(get_db), user: User = Depends(_roadmap_caller)):
    """Roadmap web page scoped to the caller (optionally restricted to chosen squads)."""
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, squad_ids, as_of)
    return HTMLResponse(render_roadmap_html(data, standalone=True))


@router.get("/roadmap.pptx", dependencies=[_roadmap_gate])
def roadmap_pptx(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                 since_days: int = Query(default=7, ge=1, le=365), squad_id: int | None = Query(default=None),
                 squad_ids: list[int] | None = Query(default=None),
                 lang: str | None = Query(default=None),
                 as_of: str | None = Query(default=None),
                 db: Session = Depends(get_db), user: User = Depends(_roadmap_caller)):
    """Roadmap deck scoped to the caller (optionally restricted to chosen squads)."""
    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, squad_ids, as_of)
    try:
        pptxtpl.use(pptxtpl.get(db))
        payload = render_roadmap_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    filename = f"roadmap_{data['year']}.pptx"
    # Fully buffered artifact → a plain Response so Starlette sets Content-Length
    # (not chunked). Without it the browser can't detect a truncated download and
    # shows "check your connection" on any mid-transfer TLS blip. See ADR/CHANGELOG.
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# L'index des versions sert les trois documents, donc il s'ouvre a qui peut lire
# l'un d'eux: gater sur le seul dashboard aurait prive de versions un persona qui
# n'exporte que la roadmap. Le module, lui, est celui qui produit les saisies
# figees: sans reporting, il n'y a aucune version a lister.
_versions_caller = caller("dashboard:read")


@router.get("/versions", dependencies=[Depends(require_module("reporting"))])
def report_versions(request: Request, tribe_id: int | None = Query(default=None),
                    year: int | None = Query(default=None),
                    squad_id: int | None = Query(default=None),
                    squad_ids: list[int] | None = Query(default=None),
                    db: Session = Depends(get_db), user: User = Depends(_versions_caller)):
    """Les versions disponibles d'un document, de la plus recente a la plus ancienne.

    GET /api/reports/versions
    Une version est une journee ou au moins une squad du perimetre a soumis sa
    saisie, avec le nombre de squads concernees: c'est ce chiffre qui dit si la
    version est complete. A passer ensuite en `as_of` sur dashboard/roadmap/weekly.
    Acces: la capacite dashboard ou la capacite roadmap, et on ne liste que les
    versions des squads que l'appelant voit aujourd'hui.
    """
    if not is_api_caller(request):
        from ..personasconfig import can
        if not (can(db, user, "dashboard") or can(db, user, "roadmap")):
            raise HTTPException(status_code=403, detail="Accès non autorisé pour votre rôle")
    year = year or reference_year(db)
    # The squads in view, read directly: this used to build the whole report
    # (40-odd queries) to throw everything away but the ids.
    from ..models import Squad
    from ..subscriptions import user_can_see_squad
    from ..deps import led_squad_ids
    if squad_id is not None:
        ids = [squad_id] if user_can_see_squad(db, user, squad_id) else []
    else:
        scope = scoped_tribe_id(user, tribe_id)
        q = select(Squad.id)
        if scope is not None:
            q = q.where(or_(Squad.tribe_id == scope, Squad.id.in_(led_squad_ids(db, user))))
        ids = list(db.scalars(q).all())
        if squad_ids:
            ids = [i for i in ids if i in set(squad_ids)]
    return {"year": year, "versions": list_versions(db, ids, year)}


def _dep_data(request: Request, db: Session, user: User, tribe_id: int | None, year: int | None,
              squad_ids: list[int] | None, lang: str | None, mode: str) -> dict:
    """Milestone-dependency data, scoped like the other exports (admin may target a
    tribe; everyone else is scoped to their own tribe). Budgets are stripped for an
    API key without budget:read, exactly as in _data()."""
    viewer = user
    if is_api_caller(request) and not caller_has_scope(request, "budget:read"):
        viewer = None
    year = year or reference_year(db)
    scope = scoped_tribe_id(user, tribe_id)
    return build_dependencies_data(db, scope, year, squad_ids=squad_ids, viewer=viewer, lang=lang, mode=mode)


@router.get("/dependencies.html", response_class=HTMLResponse, dependencies=[_roadmap_gate])
def dependencies_html(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                      squad_ids: list[int] | None = Query(default=None), lang: str | None = Query(default=None),
                      mode: str = Query(default="all"),
                      db: Session = Depends(get_db), user: User = Depends(_roadmap_caller)):
    """Milestone dependencies as a page (grouped by the entity waited on)."""
    data = _dep_data(request, db, user, tribe_id, year, squad_ids, lang, mode)
    return HTMLResponse(render_dependencies_html(data, standalone=True))


@router.get("/dependencies.pptx", dependencies=[_roadmap_gate])
def dependencies_pptx(request: Request, tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                      squad_ids: list[int] | None = Query(default=None), lang: str | None = Query(default=None),
                      mode: str = Query(default="all"),
                      db: Session = Depends(get_db), user: User = Depends(_roadmap_caller)):
    """Milestone-dependency deck (paginated table grouped by the entity waited on)."""
    data = _dep_data(request, db, user, tribe_id, year, squad_ids, lang, mode)
    try:
        pptxtpl.use(pptxtpl.get(db))
        payload = render_dependencies_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    filename = f"dependances_{data['year']}.pptx"
    # Fully buffered artifact → a plain Response so Starlette sets Content-Length
    # (not chunked). Without it the browser can't detect a truncated download and
    # shows "check your connection" on any mid-transfer TLS blip. See ADR/CHANGELOG.
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _sub_out(db: Session, sub, squad_id: int | None) -> ReportSubscriptionOut:
    """Serialize a subscription row into its API form, resolving the squad name and
    supplying sensible defaults (interval 0 = unsubscribed) when `sub` is None."""
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
    """List the caller's report subscriptions (dashboard + any per-squad ones).

    GET /api/reports/subscriptions
    Access: cookie user with the `dashboard` capability; gated by `review >
    weekly_report`. Personal, so no API-key surface.
    """
    from ..subscriptions import list_subscriptions
    return [_sub_out(db, s, s.squad_id) for s in list_subscriptions(db, user)]


@router.get("/subscription", response_model=ReportSubscriptionOut, dependencies=[_report_gate, _report_cap])
def get_my_subscription(squad_id: int | None = Query(default=None),
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Return the caller's subscription for a given squad (or the global dashboard
    one when squad_id is omitted).

    GET /api/reports/subscription?squad_id=...
    Access: cookie user with `dashboard`; gated by `review > weekly_report`.
    """
    from ..subscriptions import get_subscription
    return _sub_out(db, get_subscription(db, user.id, squad_id), squad_id)


@router.put("/subscription", response_model=ReportSubscriptionOut, dependencies=[_report_gate, _report_cap])
def set_my_subscription(payload: ReportSubscriptionIn, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Create or update the caller's report subscription (cadence/weekdays/hour).

    PUT /api/reports/subscription
    Access: cookie user with `dashboard`; gated by `review > weekly_report`.
    Business rules: a per-squad subscription requires visibility of that squad
    (404 otherwise); for the global (squad_id=None) subscription the legacy
    User.report_* flags are kept in sync with the new schedule.
    """
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


def assert_allowed_recipient(db: Session, user: User, to: str) -> None:
    """Where a report may be mailed from the app: anywhere for the admin; for
    anyone else, their own address or an active account of their tribe. (The
    company mail server otherwise carried the tribe's reporting, budgets
    included, to any outside address.)"""
    if user.role == "admin":
        return
    from sqlalchemy import func, select
    for addr in [a.strip().lower() for a in to.replace(";", ",").split(",") if a.strip()]:
        if user.email and addr == user.email.lower():
            continue
        ok = db.scalar(select(User.id).where(func.lower(User.email) == addr, User.status == "active",
                                            User.tribe_id == user.tribe_id)) if user.tribe_id else None
        if ok is None:
            raise HTTPException(status_code=403,
                                detail="Le rapport ne part qu'à votre adresse ou à celle d'une personne de votre tribe")


@router.post("/weekly/email", dependencies=[_report_gate, _report_cap])
def weekly_email(request: Request, payload: dict = Body(default=None), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Send the report now to a chosen address (HTML body + PPTX attachment).

    POST /api/reports/weekly/email
    Access: cookie user with `dashboard`; gated by `review > weekly_report`.
    Requires SMTP to be enabled (400 otherwise); defaults the recipient to the
    caller's own e-mail. Sends HTML-only if the PPTX backend is unavailable, and
    returns 502 when the actual send fails.
    """
    from ..smtpconfig import get_smtp

    payload = payload or {}
    to = (payload.get("to") or user.email or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="Adresse destinataire requise")
    tribe_id = payload.get("tribe_id")
    year = payload.get("year")
    # Same bounds as the GET exports; a word here used to be a 500.
    try:
        since_days = int(payload.get("since_days") or 7)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="since_days : nombre de jours attendu")
    if not 1 <= since_days <= 365:
        raise HTTPException(status_code=422, detail="since_days : entre 1 et 365 jours")
    squad_id = payload.get("squad_id")
    lang = payload.get("lang")
    # Le courriel peut lui aussi partir sur une version passee, ce que demande la
    # relecture d'un comite: « renvoie-moi ce qu'on avait envoye le 12 ».
    as_of = payload.get("as_of")

    assert_allowed_recipient(db, user, to)
    cfg = get_smtp(db)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="SMTP non configuré (activez-le dans l'Administration)")

    data = _data(request, db, user, tribe_id, year, since_days, squad_id, lang, as_of=as_of)
    pptx_bytes = b""
    try:
        pptxtpl.use(pptxtpl.get(db))
        pptx_bytes = render_pptx(data) or b""
    except ImportError:
        pass  # send HTML-only if PPTX backend unavailable

    from ..mail import last_error
    from ..report import _file_base, local_now, report_mail
    local = local_now(utcnow())
    week = local.isocalendar()[1]
    # Same subject form as the scheduled report: what, for whom, which week. One
    # squad is named by its name ("Squad A", not "Squad Squad A"); a past
    # version carries its date in the subject and in the file name.
    rows = [r for blk in data.get("tribes") or [] for r in blk.get("squads") or []]
    scope = rows[0]["name"] if data.get("squad_scoped") and rows else data["scope_name"]
    day = local.date().isoformat()
    subject = rt(data["lang"], "subject", scope=scope, w=week)
    if data.get("as_of"):
        from ..reportcommon import fmt_date
        subject = f'{rt(data["lang"], "report")} | {scope} | {rt(data["lang"], "as_of_full", d=fmt_date(data["as_of"], data["lang"]))}'
        day = str(data["as_of"])[:10]
    ok = report_mail(db, cfg, to, subject, data, why="manual", week=None if data.get("as_of") else week,
                     pptx=pptx_bytes, file_base=_file_base(data["lang"], scope, day))
    if not ok:
        raise HTTPException(status_code=502, detail="L'envoi de l'email a échoué (vérifiez la configuration SMTP)"
                            + (f" : {last_error()}" if last_error() else ""))
    return {"ok": True, "to": to}
