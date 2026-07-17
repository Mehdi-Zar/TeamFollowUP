"""Authentication router: local password login, OIDC & SAML SSO, impersonation.

Owns every way a user obtains (or drops) a session cookie:

  * ``/login`` — local email+password, with a per-IP brute-force throttle;
  * ``/oidc/*`` and ``/saml/*`` — SSO login/callback flows;
  * ``/me`` and ``/me/permissions`` — the identity + capability payload the SPA
    reads to decide what to render;
  * ``/impersonate`` / ``/stop-impersonation`` — admin "view as" simulation.

The shared ``_provision`` function implements just-in-time (JIT) provisioning for
SSO: it creates or updates the local account behind an IdP identity while
enforcing the account lifecycle (pending/active/disabled), the email-domain gate
and the IdP-group→role remap. See docs/05-security.md.
"""
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authconfig import email_domain_allowed, get_auth_config, role_from_groups
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_current_user_any_status, record_audit, require_admin
from ..models import User, utcnow
from ..schemas import AuthConfig, LoginIn, UserOut
from ..security import create_session_token, decode_session, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session(response: Response, user_id: int, impersonator_id: int | None = None) -> None:
    """Issue the signed session cookie for ``user_id``.

    ``impersonator_id`` is embedded when an admin is viewing the app as someone
    else, so the real actor is still recoverable. The cookie is HttpOnly (no JS
    access, mitigates XSS token theft) and its SameSite/Secure flags come from
    settings.
    """
    response.set_cookie(
        key=settings.session_cookie,
        value=create_session_token(user_id, impersonator_id),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
    )


# Simple in-memory per-IP login throttle (single-replica; see ADR-0009 for scale).
_login_failures: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """Best-effort client IP for throttling.

    Trusts the first X-Forwarded-For hop (we sit behind a known reverse proxy);
    falls back to the socket peer. Only used as a rate-limit key, not for authz.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_login_rate(ip: str) -> None:
    """Sliding-window brute-force guard: 429 once an IP exceeds the failure budget.

    Prunes failures older than the window, then rejects if too many recent ones
    remain. ``login_max_attempts <= 0`` disables the throttle entirely.
    """
    if settings.login_max_attempts <= 0:
        return
    now = time.time()
    q = _login_failures[ip]
    while q and now - q[0] > settings.login_window_seconds:
        q.popleft()
    if len(q) >= settings.login_max_attempts:
        raise HTTPException(status_code=429, detail="Trop de tentatives de connexion. Réessayez plus tard.")


@router.get("/config", response_model=AuthConfig)
def auth_config(db: Session = Depends(get_db)):
    """Public login-screen config: which SSO buttons (OIDC/SAML) to show."""
    cfg = get_auth_config(db)
    return AuthConfig(oidc_enabled=bool(cfg["oidc_enabled"]), saml_enabled=bool(cfg["saml_enabled"]))


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Local password login: verify credentials, enforce lifecycle, set session.

    Security notes:
      * Wrong email, no local password, or a bad password all yield the same
        generic 401 (no user-enumeration) and count as a throttled failure.
      * A "disabled" (revoked) account is refused with 403 even with correct
        credentials.
      * A successful login clears the IP's throttle counter and is audited (the
        break-glass account gets a distinct action for traceability).
    """
    ip = _client_ip(request)
    _check_login_rate(ip)
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        # Uniform failure path — do not reveal which of the three conditions failed.
        _login_failures[ip].append(time.time())
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    if user.status == "disabled":
        raise HTTPException(status_code=403, detail="Votre accès à cette application a été révoqué.")
    _login_failures.pop(ip, None)  # reset throttle on success
    user.last_login_at = utcnow()
    record_audit(db, user.id, "login.breakglass" if user.is_break_glass else "login.local",
                 entity="user", entity_id=user.id, detail={"email": user.email})
    db.commit()
    _set_session(response, user.id)
    return user


@router.post("/logout")
def logout(response: Response):
    """Clear the session cookie. Stateless — nothing server-side to invalidate."""
    response.delete_cookie(settings.session_cookie)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user_any_status)):
    # Returns even for pending/disabled accounts so the SPA can show the
    # "access pending / revoked" screen instead of a hard 401.
    return user


