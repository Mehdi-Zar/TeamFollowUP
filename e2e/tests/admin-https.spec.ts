import { BREAKGLASS, expect, signIn, test } from "./helpers";

/**
 * The trusted authorities must be manageable on a deployment where the
 * infrastructure terminates TLS, which is the recommended one and the one
 * docker-compose runs.
 *
 * They were not. The whole certificate panel rendered only inside
 * `{enabled && ...}`, where `enabled` means "the application terminates TLS
 * itself", so an administrator who needed to import an internal root CA (without
 * which OIDC against an internal IdP fails on the very first call, the discovery
 * fetch) was told to switch the serving mode. That toggle rebinds the listener
 * from 8000 to 8443 at the next restart, in front of a Gateway that expects
 * 8000: we were asking someone to break their production to import a CA.
 *
 * A jsdom component test covers the same split, faster. This one is here because
 * that test mocks the API, and the thing that actually went wrong was a whole
 * panel missing from a real screen in a real serving mode.
 */
test.describe("Administration, HTTPS", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, BREAKGLASS);
    await page.goto("/admin?section=tls");
    await expect(page.locator(".spinner")).toHaveCount(0);
    await expect(page.locator(".error-banner")).toHaveCount(0);
  });

  test("the served-certificate panel is hidden, and says why", async ({ page }) => {
    await expect(page.getByText(/does not handle the server certificate/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Install and activate" })).toHaveCount(0);
    await expect(page.getByText("Generate a self-signed certificate")).toHaveCount(0);
  });

  test("the trusted authorities are shown anyway, with usable controls", async ({ page }) => {
    // Exact match: the banner above mentions the same words in a sentence.
    await expect(page.getByText("Trusted authorities", { exact: true })).toBeVisible();
    await expect(page.getByLabel("CA file (.pem/.crt)")).toBeVisible();

    // Visible is not enough: the add and delete buttons used to inherit the
    // serving-mode gate through `disabled`.
    const add = page.getByRole("button", { name: "Add CA" });
    await expect(add).toBeVisible();
    await expect(add).toBeEnabled();
  });
});
