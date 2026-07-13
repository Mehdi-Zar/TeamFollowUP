from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authconfig import get_auth_config, set_auth_config
from ..database import get_db
from ..deps import ADMIN, get_current_user, record_audit, require_admin
from ..generalconfig import get_general, set_general
from ..models import User
from ..rbac import (
    assignable_roles,
    can_assign_role,
    can_manage_user,
    can_manage_users,
    users_scope_tribe,
)
from ..schemas import (
    UserCreate,
    UserOut,
    UserUpdate,
)
from ..security import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_user_manager(actor: User) -> None:
    if not can_manage_users(actor):
        raise HTTPException(status_code=403, detail="Gestion des utilisateurs réservée aux administrateurs et tribe leaders")


def _assert_can_assign(db: Session, actor: User, role: str) -> None:
    """Admins may assign any existing persona (built-in or custom); others keep
    their built-in subset."""
    if actor.role == ADMIN:
        from ..personasconfig import valid_role_keys
        if role in valid_role_keys(db):
            return
        raise HTTPException(status_code=400, detail="Persona inconnu")
    if not can_assign_role(actor, role):
        raise HTTPException(status_code=403, detail=f"Rôle non autorisé (autorisés : {', '.join(assignable_roles(actor))})")


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _require_user_manager(actor)
    q = select(User).order_by(User.id)
    scope = users_scope_tribe(actor)  # None for admin, own tribe for tribe leader
    if scope is not None:
        q = q.where(User.tribe_id == scope)
    return list(db.scalars(q).all())


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _require_user_manager(actor)
    _assert_can_assign(db, actor, payload.role)
    # Tribe leaders can only create users inside their own tribe.
    tribe_id = payload.tribe_id if actor.role == "admin" else actor.tribe_id
    if actor.role != "admin" and payload.tribe_id not in (None, actor.tribe_id):
        raise HTTPException(status_code=403, detail="Vous ne pouvez créer des utilisateurs que dans votre tribe")
    email = payload.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    user = User(
        email=email,
        display_name=payload.display_name,
        role=payload.role,
        tribe_id=tribe_id,
        password_hash=hash_password(payload.password) if payload.password else None,
    )
    db.add(user)
    db.flush()
    record_audit(db, actor.id, "user.create", entity="user", entity_id=user.id,
                 detail={"email": email, "role": user.role})
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db),
                actor: User = Depends(get_current_user)):
    _require_user_manager(actor)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not can_manage_user(actor, user):
        raise HTTPException(status_code=403, detail="Cet utilisateur n'est pas dans votre périmètre")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        pw = data.pop("password")
        if pw:
            user.password_hash = hash_password(pw)
    # Role changes must stay within what the actor may assign.
    if "role" in data and data["role"] is not None:
        if user.is_break_glass and data["role"] != "admin":
            raise HTTPException(status_code=400, detail="Le compte de secours doit rester administrateur")
        _assert_can_assign(db, actor, data["role"])
    # Only an admin may move a user to another tribe.
    if "tribe_id" in data and actor.role != "admin" and data["tribe_id"] != actor.tribe_id:
        raise HTTPException(status_code=403, detail="Vous ne pouvez pas déplacer un utilisateur hors de votre tribe")
    for k, v in data.items():
        setattr(user, k, v)
    record_audit(db, actor.id, "user.update", entity="user", entity_id=user.id, detail=data)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _require_user_manager(actor)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.is_break_glass:
        raise HTTPException(status_code=400, detail="Le compte de secours ne peut pas être supprimé")
    if user.id == actor.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")
    if not can_manage_user(actor, user):
        raise HTTPException(status_code=403, detail="Cet utilisateur n'est pas dans votre périmètre")
    record_audit(db, actor.id, "user.delete", entity="user", entity_id=user.id, detail={"email": user.email})
    db.delete(user)
    db.commit()


