import { expect, test } from "@playwright/test";
import { BREAKGLASS, signIn } from "./helpers";

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
  "tribes", "import", "squads", "users", "personas", "my_squads",
  "modules", "report", "leaves", "settings",
  "auth", "api", "smtp", "tls",
  "moderation", "logs", "audit", "ops",
];

test.describe("Administration sections", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, BREAKGLASS);
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
