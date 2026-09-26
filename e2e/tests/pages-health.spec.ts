import { BREAKGLASS, expect, signIn, test, uniqueName } from "./helpers";

/**
 * Every page opens, and opens cleanly.
 *
 * The unit suites check what a function returns and what a route answers. They
 * cannot see a screen that throws while rendering, a fetch that answers 500, a
 * label that shows up as `squad.co_leaders` because the dictionary lost an entry,
 * or a page that arrives empty. Those only appear when something opens the pages,
 * which nothing did systematically.
 *
 * So this walks them and reports three things per page: uncaught errors, failed
 * requests, and translation keys rendered as-is. It is a smoke test by design: it
 * asserts nothing about what a screen says, only that it managed to say it.
 */

// Every route the navigation offers, plus the two dashboard sub-views.
const ROUTES = [
  "/", "/?tab=steerco", "/initiatives", "/roadmap", "/organigramme",
  "/saisie", "/mes-squads", "/acces", "/prise-en-main", "/preferences",
];

// A translation key rendered as text: two or more lowercase words joined by dots,
// no space and no accent. Real sentences never look like that. File names and
// domains do, hence the tail exclusion.
const LOOKS_LIKE_A_KEY = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,3}$/;
const NOT_A_KEY = /\.(html|pptx|json|xlsx|csv|png|jpg|com|fr|org|io)$/;

test.describe("Every page opens cleanly", () => {
  for (const route of ROUTES) {
    test(`${route} renders without an error`, async ({ page }) => {
      const failures: string[] = [];
      page.on("pageerror", (e) => failures.push(`uncaught: ${e.message}`));
      page.on("console", (m) => {
        // The browser also logs every failed request here, without saying which.
        // The response listener below judges those, with the right exclusions;
        // keeping both would report a signed-out 401 as a page error.
        if (m.type() === "error" && !m.text().startsWith("Failed to load resource")) {
          failures.push(`console: ${m.text()}`);
        }
      });
      page.on("response", (r) => {
        // 401 and 403 are answers, not failures: the screen starts signed out, and
        // a panel may legitimately ask for something this account cannot see.
        if (r.status() >= 400 && ![401, 403].includes(r.status())) {
          failures.push(`${r.status()} ${new URL(r.url()).pathname}`);
        }
      });

      await signIn(page, BREAKGLASS);
      await page.goto(route);
      await expect(page.locator(".spinner")).toHaveCount(0);

      const body = (await page.locator("body").innerText()).trim();
      expect(body.length, `${route} came up empty`).toBeGreaterThan(40);

      const leaked = [...new Set(body.split(/\s+/))]
        .filter((w) => LOOKS_LIKE_A_KEY.test(w) && !NOT_A_KEY.test(w));
      expect(leaked, `${route} shows raw translation keys`).toEqual([]);
      expect(failures, `${route} failed`).toEqual([]);
    });
  }

  /**
   * The reporting screen is a walk, so walking it is the only way to see it.
   *
   * Its steps are built from the active services and each one mounts its own
   * editor; a step that throws is invisible until someone clicks it, and the
   * previous shape of this screen (eight stacked cards) hid nothing of the sort.
   */
  test("the reporting flow opens every one of its steps", async ({ page }) => {
    const failures: string[] = [];
    page.on("pageerror", (e) => failures.push(`uncaught: ${e.message}`));

    await signIn(page, BREAKGLASS);

    // The screen needs a squad to report on, and a fresh instance has none. A test
    // that leans on data it did not create is testing the machine it runs on: this
    // one brings its own, and takes it away afterwards.
    const tribe = await page.request.post("/api/tribes", {
      data: { name: uniqueName("Tribe"), description: "created by the end-to-end suite" },
    });
    expect(tribe.ok(), await tribe.text()).toBeTruthy();
    const tribeId = (await tribe.json()).id;
    const squad = await page.request.post("/api/squads", {
      data: { name: uniqueName("Squad"), tribe_id: tribeId },
    });
    expect(squad.ok(), await squad.text()).toBeTruthy();
    const squadId = (await squad.json()).id;

    try {
      await walkTheSteps(page, failures);
    } finally {
      await page.request.delete(`/api/squads/${squadId}`);
      await page.request.delete(`/api/tribes/${tribeId}`);
    }
  });
});

/** Open every step of the reporting flow and check each one actually rendered. */
async function walkTheSteps(page: import("@playwright/test").Page, failures: string[]) {
  await page.goto("/saisie");

  // The rail only exists once the squad is loaded: counting before that counts zero.
  const chips = page.locator(".step-chip");
  await expect(chips.first()).toBeVisible();
  const count = await chips.count();
  expect(count, "the reporting screen offers no step").toBeGreaterThan(2);

  for (let i = 0; i < count; i++) {
    await chips.nth(i).click();
    // Each step names itself and shows something: a step that mounts an empty
    // panel is a step the user will cross without understanding why it exists.
    // The step's own title, not the headings of the panels it hosts.
    await expect(page.locator(".step-panel > div > h2").first()).not.toBeEmpty();
    const panel = (await page.locator(".step-panel").innerText()).trim();
    expect(panel.length, `step ${i + 1} rendered an empty panel`).toBeGreaterThan(30);
  }
  expect(failures, "the reporting flow failed").toEqual([]);
}
