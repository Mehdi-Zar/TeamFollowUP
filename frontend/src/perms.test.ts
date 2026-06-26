import { describe, it, expect } from "vitest";
import { canSeeAdmin, isWriter, canSeeSaisie, isGlobalAdmin, canEditSquad } from "./perms";

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
  it("reporting (Saisie) is admin + squad leader", () => {
    expect(canSeeSaisie("admin")).toBe(true);
    expect(canSeeSaisie("squad_leader")).toBe(true);
    expect(canSeeSaisie("tribe_leader")).toBe(false);
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
});
