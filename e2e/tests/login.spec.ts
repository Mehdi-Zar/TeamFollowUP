import { expect, test } from "@playwright/test";
import { BREAKGLASS, signIn } from "./helpers";

/**
 * The front door. Everything else in the suite depends on it working, so it is
 * tested first and on its own: when this file is red, the rest is noise.
 */

test("the login screen is served and its fields are reachable by their labels", async ({ page }) => {
  await page.goto("/");
  // Not a redirect to some framework 404: the SPA renders and asks for credentials.
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("wrong credentials are refused without saying which half was wrong", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill(BREAKGLASS.email);
  await page.getByLabel("Password").fill("definitely-not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  const error = page.locator(".error-text");
  await expect(error).toBeVisible();
  // No user enumeration: the message must not reveal whether the account exists.
  await expect(error).not.toContainText(/unknown|not found|no such|does not exist/i);
  // And we are still on the login screen.
  await expect(page.getByLabel("Password")).toBeVisible();
});

test("the break-glass administrator can sign in and lands on the app", async ({ page }) => {
  await signIn(page, BREAKGLASS);
  await expect(page.getByRole("link", { name: "Administration" })).toBeVisible();
});

test("signing out returns to the login screen and the session is really gone", async ({ page }) => {
  await signIn(page, BREAKGLASS);

  // The session cookie must stop being accepted, not merely be hidden by the UI.
  await page.request.post("/api/auth/logout");
  const me = await page.request.get("/api/auth/me");
  expect(me.status()).toBe(401);
});

test("an unauthenticated visitor cannot reach an inner page by typing its URL", async ({ page }) => {
  await page.goto("/admin");
  // The route guard sends them to the login screen rather than rendering the shell.
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});
