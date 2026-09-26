import { describe, it, expect } from "vitest";
import { canSeeAdmin, isWriter, isGlobalAdmin, canEditSquad, canEditSquadInScope, leadsSquad } from "./perms";

describe("role predicates", () => {
  it("admin area is admin + tribe leader", () => {
    expect(canSeeAdmin("admin")).toBe(true);
    expect(canSeeAdmin("tribe_leader")).toBe(true);
    expect(canSeeAdmin("squad_leader")).toBe(false);
    expect(canSeeAdmin("member")).toBe(false);
  });
  it("writers are admin/tribe/squad leaders", () => {
    expect(isWriter("squad_leader")).toBe(true);
    expect(isWriter("member")).toBe(false);
  });
  it("global admin is admin only", () => {
    expect(isGlobalAdmin("admin")).toBe(true);
    expect(isGlobalAdmin("tribe_leader")).toBe(false);
  });
  it("custom personas are not writers/admins (view-scoped)", () => {
    expect(isWriter("auditor")).toBe(false);
    expect(canSeeAdmin("auditor")).toBe(false);
  });
  it("squad leaders can edit only their own squad", () => {
    expect(canEditSquad("squad_leader", 7, { leader_user_id: 7 })).toBe(true);
    expect(canEditSquad("squad_leader", 7, { leader_user_id: 9 })).toBe(false);
    expect(canEditSquad("admin", 1, { leader_user_id: 9 })).toBe(true);
  });
  // Le serveur passe par deps.leads_this_squad, qui compte le leader nomme ET ses
  // co-leaders. L'ecran ne lisait que leader_user_id: un co-leader avait donc tous
  // les droits a l'API et aucun bouton pour les exercer, sur les jalons, les
  // messages cles et l'engagement de sa squad.
  it("a co-leader leads the squad, on screen as on the server", () => {
    const squad = { leader_user_id: 9, co_leader_user_ids: [7] };
    expect(leadsSquad("squad_leader", 7, squad)).toBe(true);
    expect(canEditSquad("squad_leader", 7, squad)).toBe(true);
    expect(leadsSquad("squad_leader", 8, squad)).toBe(false);
    // Et sans co-leader declare, rien ne change.
    expect(leadsSquad("squad_leader", 7, { leader_user_id: 9 })).toBe(false);
    // Le tribe leader edite la squad mais ne la dirige pas: il n'ecrit pas son
    // engagement, exactement comme cote serveur.
    expect(canEditSquad("tribe_leader", 3, squad)).toBe(true);
    expect(leadsSquad("tribe_leader", 3, squad)).toBe(false);
  });
  // Le serveur limite le tribe leader aux squads de sa tribu: l'ecran aussi, pour
  // ne pas proposer « Gerer l'equipe » sur une squad d'une autre tribu.
  it("team editing follows the server scope", () => {
    const squad = { leader_user_id: 9, co_leader_user_ids: [7], tribe_id: 1 };
    expect(canEditSquadInScope("tribe_leader", { id: 3, tribe_id: 1 }, squad)).toBe(true);
    expect(canEditSquadInScope("tribe_leader", { id: 3, tribe_id: 2 }, squad)).toBe(false);
    expect(canEditSquadInScope("squad_leader", { id: 7, tribe_id: 1 }, squad)).toBe(true);
    expect(canEditSquadInScope("squad_leader", { id: 8, tribe_id: 1 }, squad)).toBe(false);
    // Leading a squad is a job, not a persona: whoever is named at its head edits it.
    expect(canEditSquadInScope("member", { id: 9, tribe_id: 1 }, squad)).toBe(true);
    expect(canEditSquadInScope("member", { id: 5, tribe_id: 1 }, squad)).toBe(false);
    expect(canEditSquadInScope("admin", { id: 1 }, squad)).toBe(true);
  });
});
