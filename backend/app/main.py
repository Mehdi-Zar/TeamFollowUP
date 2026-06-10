import logging
import os

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import get_db
from .routers import (
    admin,
    audit,
    auth,
    dashboard,
    exports,
    feed,
    kpis,
    members,
    notifications,
    objectives,
    org,
    roadmap,
    snapshots,
    squads,
    tribes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title=settings.app_name,
    description="Outil de pilotage de tribe : consolidation, drill-down, saisie, organigramme, exports.",
    version="1.0.0",
)

# Session middleware is required by Authlib (OIDC state/PKCE).
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=False)

for r in (auth, tribes, squads, dashboard, org, objectives, roadmap, kpis,
          members, snapshots, exports, feed, notifications, admin, audit):
    app.include_router(r.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/config", tags=["meta"])
def public_app_config(db=Depends(get_db)):
    from .generalconfig import public_config
    return public_config(db)


# ---------------- Static SPA ----------------
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
ASSETS_DIR = os.path.join(STATIC_DIR, "assets")

if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    """Serve the built SPA; client-side routing falls back to index.html."""
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    candidate = os.path.join(STATIC_DIR, full_path)
    if full_path and os.path.isfile(candidate):
        return FileResponse(candidate)
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return JSONResponse(
        status_code=503,
        content={"detail": "Frontend non build. Lancez le build du frontend ou utilisez l'image Docker."},
    )
