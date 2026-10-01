"""Corporate directory: people search for the screens, and its Administration tab.

* ``GET /api/directory/status``: whether a search source is on (the screens then
  offer "search the directory"). Any signed-in user.
* ``GET /api/directory/search?q=``: people found in Entra ID / LDAP / Google
  Workspace, merged by email (``directory.search``). Writers only: the screens
  that add a person (team, accounts) are theirs.
* ``/api/admin/directory-config``: the sources and SCIM provisioning (Administration
  > Annuaire), administrators only. Secrets are masked, a mask sent back keeps the
  stored value; every change is audited.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import directory
from ..database import get_db
from ..deps import get_current_user, record_audit, require_admin, require_writer
from ..directoryconfig import (SECRETS, get_directory, new_scim_token, search_sources,
                               set_directory)
from ..models import User

router = APIRouter(tags=["directory"])

SECRET_MASK = "********"


def _masked(cfg: dict) -> dict:
    out = {k: v for k, v in cfg.items() if k != "scim_token_hash"}
    for k in SECRETS:
        out[k] = SECRET_MASK if cfg.get(k) else ""
    out["scim_token_set"] = bool(cfg.get("scim_token_hash"))
    return out


def _without_masks(payload: dict) -> dict:
    return {k: v for k, v in (payload or {}).items() if not (k in SECRETS and v == SECRET_MASK)}


def _scim_base_url(db: Session, request: Request) -> str:
    from ..authconfig import get_auth_config
    base = (get_auth_config(db, request).get("base_url_effective") or str(request.base_url)).rstrip("/")
    return f"{base}/scim/v2"


@router.get("/api/directory/status")
def directory_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/directory/status: ``{"enabled": bool, "sources": [...]}``. Any user."""
    sources = search_sources(get_directory(db))
    return {"enabled": bool(sources), "sources": sources}


@router.get("/api/directory/search")
def directory_search(q: str = Query(..., max_length=64), db: Session = Depends(get_db),
                     user: User = Depends(require_writer)):
    """GET /api/directory/search?q=: people from the corporate directory.

    At least 2 characters, at most 20 people. Each person says which source
    found it and whether an account already exists for the email
    (``user_id``). A source that fails is reported in ``sources`` and does not
    hide the others."""
    q = (q or "").strip()
    if len(q) < 2:
        raise HTTPException(status_code=422, detail="Tapez au moins 2 caractères")
    cfg = get_directory(db)
    sources = search_sources(cfg)
    if not sources:
        raise HTTPException(status_code=409, detail="Aucun annuaire n'est configuré")
    out = directory.search(cfg, q, sources)
    emails = [p["email"] for p in out["results"]]
    if emails:
        known = dict(db.execute(select(func.lower(User.email), User.id)
                                .where(func.lower(User.email).in_(emails))).all())
        for p in out["results"]:
            p["user_id"] = known.get(p["email"])
    return out


@router.get("/api/admin/directory-config")
def read_directory_config(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/directory-config: directory sources and SCIM settings (secrets masked)."""
    out = _masked(get_directory(db))
    out["scim_base_url"] = _scim_base_url(db, request)
    return out


@router.put("/api/admin/directory-config")
def update_directory_config(request: Request, payload: dict = Body(...), db: Session = Depends(get_db),
                            admin: User = Depends(require_admin)):
    """PUT /api/admin/directory-config: update the directory settings. Audited."""
    role = (payload or {}).get("scim_default_role")
    if role is not None:
        from ..personasconfig import valid_role_keys
        if role == "admin" or role not in valid_role_keys(db):
            raise HTTPException(status_code=400, detail="Persona inconnu ou non autorisé pour le provisioning")
    cfg = set_directory(db, _without_masks(payload))
    record_audit(db, admin.id, "directory_config.update", entity="directory",
                 detail={"sources": search_sources(cfg), "scim_enabled": cfg["scim_enabled"]})
    db.commit()
    out = _masked(cfg)
    out["scim_base_url"] = _scim_base_url(db, request)
    return out


@router.post("/api/admin/directory-config/test")
def test_directory_config(payload: dict = Body(...), db: Session = Depends(get_db),
                          admin: User = Depends(require_admin)):
    """POST /api/admin/directory-config/test: run a sample search on one source.

    Body ``{"source": "entra|ldap|google", "q": "...", "config": {...}}``: the
    draft values on screen are layered over the stored ones, so a change can be
    checked before it is saved. Nothing is persisted."""
    source = (payload or {}).get("source")
    if source not in ("entra", "ldap", "google"):
        raise HTTPException(status_code=400, detail="Source inconnue (attendu : entra, ldap ou google)")
    cfg = get_directory(db)
    for k, v in _without_masks((payload or {}).get("config") or {}).items():
        if k in cfg:
            cfg[k] = v
    q = ((payload or {}).get("q") or "").strip() or "a"
    try:
        people = directory.search_one(source, cfg, q, 5)
    except directory.DirectoryError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "count": len(people), "sample": people[:5]}


@router.post("/api/admin/directory-config/scim-token")
def generate_scim_token(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """POST /api/admin/directory-config/scim-token: a new SCIM bearer token.

    Returned once, only its hash is kept; the previous token stops working at once."""
    token = new_scim_token(db)
    record_audit(db, admin.id, "directory_config.scim_token", entity="directory")
    db.commit()
    return {"token": token}
