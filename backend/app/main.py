"""FastAPI application factory and wiring.

Defines the single ``app`` instance: mounts the session middleware, registers
every feature router, wires the startup hooks (security warnings + the in-process
weekly-report scheduler), exposes the small meta endpoints, and finally serves the
built single-page app with client-side-routing fallback. This is the module
``app.server`` / uvicorn loads.
"""
import logging
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import get_db
from .deps import get_current_user
from .models import User
from .routers import (
    admin,
    audit,
    auth,
    committees,
    dashboard,
    data,
    feed,
    initiatives,
    kpis,
    leaves,
    members,
    notifications,
    access,
    org,
    orgexport,
    otds,
    reports,
    roadmap,
    roadmapview,
    snapshots,
    squads,
    steerco,
    tribes,
)

from .logconfig import configure_logging

# Text lines locally, GCP Cloud Logging JSON when LOG_FORMAT=json (see logconfig).
configure_logging(settings.log_format, settings.log_level)

app = FastAPI(
    title=settings.app_name,
    description="Outil de pilotage de tribe : consolidation, drill-down, saisie, organigramme, exports.",
    version="2.1.0",
    # The API documentation is served below, to administrators only: public, it
    # handed the whole map of the API to anyone who could reach the app.
    docs_url=None, redoc_url=None, openapi_url=None,
)

# Security headers on every response, and no caching of the API (personal data
# behind a shared proxy). The SPA and the exports get a strict CSP; the API docs
# page loads Swagger UI from its CDN, so it gets its own.
_CSP_APP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
_CSP_DOCS = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
             "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: "
             "https://fastapi.tiangolo.com https://cdn.redoc.ly; font-src 'self' data: https://fonts.gstatic.com; "
             "connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'")


@app.middleware("http")
async def _security_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "SAMEORIGIN")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    # Only obeyed by the browser on the HTTPS response the infrastructure serves.
    h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    h.setdefault("Content-Security-Policy", _CSP_DOCS if path in ("/docs", "/redoc") else _CSP_APP)
    if path.startswith("/api/") or path in ("/openapi.json", "/metrics"):
        h.setdefault("Cache-Control", "no-store")
    return response

# Refuse to serve with a configuration that hands out sessions (see config).
for _reason in settings.startup_refusals():
    import logging as _logging
    _logging.getLogger("trt.security").critical("SECURITY: refusing to start: %s", _reason)
if settings.startup_refusals():
    raise SystemExit("SECURITY: " + " ".join(settings.startup_refusals()))

# Session middleware is required by Authlib (OIDC state/PKCE). Its cookie only
# carries a login in progress: ten minutes are plenty.
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=600,
                   same_site=settings.cookie_samesite, https_only=settings.cookie_secure)

# CSRF, defence in depth on top of SameSite=Lax: a state-changing API call made
# with the session cookie must come from the app's own pages. The browser says
# where a request comes from (Sec-Fetch-Site, Origin); a cross-site one is
# refused. API keys (Authorization header) are not browser credentials and are
# not concerned; the SAML ACS is posted by the IdP, cross-site by design.
_CSRF_EXEMPT = ("/api/auth/saml/acs",)


@app.middleware("http")
async def _csrf_guard(request, call_next):
    if (request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/")
            and request.url.path not in _CSRF_EXEMPT and not request.headers.get("authorization")):
        site = (request.headers.get("sec-fetch-site") or "").lower()
        origin = request.headers.get("origin")
        bad = bool(site) and site not in ("same-origin", "none")
        if not bad and origin and origin != "null":
            from urllib.parse import urlsplit
            allowed = {h.split(",")[0].strip().lower() for h in (
                request.headers.get("x-forwarded-host"), request.headers.get("host")) if h}
            if settings.public_base_url:
                allowed.add(urlsplit(settings.public_base_url).netloc.lower())
            bad = urlsplit(origin).netloc.lower() not in allowed
        elif origin == "null":
            bad = True
        if bad:
            return JSONResponse(status_code=403, content={"detail": "Requête refusée (origine croisée)"})
    return await call_next(request)

# Metrics wrap everything, including the session middleware, so the latency they
# record is the latency the client experienced. Added last = outermost, since
# Starlette applies middleware in reverse order of registration.
if settings.metrics_enabled:
    from .metrics import MetricsMiddleware, init_metrics
    init_metrics()
    app.add_middleware(MetricsMiddleware)

# Readable answers for crashes, constraint failures and validation errors.
from . import errors  # noqa: E402
errors.install(app)

for r in (auth, tribes, squads, dashboard, org, orgexport, roadmap, roadmapview, kpis,
          members, snapshots, feed, notifications, admin, audit, reports,
          initiatives, otds, access, leaves, committees, steerco, data):
    app.include_router(r.router)


