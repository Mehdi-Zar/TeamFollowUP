from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authconfig import get_auth_config, set_auth_config
from ..database import get_db
from ..deps import record_audit, require_admin
from ..generalconfig import get_general, set_general
from ..models import User
from ..schemas import (
    UserCreate,
    UserOut,
    UserUpdate,
)
from ..security import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return list(db.scalars(select(User).order_by(User.id)).all())


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    email = payload.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email déjà utilisé")
    user = User(
        email=email,
        display_name=payload.display_name,
        role=payload.role,
        tribe_id=payload.tribe_id,
        password_hash=hash_password(payload.password) if payload.password else None,
    )
    db.add(user)
    db.flush()
    record_audit(db, admin.id, "user.create", entity="user", entity_id=user.id,
                 detail={"email": email, "role": user.role})
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        pw = data.pop("password")
        if pw:
            user.password_hash = hash_password(pw)
    if data.get("role") and user.is_break_glass and data["role"] != "admin":
        raise HTTPException(status_code=400, detail="Le compte de secours doit rester administrateur")
    for k, v in data.items():
        setattr(user, k, v)
    record_audit(db, admin.id, "user.update", entity="user", entity_id=user.id, detail=data)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.is_break_glass:
        raise HTTPException(status_code=400, detail="Le compte de secours ne peut pas être supprimé")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")
    record_audit(db, admin.id, "user.delete", entity="user", entity_id=user.id, detail={"email": user.email})
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
    ok = send_email(cfg, to, "Tribe Cockpit — test SMTP",
                    "Ceci est un email de test envoyé depuis Tribe Cockpit. Si vous le recevez, la configuration SMTP fonctionne.")
    return {"ok": ok, "to": to}


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
    # last_sent_week is bookkeeping owned by the scheduler — never let the UI set it.
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
    ok = send_email(cfg, to, f"{data['app_name']} — Rapport hebdomadaire (test)",
                    html_body, attachment=attachment, html=True)
    record_audit(db, admin.id, "report_config.test", entity="weekly_report", detail={"ok": ok, "to": to})
    db.commit()
    return {"ok": ok, "to": to, "pptx": bool(attachment)}


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

