import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { I18nProvider } from "../i18n";
import { api } from "../api";
import DirectorySearch, { invalidateDirectoryStatus, splitName } from "./DirectorySearch";

/**
 * The directory search shows nothing until an administrator switched a source
 * on, then searches once the typing pauses and hands the picked person over.
 */

const ALICE = { name: "Alice Martin", first_name: "Alice", last_name: "Martin", email: "alice@corp.example",
                title: "Architecte", department: "Cloud", source: "entra", user_id: null };

function setup(enabled: boolean, onPick = vi.fn()) {
  localStorage.setItem("trt_lang", "fr");
  invalidateDirectoryStatus();
  const get = vi.spyOn(api, "get").mockImplementation(((url: string) => {
    if (url === "/api/directory/status") return Promise.resolve({ enabled, sources: enabled ? ["entra"] : [] });
    return Promise.resolve({ results: [ALICE], sources: { entra: { ok: true, count: 1 }, ldap: { ok: false, error: "x" } } });
  }) as never);
  render(<I18nProvider><DirectorySearch onPick={onPick} /></I18nProvider>);
  return { get, onPick };
}

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

describe("DirectorySearch", () => {
  it("renders nothing without a directory", async () => {
    const { get } = setup(false);
    await waitFor(() => expect(get).toHaveBeenCalledWith("/api/directory/status"));
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("searches after a pause and hands the person over", async () => {
    const { get, onPick } = setup(true);
    const box = await screen.findByRole("searchbox");
    fireEvent.change(box, { target: { value: "al" } });
    const option = await screen.findByRole("option", {}, { timeout: 2000 });
    expect(get).toHaveBeenCalledWith("/api/directory/search?q=al");
    expect(screen.getByText(/LDAP \/ Active Directory n'a pas répondu/)).toBeTruthy();
    fireEvent.click(option);
    expect(onPick).toHaveBeenCalledWith(ALICE);
  });

  it("splits a display name when the directory gave no first name", () => {
    expect(splitName({ ...ALICE, first_name: null, last_name: null, name: "Jean de la Tour" } as never))
      .toEqual({ first: "Jean", last: "de la Tour" });
  });
});
