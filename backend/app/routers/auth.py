from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authconfig import get_auth_config, role_from_groups
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, record_audit
from ..models import User, utcnow
from ..schemas import AuthConfig, LoginIn, UserOut
from ..security import create_session_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        key=settings.session_cookie,
        value=create_session_token(user_id),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=False,
    )


@router.get("/config", response_model=AuthConfig)
def auth_config(db: Session = Depends(get_db)):
    cfg = get_auth_config(db)
    return AuthConfig(oidc_enabled=bool(cfg["oidc_enabled"]), saml_enabled=bool(cfg["saml_enabled"]))


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    user.last_login_at = utcnow()
    record_audit(db, user.id, "login.breakglass" if user.is_break_glass else "login.local",
                 entity="user", entity_id=user.id, detail={"email": user.email})
    db.commit()
    _set_session(response, user.id)
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.session_cookie)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/me/permissions")
def my_permissions(user: User = Depends(get_current_user)):
    from ..rbac import permissions_payload
    return permissions_payload(user)


def _provision(db: Session, *, subject: str | None, email: str, name: str, groups, cfg, source: str) -> User:
    user = None
    if subject:
        user = db.scalar(select(User).where(User.auth_subject == subject))
    if user is None and email:
        user = db.scalar(select(User).where(User.email == email))
    if user is None:
        role = role_from_groups(cfg, groups) or "member"
        user = User(email=email or subject, display_name=name or email, role=role, auth_subject=subject)
        db.add(user)
        db.flush()
        record_audit(db, user.id, f"user.provisioned.{source}", entity="user", entity_id=user.id,
                     detail={"email": email, "role": role})
    else:
        if subject and not user.auth_subject:
            user.auth_subject = subject
        mapped = role_from_groups(cfg, groups)
        if mapped:
            user.role = mapped
    user.last_login_at = utcnow()
    record_audit(db, user.id, f"login.{source}", entity="user", entity_id=user.id, detail={"email": email})
    return user


# ---------------- OIDC ----------------
@router.get("/oidc/login")
async def oidc_login(request: Request, db: Session = Depends(get_db)):
    cfg = get_auth_config(db)
    if not cfg["oidc_enabled"] or not cfg["oidc_issuer_url"] or not cfg["oidc_client_id"]:
        raise HTTPException(status_code=404, detail="OIDC désactivé ou mal configuré")
    from ..oidc import get_oauth
    oauth = get_oauth(cfg)
    request.session["_oidc_cfg"] = True
    return await oauth.oidc.authorize_redirect(request, cfg["oidc_redirect_uri"])


@router.get("/oidc/callback")
async def oidc_callback(request: Request, db: Session = Depends(get_db)):
    cfg = get_auth_config(db)
    if not cfg["oidc_enabled"]:
        raise HTTPException(status_code=404, detail="OIDC désactivé")
    from ..oidc import get_oauth
    oauth = get_oauth(cfg)
    token = await oauth.oidc.authorize_access_token(request)
    info = token.get("userinfo") or {}
    sub = info.get("sub")
    email = (info.get("email") or "").lower().strip()
    name = info.get("name") or info.get("preferred_username") or email
    groups = info.get(cfg.get("oidc_groups_claim") or "groups")
    if not email and not sub:
        raise HTTPException(status_code=400, detail="Réponse OIDC sans identité exploitable")
    user = _provision(db, subject=sub, email=email, name=name, groups=groups, cfg=cfg, source="oidc")
    db.commit()
    response = RedirectResponse(url="/")
    _set_session(response, user.id)
    return response


# ---------------- SAML ----------------
@router.get("/saml/metadata")
async def saml_metadata(db: Session = Depends(get_db)):
    cfg = get_auth_config(db)
    if not cfg["saml_enabled"]:
        raise HTTPException(status_code=404, detail="SAML désactivé")
    from ..saml import build_settings
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    s = OneLogin_Saml2_Settings(build_settings(cfg), sp_validation_only=True)
    metadata = s.get_sp_metadata()
    errors = s.validate_metadata(metadata)
    if errors:
        raise HTTPException(status_code=500, detail="Métadonnées SP invalides: " + ", ".join(errors))
    return Response(content=metadata, media_type="application/xml")


@router.get("/saml/login")
async def saml_login(request: Request, db: Session = Depends(get_db)):
    cfg = get_auth_config(db)
    if not cfg["saml_enabled"]:
        raise HTTPException(status_code=404, detail="SAML désactivé")
    from ..saml import make_auth
    auth = await make_auth(request, cfg)
    return RedirectResponse(url=auth.login())


@router.post("/saml/acs")
async def saml_acs(request: Request, db: Session = Depends(get_db)):
    cfg = get_auth_config(db)
    if not cfg["saml_enabled"]:
        raise HTTPException(status_code=404, detail="SAML désactivé")
    from ..saml import make_auth
    auth = await make_auth(request, cfg)
    auth.process_response()
    if auth.get_errors() or not auth.is_authenticated():
        raise HTTPException(status_code=401, detail="Authentification SAML refusée")
    attrs = auth.get_attributes()
    nameid = auth.get_nameid()
    email = (_first(attrs.get("email")) or nameid or "").lower().strip()
    name = _first(attrs.get("displayName")) or _first(attrs.get("name")) or email
    groups = attrs.get(cfg.get("saml_groups_attr") or "groups")
    user = _provision(db, subject=nameid, email=email, name=name, groups=groups, cfg=cfg, source="saml")
    db.commit()
    response = RedirectResponse(url="/", status_code=303)
    _set_session(response, user.id)
    return response


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value