@router.get("/me/permissions")
def my_permissions(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user_any_status)):
    """The SPA's authorization map: role permissions + persona capabilities +
    access-review status + impersonation context.

    Uses ``_any_status`` so even a pending/disabled user gets a coherent (locked-
    down) payload rather than a 401. Capabilities gate section visibility client-
    side (and are re-checked server-side on the corresponding endpoints).
    """
    from ..rbac import permissions_payload
    from ..personasconfig import persona_caps, get_personas
    payload = permissions_payload(user)
    # Persona capabilities drive section access in the SPA (and a few endpoints).
    payload["capabilities"] = persona_caps(db, user.role)
    # Access-request queue: who may review, and how many are pending.
    from ..access import can_review_access, pending_count
    payload["can_review_access"] = can_review_access(user)
    payload["pending_access_count"] = pending_count(db, user)
    # Admins may assign any persona (built-in or custom); others keep their subset.
    if user.role == "admin":
        payload["assignable_roles"] = [p["key"] for p in get_personas(db)]
    # Impersonation context, so the SPA can show the "viewing as" banner.
    imp_id = getattr(request.state, "impersonator_id", None)
    payload["impersonating"] = imp_id is not None
    payload["viewing_as"] = user.display_name if imp_id is not None else None
    if imp_id is not None:
        admin = db.get(User, imp_id)
        payload["impersonator_name"] = admin.display_name if admin else None
    return payload


