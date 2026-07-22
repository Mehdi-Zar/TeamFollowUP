"""Admin console endpoints (prefix ``/api/admin``).

This router groups everything managed from the Admin area: user management,
application settings, authentication (OIDC/SAML) and SMTP config, personas
(custom roles + capabilities), feature modules, the weekly report and
change-notification emails, log export, TLS/HTTPS certificates, and service
API keys.

Access model: most endpoints are admin-only (``require_admin``). User management
is the exception — it is opened to tribe leaders as well, but strictly scoped to
their own tribe (see ``_require_user_manager`` / ``users_scope_tribe``). Every
mutating endpoint writes an audit entry via ``record_audit`` before committing.
"""
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response
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
    """Guard for the user-management endpoints: only admins and tribe leaders may
    manage users. Raises 403 for anyone else."""
    if not can_manage_users(actor):
        raise HTTPException(status_code=403, detail="Gestion des utilisateurs réservée aux administrateurs et tribe leaders")


def _assert_can_assign(db: Session, actor: User, role: str) -> None:
    """Guard: verify ``actor`` is allowed to grant ``role`` to a user.

    Admins may assign any existing persona (built-in or custom); others keep
    their built-in subset. Raises 400 for an unknown persona, 403 for a role
    outside the actor's assignable set."""
    if actor.role == ADMIN:
        from ..personasconfig import valid_role_keys
        if role in valid_role_keys(db):
            return
        raise HTTPException(status_code=400, detail="Persona inconnu")
    if not can_assign_role(actor, role):
        raise HTTPException(status_code=403, detail=f"Rôle non autorisé (autorisés : {', '.join(assignable_roles(actor))})")


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """GET /api/admin/users — list users.

    Admins and tribe leaders only. A tribe leader sees only users of their own
    tribe (scope from ``users_scope_tribe``); an admin sees everyone."""
    _require_user_manager(actor)
    q = select(User).order_by(User.id)
    scope = users_scope_tribe(actor)  # None for admin, own tribe for tribe leader
    if scope is not None:
        q = q.where(User.tribe_id == scope)
    return list(db.scalars(q).all())


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """POST /api/admin/users — create a user (201).

    Admins and tribe leaders only. The actor must be allowed to assign the
    requested role, and a tribe leader may only create users inside their own
    tribe. Email must be unique. Writes a ``user.create`` audit entry."""
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
    """PUT /api/admin/users/{user_id} — update a user.

    Admins and tribe leaders only, and the target must be inside the actor's
    scope (``can_manage_user``). Enforces several rules: role changes stay within
    what the actor may assign; the break-glass account must remain admin; only an
    admin may move a user to a different tribe. Writes a ``user.update`` audit."""
    _require_user_manager(actor)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    # Scope check: tribe leaders can only touch users in their own tribe.
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
    """DELETE /api/admin/users/{user_id} — delete a user (204).

    Admins and tribe leaders only, target must be in the actor's scope. The
    break-glass account cannot be deleted, and nobody may delete their own
    account. Writes a ``user.delete`` audit entry."""
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
    """GET /api/admin/settings — read general application settings. Admin only."""
    return get_general(db)


@router.put("/settings")
def update_settings_endpoint(payload: dict = Body(...), db: Session = Depends(get_db),
                             admin: User = Depends(require_admin)):
    """PUT /api/admin/settings — update general settings. Admin only; audited."""
    cfg = set_general(db, payload)
    record_audit(db, admin.id, "settings.update", entity="settings", detail=payload)
    db.commit()
    return cfg


@router.get("/auth-config")
def read_auth_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/auth-config — read the OIDC/SAML auth config. Admin only."""
    return get_auth_config(db)


@router.put("/auth-config")
def update_auth_config(payload: dict = Body(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """PUT /api/admin/auth-config — update the OIDC/SAML auth config. Admin only;
    audits which providers are enabled."""
    cfg = set_auth_config(db, payload)
    record_audit(db, admin.id, "auth_config.update", entity="auth_config",
                 detail={"oidc_enabled": cfg["oidc_enabled"], "saml_enabled": cfg["saml_enabled"]})
    db.commit()
    return cfg


@router.get("/smtp-config")
def read_smtp_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/smtp-config — read outbound email (SMTP) config. Admin only."""
    from ..smtpconfig import get_smtp
    return get_smtp(db)


