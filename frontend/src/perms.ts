import { Role, SquadDetail } from "./types";

export const ALL_ROLES: Role[] = ["admin", "tribe_leader", "squad_leader", "member"];

// Admin tabs a role may open — mirrors backend app/rbac.py ADMIN_TABS.
// Used so the admin "preview as role" reflects the scoped tab set.
export const ADMIN_TABS_BY_ROLE: Record<Role, string[]> = {
  admin: ["tribes", "squads", "users", "modules", "moderation", "auth", "smtp", "report", "logs", "settings", "audit"],
  tribe_leader: ["tribe", "users"],
  squad_leader: [],
  member: [],
};
// Who gets the dedicated "my squads" page. Tribe leaders & admins manage KPIs /
// objectives; squad leaders manage their squad's team (members).
export const canManageMySquads = (r: Role) => r === "tribe_leader" || r === "admin" || r === "squad_leader";

export const isAdmin = (r: Role) => r === "admin";
/** Who may open the Admin page: admins and tribe leaders (squad leaders use the
 *  dedicated "my squad" page instead). */
export const canSeeAdmin = (r: Role) => r === "admin" || r === "tribe_leader";
/** Strictly the global administrator (system configuration). */
export const isGlobalAdmin = (r: Role) => r === "admin";
export const canManageSquads = (r: Role) => r === "admin" || r === "tribe_leader";
export const canManageObjectives = (r: Role) => r === "admin" || r === "tribe_leader";
export const canEditOrg = (r: Role) => r === "admin" || r === "tribe_leader";
export const isWriter = (r: Role) => r === "admin" || r === "tribe_leader" || r === "squad_leader";
// Reporting (saisie) is for squad leaders (and admins). Tribe leaders steer their
// squads via the admin "Squads" tab (KPIs on/off, annual objectives), not reporting.
export const canSeeSaisie = (r: Role) => r === "admin" || r === "squad_leader";

/** Can this role (with this user id) edit the given squad's roadmap/KPIs/members? */
export function canEditSquad(role: Role, userId: number | undefined, squad: Pick<SquadDetail, "leader_user_id">): boolean {
  if (role === "admin" || role === "tribe_leader") return true;
  if (role === "squad_leader") return squad.leader_user_id === userId;
  return false;
}