@router.post("/impersonate", response_model=UserOut)
def impersonate(payload: dict, response: Response, request: Request,
                db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Admin starts viewing the whole app as another user (full simulation)."""
    # If already impersonating, the real admin is the impersonator in the token.
    imp_id = getattr(request.state, "impersonator_id", None)
    real_admin_id = imp_id if imp_id is not None else admin.id
    target_id = (payload or {}).get("user_id")
    target = db.get(User, target_id) if target_id is not None else None
    if target is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if target.id == real_admin_id:
        # "viewing as myself" → just stop impersonating.
        _set_session(response, real_admin_id)
        return db.get(User, real_admin_id)
    record_audit(db, real_admin_id, "impersonate.start", entity="user", entity_id=target.id,
                 detail={"email": target.email})
    db.commit()
    _set_session(response, target.id, impersonator_id=real_admin_id)
    return target


@router.post("/stop-impersonation", response_model=UserOut)
def stop_impersonation(response: Response, request: Request,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """End a simulation: reissue a plain session for the original admin.

    The admin identity is recovered from the impersonator_id carried in the
    current (impersonated) session token, so no elevated input is trusted.
    """
    imp_id = getattr(request.state, "impersonator_id", None)
    if imp_id is None:
        raise HTTPException(status_code=400, detail="Aucune simulation en cours")
    admin = db.get(User, imp_id)
    if admin is None:
        raise HTTPException(status_code=404, detail="Compte administrateur introuvable")
    _set_session(response, admin.id)
    return admin


def _provision(db: Session, *, subject: str | None, email: str, name: str, groups, cfg, source: str) -> User:
    """Just-in-time provisioning for an SSO-authenticated identity (OIDC or SAML).

    Resolves the local account for the asserted identity and returns it ready to
    receive a session, creating it on first login. The IdP has proven *who* the
    user is; this function decides *whether and how* they enter:

    Account matching: by stable IdP subject first, then by email (so an existing
    local/email account gets linked to its SSO subject).

    New account:
      * blocked unless the email domain is allowlisted (first gate);
      * role proposed from IdP groups, defaulting to ``member``;
      * created ``pending`` (no access until a manager validates) when approval is
        required, else ``active``; a pending creation pings the reviewers.

    Existing account:
      * a ``disabled`` (revoked) account is refused even though the IdP accepted
        it — revocation wins over a valid SSO assertion;
      * the IdP subject is backfilled if it was missing;
      * the group→role remap is applied ONLY to already-``active`` accounts, so IdP
        claims can never silently elevate or re-activate a pending/disabled one.

    Side effects: writes audit rows and may enqueue notifications. Does not commit
    — the calling endpoint owns the transaction.
    """
    user = None
    if subject:
        # Prefer the stable IdP subject; email can change, the subject shouldn't.
        user = db.scalar(select(User).where(User.auth_subject == subject))
    if user is None and email:
        user = db.scalar(select(User).where(User.email == email))
    if user is None:
        # First gate: only allowed email domains may even be provisioned.
        if not email_domain_allowed(cfg, email):
            raise HTTPException(status_code=403, detail="Votre domaine de messagerie n'est pas autorisé à accéder à cette application.")
        proposed = role_from_groups(cfg, groups) or "member"
        # Second gate: when approval is required, the account starts pending (no
        # access) until a manager validates it.
        status = "pending" if cfg.get("require_approval", True) else "active"
        user = User(email=email or subject, display_name=name or email, role=proposed,
                    status=status, auth_subject=subject)
        db.add(user)
        db.flush()
        record_audit(db, user.id, f"user.provisioned.{source}", entity="user", entity_id=user.id,
                     detail={"email": email, "role": proposed, "status": status})
        if status == "pending":
            from ..access import notify_access_request
            notify_access_request(db, user)
    else:
        # A revoked account cannot log back in (even though the IdP authenticated it).
        if user.status == "disabled":
            raise HTTPException(status_code=403, detail="Votre accès à cette application a été révoqué.")
        if subject and not user.auth_subject:
            user.auth_subject = subject
        # Only (re)map the role for already-validated accounts; never silently
        # elevate or re-activate a pending/disabled one from IdP group claims.
        if user.status == "active":
            mapped = role_from_groups(cfg, groups)
            if mapped:
                user.role = mapped
    user.last_login_at = utcnow()
    record_audit(db, user.id, f"login.{source}", entity="user", entity_id=user.id, detail={"email": email})
    return user


# ---------------- OIDC ----------------
@router.get("/oidc/login")
async def oidc_login(request: Request, db: Session = Depends(get_db)):
    """Start the OIDC Authorization Code + PKCE flow: redirect to the IdP.

    404s when OIDC is disabled or incompletely configured, keeping the endpoint
    indistinguishable from a non-existent one. Authlib stashes the state/PKCE
    verifier in the server-side session for the callback to consume.
    """
    cfg = get_auth_config(db)
    if not cfg["oidc_enabled"] or not cfg["oidc_issuer_url"] or not cfg["oidc_client_id"]:
        raise HTTPException(status_code=404, detail="OIDC désactivé ou mal configuré")
    from ..oidc import get_oauth
    oauth = get_oauth(cfg)
    request.session["_oidc_cfg"] = True
    return await oauth.oidc.authorize_redirect(request, cfg["oidc_redirect_uri"])


@router.get("/oidc/callback")
async def oidc_callback(request: Request, db: Session = Depends(get_db)):
    """OIDC redirect target: exchange the code, provision the user, set the session.

    Authlib validates state/PKCE and the ID-token signature during
    ``authorize_access_token``. We then extract identity (sub/email/name/groups,
    the groups claim being configurable), require at least one usable identifier,
    JIT-provision via ``_provision``, and redirect into the SPA with a session.
    """
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
    """Serve this SP's SAML metadata XML (for registering the app at the IdP).

    Validates the generated metadata and 500s on any error rather than publishing
    a malformed descriptor.
    """
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
    """Start the SP-initiated SAML flow: redirect to the IdP's SSO endpoint."""
    cfg = get_auth_config(db)
    if not cfg["saml_enabled"]:
        raise HTTPException(status_code=404, detail="SAML désactivé")
    from ..saml import make_auth
    auth = await make_auth(request, cfg)
    return RedirectResponse(url=auth.login())


@router.post("/saml/acs")
async def saml_acs(request: Request, db: Session = Depends(get_db)):
    """Assertion Consumer Service: verify the IdP response, provision, set session.

    ``process_response`` validates the signed assertion (settings use strict mode);
    any validation error or a non-authenticated result is a hard 401. Identity is
    read from attributes with the NameID as email fallback, then JIT-provisioned.
    Uses a 303 redirect so the browser switches the POST callback to a GET of "/".
    """
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
    """SAML attributes arrive as lists; return the first value (or the scalar as-is)."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value
