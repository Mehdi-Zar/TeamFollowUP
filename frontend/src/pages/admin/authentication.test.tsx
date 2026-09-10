import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { api } from "../../api";
import { TrustAdmin } from "./authentication";

/**
 * The screen manages ONE thing: the authorities the app trusts when it calls an
 * IdP, an SMTP relay or a log sink. It used to also manage the certificate the
 * app served, behind a toggle that rebound the listener from 8000 to 8443 at the
 * next restart, in front of a Gateway that expects 8000. TLS is the load
 * balancer's job now (ADR 0013), and the second test below is what keeps the
 * served-certificate controls from creeping back onto this screen.
 */

/** What GET /api/admin/trust-store returns with one internal authority imported. */
const STORE = {
  cas: [{ id: "abc", name: "Corp Internal Root", kind: "root", issuer: "Corp Internal Root", not_after: "2035-01-01T00:00:00Z" }],
  roots: [{ id: "abc", name: "Corp Internal Root", kind: "root", issuer: "Corp Internal Root", not_after: "2035-01-01T00:00:00Z" }],
  intermediates: [],
};

function renderTrust(status: object) {
  // A stored choice, so the assertions below can name the French labels: the
  // provider on its own starts from the viewer's choice, and there is no server
  // here to supply the instance default.
  localStorage.setItem("trt_lang", "fr");
  vi.spyOn(api, "get").mockResolvedValue(status as never);
  return render(
    <I18nProvider>
      <TrustAdmin />
    </I18nProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("Admin > certificate authorities", () => {
  it("lists the trusted authorities and lets them be managed", async () => {
    renderTrust(STORE);

    expect(await screen.findByText("Autorités approuvées")).toBeDefined();
    expect(screen.getByText("Corp Internal Root")).toBeDefined();
    expect(screen.getByLabelText("Fichier CA (.pem/.crt)")).toBeDefined();
    expect(screen.getByRole("button", { name: "Ajouter la CA" })).not.toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Supprimer" })).not.toHaveProperty("disabled", true);
  });

  it("offers nothing about a certificate the app would serve", async () => {
    renderTrust(STORE);
    await screen.findByText("Autorités approuvées");

    expect(screen.queryByText("Générer un certificat auto-signé")).toBeNull();
    expect(screen.queryByRole("button", { name: "Installer et activer" })).toBeNull();
    expect(screen.queryByLabelText("Fichier PFX (.pfx/.p12)")).toBeNull();
    // And it says who does terminate the TLS, rather than staying silent about it.
    expect(screen.getByText(/le TLS entrant est assuré par le répartiteur de charge/)).toBeDefined();
  });

  it("reads the store from the trust-store endpoint", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue(STORE as never);
    localStorage.setItem("trt_lang", "fr");
    render(<I18nProvider><TrustAdmin /></I18nProvider>);

    await screen.findByText("Autorités approuvées");
    expect(get).toHaveBeenCalledWith("/api/admin/trust-store");
  });
});
