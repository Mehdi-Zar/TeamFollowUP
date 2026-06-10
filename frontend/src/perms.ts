import { Role, SquadDetail } from "./types";

export const ALL_ROLES: Role[] = ["admin", "tribe_leader", "squad_leader", "member"];

export const isAdmin = (r: Role) => r === "admin";
export const canSeeAdmin = (r: Role) => r === "admin";
export const canManageSquads = (r: Role) => r === "admin" || r === "tribe_leader";
export const canManageObjectives = (r: Role) => r === "admin" || r === "tribe_leader";
export const canEditOrg = (r: Role) => r === "admin" || r === "tribe_leader";
export const isWriter = (r: Role) => r === "admin" || r === "tribe_leader" || r === "squad_leader";
export const canSeeSaisie = (r: Role) => isWriter(r);

/** Can this role (with this user id) edit the given squad's roadmap/KPIs/members? */
export function canEditSquad(role: Role, userId: number | undefined, squad: Pick<SquadDetail, "leader_user_id">): boolean {
  if (role === "admin" || role === "tribe_leader") return true;
  if (role === "squad_leader") return squad.leader_user_id === userId;
  return false;
}
