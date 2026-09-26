import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { I18nProvider, storedLang, useI18n } from "./i18n";
import { ConfigProvider } from "./config";
import { api } from "./api";

/**
 * The instance's default language must actually reach a first-time visitor.
 *
 * It did not. `I18nProvider` wrote `trt_lang` from a mount effect, so "en" was
 * stamped into storage before /api/config had answered; `ConfigProvider` then
 * found a stored value, read it as "the viewer has chosen", and skipped applying
 * `default_lang`. On a French instance every new visitor got English, and the
 * setting in Administration did nothing at all.
 *
 * The rule these tests pin: a stored value means the viewer chose, and only
 * picking a language stores one.
 */
const CONFIG = {
  app_name: "TeamFollowUP",
  app_subtitle: "",
  default_lang: "fr",
  default_year: 2026,
  feed_post_scope: "leaders",
  smtp_enabled: false,
  modules: {},
};

function Probe() {
  const { lang, setLang } = useI18n();
  return <button data-testid="lang" onClick={() => setLang("en")}>{lang}</button>;
}

function renderApp(config: object = CONFIG) {
  vi.spyOn(api, "get").mockResolvedValue(config as never);
  return render(
    <I18nProvider>
      <ConfigProvider>
        <Probe />
      </ConfigProvider>
    </I18nProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("the language a visitor actually gets", () => {
  it("is the instance default when they have never chosen one", async () => {
    renderApp();
    await waitFor(() => expect(screen.getByTestId("lang").textContent).toBe("fr"));
  });

  it("is not persisted, so changing the default later still reaches them", async () => {
    renderApp();
    await waitFor(() => expect(screen.getByTestId("lang").textContent).toBe("fr"));
    expect(storedLang()).toBeNull();
  });

  it("is their own choice when they have made one, whatever the instance says", async () => {
    localStorage.setItem("trt_lang", "en");
    renderApp();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.getByTestId("lang").textContent).toBe("en");
  });

  it("is stored the moment they pick it", async () => {
    renderApp();
    await waitFor(() => expect(screen.getByTestId("lang").textContent).toBe("fr"));
    expect(storedLang()).toBeNull();

    screen.getByTestId("lang").click();
    await waitFor(() => expect(storedLang()).toBe("en"));
  });
});
