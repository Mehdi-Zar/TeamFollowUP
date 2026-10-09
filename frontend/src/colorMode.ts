// Light or dark display, per browser.
//
// Three choices: light, dark, or "system" (follow the operating system, the
// default). The choice is kept in the browser (a display preference, like the
// sort of a table), and the resolved mode is written on <html data-theme>, which
// theme.css reads. Applied before the first render, so a dark page never flashes
// white.
import { useEffect, useState } from "react";

export type ColorMode = "light" | "dark" | "system";
const KEY = "tfu.colorMode";
const EVENT = "tfu-color-mode";

function media(): MediaQueryList | null {
  try { return window.matchMedia("(prefers-color-scheme: dark)"); } catch { return null; }
}

export function getColorMode(): ColorMode {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch { return "system"; }
}

/** The mode on screen: the choice, or the system's when the choice is "system". */
export function resolvedMode(mode: ColorMode = getColorMode()): "light" | "dark" {
  if (mode !== "system") return mode;
  return media()?.matches ? "dark" : "light";
}

function apply(): void {
  document.documentElement.dataset.theme = resolvedMode();
}

export function setColorMode(mode: ColorMode): void {
  try {
    if (mode === "system") localStorage.removeItem(KEY); else localStorage.setItem(KEY, mode);
  } catch { /* storage blocked: applies for this page only */ }
  apply();
  window.dispatchEvent(new Event(EVENT));
}

/** Applies the saved mode now, and follows the system while on "system". */
export function installColorMode(): void {
  apply();
  media()?.addEventListener?.("change", () => { if (getColorMode() === "system") apply(); });
}

/** The current choice and the mode on screen, kept in sync across the page. */
export function useColorMode(): { mode: ColorMode; resolved: "light" | "dark"; set: (m: ColorMode) => void } {
  const [mode, setMode] = useState<ColorMode>(getColorMode);
  const [resolved, setResolved] = useState(() => resolvedMode());
  useEffect(() => {
    const sync = () => { setMode(getColorMode()); setResolved(resolvedMode()); };
    window.addEventListener(EVENT, sync);
    const m = media();
    m?.addEventListener?.("change", sync);
    return () => { window.removeEventListener(EVENT, sync); m?.removeEventListener?.("change", sync); };
  }, []);
  return { mode, resolved, set: setColorMode };
}
