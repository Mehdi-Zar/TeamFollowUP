"""FastAPI dependencies enforcing authentication, RBAC and tribe-scoped access.

This is the security backbone of the API: it turns the session cookie (or an API
key) into an authenticated principal and exposes the reusable authorization
building blocks that every router depends on. Two orthogonal axes are enforced
here:

  * Role tiers (admin > tribe_leader > squad_leader > member) grant coarse-grained
    write/manage rights.
  * Tribe scope confines non-admins to their own tribe's data, and squad
    ownership further narrows squad leaders to the squads they lead.

Design conventions used throughout:
  * ``get_current_user`` is the default gate (valid session AND an "active"
    account); ``get_current_user_any_status`` is the deliberate exception for the
    handful of endpoints a pending/disabled user still needs.
  * ``can_*`` helpers return a bool (for branching), while the ``assert_*`` /
    ``require_*`` wrappers raise an HTTPException so they can be dropped straight
    into a route as a guard/dependency.
  * A denied request returns 403 (forbidden) except when the resource must stay
    hidden, where 404 is used instead (see ``require_module``).
"""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AuditLog, Squad, User
from .security import decode_session

THRESHOLD_KEY = "staleness_threshold_days"

# Role tiers, from most to least privileged. String literals are the values
# persisted on User.role; these constants avoid magic strings across the codebase.
ADMIN = "admin"
TRIBE = "tribe_leader"
SQUAD = "squad_leader"
MEMBER = "member"
# Fills in the reporting of the squads they are named contributor of, nothing else.
CONTRIB = "contributor"


def get_threshold(db: Session) -> int:
    """Days after which a reporting item is considered stale (from general config)."""
    from .generalconfig import get_general
    return get_general(db)["staleness_threshold_days"]


def set_threshold(db: Session, value: int) -> None:
    """Persist the staleness threshold (admin-configurable general setting)."""
    from .generalconfig import set_general
    set_general(db, {"staleness_threshold_days": value})


def record_audit(db: Session, user_id, action, entity=None, entity_id=None, detail=None) -> None:
    """Append an audit-trail entry within the caller's transaction.

    Only stages the row (no commit) so the audit line lives or dies with the
    business change it records. ``entity_id`` is coerced to str for uniform
    storage across entity types.
    """
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
        # Session referenced a user that no longer exists (deleted account).
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    # Surface impersonation context (admin viewing the app as another user) on
    # request.state so downstream code/audit can tell who is really acting.
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


