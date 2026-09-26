/**
 * Client-side, role-based permission helpers.
 *
 * These predicates decide what a role may SEE/DO in the UI (which menus, tabs
 * and edit affordances to render). They are convenience mirrors of the backend
 * RBAC (app/rbac.py, app/deps.py) - the server remains the source of truth and
 * re-checks every write; these helpers only keep the UI honest and uncluttered.
 */
import { Role, SquadDetail } from "./types";

/** The built-in roles, in privilege order. */
export const ALL_ROLES: Role[] = ["admin", "tribe_leader", "squad_leader", "contributor", "member"];

// Admin tabs a role may open - mirrors backend app/rbac.py ADMIN_TABS.
// Used so the admin "preview as role" reflects the scoped tab set.
export const ADMIN_TABS_BY_ROLE: Record<string, string[]> = {
  admin: ["tribes", "squads", "platforms", "users", "personas", "import",
          "modules", "report", "leaves", "settings", "branding",
          "auth", "api", "smtp", "trust",
          "audit", "moderation", "logs", "data", "ops"],
  tribe_leader: ["tribe", "platforms", "users", "leaves", "report"],  // default; Admin > Personas decides
  squad_leader: [],
  contributor: [],
  member: [],
};
/** Exactly the admin role. */
export const isAdmin = (r: Role) => r === "admin";
/** Who may open the Admin page: admins and tribe leaders (squad leaders use the
 *  dedicated "my squad" page instead). */
export const canSeeAdmin = (r: Role) => r === "admin" || r === "tribe_leader";
/** Strictly the global administrator (system configuration). */
export const isGlobalAdmin = (r: Role) => r === "admin";
/** Edit the org chart: admins and tribe leaders. */
export const canEditOrg = (r: Role) => r === "admin" || r === "tribe_leader";
/** Writes the feed and pins in it: admin, tribe leader, squad leader (the feed
 *  scope "leaders"). Squad-level writing goes through leadsSquad / contributesTo. */
export const isWriter = (r: Role) => r === "admin" || r === "tribe_leader" || r === "squad_leader";
// Qui atteint l'ecran de saisie ne se decide pas ici: c'est la capacite « reporting »
// du persona, reglable dans l'administration, que la navigation et la route lisent.
// Une fonction locale a longtemps affirme la meme regle en dur sans etre appelee par
// aucun ecran, et son test la jurait: une regle testee que l'application n'applique
// pas donne une fausse assurance, et un admin qui coche « reporting » pour les tribe
// leaders la contredit sans que rien ne bronche. La regle est verifiee la ou elle
// decide, dans backend/tests/test_personas.py.

/** Diriger cette squad: en etre le leader nomme, ou l'un de ses co-leaders.
 *
 *  Miroir de `deps.leads_this_squad`, qui est le point de passage unique cote
 *  serveur. L'ecran ne connaissait que `leader_user_id`: un co-leader avait donc
 *  tous les droits d'ecriture a l'API et aucun bouton pour les exercer, sur les
 *  jalons, les messages cles et l'engagement de sa squad. Une co-direction que
 *  l'ecran ignore n'est pas une co-direction. */
type SquadLeadership = Pick<SquadDetail, "leader_user_id"> & { co_leader_user_ids?: number[] };

function leadsThis(userId: number | undefined, squad: SquadLeadership): boolean {
  if (userId === undefined) return false;
  return squad.leader_user_id === userId || (squad.co_leader_user_ids ?? []).includes(userId);
}

/** Can this role (with this user id) edit the given squad's KPIs/members/budget? */
export function canEditSquad(role: Role, userId: number | undefined, squad: SquadLeadership): boolean {
  if (role === "admin" || role === "tribe_leader") return true;
  return leadsThis(userId, squad);
}

/** canEditSquad with the tribe scope the server applies (deps.can_edit_squad): a
 *  tribe leader edits the squads of their own tribe only. For screens that list
 *  squads across tribes, like the roadmap matrix. */
export function canEditSquadInScope(
  role: Role, user: { id?: number; tribe_id?: number | null } | null | undefined,
  squad: SquadLeadership & { tribe_id: number },
): boolean {
  if (role === "tribe_leader") return (user?.tribe_id != null && user.tribe_id === squad.tribe_id) || leadsThis(user?.id, squad);
  return canEditSquad(role, user?.id, squad);
}

/** Named contributor of this squad: fills in and submits its reporting. */
export function contributesTo(userId: number | undefined, squad: { contributor_user_ids?: number[] }): boolean {
  return userId !== undefined && (squad.contributor_user_ids ?? []).includes(userId);
}

/** Stricter than canEditSquad: only the squad's own leadership (or admin), whatever
 *  their role: a tribe leader named at the head of a squad leads it. Mirrors
 *  backend deps.assert_leads_squad. Used for milestones (jalons), key messages,
 *  the squad's own commitment and the submission. */
export function leadsSquad(role: Role, userId: number | undefined, squad: SquadLeadership): boolean {
  if (role === "admin") return true;
  return leadsThis(userId, squad);
}