def custom_openapi():
    """OpenAPI schema with an API-key (Bearer) security scheme.

    Declaring ``ApiKeyAuth`` (HTTP bearer) gives the Swagger UI an **Authorize**
    button: paste an API key (Admin > API) and Swagger sends it as
    ``Authorization: Bearer <key>`` on every "Try it out" call - matching
    ``deps.api_key_from_request``. Security is ``[{}, {ApiKeyAuth: []}]`` (the
    empty alternative) so it stays optional: human/session-cookie calls, which
    the same-origin browser sends automatically, keep working without a key.
    """
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title=app.title, version=app.version,
                         description=app.description, routes=app.routes)
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "description": "Clé d'API créée dans Admin > API, envoyée en `Authorization: Bearer <clé>`.",
    }
    schema["security"] = [{}, {"ApiKeyAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


def require_admin_docs(user: User = Depends(get_current_user)) -> User:
    """The API documentation: administrators only (it is where production is
    troubleshot from a browser, and a full map of the API for anyone else)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return user


@app.on_event("startup")
async def _warn_on_insecure_defaults():
    """Fail loud (log) if dev-default secrets are still in use - see docs/05-security.md."""
    import logging
    log = logging.getLogger("trt.security")
    if str(settings.secret_key).startswith("change-me"):
        log.warning("SECURITY: default SECRET_KEY in use - set a strong SECRET_KEY in production.")
    if settings.postgres_password == "tribe":
        log.warning("SECURITY: default POSTGRES_PASSWORD in use - override it in production.")
    # A configured public base URL means this is not somebody's laptop. An open
    # /metrics there is reachable by whoever can reach the app.
    if settings.metrics_enabled and not settings.metrics_token and settings.public_base_url:
        log.warning("SECURITY: /metrics is enabled without METRICS_TOKEN while PUBLIC_BASE_URL is set - "
                    "keep /metrics off the public route, or set METRICS_TOKEN (docs/17).")


@app.on_event("startup")
async def _apply_outbound_trust():
    """Make the admin-managed CA store effective for the app's outbound TLS.

    Trusting an internal authority is about the calls the app *makes* (IdP, SMTP,
    log export), and has nothing to do with who terminates the TLS in front of
    it. A failure here must not stop the app from booting, it only means outbound
    calls keep the public trust store.
    """
    import logging
    log = logging.getLogger("trt.tls")
    from . import trustconfig
    from .database import SessionLocal
    db = SessionLocal()
    try:
        count = trustconfig.ensure_trust(db)
        if count:
            log.info("Outbound TLS trust: %d admin-managed authority/ies applied.", count)
    except Exception as exc:
        log.warning("Could not apply the outbound trust store (%s); public roots only.", exc)
    finally:
        db.close()


@app.on_event("startup")
async def _start_weekly_progress_scheduler():
    """Lightweight in-process scheduler.

    Runs hourly and, when due, sends the weekly HTML/PPTX report by email on the
    configured weekday/hour and the personal subscriptions, then purges old
    records. All steps are idempotent and self-healing. Disabled in tests via
    DISABLE_SCHEDULER=1.
    """
    if os.environ.get("DISABLE_SCHEDULER") == "1":
        return
    import asyncio

    from sqlalchemy import text

    from .database import SessionLocal, engine
    from .maintenance import purge_old_records
    from .report import send_due_weekly_reports, send_personal_subscriptions

    _LOCK_KEY = 911001  # advisory-lock id: only one replica runs the tick

    def _tick_metric(outcome: str) -> None:
        """Count a scheduler tick. Never let telemetry break the scheduler."""
        try:
            if not settings.metrics_enabled:
                return
            import time as _time

            from .metrics import scheduler_last_success_timestamp, scheduler_runs_total
            scheduler_runs_total.labels(outcome=outcome).inc()
            if outcome == "ok":
                scheduler_last_success_timestamp.set(_time.time())
        except Exception:
            pass

    async def loop():
        # Small initial delay so startup (migrations/seed) settles first.
        await asyncio.sleep(20)
        while True:
            try:
                # The advisory lock is a *session-level* (per-connection) lock, so it
                # MUST be acquired and released on the SAME, dedicated connection held
                # for the whole tick. The work below opens its own Session(s) whose
                # commits return THEIR connections to the pool; if we locked on one of
                # those, the later unlock could land on a different pooled connection,
                # silently fail, and leak the lock forever (every later tick then finds
                # it held → automatic sends stop across all replicas). AUTOCOMMIT keeps
                # the lock independent of any transaction.
                lock_conn = None
                got_lock = True
                try:
                    try:
                        lock_conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
                        got_lock = bool(lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"),
                                                          {"k": _LOCK_KEY}).scalar())
                    except Exception:
                        got_lock = True  # non-Postgres (tests) - proceed without a lock
                    if got_lock:
                        db = SessionLocal()
                        try:
                            sent = send_due_weekly_reports(db)
                            if sent:
                                logging.getLogger("trt.report").info("Weekly reports emailed: %s", sent)
                            subs = send_personal_subscriptions(db)
                            if subs:
                                logging.getLogger("trt.report").info("Personal report subscriptions emailed: %s", subs)
                            # Change notices still waiting (a restart lost their timer).
                            from .changenotify import flush_pending
                            flush_pending()
                            purge_old_records(db)
                            # Automatic data snapshot when one is due (off by
                            # default, see app/datasnapshots.py).
                            from .datasnapshots import run_due_snapshot
                            took = run_due_snapshot(db)
                            if took:
                                logging.getLogger('trt.datasnapshots').info(
                                    'automatic snapshot: %s', took)
                            _tick_metric("ok")
                        finally:
                            db.close()
                    else:
                        # Another replica is doing the work. Counted separately so a
                        # silent scheduler can be told apart from a losing replica.
                        _tick_metric("skipped_not_leader")
                finally:
                    if lock_conn is not None:
                        try:
                            if got_lock:
                                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
                        except Exception:
                            pass
                        finally:
                            lock_conn.close()
            except Exception as exc:  # never crash the loop
                logging.getLogger("trt.progress").warning("weekly scheduler error: %s", exc)
                _tick_metric("error")
            # ALWAYS wait a full hour before the next attempt - even when another
            # replica held the lock (no tight busy-loop on the non-leader replicas).
            await asyncio.sleep(3600)

    asyncio.create_task(loop())


@app.get("/api/health", tags=["meta"])
def health():
    """Liveness probe: cheap, unauthenticated, no DB access."""
    return {"status": "ok", "app": settings.app_name}


@app.get("/openapi.json", include_in_schema=False)
def openapi_json(admin: User = Depends(require_admin_docs)):
    """The API schema, for administrators (the Swagger page reads it)."""
    return JSONResponse(app.openapi())


@app.get("/docs", include_in_schema=False)
def swagger_ui(admin: User = Depends(require_admin_docs)):
    """Swagger UI, for administrators: the way to troubleshoot production from a
    browser. Its "Authorize" button still takes an API key."""
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{settings.app_name} API")


@app.get("/redoc", include_in_schema=False)
def redoc_ui(admin: User = Depends(require_admin_docs)):
    """ReDoc, for administrators."""
    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(openapi_url="/openapi.json", title=f"{settings.app_name} API")


@app.get("/metrics", include_in_schema=False)
def metrics(request: Request, authorization: str | None = Header(default=None)):
    """Prometheus exposition endpoint. See app/metrics.py and docs/17.

    Kept out of the OpenAPI schema: it is an operational endpoint, not part of
    the product's API contract, and listing it in the public schema would
    advertise it to every reader of /docs.
    """
    from .metrics import metrics_authorized, render
    if not settings.metrics_enabled:
        return PlainTextResponse("metrics disabled", status_code=404)
    # Without a token, only a direct scrape (inside the cluster) is served: a
    # request that came through a proxy or gateway (forwarded headers) is from
    # outside, and the metrics describe the whole API and its traffic.
    if not (settings.metrics_token or "").strip() and (
            request.headers.get("x-forwarded-for") or request.headers.get("forwarded")):
        return PlainTextResponse("not found", status_code=404)
    if not metrics_authorized(authorization):
        # 401 + the challenge header, so a misconfigured scraper reports
        # "unauthorized" rather than a bare parse failure on an HTML error page.
        return PlainTextResponse("unauthorized", status_code=401,
                                 headers={"WWW-Authenticate": "Bearer"})
    payload, content_type = render()
    return Response(content=payload, media_type=content_type)


@app.get("/api/config", tags=["meta"])
def public_app_config(db=Depends(get_db)):
    """Public (pre-login) app configuration the SPA needs to render its shell."""
    from .generalconfig import public_config
    return public_config(db)


# ---------------- Static SPA ----------------
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
ASSETS_DIR = os.path.join(STATIC_DIR, "assets")

if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


# index.html references hash-stamped asset filenames, so it MUST be revalidated on
# every load - otherwise a cached index keeps pointing at chunks a new build deleted
# (stale SPA / 404 on old assets). Hashed assets under /assets are immutable & cacheable.
_INDEX_HEADERS = {"Cache-Control": "no-cache, must-revalidate"}


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str, request: Request):
    """Serve the built SPA; client-side routing falls back to index.html."""
    if full_path.startswith("api/"):
        en = errors.lang_of(request) == "en"
        return JSONResponse(status_code=404, content={"detail": "Unknown route" if en else "Route inconnue"})
    # Only a file INSIDE the built SPA folder. "//etc/passwd", "../../x" or an
    # encoded "..%2f" used to leave STATIC_DIR (os.path.join with an absolute or
    # climbing segment) and read any file of the server, unauthenticated.
    root = os.path.realpath(STATIC_DIR)
    candidate = os.path.realpath(os.path.join(root, full_path.lstrip("/\\")))
    inside = candidate.startswith(root + os.sep)
    if full_path and inside and os.path.isfile(candidate):
        headers = _INDEX_HEADERS if os.path.basename(candidate) == "index.html" else None
        return FileResponse(candidate, headers=headers)
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(index, headers=_INDEX_HEADERS)
    return JSONResponse(
        status_code=503,
        content={"detail": "Frontend non build. Lancez le build du frontend ou utilisez l'image Docker."},
    )
