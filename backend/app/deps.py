from fastapi import Depends, HTTPException, Request, status as http_status
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AppSetting, AuditLog, Squad, User
from .security import decode_session

THRESHOLD_KEY = "staleness_threshold_days"

# Role tiers
ADMIN = "admin"
TRIBE = "tribe_leader"
SQUAD = "squad_leader"
MEMBER = "member"


def get_threshold(db: Session) -> int:
    from .generalconfig import get_general
    return get_general(db)["staleness_threshold_days"]


def set_threshold(db: Session, value: int) -> None:
    from .generalconfig import set_general
    set_general(db, {"staleness_threshold_days": value})


def record_audit(db: Session, user_id, action, entity=None, entity_id=None, detail=None) -> None:
    db.add(AuditLog(user_id=user_id, action=action, entity=entity,
                    entity_id=str(entity_id) if entity_id is not None else None, detail=detail))


def get_current_user_any_status(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the session user WITHOUT enforcing the access lifecycle. Only the
    few endpoints a pending/disabled user legitimately needs (me, permissions,
    logout) depend on this; everything else uses get_current_user."""
    token = request.cookies.get(settings.session_cookie)
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    user_id, impersonator_id = decode_session(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session invalide")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    # Surface impersonation context (admin viewing the app as another user).
    request.state.impersonator_id = impersonator_id
    return user


def get_current_user(user: User = Depends(get_current_user_any_status)) -> User:
    """The standard dependency for every protected endpoint: a valid session AND
    a validated ("active") account. Pending/disabled accounts are denied with a
    machine-readable detail so the SPA can show the right screen."""
    if user.status != "active":
        detail = "access_pending" if user.status == "pending" else "access_disabled"
        raise HTTPException(status_code=403, detail=detail)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return user


def require_tribe_or_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in (ADMIN, TRIBE):
        raise HTTPException(status_code=403, detail="Accès réservé au tribe leader")
    return user


def require_writer(user: User = Depends(get_current_user)) -> User:
    if user.role not in (ADMIN, TRIBE, SQUAD):
        raise HTTPException(status_code=403, detail="Accès en écriture refusé")
    return user


def visible_tribe_id(user: User) -> int | None:
    """None means 'all tribes' (admin). Otherwise the user's own tribe."""
    return None if user.role == ADMIN else user.tribe_id


def tribe_in_scope(user: User, tribe_id: int | None) -> bool:
    if user.role == ADMIN:
        return True
    return tribe_id is not None and tribe_id == user.tribe_id


def assert_tribe_scope(user: User, tribe_id: int | None) -> None:
    if not tribe_in_scope(user, tribe_id):
        raise HTTPException(status_code=403, detail="Cette tribe n'est pas dans votre périmètre")


def can_edit_squad(db: Session, user: User, squad_id: int) -> bool:
    """Roadmap / KPIs / members / progress of a squad (tribe-scoped)."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        return False
    if user.role == ADMIN:
        return True
    if user.role == TRIBE:
        return squad.tribe_id == user.tribe_id
    if user.role == SQUAD:
        return squad.leader_user_id == user.id
    return False


def assert_can_edit_squad(db: Session, user: User, squad_id: int) -> None:
    if not can_edit_squad(db, user, squad_id):
        raise HTTPException(status_code=403, detail="Vous ne pouvez éditer que votre squad")


def is_squad_privileged(user: User, squad: Squad) -> bool:
    """Can see a squad's restricted data (objectives, KPIs, budget): admin, the
    squad's tribe leader, or the squad's own leader."""
    if user.role == ADMIN:
        return True
    if user.role == TRIBE:
        return squad.tribe_id == user.tribe_id
    if user.role == SQUAD:
        return squad.leader_user_id == user.id
    return False


def assert_can_manage_objectives(user: User, squad=None) -> None:
    """Objectives are set by the tribe leader (or admin), within their tribe."""
    if user.role == ADMIN:
        return
    if user.role == TRIBE and (squad is None or squad.tribe_id == user.tribe_id):
        return
    raise HTTPException(status_code=403, detail="Les objectifs sont définis par le tribe leader de la tribe")


def assert_can_manage_tribe_reporting(user: User, tribe_id: int | None) -> None:
    """Initiatives + OTD are set by the tribe leader (or admin), within their tribe."""
    if user.role == ADMIN:
        return
    if user.role == TRIBE and tribe_id is not None and tribe_id == user.tribe_id:
        return
    raise HTTPException(status_code=403,
                        detail="Initiatives et OTD sont gérés par le tribe leader de la tribe")


def can_manage_leave(db: Session, viewer: User, target_user_id: int) -> bool:
    """Who may approve/edit/cancel someone else's absence: admin, the person's
    tribe leader, or a squad leader of a squad the person belongs to."""
    if viewer.role == ADMIN:
        return True
    target = db.get(User, target_user_id)
    if target is None:
        return False
    if viewer.role == TRIBE:
        return target.tribe_id is not None and target.tribe_id == viewer.tribe_id
    if viewer.role == SQUAD:
        from sqlalchemy import select
        from .models import Member
        led = db.scalars(select(Squad.id).where(Squad.leader_user_id == viewer.id)).all()
        if not led:
            return False
        member = db.scalar(select(Member.id).where(
            Member.user_id == target_user_id, Member.squad_id.in_(led)))
        return member is not None
    return False


def can_see_leaves_of(viewer: User, tribe_id: int | None) -> bool:
    """Leaves are visible to everyone within their tribe scope (admins see all)."""
    if viewer.role == ADMIN:
        return True
    return tribe_id is not None and tribe_id == viewer.tribe_id


def require_org_editor(user: User = Depends(get_current_user)) -> User:
    if user.role not in (ADMIN, TRIBE):
        raise HTTPException(status_code=403, detail="L'organigramme est géré par le tribe leader")
    return user


def require_capability(capability: str):
    """Dependency that 403s when the caller's persona lacks a section capability.

    Capabilities (persona access toggles) are managed in Admin → Personas.
    """
    def _dep(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        from .personasconfig import can
        if can(db, user, capability):
            return user
        raise HTTPException(status_code=403, detail="Accès non autorisé pour votre rôle")
    return _dep


def api_key_from_request(request: Request, db: Session):
    """The ApiKey presented in `Authorization: Bearer …`, or None if absent.

    A malformed/expired/revoked/unknown key is a 401 - we do not silently fall
    back to the cookie, because a client that sent a key meant to use it and must
    be told the key is bad rather than get an opaque 401 about a missing session.
    """
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    from .apikeys import resolve
    key = resolve(db, header[7:].strip())
    if key is None:
        raise HTTPException(status_code=401, detail="Clé d'API invalide, expirée ou révoquée")
    return key


def caller(scope: str, capability: str | None = None):
    """The dependency for a route open to BOTH humans and API keys.

    Humans authenticate with the session cookie and are gated by their persona
    capability, exactly as before. Machines authenticate with an API key and are
    gated by the key's *scope* - personas do not apply to them (a persona is a
    human navigating sections; a scope is a credential reading a resource).

    Routes that do not name a scope stay cookie-only: an API key is never an
    implicit passport to the whole API.
    """
    def _dep(request: Request, db: Session = Depends(get_db)) -> User:
        key = api_key_from_request(request, db)
        if key is not None:
            if scope not in (key.scopes or []):
                raise HTTPException(status_code=403,
                                    detail=f"Cette clé d'API n'a pas le scope « {scope} »")
            from .apikeys import principal, touch
            touch(db, key)
            db.commit()
            request.state.api_key = key           # read by reports.py (budget:read)
            return principal(key)

        user = get_current_user(get_current_user_any_status(request, db))
        if capability is not None:
            from .personasconfig import can
            if not can(db, user, capability):
                raise HTTPException(status_code=403, detail="Accès non autorisé pour votre rôle")
        return user

    return _dep


def caller_has_scope(request: Request, scope: str) -> bool:
    """True when the current caller is an API key carrying `scope`.

    Used for scopes that shape a payload rather than open a route (budget:read).
    A human caller is not an API key, so this is False for them - their own rules
    (is_squad_privileged) decide instead.
    """
    key = getattr(request.state, "api_key", None)
    return key is not None and scope in (key.scopes or [])


def is_api_caller(request: Request) -> bool:
    return getattr(request.state, "api_key", None) is not None


def require_module(module: str, feature: str | None = None):
    """Dependency that 404s when a module/feature is disabled in the admin.

    Used as a route or router dependency to enforce the on/off switches
    server-side (the SPA also hides the corresponding UI). 404 keeps a disabled
    service indistinguishable from a non-existent one.
    """
    def _dep(db: Session = Depends(get_db)) -> None:
        from .modulesconfig import get_modules, is_active
        if not is_active(get_modules(db), module, feature):
            raise HTTPException(status_code=404, detail="Service désactivé")

    return _dep
