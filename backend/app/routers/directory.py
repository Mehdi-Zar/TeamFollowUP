"""Corporate directory: people search for the screens, and its Administration tab.

* ``GET /api/directory/status``: whether a search source is on (the screens then
  offer "search the directory"). Any signed-in user.
* ``GET /api/directory/search?q=``: people found in Entra ID, Active Directory,
  LDAP, Google Workspace, merged by email (``directory.search``). Writers only: the screens
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
from ..directoryconfig import (SECRETS, SOURCES, get_directory, new_scim_token, scim_token_ok,
                               search_sources, set_directory)
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
    from .scim import scim_base_url
    return scim_base_url(db, request)


def _with_urls(out: dict, db: Session, request: Request) -> dict:
    """The SCIM URL, and where its base comes from: the public URL configured in
    Administration > Authentification (shared with OIDC and SAML), or, when it is
    empty, the address of the request."""
    from ..authconfig import get_auth_config
    auth = get_auth_config(db, request)
    out["scim_base_url"] = _scim_base_url(db, request)
    out["public_base_url"] = auth.get("public_base_url") or ""
    out["base_url_source"] = auth.get("base_url_source")
    return out


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
    return _with_urls(_masked(get_directory(db)), db, request)


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
    return _with_urls(_masked(cfg), db, request)


@router.post("/api/admin/directory-config/test")
def test_directory_config(payload: dict = Body(...), db: Session = Depends(get_db),
                          admin: User = Depends(require_admin)):
    """POST /api/admin/directory-config/test: run a sample search on one source, step by step.

    Body ``{"source": "entra|ad|ldap|google", "mode": "user|group|custom", "q": "...",
    "custom": {...}, "config": {...}}``. ``mode`` picks a people search, a group
    search, or the administrator's own read-only query (``custom``: LDAP ``base``,
    ``scope`` base|one|sub, ``filter``, ``attributes``, ``limit``; Entra ``path``
    under /v1.0/ or /beta/; Google ``path`` under the Admin SDK directory and
    ``scope`` user|group), always on the configured server. The
    draft values on screen are layered over the stored ones, so a change can be
    checked before it is saved. Nothing is persisted. The answer lists each step
    (configuration, connection, authentication, query, attributes) with its
    outcome, duration and detail, the people found, and for LDAP and AD the first
    entry with all its attributes."""
    source = (payload or {}).get("source")
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail="Source inconnue (attendu : entra, ad, ldap ou google)")
    cfg = get_directory(db)
    for k, v in _without_masks((payload or {}).get("config") or {}).items():
        if k in cfg:
            cfg[k] = v
    custom = (payload or {}).get("custom")
    return directory.diagnose(source, cfg, (payload or {}).get("q") or "",
                              mode=(payload or {}).get("mode") or "user",
                              custom=custom if isinstance(custom, dict) else None)


@router.post("/api/admin/directory-config/scim-test")
def test_scim_config(request: Request, payload: dict = Body(default={}), db: Session = Depends(get_db),
                     admin: User = Depends(require_admin)):
    """POST /api/admin/directory-config/scim-test: what an identity provider would meet.

    Body ``{"token": "..."}`` (optional): the token pasted in the identity
    provider, checked against the stored hash. Returns the checks (enabled,
    token, URL, persona and tribe given to new accounts), the last calls received
    by this process, accepted or refused, and the last provisioning changes from
    the audit trail."""
    from ..models import AuditLog, Tribe
    from ..personasconfig import valid_role_keys
    from .scim import RECENT

    cfg = get_directory(db)
    url = _scim_base_url(db, request)
    steps = []

    def add(key, status, detail):
        steps.append({"key": key, "status": status, "detail": detail, "ms": None})

    add("enabled", "ok" if cfg.get("scim_enabled") else "fail",
        "provisioning activé" if cfg.get("scim_enabled")
        else "provisioning désactivé : toute requête reçoit 401. Activez-le et enregistrez.")
    if not cfg.get("scim_token_hash"):
        add("token", "fail", "aucun jeton généré : générez-en un et collez-le dans le fournisseur d'identité")
    else:
        presented = ((payload or {}).get("token") or "").strip()
        if not presented:
            add("token", "ok", f"jeton en place ({cfg.get('scim_token_hint')}). Collez celui du fournisseur "
                               "d'identité dans le champ de test pour vérifier que c'est le même.")
        elif scim_token_ok(cfg, presented):
            add("token", "ok", "le jeton collé est bien le jeton en place")
        else:
            add("token", "fail", f"le jeton collé ne correspond pas au jeton en place ({cfg.get('scim_token_hint')}) : "
                                 "il a été régénéré depuis, ou mal copié. Les appels recevront 401.")
    from ..authconfig import get_auth_config
    configured = get_auth_config(db, request).get("base_url_source") == "configured"
    local = url.startswith(("http://localhost", "http://127.0.0.1", "http://testserver"))
    if not url.startswith("https://"):
        add("url", "warn" if local else "fail",
            url + " : Entra ID, Okta et PingFederate exigent HTTPS. Renseignez l'URL publique de "
                  "l'application (celle des rappels OIDC et SAML), derrière le reverse proxy TLS.")
    elif not configured:
        add("url", "warn", url + " : déduite de l'adresse de ce navigateur. Renseignez l'URL publique de "
                                 "l'application pour la figer, sinon elle change avec l'adresse utilisée.")
    else:
        add("url", "ok", url)
    role = cfg.get("scim_default_role") or "member"
    add("persona", "ok" if role in valid_role_keys(db) and role != "admin" else "fail",
        f"les comptes créés reçoivent le persona « {role} »")
    tid = cfg.get("scim_default_tribe_id")
    tribe = db.get(Tribe, tid) if tid else None
    add("tribe", "ok" if tribe else "warn",
        f"les comptes créés rejoignent la tribe « {tribe.name} »" if tribe
        else "aucune tribe : les comptes créés n'en ont pas, à rattacher à la main")
    calls = list(RECENT)[:15]
    if not calls:
        add("calls", "warn", "aucun appel reçu depuis le dernier démarrage : le fournisseur d'identité n'a pas "
                             "encore appelé, ou il n'atteint pas cette URL (pare-feu, proxy, DNS)")
    else:
        refused = [c for c in calls if c["outcome"] != "accepted"]
        add("calls", "warn" if calls[0]["outcome"] != "accepted" else "ok",
            f"{len(calls)} appel(s) récent(s), dont {len(refused)} refusé(s)")
    events = db.scalars(select(AuditLog).where(AuditLog.action.like("scim.%"))
                        .order_by(AuditLog.timestamp.desc()).limit(10)).all()
    return {
        "ok": not any(s["status"] == "fail" for s in steps),
        "steps": steps,
        "base_url": url,
        "calls": calls,
        "events": [{"at": e.timestamp.isoformat() if e.timestamp else None, "action": e.action,
                    "entity_id": e.entity_id} for e in events],
    }


@router.post("/api/admin/directory-config/scim-token")
def generate_scim_token(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """POST /api/admin/directory-config/scim-token: a new SCIM bearer token.

    Returned once, only its hash is kept; the previous token stops working at once."""
    token = new_scim_token(db)
    record_audit(db, admin.id, "directory_config.scim_token", entity="directory")
    db.commit()
    return {"token": token}
