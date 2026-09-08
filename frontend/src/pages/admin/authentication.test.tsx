import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { api } from "../../api";
import { TlsAdmin } from "./authentication";

/**
 * Regression test for the defect that started this: on a deployment where the
 * infrastructure terminates TLS, which is the recommended one, the whole
 * certificate panel rendered only inside `{enabled && ...}`. The trusted
 * authorities went with it, so an administrator who needed to import an internal
 * root CA (without which OIDC against an internal IdP fails on the discovery
 * call) was told to switch the app to terminating TLS itself, which rebinds the
 * listener from 8000 to 8443 at the next restart, in front of a Gateway that
 * expects 8000.
 *
 * Serving TLS and trusting TLS are separate concerns. Only the first belongs
 * behind that toggle, and this asserts the split from the screen's side.
 */

/** What GET /api/admin/tls-config returns on an infra-TLS deployment: no
 *  certificate of our own, and one internal authority already imported. */
const INFRA_TLS = {
  tls_enabled: false,
  tls_running: false,
  mode: "self_signed",
  self_signed: {},
  active: null,
  chain_len: 0,
  cas: [{ id: "abc", name: "Corp Internal Root", kind: "root", issuer: "Corp Internal Root", not_after: "2035-01-01T00:00:00Z" }],
  roots: [{ id: "abc", name: "Corp Internal Root", kind: "root", issuer: "Corp Internal Root", not_after: "2035-01-01T00:00:00Z" }],
  intermediates: [],
};

function renderTls(status: object) {
  // A stored choice, so the assertions below can name the French labels: the
  // provider on its own starts from the viewer's choice, and there is no server
  // here to supply the instance default.
  localStorage.setItem("trt_lang", "fr");
  vi.spyOn(api, "get").mockResolvedValue(status as never);
  return render(
    <I18nProvider>
      <TlsAdmin />
    </I18nProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("Admin > HTTPS, with TLS terminated by the infrastructure", () => {
  it("still offers the trusted authorities, and lets them be managed", async () => {
    renderTls(INFRA_TLS);

    expect(await screen.findByText("Autorités approuvées")).toBeDefined();
    expect(screen.getByText("Corp Internal Root")).toBeDefined();
    // Managing them must be possible, not merely visible: the delete and add
    // controls used to inherit the serving-mode gate through `disabled`.
    expect(screen.getByLabelText("Fichier CA (.pem/.crt)")).toBeDefined();
    expect(screen.getByRole("button", { name: "Ajouter la CA" })).not.toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Supprimer" })).not.toHaveProperty("disabled", true);
  });

  it("hides the served-certificate panel, which really does depend on the toggle", async () => {
    renderTls(INFRA_TLS);
    await screen.findByText("Autorités approuvées");

    expect(screen.queryByText("Générer un certificat auto-signé")).toBeNull();
    expect(screen.queryByRole("button", { name: "Installer et activer" })).toBeNull();
    // And it says why, rather than leaving an empty screen.
    expect(screen.getByText(/l'infrastructure \(Gateway\/ALB\) qui termine le TLS/)).toBeDefined();
  });

  it("shows both panels once the app terminates TLS itself", async () => {
    renderTls({ ...INFRA_TLS, tls_enabled: true, tls_running: true });

    expect(await screen.findByText("Générer un certificat auto-signé")).toBeDefined();
    expect(screen.getByText("Autorités approuvées")).toBeDefined();
  });
});
