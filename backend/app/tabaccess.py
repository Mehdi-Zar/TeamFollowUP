"""Administration tabs as permissions: which persona may use which admin screen.

The admin chooses, in Admin > Personas, the Administration tabs of every persona
(personasconfig.admin_tabs_for). This module makes the server follow those ticks:

* the routes of a *global* tab (SMTP, SSO, backups, logs...) were admin-only
  (``deps.require_admin``). They now also open to a persona holding the tab,
  found from the request path (ROUTE_TABS). A path not listed stays admin-only;
* the *tribe* tabs (my tribe, accounts, leave rules, platforms, weekly report) act
  on one tribe. A persona holding one acts there as the tribe leader of their own
  tribe (``acting_manager``), whatever its role; without a tribe it gets nothing.

Impersonation is not a tab and stays the admin's: it is every right at once.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import User

ADMIN = "admin"
TRIBE = "tribe_leader"

# Route prefix -> the tab that opens it. Longest prefix wins.
ROUTE_TABS: list[tuple[str, str]] = [
    ("/api/admin/settings", "settings"),
    ("/api/admin/auth-config", "auth"),
    ("/api/admin/smtp-config", "smtp"),
    ("/api/admin/personas", "personas"),
    ("/api/admin/modules-config", "modules"),
    ("/api/admin/change-notify-config", "report"),
    ("/api/admin/log-export-config", "logs"),
    ("/api/admin/logs", "logs"),
    ("/api/admin/log-level", "logs"),
    ("/api/admin/trust-store", "trust"),
    ("/api/admin/runtime", "ops"),
    ("/api/admin/restart", "ops"),
    ("/api/admin/api-keys", "api"),
    ("/api/admin/import-org", "import"),
    ("/api/admin/import-steerco", "platforms"),
    ("/api/admin/branding", "branding"),
    ("/api/admin/pptx-template", "branding"),
    ("/api/admin/data", "data"),
    ("/api/audit-log", "audit"),
    ("/api/leaves/types", "leaves"),
    ("/api/tribes", "tribes"),
    ("/api/squads", "squads"),
]


def tab_for(path: str) -> str | None:
    """The tab a request path belongs to, or None (then admin only)."""
    best = None
    for prefix, tab in ROUTE_TABS:
        if (path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?")) \
                and (best is None or len(prefix) > len(best[0])):
            best = (prefix, tab)
    return best[1] if best else None


def has_tab(db: Session, user: User, tab: str) -> bool:
    """The admin holds every tab; any other persona the ones ticked for it."""
    if user.role == ADMIN:
        return True
    from .personasconfig import admin_tabs_for
    return tab in admin_tabs_for(db, user)


def acting_manager(db: Session, user: User, tab: str) -> User:
    """The identity to run a *tribe* tab with.

    The admin as themself. Anyone else holding the tab acts as the tribe leader
    of their own tribe: a transient (never persisted) copy carrying that role, so
    the existing tribe-scoped rules apply unchanged. 403 otherwise.
    """
    if user.role == ADMIN:
        return user
    if user.tribe_id is None or not has_tab(db, user, tab):
        raise HTTPException(status_code=403, detail="Cet onglet d'administration ne vous est pas ouvert")
    if user.role == TRIBE:
        return user
    return User(id=user.id, email=user.email, display_name=user.display_name, role=TRIBE,
                status=user.status, tribe_id=user.tribe_id, is_break_glass=False)
