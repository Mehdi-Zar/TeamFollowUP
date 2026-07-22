"""Central RBAC model.

One place that answers "can actor X do action Y on object Z?" so routers and the
SPA stay consistent. Three management scopes:

  - admin         : everything, all tribes (global configuration included).
  - tribe_leader  : own tribe (edit) + its squads (CRUD) + users of that tribe
                    (assignable roles capped at squad_leader / member).
  - squad_leader  : squads they lead (content, members, KPIs on/off).

Members have no management scope. Global configuration (modules, SMTP, SSO,
logs, audit, general settings, weekly report) is admin-only.
"""
from __future__ import annotations

from .models import Squad, User

ADMIN = "admin"
TRIBE = "tribe_leader"
SQUAD = "squad_leader"
MEMBER = "member"

MANAGER_ROLES = (ADMIN, TRIBE, SQUAD)

# Admin tabs each role may open. Global-config tabs are admin-only.
ADMIN_TABS = {
    ADMIN: ["tribes", "import", "squads", "users", "personas", "modules", "report", "leaves", "moderation",
            "auth", "api", "smtp", "tls", "logs", "settings", "audit", "ops"],
    # Tribe & squad leaders manage their squads on the dedicated "my squads"
    # page, not in Administration. Tribe leaders may set their own tribe's leave rules.
    TRIBE: ["tribe", "users", "leaves"],
    SQUAD: [],
    MEMBER: [],
}


def can_access_admin(user: User) -> bool:
    """True if the user has any management scope (admin / tribe / squad leader).

    Gate for reaching the Administration area at all; which tabs are shown is
    then narrowed by :data:`ADMIN_TABS`.
    """
    return user.role in MANAGER_ROLES


# ----- tribes -------------------------------------------------------------------

def can_create_or_delete_tribe(user: User) -> bool:
    """Only admins may create or delete tribes (they are the top-level tenants)."""
    return user.role == ADMIN


def can_edit_tribe(user: User, tribe_id: int | None) -> bool:
    """True if the user may edit the given tribe.

    Admins may edit any tribe; a tribe leader may edit only their own tribe.
    ``tribe_id`` is optional so callers can pass an unresolved value safely - a
    missing id can never match a leader's own tribe.
    """
    if user.role == ADMIN:
        return True
    if user.role == TRIBE:
        return tribe_id is not None and tribe_id == user.tribe_id
    return False


# ----- squads -------------------------------------------------------------------

def can_manage_squads_in_tribe(user: User, tribe_id: int | None) -> bool:
    """Create / delete / set leader & order of squads in a tribe.

    Managing a tribe's squads is the same scope as editing the tribe itself, so
    this simply delegates to :func:`can_edit_tribe`.
    """
    return can_edit_tribe(user, tribe_id)


def leads_squad(user: User, squad: Squad) -> bool:
    """True if the user is the assigned leader of this specific squad.

    Note it requires the SQUAD role: admins and tribe leaders are handled by the
    tribe-level checks, not by direct squad leadership.
    """
    return user.role == SQUAD and squad.leader_user_id == user.id


# ----- users --------------------------------------------------------------------

def can_manage_users(user: User) -> bool:
    """True if the user may manage accounts (admins globally, tribe leaders in-tribe)."""
    return user.role in (ADMIN, TRIBE)


def assignable_roles(user: User) -> list[str]:
    """Roles this actor is allowed to grant to others.

    Enforces privilege capping: a tribe leader may only create squad leaders and
    members (never admins or other tribe leaders); members may grant nothing.
    """
    if user.role == ADMIN:
        return [ADMIN, TRIBE, SQUAD, MEMBER]
    if user.role == TRIBE:
        return [SQUAD, MEMBER]
    return []


def users_scope_tribe(user: User) -> int | None:
    """Tribe filter for the users a manager may see (None = all, admin)."""
    return None if user.role == ADMIN else user.tribe_id


def can_manage_user(actor: User, target: User) -> bool:
    """Edit/delete an existing user account.

    Break-glass accounts are protected: only an admin may ever touch them, so a
    tribe leader can never disable the emergency admin. Otherwise admins manage
    anyone, and a tribe leader manages only squad leaders / members in their own
    tribe.
    """
    # Guard the emergency admin account against non-admin actors first.
    if target.is_break_glass and actor.role != ADMIN:
        return False
    if actor.role == ADMIN:
        return True
    if actor.role == TRIBE:
        return target.tribe_id == actor.tribe_id and target.role in (SQUAD, MEMBER)
    return False


def can_assign_role(actor: User, role: str) -> bool:
    """True if ``actor`` is permitted to grant ``role`` (see :func:`assignable_roles`)."""
    return role in assignable_roles(actor)


def permissions_payload(user: User) -> dict:
    """Capability summary consumed by the SPA to drive the admin UI."""
    return {
        "role": user.role,
        "tribe_id": user.tribe_id,
        "can_access_admin": can_access_admin(user),
        "admin_tabs": ADMIN_TABS.get(user.role, []),
        "assignable_roles": assignable_roles(user),
        "can_create_tribe": can_create_or_delete_tribe(user),
        "can_manage_users": can_manage_users(user),
    }
