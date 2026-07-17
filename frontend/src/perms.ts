/**
 * Client-side, role-based permission helpers.
 *
 * These predicates decide what a role may SEE/DO in the UI (which menus, tabs
 * and edit affordances to render). They are convenience mirrors of the backend
 * RBAC (app/rbac.py, app/deps.py) - the server remains the source of truth and
 * re-checks every write; these helpers only keep the UI honest and uncluttered.
 */
import { Role, SquadDetail } from "./types";

/** The four built-in roles, in privilege order. */
export const ALL_ROLES: Role[] = ["admin", "tribe_leader", "squad_leader", "member"];

// Admin tabs a role may open - mirrors backend app/rbac.py ADMIN_TABS.
// Used so the admin "preview as role" reflects the scoped tab set.
export const ADMIN_TABS_BY_ROLE: Record<string, string[]> = {
  admin: ["tribes", "squads", "users", "personas", "modules", "report", "leaves", "moderation", "auth", "api", "smtp", "tls", "logs", "settings", "audit"],
  tribe_leader: ["tribe", "users", "leaves"],
  squad_leader: [],
  member: [],
};
// Who gets the dedicated "my squads" page. Tribe leaders & admins manage KPIs /
// objectives; squad leaders manage their squad's team (members).
/** Admins, tribe leaders and squad leaders may open the "my squads" page. */
export const canManageMySquads = (r: Role) => r === "tribe_leader" || r === "admin" || r === "squad_leader";

/** Exactly the admin role. */
export const isAdmin = (r: Role) => r === "admin";
/** Who may open the Admin page: admins and tribe leaders (squad leaders use the
 *  dedicated "my squad" page instead). */
export const canSeeAdmin = (r: Role) => r === "admin" || r === "tribe_leader";
/** Strictly the global administrator (system configuration). */
export const isGlobalAdmin = (r: Role) => r === "admin";
/** Create/edit/delete squads: admins and tribe leaders. */
export const canManageSquads = (r: Role) => r === "admin" || r === "tribe_leader";
/** Set squad objectives/OTDs: admins and tribe leaders (not squad leaders). */
export const canManageObjectives = (r: Role) => r === "admin" || r === "tribe_leader";
/** Edit the org chart: admins and tribe leaders. */
export const canEditOrg = (r: Role) => r === "admin" || r === "tribe_leader";
/** Any writer role (has some edit rights): admin, tribe leader or squad leader. */
export const isWriter = (r: Role) => r === "admin" || r === "tribe_leader" || r === "squad_leader";
// Reporting (saisie) is for squad leaders (and admins). Tribe leaders steer their
// squads via the admin "Squads" tab (KPIs on/off, annual objectives), not reporting.
/** Open the reporting (saisie) screen: admins and squad leaders. */
export const canSeeSaisie = (r: Role) => r === "admin" || r === "squad_leader";

/** Can this role (with this user id) edit the given squad's KPIs/members/budget? */
export function canEditSquad(role: Role, userId: number | undefined, squad: Pick<SquadDetail, "leader_user_id">): boolean {
  if (role === "admin" || role === "tribe_leader") return true;
  if (role === "squad_leader") return squad.leader_user_id === userId;
  return false;
}

/** Stricter than canEditSquad: only the squad's OWN leader (or admin) - the tribe
 *  leader is deliberately excluded. Mirrors backend deps.assert_leads_squad.
 *  Used for milestones (jalons) and key messages, stewarded by the squad leader alone. */
export function leadsSquad(role: Role, userId: number | undefined, squad: Pick<SquadDetail, "leader_user_id">): boolean {
  if (role === "admin") return true;
  if (role === "squad_leader") return squad.leader_user_id === userId;
  return false;
}
