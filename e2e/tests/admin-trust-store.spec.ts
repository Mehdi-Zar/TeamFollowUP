import { BREAKGLASS, expect, signIn, test } from "./helpers";

/**
 * Administration > Certificate authorities, on the deployment docker-compose
 * runs: plain HTTP, TLS terminated by the infrastructure in front of the app
 * (ADR 0013).
 *
 * The screen used to manage the served certificate too, behind a toggle, and the
 * authorities rendered inside `{enabled && ...}` with it. An administrator who
 * needed to import an internal root CA (without which OIDC against an internal
 * IdP fails on the very first call, the discovery fetch) was told to switch the
 * serving mode, which rebinds the listener from 8000 to 8443 at the next restart
 * in front of a Gateway that expects 8000: we were asking someone to break their
 * production to import a CA. The listener and the toggle are gone; this pins what
 * remains, on a real screen rather than a mocked one.
 */
test.describe("Administration, certificate authorities", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, BREAKGLASS);
    await page.goto("/admin?section=trust");
    await expect(page.locator(".spinner")).toHaveCount(0);
    await expect(page.locator(".error-banner")).toHaveCount(0);
  });

  test("nothing on the screen manages a certificate the app would serve", async ({ page }) => {
    await expect(page.getByText(/inbound TLS is handled by the load balancer/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Install and activate" })).toHaveCount(0);
    await expect(page.getByText("Generate a self-signed certificate")).toHaveCount(0);
  });

  test("the trusted authorities are shown, with usable controls", async ({ page }) => {
    // Exact match: the banner above mentions the same words in a sentence.
    await expect(page.getByText("Trusted authorities", { exact: true })).toBeVisible();
    await expect(page.getByLabel("CA file (.pem/.crt)")).toBeVisible();

    const add = page.getByRole("button", { name: "Add CA" });
    await expect(add).toBeVisible();
    await expect(add).toBeEnabled();
  });
});
