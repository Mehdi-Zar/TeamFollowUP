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


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
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


def assert_can_manage_objectives(user: User, squad=None) -> None:
    """Objectives are set by the tribe leader (or admin), within their tribe."""
    if user.role == ADMIN:
        return
    if user.role == TRIBE and (squad is None or squad.tribe_id == user.tribe_id):
        return
    raise HTTPException(status_code=403, detail="Les objectifs sont définis par le tribe leader de la tribe")


def require_org_editor(user: User = Depends(get_current_user)) -> User:
    if user.role not in (ADMIN, TRIBE):
        raise HTTPException(status_code=403, detail="L'organigramme est géré par le tribe leader")
    return user


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
