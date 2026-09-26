import { BREAKGLASS, expect, signIn, test } from "./helpers";

/**
 * Every administration section renders.
 *
 * A smoke test, and unapologetically so. Administration is one screen with
 * twenty-odd panels, each fetching its own configuration; a panel that throws
 * shows an error banner or an empty card, and nothing else in the suite would
 * notice. This walks all of them and asserts each one actually rendered.
 *
 * It is also the safety net for refactoring that screen: run it before, refactor,
 * run it after.
 */

// The keys AdminPage accepts in ?section=, from ADMIN_TABS. An administrator can
// open all of them; a narrower role would see a subset, which roles.spec covers.
const SECTIONS = [
  "tribes", "import", "squads", "platforms", "users", "personas", "my_squads",
  "modules", "report", "leaves", "settings", "branding",
  "auth", "api", "smtp", "trust",
  "moderation", "logs", "data", "audit", "ops",
];

// The feed, leave, committee and steerco services ship switched off: they are
// extras, and a fresh install shows what it needs. Their administration tabs are
// hidden with them, because their routes answer 404 and an empty panel with two
// console errors is worse than no tab at all. This suite is about the panels, not
// about the default, so it turns them on before walking them.
const OPTIONAL_SERVICES = {
  feed: { enabled: true },
  leaves: { enabled: true },
  committees: { enabled: true },
  steerco: { enabled: true },
};

test.describe("Administration sections", () => {
  // What the instance had before the suite touched it, so it can be given back.
  let previous: Record<string, { enabled: boolean }> | null = null;

  test.beforeEach(async ({ page }) => {
    await signIn(page, BREAKGLASS);
    const before = await page.request.get("/api/admin/modules-config");
    const cfg = await before.json();
    previous ??= Object.fromEntries(
      Object.keys(OPTIONAL_SERVICES).map((k) => [k, { enabled: !!cfg[k]?.enabled }]));
    const on = await page.request.put("/api/admin/modules-config", { data: OPTIONAL_SERVICES });
    expect(on.ok(), await on.text()).toBeTruthy();
    // The tab list is built from the config the SPA loaded at startup.
    await page.reload();
  });

  // Switching a service on to walk its panel is fair; leaving it on is not. The
  // suite does not always run against a throwaway instance, and a setting someone
  // deliberately turned off must be found off afterwards.
  test.afterAll(async ({ playwright }, testInfo) => {
    if (!previous) return;
    const ctx = await playwright.request.newContext({ baseURL: testInfo.project.use.baseURL });
    await ctx.post("/api/auth/login", { data: BREAKGLASS });
    await ctx.put("/api/admin/modules-config", { data: previous });
    await ctx.dispose();
  });

  for (const section of SECTIONS) {
    test(`section "${section}" renders without an error`, async ({ page }) => {
      const failures: string[] = [];
      page.on("pageerror", (e) => failures.push(`uncaught: ${e.message}`));
      page.on("console", (m) => {
        if (m.type() === "error") failures.push(`console: ${m.text()}`);
      });

      await page.goto(`/admin?section=${section}`);

      // The shell is there...
      await expect(page.getByRole("navigation", { name: "Administration" })).toBeVisible();
      // ...the panel finished loading (no spinner left)...
      await expect(page.locator(".spinner")).toHaveCount(0);
      // ...and it did not fail.
      await expect(page.locator(".error-banner")).toHaveCount(0);

      // A rendered panel has content: a card, a table or a form control. An empty
      // <main> is the shape a component that returned null takes, which is the
      // failure this test is looking for.
      const content = page.locator("main .card, main table, main input, main select, main textarea, main button");
      await expect(content.first()).toBeVisible();

      expect(failures, `runtime errors in section "${section}"`).toEqual([]);
    });
  }
});
