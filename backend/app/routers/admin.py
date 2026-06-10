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

