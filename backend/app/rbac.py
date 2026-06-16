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
    ADMIN: ["tribes", "squads", "users", "modules", "moderation", "auth",
            "smtp", "report", "logs", "settings", "audit"],
    # Tribe leaders manage squads (KPIs / annual objectives) on the dedicated
    # "Gestion de mes squads" page, not in Administration.
    TRIBE: ["tribe", "users"],
    SQUAD: ["my_squads"],
    MEMBER: [],
}


def can_access_admin(user: User) -> bool:
    return user.role in MANAGER_ROLES


# ----- tribes -------------------------------------------------------------------

def can_create_or_delete_tribe(user: User) -> bool:
    return user.role == ADMIN


def can_edit_tribe(user: User, tribe_id: int | None) -> bool:
    if user.role == ADMIN:
        return True
    if user.role == TRIBE:
        return tribe_id is not None and tribe_id == user.tribe_id
    return False


# ----- squads -------------------------------------------------------------------

def can_manage_squads_in_tribe(user: User, tribe_id: int | None) -> bool:
    """Create / delete / set leader & order of squads in a tribe."""
    return can_edit_tribe(user, tribe_id)


def leads_squad(user: User, squad: Squad) -> bool:
    return user.role == SQUAD and squad.leader_user_id == user.id


# ----- users --------------------------------------------------------------------

def can_manage_users(user: User) -> bool:
    return user.role in (ADMIN, TRIBE)


def assignable_roles(user: User) -> list[str]:
    if user.role == ADMIN:
        return [ADMIN, TRIBE, SQUAD, MEMBER]
    if user.role == TRIBE:
        return [SQUAD, MEMBER]
    return []


def users_scope_tribe(user: User) -> int | None:
    """Tribe filter for the users a manager may see (None = all, admin)."""
    return None if user.role == ADMIN else user.tribe_id


def can_manage_user(actor: User, target: User) -> bool:
    """Edit/delete an existing user account."""
    if target.is_break_glass and actor.role != ADMIN:
        return False
    if actor.role == ADMIN:
        return True
    if actor.role == TRIBE:
        return target.tribe_id == actor.tribe_id and target.role in (SQUAD, MEMBER)
    return False


def can_assign_role(actor: User, role: str) -> bool:
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
