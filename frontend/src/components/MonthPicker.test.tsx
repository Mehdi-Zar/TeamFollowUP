import { describe, it, expect } from "vitest";
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider } from "../i18n";
import MonthPicker from "./MonthPicker";

/**
 * The Steerco month is picked in a calendar (year, then month), not in a long
 * dropdown: moving to another year and clicking a month must give that "YYYY-MM".
 */
function Field() {
  const [p, setP] = useState("2026-07");
  return <><MonthPicker id="m" value={p} onChange={setP} /><output>{p}</output></>;
}

describe("MonthPicker", () => {
  it("picks a month of another year", () => {
    render(<I18nProvider><Field /></I18nProvider>);
    fireEvent.click(screen.getByText("July 2026"));
    expect(screen.getByText("2026")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Previous year"));
    expect(screen.getByText("2025")).toBeTruthy();
    fireEvent.click(screen.getByTitle("March 2025"));
    expect(screen.getByRole("status").textContent).toBe("2025-03");
    // The panel closes on a pick and the button shows the new month.
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("March 2025")).toBeTruthy();
  });

  it("reopens on the chosen month's year", () => {
    render(<I18nProvider><Field /></I18nProvider>);
    fireEvent.click(screen.getByText("July 2026"));
    fireEvent.click(screen.getByLabelText("Next year"));
    fireEvent.click(screen.getByText("July 2026"));   // close without picking
    fireEvent.click(screen.getByText("July 2026"));
    expect(screen.getByText("2026")).toBeTruthy();
    expect(screen.getByTitle("July 2026").getAttribute("aria-pressed")).toBe("true");
  });
});
