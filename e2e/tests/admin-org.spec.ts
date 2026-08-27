import { expect, test } from "@playwright/test";
import { BREAKGLASS, signIn, uniqueName } from "./helpers";

/**
 * The write path, end to end: a tribe created by this deployment is visible to
 * it, is recorded in the audit trail, and can be removed. This is the journey
 * that proves the pieces are actually wired together - request, transaction,
 * audit line, reload - which no unit test covers as a whole.
 *
 * It creates real rows. Run it against a throwaway instance.
 *
 * Deep links use `?section=`, the parameter AdminPage reads. `?tab=` is the
 * Dashboard's Steerco switch and does nothing here.
 */

test.describe("Administration, organisation", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, BREAKGLASS);
  });

  test("a tribe can be created, listed and deleted", async ({ page }) => {
    const name = uniqueName("Tribe");

    const created = await page.request.post("/api/tribes", {
      data: { name, description: "created by the end-to-end suite" },
    });
    expect(created.ok(), await created.text()).toBeTruthy();
    const tribe = await created.json();

    await page.goto("/admin?section=tribes");
    // The row's name cell is an editable input, so the value is the assertion.
    await expect(page.locator(`input[value="${name}"]`)).toBeVisible();

    const removed = await page.request.delete(`/api/tribes/${tribe.id}`);
    expect(removed.ok(), await removed.text()).toBeTruthy();

    await page.goto("/admin?section=tribes");
    await expect(page.locator(`input[value="${name}"]`)).toHaveCount(0);
  });

  test("the audit trail records what was just done, and the filter finds it", async ({ page }) => {
    const name = uniqueName("Audited");
    const created = await page.request.post("/api/tribes", { data: { name } });
    expect(created.ok()).toBeTruthy();
    const tribe = await created.json();

    await page.goto("/admin?section=audit");
    // Narrow to the creation we just made: the instance may hold thousands of rows.
    await page.getByRole("textbox", { name: "Action contains" }).fill("tribe.create");

    const row = page.locator("tbody tr", { hasText: "tribe.create" }).first();
    await expect(row).toBeVisible();
    // The acting user is resolved to a name, not printed as a bare numeric id.
    await expect(row).toContainText("Administrateur");

    // The count reflects the FILTERED set, which is the whole point of it.
    await expect(page.getByText(/Showing \d+ of \d+ entries/)).toBeVisible();

    await page.request.delete(`/api/tribes/${tribe.id}`);
  });

  test("an entity filter that matches nothing says so instead of showing everything", async ({ page }) => {
    await page.goto("/admin?section=audit");
    await page.getByRole("textbox", { name: "Entity type" }).fill("no-such-entity-type");
    await expect(page.getByText("No entry.")).toBeVisible();
    await expect(page.getByText("Showing 0 of 0 entries")).toBeVisible();
  });

  test("the audit pager walks the log without repeating a row", async ({ page }) => {
    // The pager only renders when there is more than one page, so make sure there
    // is. A create plus a delete is two audit lines, and a fresh instance can
    // legitimately have almost none.
    const countEntries = async () =>
      (await (await page.request.get("/api/audit-log?limit=1")).json()).total as number;
    while ((await countEntries()) <= 30) {
      const r = await page.request.post("/api/tribes", { data: { name: uniqueName("Pager") } });
      await page.request.delete(`/api/tribes/${(await r.json()).id}`);
    }

    await page.goto("/admin?section=audit");
    await page.getByLabel("Per page").selectOption("25");
    // Wait for the page size to have been APPLIED before reading anything: the
    // fetch is debounced, so the table still shows the previous page for a moment
    // and a signature taken now would belong to the wrong request.
    await expect(page.getByText(/Showing 25 of \d+ entries/)).toBeVisible();

    // Column 3 is the action; joining a page's actions makes a signature to compare.
    const signature = async () =>
      (await page.locator("tbody tr td:nth-child(3)").allTextContents()).join("|");
    const pageNumber = async () =>
      Number((await page.getByText(/Page \d+ of \d+/).textContent())?.match(/Page (\d+)/)?.[1]);

    await expect(page.getByText(/Page 1 of \d+/)).toBeVisible();
    const firstPage = await signature();

    await page.getByRole("button", { name: "Next" }).click();
    await expect.poll(pageNumber).toBe(2);
    await expect.poll(signature).not.toBe(firstPage);

    await page.getByRole("button", { name: "Previous" }).click();
    await expect.poll(pageNumber).toBe(1);
    await expect.poll(signature).toBe(firstPage);
  });
});