def require_admin(request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> User:
    """Route guard: administrators, and any persona the admin gave the tab this
    route belongs to (Admin > Personas, see tabaccess). A route no tab covers
    stays administrators only."""
    if user.role == ADMIN:
        return user
    from .tabaccess import has_tab, tab_for
    tab = tab_for(request.url.path)
    if tab is not None and has_tab(db, user, tab):
        return user
    raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")


def require_strict_admin(user: User = Depends(get_current_user)) -> User:
    """Administrators only, whatever the personas say (impersonation: every right
    at once is not something to hand out as a tab)."""
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return user


def assert_admin_tab(db: Session, user: User, tab: str) -> None:
    """403 unless the user holds this Administration tab (Admin > Personas)."""
    from .tabaccess import has_tab
    if not has_tab(db, user, tab):
        raise HTTPException(status_code=403, detail="Cet onglet d'administration ne vous est pas ouvert")


def require_admin_tab(tab: str):
    """Route guard for a tribe tab: the admin, or whoever holds the tab, acting as
    the tribe leader of their own tribe (tabaccess.acting_manager)."""
    def dep(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
        from .tabaccess import acting_manager
        return acting_manager(db, user, tab)
    return dep


def require_tribe_or_admin(request: Request, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)) -> User:
    """Route guard: tribe leaders and admins (tribe-level management), and a
    persona holding the tab of this route (e.g. Squads), acting as the tribe
    leader of their own tribe."""
    if user.role in (ADMIN, TRIBE):
        return user
    from .tabaccess import acting_manager, tab_for
    tab = tab_for(request.url.path)
    if tab is not None:
        return acting_manager(db, user, tab)
    raise HTTPException(status_code=403, detail="Accès réservé au tribe leader")


def require_writer(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    """Route guard: allow anyone who can write (admin/tribe/squad/contributor), or
    anyone named leader, co-leader or contributor of a squad whatever their
    persona (a custom persona included). Each route then checks the squad itself."""
    if user.role in (ADMIN, TRIBE, SQUAD, CONTRIB):
        return user
    if db.scalars(led_squad_ids(db, user).limit(1)).first() is not None \
            or db.scalars(contributed_squad_ids(db, user).limit(1)).first() is not None:
        return user
    raise HTTPException(status_code=403, detail="Accès en écriture refusé")


# Fields that name the row: a blank value is refused like a missing one.
_NAMING_FIELDS = {"name", "title", "full_name", "display_name", "text"}


def update_data(payload, model) -> dict:
    """The fields a partial update (PUT) sets, checked against ``model``'s columns.

    ``model_dump(exclude_unset=True)`` keeps an explicit null, and on a NOT NULL
    column that null only failed at commit, as a 500. It is a 422 here, and so is
    a blank name or title.
    """
    data = payload.model_dump(exclude_unset=True)
    columns = model.__table__.columns
    for k, v in data.items():
        col = columns.get(k)
        if col is None:
            continue
        if v is None and not col.nullable:
            raise HTTPException(status_code=422, detail=f"Le champ {k} ne peut pas être vide")
        if k in _NAMING_FIELDS and isinstance(v, str) and not v.strip():
            raise HTTPException(status_code=422, detail=f"Le champ {k} ne peut pas être vide")
    return data


# Every read helper takes None as "all tribes". A non-admin account without a tribe
# (created without one, or left behind by a tribe deletion) must see nothing, not
# everything: it gets this id instead, which matches no row.
NO_TRIBE = -1


def scoped_tribe_id(user: User, tribe_id: int | None = None) -> int | None:
    """Tribe a read is limited to: the admin's choice (None = all tribes), anyone
    else their own tribe, or NO_TRIBE when they have none."""
    if user.role == ADMIN:
        return tribe_id
    return user.tribe_id if user.tribe_id is not None else NO_TRIBE


def visible_tribe_id(user: User) -> int | None:
    """None means 'all tribes' (admin). Otherwise the user's own tribe."""
    return scoped_tribe_id(user)


def tribe_in_scope(user: User, tribe_id: int | None) -> bool:
    """True if the user may act on ``tribe_id``: admins anywhere, others only in
    their own tribe. A None target is out of scope for non-admins (no cross-tribe
    or org-wide reach)."""
    if user.role == ADMIN:
        return True
    return tribe_id is not None and tribe_id == user.tribe_id


def assert_tribe_scope(user: User, tribe_id: int | None) -> None:
    """Raising counterpart of ``tribe_in_scope`` for use as an inline guard."""
    if not tribe_in_scope(user, tribe_id):
        raise HTTPException(status_code=403, detail="Cette tribe n'est pas dans votre périmètre")


def leads_this_squad(squad: Squad, user: User) -> bool:
    """True when ``user`` is this squad's named leader OR one of its co-leaders.

    A squad has one leader for identity (an OTD is committed on them, the report is
    addressed to them) and any number of co-leaders holding the same rights. Every
    squad-level permission goes through this one function, so adding a co-leader
    cannot grant a right in one screen and forget it in another.
    """
    # An API key acts with no id: "no leader" must not read as "led by nobody = me".
    if user.id is None:
        return False
    return squad.leader_user_id == user.id or any(u.id == user.id for u in squad.co_leaders)


def led_squad_ids(db: Session, user: User):
    """Ids of the squads ``user`` leads, as leader or co-leader (query side)."""
    from sqlalchemy import false, or_, select as _select

    from .models import squad_coleaders
    # An API key acts with no id: "leader_user_id == None" would match every squad
    # without a leader, in every tribe.
    if user.id is None:
        return _select(Squad.id).where(false())
    co = _select(squad_coleaders.c.squad_id).where(squad_coleaders.c.user_id == user.id)
    return _select(Squad.id).where(or_(Squad.leader_user_id == user.id, Squad.id.in_(co)))


def can_edit_squad(db: Session, user: User, squad_id: int) -> bool:
    """Roadmap / KPIs / members / progress of a squad (tribe-scoped).

    Admin edits any squad; a tribe leader any squad of their tribe; anyone else
    only the squads they lead, whatever their role. Unknown squad: denied.
    """
    squad = db.get(Squad, squad_id)
    if squad is None:
        return False
    if user.role == ADMIN:
        return True
    if user.role == TRIBE and squad.tribe_id == user.tribe_id:
        return True
    return leads_this_squad(squad, user)


def assert_can_edit_squad(db: Session, user: User, squad_id: int) -> None:
    """Raising counterpart of ``can_edit_squad``."""
    if not can_edit_squad(db, user, squad_id):
        raise HTTPException(status_code=403, detail="Vous ne pouvez éditer que votre squad")


def leads_squad(db: Session, user: User, squad_id: int) -> bool:
    """Stricter than ``can_edit_squad``: ONLY the squad's own leader (or admin).
    The tribe leader is excluded, unless they lead this very squad. Used for
    squad-owned content whose stewardship belongs to the squad's leadership alone:
    roadmap milestones (jalons), key messages, the squad's own OTD, submission."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        return False
    if user.role == ADMIN:
        return True
    # Whoever is named at the head of the squad, whatever their role: a tribe
    # leader may lead a squad too, and must then be able to fill it in.
    return leads_this_squad(squad, user)


def can_read_squad(user: User, squad: Squad) -> bool:
    """May read this squad (page, history, exports): its tribe (or admin), or
    leading it or contributing to it, from whatever tribe."""
    scope = visible_tribe_id(user)  # None = all tribes (admin); honours API key scopes
    if scope is None or squad.tribe_id == scope:
        return True
    return leads_this_squad(squad, user) or contributes_to(squad, user)


def assert_can_read_squad(user: User, squad: Squad) -> None:
    """Raising counterpart of ``can_read_squad`` (403, like the tribe scope)."""
    if not can_read_squad(user, squad):
        raise HTTPException(status_code=403, detail="Accès refusé à cette squad")


def manages_squad(user: User, squad: Squad) -> bool:
    """Set-up reserved to the tribe leader: admin, or tribe leader OF THIS squad's
    tribe. A tribe leader who leads a squad of another tribe leads it, nothing more."""
    if user.role == ADMIN:
        return True
    return user.role == TRIBE and user.tribe_id == squad.tribe_id


def contributes_to(squad: Squad, user: User) -> bool:
    """True when ``user`` is named contributor of this squad."""
    return user.id is not None and any(u.id == user.id for u in squad.contributors)


def contributed_squad_ids(db: Session, user: User):
    """Ids of the squads ``user`` is contributor of (query side)."""
    from sqlalchemy import select as _select

    from .models import squad_contributors
    return _select(squad_contributors.c.squad_id).where(squad_contributors.c.user_id == user.id)


def reports_for_squad(db: Session, user: User, squad_id: int) -> bool:
    """May fill in and submit this squad's reporting: its leadership (leader,
    co-leaders, admin) and its contributors. The weekly content only: milestones,
    OTD of the squad, key messages, submission."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        return False
    return leads_squad(db, user, squad_id) or contributes_to(squad, user)


def assert_reports_for_squad(db: Session, user: User, squad_id: int) -> None:
    """Raising counterpart of ``reports_for_squad``."""
    if not reports_for_squad(db, user, squad_id):
        raise HTTPException(status_code=403, detail="Vous ne faites pas le reporting de cette squad")


def can_report(db: Session, user: User, squad_id: int) -> bool:
    """``can_edit_squad`` widened to the squad's contributors, for the reporting
    values it also covers: mood, progress comment, KPI values, Steerco figures."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        return False
    return can_edit_squad(db, user, squad_id) or contributes_to(squad, user)


def assert_can_report(db: Session, user: User, squad_id: int) -> None:
    """Raising counterpart of ``can_report``."""
    if not can_report(db, user, squad_id):
        raise HTTPException(status_code=403, detail="Vous ne faites pas le reporting de cette squad")


def assert_leads_squad(db: Session, user: User, squad_id: int) -> None:
    """Raising counterpart of ``leads_squad`` (excludes the tribe leader)."""
    if not leads_squad(db, user, squad_id):
        raise HTTPException(status_code=403,
                            detail="Réservé au squad leader de cette squad")


def is_squad_privileged(user: User, squad: Squad) -> bool:
    """Can see a squad's restricted data (budget): admin, the squad's tribe leader,
    or whoever leads the squad (leader or co-leader), whatever their role."""
    if user.role == ADMIN:
        return True
    if user.role == TRIBE and squad.tribe_id == user.tribe_id:
        return True
    return leads_this_squad(squad, user)


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
    # Nobody below the tribe leader approves their own absence.
    if target_user_id == viewer.id:
        return False
    # Leading a squad is a job, not a persona: whoever leads a squad the person
    # belongs to (any role) manages their absences.
    if viewer.id is not None:
        from sqlalchemy import select
        from .models import Member
        led = db.scalars(led_squad_ids(db, viewer)).all()
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
    """Route guard: only tribe leaders and admins may edit the org chart."""
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
