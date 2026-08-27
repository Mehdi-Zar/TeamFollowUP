import { expect, type Page } from "@playwright/test";

/**
 * Shared fixtures for the end-to-end suite.
 *
 * The credentials below are the ones docker-compose gives a local stack, and
 * they exist nowhere else. The suite is meant to run against a throwaway
 * instance: it creates and deletes real records.
 */
export const BREAKGLASS = {
  email: process.env.E2E_ADMIN_EMAIL || "admin@local",
  password: process.env.E2E_ADMIN_PASSWORD || "changeme-admin",
};

/** Sign in through the real form and wait until the app shell is on screen. */
export async function signIn(page: Page, who = BREAKGLASS) {
  await page.goto("/");
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  // The left navigation only exists once a session is established, so its
  // appearance is the honest signal that the login worked.
  await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
  await dismissWelcome(page);
}

/**
 * Close the getting-started dialog if it is up.
 *
 * It is shown once per user per browser, gated by a localStorage key, and every
 * Playwright test starts from a clean profile - so it is up every single time.
 * Its overlay swallows clicks, which is exactly the kind of failure that reads
 * as "the button is broken" while nothing is broken at all. Dismissing it is
 * also what a real user does on their first visit.
 */
export async function dismissWelcome(page: Page) {
  const later = page.getByRole("button", { name: "Later" });
  if (await later.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await later.click();
    await expect(later).toBeHidden();
  }
}

/** A name nothing else will collide with, so a leftover from a failed run is obvious. */
export function uniqueName(prefix: string): string {
  return `${prefix}-e2e-${Date.now().toString(36)}`;
}
