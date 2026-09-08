import { type APIRequestContext } from "@playwright/test";
import { BREAKGLASS, dismissWelcome, expect, signIn, test, uniqueName } from "./helpers";

/**
 * Authorization, checked where it counts: in a browser, against the deployed
 * build, with a real session cookie.
 *
 * The backend suite already proves the guards return 403. What it cannot prove
 * is that the SPA does not hand a member the administration screen anyway - a
 * route guard is frontend code, and a frontend that renders admin controls it
 * will fail to use is both a bug and a bad look.
 */

const MEMBER_PASSWORD = "e2e-member-pw-2026";

async function createMember(api: APIRequestContext) {
  const email = `${uniqueName("member")}@e2e.local`;
  const created = await api.post("/api/admin/users", {
    data: {
      email,
      display_name: "E2E Member",
      role: "member",
      password: MEMBER_PASSWORD,
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  return { email, id: (await created.json()).id as number };
}

test.describe("Roles and route guards", () => {
  test("a member is not offered Administration, and cannot reach it by URL", async ({ page }) => {
    await signIn(page, BREAKGLASS);
    const member = await createMember(page.request);

    // Become that member: a real login, not a mutated cookie.
    await page.request.post("/api/auth/logout");
    await page.goto("/");
    await page.getByLabel("Email").fill(member.email);
    await page.getByLabel("Password").fill(MEMBER_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await dismissWelcome(page);

    // The navigation does not offer it...
    await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(0);

    // ...and typing the URL does not open it either.
    await page.goto("/admin");
    await expect(page.getByRole("navigation", { name: "Administration" })).toHaveCount(0);

    // The API agrees, which is the guarantee that actually matters.
    const forbidden = await page.request.get("/api/admin/users");
    expect(forbidden.status()).toBe(403);

    // Clean up as the administrator, and ASSERT it worked. Unasserted cleanup is
    // cleanup that silently does not happen: this delete had been returning 500
    // on every run (nineteen columns point at users.id and nothing detached them),
    // so each run left a member-e2e-*@e2e.local account behind. Nobody noticed,
    // because nobody looked at the status code.
    await page.request.post("/api/auth/logout");
    const back = await page.request.post("/api/auth/login", { data: BREAKGLASS });
    expect(back.ok(), await back.text()).toBeTruthy();
    const removed = await page.request.delete(`/api/admin/users/${member.id}`);
    expect(removed.status(), await removed.text()).toBe(204);
  });

  test("the administrator sees the administration screen and its sections", async ({ page }) => {
    await signIn(page, BREAKGLASS);
    await page.goto("/admin");
    const nav = page.getByRole("navigation", { name: "Administration" });
    await expect(nav).toBeVisible();
    for (const section of ["Tribes", "Squads", "Users", "Personas & access"]) {
      await expect(nav.getByRole("button", { name: section })).toBeVisible();
    }
  });

  test("the dashboard renders for the administrator", async ({ page }) => {
    await signIn(page, BREAKGLASS);
    await page.goto("/");
    // Whatever the content, the page must not be the error banner or a blank shell.
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.locator(".error-banner, .error-text")).toHaveCount(0);
  });
});