@router.get("/settings")
def get_settings_endpoint(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return get_general(db)


@router.put("/settings")
def update_settings_endpoint(payload: dict = Body(...), db: Session = Depends(get_db),
                             admin: User = Depends(require_admin)):
    cfg = set_general(db, payload)
    record_audit(db, admin.id, "settings.update", entity="settings", detail=payload)
    db.commit()
    return cfg


@router.get("/auth-config")
def read_auth_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return get_auth_config(db)


@router.put("/auth-config")
def update_auth_config(payload: dict = Body(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    cfg = set_auth_config(db, payload)
    record_audit(db, admin.id, "auth_config.update", entity="auth_config",
                 detail={"oidc_enabled": cfg["oidc_enabled"], "saml_enabled": cfg["saml_enabled"]})
    db.commit()
    return cfg


@router.get("/smtp-config")
def read_smtp_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..smtpconfig import get_smtp
    return get_smtp(db)


@router.put("/smtp-config")
def update_smtp_config(payload: dict = Body(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..smtpconfig import set_smtp
    cfg = set_smtp(db, payload)
    record_audit(db, admin.id, "smtp_config.update", entity="smtp", detail={"enabled": cfg["enabled"], "host": cfg["host"]})
    db.commit()
    return cfg


@router.post("/smtp-config/test")
def test_smtp(payload: dict = Body(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..smtpconfig import get_smtp
    from ..mail import send_email
    to = (payload or {}).get("to") or admin.email
    cfg = get_smtp(db)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="SMTP désactivé")
    ok = send_email(cfg, to, "Tribe Cockpit - test SMTP",
                    "Ceci est un email de test envoyé depuis Tribe Cockpit. Si vous le recevez, la configuration SMTP fonctionne.")
    return {"ok": ok, "to": to}


@router.get("/personas")
def read_personas(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..personasconfig import get_personas, CAPABILITIES
    return {"capabilities": CAPABILITIES, "personas": get_personas(db)}


@router.put("/personas")
def update_personas(payload: dict = Body(...), db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    from ..personasconfig import set_personas, valid_role_keys, CAPABILITIES
    personas = set_personas(db, payload.get("personas", []))
    # Reassign users whose persona was removed, so nobody is left without access.
    valid = valid_role_keys(db)
    for u in db.scalars(select(User)).all():
        if u.role not in valid and not u.is_break_glass:
            u.role = "member"
    record_audit(db, admin.id, "personas.update", entity="personas",
                 detail={"keys": [p["key"] for p in personas]})
    db.commit()
    return {"capabilities": CAPABILITIES, "personas": personas}


@router.get("/modules-config")
def read_modules_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..modulesconfig import get_modules
    return get_modules(db)


@router.put("/modules-config")
def update_modules_config(payload: dict = Body(...), db: Session = Depends(get_db),
                          admin: User = Depends(require_admin)):
    from ..modulesconfig import set_modules
    cfg = set_modules(db, payload)
    record_audit(db, admin.id, "modules_config.update", entity="modules",
                 detail={m: v.get("enabled") for m, v in cfg.items()})
    db.commit()
    return cfg


@router.get("/report-config")
def read_report_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..reportconfig import get_report
    return get_report(db)


@router.put("/report-config")
def update_report_config(payload: dict = Body(...), db: Session = Depends(get_db),
                         admin: User = Depends(require_admin)):
    from ..reportconfig import set_report
    # last_sent_week is bookkeeping owned by the scheduler - never let the UI set it.
    payload = {k: v for k, v in (payload or {}).items() if k != "last_sent_week"}
    cfg = set_report(db, payload)
    record_audit(db, admin.id, "report_config.update", entity="weekly_report",
                 detail={"enabled": cfg["enabled"], "weekday": cfg["weekday"],
                         "hour": cfg["hour"], "recipients": len(cfg["recipients"])})
    db.commit()
    return cfg


@router.post("/report-config/test")
def test_report_config(payload: dict = Body(default=None), db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    """Send the weekly report now to the admin (or a chosen address) as a check."""
    from ..smtpconfig import get_smtp
    from ..mail import send_email
    from ..report import build_report_data, render_html, render_pptx
    from .. import status as st

    to = (payload or {}).get("to") or admin.email
    cfg = get_smtp(db)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="SMTP désactivé")
    year = st.current_year_quarter()[0]
    data = build_report_data(db, None, year, 7)
    html_body = render_html(data, standalone=True)
    attachment = None
    try:
        pptx_bytes = render_pptx(data)
        attachment = (f"rapport_hebdo_{year}.pptx", pptx_bytes,
                      "application", "vnd.openxmlformats-officedocument.presentationml.presentation")
    except ImportError:
        pass
    ok = send_email(cfg, to, f"{data['app_name']} - Rapport hebdomadaire (test)",
                    html_body, attachment=attachment, html=True)
    record_audit(db, admin.id, "report_config.test", entity="weekly_report", detail={"ok": ok, "to": to})
    db.commit()
    return {"ok": ok, "to": to, "pptx": bool(attachment)}


# ---------- Change-notification emails (on modification) ----------
@router.get("/change-notify-config")
def read_change_notify_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..changeconfig import get_change_notify, ALL_EVENTS
    cfg = get_change_notify(db)
    cfg["_all_events"] = ALL_EVENTS  # let the UI render every available condition
    return cfg


@router.put("/change-notify-config")
def update_change_notify_config(payload: dict = Body(...), db: Session = Depends(get_db),
                                admin: User = Depends(require_admin)):
    from ..changeconfig import set_change_notify
    payload = {k: v for k, v in (payload or {}).items() if not k.startswith("_")}
    cfg = set_change_notify(db, payload)
    record_audit(db, admin.id, "change_notify_config.update", entity="change_notify",
                 detail={"enabled": cfg["enabled"], "events": cfg["events"],
                         "recipients": len(cfg["recipients"]),
                         "min_interval_minutes": cfg["min_interval_minutes"]})
    db.commit()
    return cfg


@router.post("/change-notify-config/test")
def test_change_notify_config(payload: dict = Body(default=None), db: Session = Depends(get_db),
                              admin: User = Depends(require_admin)):
    """Send a sample change-notification (a real squad's export) to verify setup."""
    from ..smtpconfig import get_smtp
    from ..mail import send_email
    from ..report import build_report_data, render_html, render_pptx
    from ..models import Squad
    from .. import status as st

    to = (payload or {}).get("to") or admin.email
    squad_id = (payload or {}).get("squad_id")
    cfg = get_smtp(db)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="SMTP désactivé")
    squad = db.get(Squad, squad_id) if squad_id else db.scalars(select(Squad).order_by(Squad.display_order, Squad.id)).first()
    if squad is None:
        raise HTTPException(status_code=400, detail="Aucune squad disponible pour le test")
    year = st.current_year_quarter()[0]
    data = build_report_data(db, None, year, 7, squad_id=squad.id)
    html_body = render_html(data, standalone=True)
    attachment = None
    try:
        pptx_bytes = render_pptx(data)
        attachment = (f"{squad.name}_{year}.pptx", pptx_bytes,
                      "application", "vnd.openxmlformats-officedocument.presentationml.presentation")
    except Exception:
        pass
    ok = send_email(cfg, to, f"[Reporting] {squad.name} — test", html_body, attachment=attachment, html=True)
    record_audit(db, admin.id, "change_notify_config.test", entity="change_notify",
                 detail={"ok": ok, "to": to, "squad": squad.name})
    db.commit()
    return {"ok": ok, "to": to, "squad": squad.name}


@router.get("/log-export-config")
def read_log_export_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..logexportconfig import get_log_export
    return get_log_export(db)


@router.put("/log-export-config")
def update_log_export_config(payload: dict = Body(...), db: Session = Depends(get_db),
                             admin: User = Depends(require_admin)):
    from ..logexportconfig import set_log_export
    cfg = set_log_export(db, payload)
    record_audit(db, admin.id, "log_export_config.update", entity="log_export",
                 detail={"enabled": cfg["enabled"], "destination": cfg["destination"]})
    db.commit()
    return cfg


@router.post("/log-export-config/test")
def test_log_export(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..logexportconfig import get_log_export
    from ..logexport import export_entries, sample_entry
    cfg = get_log_export(db, reveal_secrets=True)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="Export des logs désactivé")
    ok, message = export_entries(cfg, [sample_entry()])
    record_audit(db, admin.id, "log_export.test", entity="log_export",
                 detail={"destination": cfg["destination"], "ok": ok})
    db.commit()
    return {"ok": ok, "message": message, "destination": cfg["destination"]}


@router.post("/log-export-config/flush")
def flush_log_export(payload: dict = Body(default=None), db: Session = Depends(get_db),
                     admin: User = Depends(require_admin)):
    from ..logexportconfig import get_log_export
    from ..logexport import export_entries, serialize_entries
    cfg = get_log_export(db, reveal_secrets=True)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="Export des logs désactivé")
    limit = int((payload or {}).get("limit") or 200)
    limit = max(1, min(limit, 1000))
    entries = serialize_entries(db, limit=limit)
    ok, message = export_entries(cfg, entries)
    record_audit(db, admin.id, "log_export.flush", entity="log_export",
                 detail={"destination": cfg["destination"], "count": len(entries), "ok": ok})
    db.commit()
    return {"ok": ok, "message": message, "count": len(entries), "destination": cfg["destination"]}


# =============================================================================
# HTTPS / TLS certificates
# =============================================================================

async def _text_from(upload: UploadFile | None, pasted: str | None) -> str:
    if upload is not None:
        return (await upload.read()).decode("utf-8", errors="replace")
    return pasted or ""


@router.get("/tls-config")
def read_tls_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..tlsconfig import status
    return status(db)


@router.put("/tls-config")
def update_tls_config(payload: dict = Body(...), db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    from ..tlsconfig import set_options
    cfg = set_options(db, payload)
    record_audit(db, admin.id, "tls_config.update", entity="tls",
                 detail={"redirect_http": cfg["redirect_http"]})
    db.commit()
    return cfg


@router.post("/tls-config/self-signed")
def tls_regenerate_self_signed(payload: dict = Body(default=None), db: Session = Depends(get_db),
                               admin: User = Depends(require_admin)):
    from ..tlsconfig import regenerate_self_signed
    payload = payload or {}
    cn = (payload.get("cn") or "localhost").strip()
    sans = payload.get("sans")
    if isinstance(sans, str):
        sans = [s.strip() for s in sans.replace("\n", ",").split(",")]
    try:
        cfg = regenerate_self_signed(db, cn=cn, sans=sans)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    record_audit(db, admin.id, "tls_config.self_signed", entity="tls", detail={"cn": cn})
    db.commit()
    return cfg


@router.post("/tls-config/import-pem")
async def tls_import_pem(
    cert: UploadFile | None = File(default=None),
    key: UploadFile | None = File(default=None),
    cert_pem: str | None = Form(default=None),
    key_pem: str | None = Form(default=None),
    passphrase: str | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from ..tlsconfig import import_pem
    cert_text = await _text_from(cert, cert_pem)
    key_text = await _text_from(key, key_pem)
    if not cert_text.strip() or not key_text.strip():
        raise HTTPException(status_code=400, detail="Certificat et clé privée requis (fichier ou texte).")
    try:
        cfg = import_pem(db, cert_text, key_text, passphrase or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Import PEM impossible : {exc}")
    record_audit(db, admin.id, "tls_config.import_pem", entity="tls",
                 detail={"subject": (cfg.get("active") or {}).get("subject")})
    db.commit()
    return cfg


@router.post("/tls-config/import-pfx")
async def tls_import_pfx(
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from ..tlsconfig import import_pfx
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier PFX vide.")
    try:
        cfg = import_pfx(db, data, password or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Import PFX impossible (mot de passe ?) : {exc}")
    record_audit(db, admin.id, "tls_config.import_pfx", entity="tls",
                 detail={"subject": (cfg.get("active") or {}).get("subject")})
    db.commit()
    return cfg


@router.post("/tls-config/ca")
async def tls_add_ca(
    ca: UploadFile | None = File(default=None),
    ca_pem: str | None = Form(default=None),
    name: str | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from ..tlsconfig import add_ca
    pem = await _text_from(ca, ca_pem)
    if not pem.strip():
        raise HTTPException(status_code=400, detail="Certificat d'autorité requis (fichier ou texte).")
    try:
        cfg = add_ca(db, pem, (name or "").strip() or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Ajout d'autorité impossible : {exc}")
    record_audit(db, admin.id, "tls_config.add_ca", entity="tls", detail={"name": name})
    db.commit()
    return cfg


@router.delete("/tls-config/ca/{ca_id}")
def tls_remove_ca(ca_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..tlsconfig import remove_ca
    try:
        cfg = remove_ca(db, ca_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    record_audit(db, admin.id, "tls_config.remove_ca", entity="tls", detail={"ca_id": ca_id})
    db.commit()
    return cfg


@router.get("/tls-config/ca/{ca_id}/download")
def tls_download_ca(ca_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..tlsconfig import export_ca_pem
    try:
        pem = export_ca_pem(db, ca_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return PlainTextResponse(pem, headers={"Content-Disposition": f'attachment; filename="ca-{ca_id}.pem"'})


@router.get("/tls-config/active/download")
def tls_download_active(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..tlsconfig import export_active_cert_pem
    try:
        pem = export_active_cert_pem(db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return PlainTextResponse(pem, headers={"Content-Disposition": 'attachment; filename="server-cert.pem"'})



# ----- API keys (Admin -> API) ------------------------------------------------
# A key is a service credential: created here, shown ONCE, then only ever
# identified by its prefix. See app/apikeys.py for the model and the scopes.

@router.get("/api-keys")
def list_api_keys(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from ..apikeys import SCOPES, public
    from ..models import ApiKey
    keys = db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
    return {"scopes": SCOPES, "keys": [public(k) for k in keys]}


@router.post("/api-keys", status_code=201)
def create_api_key(payload: dict = Body(...), db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    """Mint a key. The plaintext secret is returned HERE AND NOWHERE ELSE."""
    from datetime import timedelta

    from ..apikeys import generate_key, hash_key, normalize_scopes, public, split_key
    from ..models import ApiKey, utcnow

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom requis")
    scopes = normalize_scopes(payload.get("scopes"))
    if not scopes:
        raise HTTPException(status_code=400, detail="Au moins un scope est requis")

    expires_at = None
    days = payload.get("expires_in_days")
    if days not in (None, "", 0):
        try:
            days = int(days)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Durée de validité invalide")
        if days < 1:
            raise HTTPException(status_code=400, detail="Durée de validité invalide")
        expires_at = utcnow() + timedelta(days=days)

    secret, prefix = generate_key()
    key = ApiKey(
        name=name,
        prefix=prefix,
        key_hash=hash_key(split_key(secret)[1]),
        scopes=scopes,
        tribe_id=payload.get("tribe_id"),
        created_by_user_id=admin.id,
        expires_at=expires_at,
    )
    db.add(key)
    db.flush()
    record_audit(db, admin.id, "api_key.create", entity="api_key", entity_id=key.id,
                 detail={"name": name, "prefix": prefix, "scopes": scopes,
                         "tribe_id": key.tribe_id})
    db.commit()
    # `secret` is the only time the caller will ever see it.
    return {**public(key), "secret": secret}


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(key_id: int, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    """Revoking is immediate and irreversible - the row is kept for the audit trail."""
    from ..apikeys import public
    from ..models import ApiKey, utcnow
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Clé introuvable")
    if key.revoked_at is None:
        key.revoked_at = utcnow()
        record_audit(db, admin.id, "api_key.revoke", entity="api_key", entity_id=key.id,
                     detail={"name": key.name, "prefix": key.prefix})
        db.commit()
    return public(key)


@router.delete("/api-keys/{key_id}", status_code=204)
def delete_api_key(key_id: int, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    from ..models import ApiKey
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Clé introuvable")
    record_audit(db, admin.id, "api_key.delete", entity="api_key", entity_id=key.id,
                 detail={"name": key.name, "prefix": key.prefix})
    db.delete(key)
    db.commit()
