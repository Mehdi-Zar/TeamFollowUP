import { test, expect } from "@playwright/test";

/**
 * A first-time visitor must get the language the instance is configured for.
 *
 * They did not. `I18nProvider` wrote `trt_lang` from a mount effect, stamping
 * "en" into localStorage before /api/config had answered; `ConfigProvider` then
 * found a stored value, read it as "the viewer has chosen", and declined to apply
 * `default_lang`. So a French instance greeted every new visitor in English while
 * emailing them in French, and the setting in Administration did nothing.
 *
 * This is the one spec that imports `test` from @playwright/test rather than from
 * ./helpers, and deliberately: the helper fixture pins `trt_lang=en` before the
 * first navigation so the rest of the suite can name English labels. Here the
 * absence of a stored choice IS the case under test.
 *
 * `default_lang` is French out of the box (`generalconfig._defaults`), and
 * docker-compose does not override it, so French is what a clean profile must get.
 */
test.describe("the language a first-time visitor gets", () => {
  test("is the instance default, not the browser's and not a leftover", async ({ page }) => {
    await page.goto("/");

    // Nothing chosen: the guard that used to be poisoned must still be clear.
    expect(await page.evaluate(() => window.localStorage.getItem("trt_lang"))).toBeNull();

    // And the interface is in the configured language, on the login screen the
    // visitor lands on before any session exists.
    await expect(page.getByLabel("Mot de passe")).toBeVisible();
    await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
  });

  test("stays their own once they choose, and only then is it remembered", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByLabel("Mot de passe")).toBeVisible();

    // The picker lives in the app chrome, so choose the way the SPA does and
    // reload: what must survive is the choice, not the server default.
    await page.evaluate(() => window.localStorage.setItem("trt_lang", "en"));
    await page.reload();

    await expect(page.getByLabel("Password")).toBeVisible();
    expect(await page.evaluate(() => window.localStorage.getItem("trt_lang"))).toBe("en");
  });
});