@router.put("/smtp-config")
def update_smtp_config(payload: dict = Body(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """PUT /api/admin/smtp-config — update the SMTP config. Admin only; audited."""
    from ..smtpconfig import set_smtp
    cfg = set_smtp(db, payload)
    record_audit(db, admin.id, "smtp_config.update", entity="smtp", detail={"enabled": cfg["enabled"], "host": cfg["host"]})
    db.commit()
    return cfg


@router.post("/smtp-config/test")
def test_smtp(payload: dict = Body(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """POST /api/admin/smtp-config/test — send a test email to check SMTP.

    Admin only. Sends to ``payload.to`` or, by default, the admin's own address.
    Fails with 400 if SMTP is disabled."""
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
    """GET /api/admin/personas — list personas (roles) and the full capability
    catalogue the UI can toggle. Admin only."""
    from ..personasconfig import get_personas, CAPABILITIES
    return {"capabilities": CAPABILITIES, "personas": get_personas(db)}


@router.put("/personas")
def update_personas(payload: dict = Body(...), db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """PUT /api/admin/personas — replace the persona definitions. Admin only.

    Side effect: any user whose persona no longer exists is downgraded to
    ``member`` (the break-glass account is left untouched) so nobody is stranded
    with an invalid role. Audited."""
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
    """GET /api/admin/modules-config — read feature-module enablement. Admin only."""
    from ..modulesconfig import get_modules
    return get_modules(db)


@router.put("/modules-config")
def update_modules_config(payload: dict = Body(...), db: Session = Depends(get_db),
                          admin: User = Depends(require_admin)):
    """PUT /api/admin/modules-config — enable/disable feature modules. Admin only;
    audits which modules ended up enabled."""
    from ..modulesconfig import set_modules
    cfg = set_modules(db, payload)
    record_audit(db, admin.id, "modules_config.update", entity="modules",
                 detail={m: v.get("enabled") for m, v in cfg.items()})
    db.commit()
    return cfg


@router.get("/report-config")
def read_report_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/report-config — read the weekly-report schedule/recipients.
    Admin only."""
    from ..reportconfig import get_report
    return get_report(db)


@router.put("/report-config")
def update_report_config(payload: dict = Body(...), db: Session = Depends(get_db),
                         admin: User = Depends(require_admin)):
    """PUT /api/admin/report-config — update the weekly-report schedule. Admin
    only; audited. ``last_sent_week`` is scheduler bookkeeping and is stripped
    from the payload so the UI can never overwrite it."""
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
    """POST /api/admin/report-config/test — send the weekly report now to the
    admin (or a chosen address) as a check. Admin only.

    Builds the current-year report, renders the HTML body and (if python-pptx is
    available) attaches the PPTX. Fails with 400 if SMTP is disabled. Audited."""
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
    """GET /api/admin/change-notify-config — read the on-modification email config.
    Admin only. Also returns the full ``_all_events`` catalogue so the UI can
    render every available trigger condition."""
    from ..changeconfig import get_change_notify, ALL_EVENTS
    cfg = get_change_notify(db)
    cfg["_all_events"] = ALL_EVENTS  # let the UI render every available condition
    return cfg


@router.put("/change-notify-config")
def update_change_notify_config(payload: dict = Body(...), db: Session = Depends(get_db),
                                admin: User = Depends(require_admin)):
    """PUT /api/admin/change-notify-config — update the on-modification email
    config. Admin only; audited. Keys prefixed with ``_`` are UI-only helpers
    (e.g. ``_all_events``) and are stripped before saving."""
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
    """POST /api/admin/change-notify-config/test — send a sample change
    notification (a real squad's export) to verify setup. Admin only.

    Uses ``payload.squad_id`` or the first squad by display order. Fails with 400
    if SMTP is disabled or no squad exists. Audited."""
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
    ok = send_email(cfg, to, f"[Reporting] {squad.name} - test", html_body, attachment=attachment, html=True)
    record_audit(db, admin.id, "change_notify_config.test", entity="change_notify",
                 detail={"ok": ok, "to": to, "squad": squad.name})
    db.commit()
    return {"ok": ok, "to": to, "squad": squad.name}


@router.get("/log-export-config")
def read_log_export_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/log-export-config — read the audit-log export config (e.g.
    SIEM destination). Admin only; secrets stay masked."""
    from ..logexportconfig import get_log_export
    return get_log_export(db)


@router.put("/log-export-config")
def update_log_export_config(payload: dict = Body(...), db: Session = Depends(get_db),
                             admin: User = Depends(require_admin)):
    """PUT /api/admin/log-export-config — update the log-export config. Admin
    only; audited."""
    from ..logexportconfig import set_log_export
    cfg = set_log_export(db, payload)
    record_audit(db, admin.id, "log_export_config.update", entity="log_export",
                 detail={"enabled": cfg["enabled"], "destination": cfg["destination"]})
    db.commit()
    return cfg


@router.post("/log-export-config/test")
def test_log_export(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """POST /api/admin/log-export-config/test — push a single synthetic entry to
    the configured destination to check connectivity. Admin only.

    Reads the config with secrets revealed (needed to actually connect). Fails
    with 400 if export is disabled. Audited."""
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
    """POST /api/admin/log-export-config/flush — export the most recent audit
    entries on demand. Admin only.

    ``payload.limit`` (default 200) is clamped to 1..1000. Fails with 400 if
    export is disabled. Audited."""
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
    """Return PEM text either from an uploaded file or from a pasted string.

    Every TLS endpoint accepts both an upload and a textarea; the upload wins."""
    if upload is not None:
        return (await upload.read()).decode("utf-8", errors="replace")
    return pasted or ""


@router.get("/tls-config")
def read_tls_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/tls-config — read the current TLS status (active cert +
    trusted CAs). Admin only."""
    from ..tlsconfig import status
    return status(db)


@router.post("/tls-config/enabled")
def tls_set_enabled(payload: dict = Body(default=None), db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """POST /api/admin/tls-config/enabled - toggle in-app TLS termination.

    Body: ``{"enabled": bool}``. When false the app serves plain HTTP and the
    infrastructure (Gateway/ALB) terminates TLS. Applied at the next server start
    (the listener is bound at boot), so the response's ``tls_running`` may still
    differ from ``tls_enabled`` until then. Admin only. Audited."""
    from ..tlsconfig import set_tls_enabled
    enabled = bool((payload or {}).get("enabled"))
    st = set_tls_enabled(db, enabled)
    record_audit(db, admin.id, "tls_config.set_enabled", entity="tls", detail={"enabled": enabled})
    db.commit()
    return st


@router.post("/tls-config/self-signed")
def tls_regenerate_self_signed(payload: dict = Body(default=None), db: Session = Depends(get_db),
                               admin: User = Depends(require_admin)):
    """POST /api/admin/tls-config/self-signed — (re)generate a self-signed cert.
    Admin only.

    ``cn`` defaults to ``localhost``; ``sans`` may be a list or a comma/newline
    separated string. Invalid input yields 400. Audited."""
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
    """POST /api/admin/tls-config/import-pem — install a cert + private key from
    PEM (uploaded files or pasted text). Admin only.

    Both cert and key are required (400 otherwise); an optional ``passphrase``
    decrypts the key. Parse/validation errors yield 400. Audited."""
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
    """POST /api/admin/tls-config/import-pfx — install a cert + key from a PKCS#12
    (.pfx) bundle. Admin only.

    Empty file yields 400; a wrong password or malformed bundle also yields 400.
    Audited."""
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
    """POST /api/admin/tls-config/ca — add a trusted CA certificate (upload or
    pasted text), with an optional friendly ``name``. Admin only.

    Empty/invalid input yields 400. Audited."""
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
    """DELETE /api/admin/tls-config/ca/{ca_id} — remove a trusted CA. Admin only.
    Unknown id yields 404. Audited."""
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
    """GET /api/admin/tls-config/ca/{ca_id}/download — download a trusted CA as a
    PEM attachment. Admin only. Unknown id yields 404."""
    from ..tlsconfig import export_ca_pem
    try:
        pem = export_ca_pem(db, ca_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return PlainTextResponse(pem, headers={"Content-Disposition": f'attachment; filename="ca-{ca_id}.pem"'})


@router.get("/tls-config/active/download")
def tls_download_active(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/tls-config/active/download — download the active server
    certificate as a PEM attachment. Admin only. 404 if none is set."""
    from ..tlsconfig import export_active_cert_pem
    try:
        pem = export_active_cert_pem(db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return PlainTextResponse(pem, headers={"Content-Disposition": 'attachment; filename="server-cert.pem"'})


# ----- Ops / Maintenance (Admin -> Ops) --------------------------------------
# Runtime diagnostics + a self-restart button. The listener (HTTP vs in-app TLS)
# is bound at boot, so config like the TLS toggle needs a restart to take effect;
# rather than shell in, an admin can trigger it here. See app/ops.py.

@router.get("/runtime")
def read_runtime(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/runtime : read-only runtime diagnostics (version, host, uptime,
    serving mode, whether a restart is pending). Admin only."""
    from ..ops import runtime_status
    return runtime_status(db)


@router.post("/restart")
def restart_app(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """POST /api/admin/restart : gracefully restart the application.

    Schedules a SIGTERM on our own process right after this response; uvicorn drains
    in-flight requests and exits, and the orchestrator (Docker/Kubernetes) restarts
    the container with the current configuration applied. Admin only. Audited.
    Returns whether the restart was scheduled and whether a supervisor will bring the
    process back (``auto_restart``)."""
    from ..ops import request_restart
    record_audit(db, admin.id, "ops.restart", entity="ops", detail={})
    db.commit()
    return request_restart()


@router.get("/logs")
def read_logs(limit: int = 500, level: str | None = None,
              db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/logs?limit=&level= : recent application log records from the
    in-memory ring buffer (oldest first), plus the current level and buffer stats.
    ``level`` filters to that severity and above. Admin only."""
    from .. import logbuffer
    st = logbuffer.stats()
    return {
        "level": logbuffer.current_level(),
        "levels": logbuffer.LEVELS,
        "count": st["count"],
        "capacity": st["capacity"],
        "records": logbuffer.records(limit=limit, min_level=level),
    }


@router.get("/logs/download")
def download_logs(fmt: str = "txt", level: str | None = None,
                  db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/logs/download?fmt=txt|json&level= : download the buffered logs
    as a text or NDJSON attachment. Admin only. Audited."""
    from .. import logbuffer
    items = logbuffer.records(limit=logbuffer.CAPACITY, min_level=level)
    record_audit(db, admin.id, "ops.logs_download", entity="ops", detail={"fmt": fmt, "n": len(items)})
    db.commit()
    if fmt == "json":
        body, media, ext = logbuffer.as_ndjson(items), "application/x-ndjson", "ndjson"
    else:
        body, media, ext = logbuffer.as_text(items), "text/plain; charset=utf-8", "log"
    return PlainTextResponse(body, media_type=media,
                             headers={"Content-Disposition": f'attachment; filename="app-logs.{ext}"'})


@router.post("/log-level")
def set_log_level(payload: dict = Body(...), db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    """POST /api/admin/log-level : set the live log level (root + uvicorn loggers).

    Body: ``{"level": "DEBUG"|..., "persist": bool}``. When ``persist`` is true the
    level is stored and re-applied on the next restart. Admin only. Audited."""
    from .. import logbuffer
    level = str((payload or {}).get("level", "")).upper()
    persist = bool((payload or {}).get("persist"))
    try:
        applied = logbuffer.set_live_level(level)
        if persist:
            logbuffer.persist_level(db, level)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    record_audit(db, admin.id, "ops.set_log_level", entity="ops", detail={"level": applied, "persist": persist})
    db.commit()
    return {"level": applied, "persisted": persist}


@router.post("/logs/clear")
def clear_logs(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """POST /api/admin/logs/clear : empty the in-memory log buffer. Admin only. Audited."""
    from .. import logbuffer
    logbuffer.clear()
    record_audit(db, admin.id, "ops.logs_clear", entity="ops", detail={})
    db.commit()
    return {"ok": True}


# ----- API keys (Admin -> API) ------------------------------------------------
# A key is a service credential: created here, shown ONCE, then only ever
# identified by its prefix. See app/apikeys.py for the model and the scopes.

@router.get("/api-keys")
def list_api_keys(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/api-keys — list API keys (public view: prefix only, never
    the secret) plus the catalogue of assignable scopes. Admin only."""
    from ..apikeys import SCOPES, public
    from ..models import ApiKey
    keys = db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
    return {"scopes": SCOPES, "keys": [public(k) for k in keys]}


@router.post("/api-keys", status_code=201)
def create_api_key(payload: dict = Body(...), db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    """POST /api/admin/api-keys — mint a service API key (201). Admin only.

    The plaintext secret is returned HERE AND NOWHERE ELSE (only its hash is
    stored). Requires a name and at least one valid scope; an optional
    ``expires_in_days`` (>= 1) sets expiry, and ``tribe_id`` scopes the key to a
    tribe. Invalid input yields 400. Audited."""
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
    """POST /api/admin/api-keys/{key_id}/revoke — revoke a key. Admin only.

    Revoking is immediate and irreversible; the row is kept (not deleted) for the
    audit trail. Idempotent — re-revoking an already-revoked key is a no-op.
    Unknown id yields 404. Audited on the first revoke."""
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
    """DELETE /api/admin/api-keys/{key_id} — permanently delete a key (204). Admin
    only. Unlike revoke, this removes the row entirely. Unknown id yields 404.
    Audited."""
    from ..models import ApiKey
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Clé introuvable")
    record_audit(db, admin.id, "api_key.delete", entity="api_key", entity_id=key.id,
                 detail={"name": key.name, "prefix": key.prefix})
    db.delete(key)
    db.commit()


# ----- Organisation import (Admin -> Organisation) ----------------------------
# Populate a fresh environment (local or S3NS) from a filled Excel file, uploaded
# through the running app. No image rebuild is needed: the file is parsed in
# memory and imported idempotently (see app/import_org.py).

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/import-org/template")
def download_org_template(admin: User = Depends(require_admin)):
    """GET /api/admin/import-org/template — download the blank Excel template
    (4 sheets: Tribu / Squads / Initiatives / OTD) to fill in. Admin only."""
    from ..import_org import template_bytes
    return Response(
        content=template_bytes(),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="org.template.xlsx"'},
    )


@router.post("/import-org")
async def import_org_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """POST /api/admin/import-org — upload a filled Excel (.xlsx) or YAML file and
    import the organisation (tribe, squads + leaders, initiatives, OTD). Admin
    only. Idempotent: re-running updates existing rows instead of duplicating.

    Returns a summary of what was processed. 400 if the file is the wrong format
    or has no tribe. Audited."""
    from ..import_org import import_org, read_upload

    content = await file.read()
    try:
        data = read_upload(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not data or not (data.get("tribe") or {}).get("name"):
        raise HTTPException(status_code=400, detail="Le fichier doit definir une tribu (onglet 'Tribu' rempli).")
    try:
        summary = import_org(db, data)
    except Exception as exc:  # bad references, malformed cells, etc.
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Import impossible : {exc}")
    record_audit(db, admin.id, "org.import", entity="tribe", detail=summary)
    db.commit()
    return summary


# ----- Steerco import (Admin -> Import) ---------------------------------------
# Collect a squad's Steerco data (KPI/SLA/incidents/events, 12 months) in an Excel
# file and upload it here; parsed in memory and written to SteercoEntry rows.

@router.get("/import-steerco/template")
def download_steerco_template(squad_id: int | None = None, db: Session = Depends(get_db),
                              admin: User = Depends(require_admin)):
    """GET /api/admin/import-steerco/template?squad_id= : download the Steerco Excel
    template (Infos / KPIs / SLA / Incidents / Evenements) to fill in. Admin only.

    With ``squad_id`` the workbook is built *for that squad*: its name is pre-filled
    and the KPI / SLA rows are the ones it actually reports, so the file matches the
    app instead of proposing a canned list. Without it, the standard structure."""
    from ..models import Squad
    from ..steerco_import import structure_for_squad, template_bytes
    kpis = services = None
    name = ""
    if squad_id is not None:
        squad = db.get(Squad, squad_id)
        if squad is None:
            raise HTTPException(status_code=404, detail="Squad introuvable")
        kpis, services = structure_for_squad(db, squad_id)
        name = squad.name
    slug = "".join(c if c.isalnum() else "-" for c in name).strip("-").lower() or "template"
    return Response(
        content=template_bytes(None, kpis, services, name),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="steerco.{slug}.xlsx"'},
    )


@router.post("/import-steerco")
async def import_steerco_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """POST /api/admin/import-steerco : upload a filled Steerco Excel and write the
    squad's monthly snapshots (12-month history + full current month). Admin only.
    Idempotent per (squad, period). 400 on wrong format / unknown squad. Audited."""
    from ..steerco_import import import_steerco

    content = await file.read()
    try:
        summary = import_steerco(db, content, user_id=admin.id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # malformed cells, etc.
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Import impossible : {exc}")
    record_audit(db, admin.id, "steerco.import", entity="squad",
                 entity_id=summary.get("squad_id"), detail=summary)
    db.commit()
    return summary
