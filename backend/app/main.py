"""FastAPI application factory and wiring.

Defines the single ``app`` instance: mounts the session middleware, registers
every feature router, wires the startup hooks (security warnings + the in-process
weekly-report scheduler), exposes the small meta endpoints, and finally serves the
built single-page app with client-side-routing fallback. This is the module
``app.server`` / uvicorn loads.
"""
import logging
import os

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import get_db
from .routers import (
    actions,
    admin,
    audit,
    auth,
    committees,
    dashboard,
    feed,
    initiatives,
    kpis,
    leaves,
    members,
    notifications,
    access,
    objectives,
    org,
    orgexport,
    otds,
    reports,
    roadmap,
    roadmapview,
    snapshots,
    squads,
    tribes,
)

from .logconfig import configure_logging

# Text lines locally, GCP Cloud Logging JSON when LOG_FORMAT=json (see logconfig).
configure_logging(settings.log_format, settings.log_level)

app = FastAPI(
    title=settings.app_name,
    description="Outil de pilotage de tribe : consolidation, drill-down, saisie, organigramme, exports.",
    version="1.0.0",
)

# Session middleware is required by Authlib (OIDC state/PKCE).
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key,
                   same_site=settings.cookie_samesite, https_only=settings.cookie_secure)

for r in (auth, tribes, squads, dashboard, org, orgexport, objectives, roadmap, roadmapview, kpis,
          members, snapshots, feed, notifications, admin, audit, reports,
          actions, initiatives, otds, access, leaves, committees):
    app.include_router(r.router)


@app.on_event("startup")
async def _warn_on_insecure_defaults():
    """Fail loud (log) if dev-default secrets are still in use - see docs/05-security.md."""
    import logging
    log = logging.getLogger("trt.security")
    if str(settings.secret_key).startswith("change-me"):
        log.warning("SECURITY: default SECRET_KEY in use - set a strong SECRET_KEY in production.")
    if settings.postgres_password == "tribe":
        log.warning("SECURITY: default POSTGRES_PASSWORD in use - override it in production.")


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
                            purge_old_records(db)
                        finally:
                            db.close()
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
            # ALWAYS wait a full hour before the next attempt - even when another
            # replica held the lock (no tight busy-loop on the non-leader replicas).
            await asyncio.sleep(3600)

    asyncio.create_task(loop())


@app.get("/api/health", tags=["meta"])
def health():
    """Liveness probe: cheap, unauthenticated, no DB access."""
    return {"status": "ok", "app": settings.app_name}


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
def spa(full_path: str):
    """Serve the built SPA; client-side routing falls back to index.html."""
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    candidate = os.path.join(STATIC_DIR, full_path)
    if full_path and os.path.isfile(candidate):
        headers = _INDEX_HEADERS if os.path.basename(candidate) == "index.html" else None
        return FileResponse(candidate, headers=headers)
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(index, headers=_INDEX_HEADERS)
    return JSONResponse(
        status_code=503,
        content={"detail": "Frontend non build. Lancez le build du frontend ou utilisez l'image Docker."},
    )
