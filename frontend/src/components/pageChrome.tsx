// "Chrome" de page : permet à une page de remonter son titre et/ou ses onglets
// contextuels vers la top bar globale rendue par le Layout.
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type ChromeTab = { key: string; label: string };

export type PageChrome = {
  title?: string;
  tabs?: ChromeTab[];
  activeTab?: string;
  onTab?: (key: string) => void;
};

type ChromeCtx = {
  chrome: PageChrome;
  setChrome: (c: PageChrome) => void;
};

const Ctx = createContext<ChromeCtx | null>(null);

export function PageChromeProvider({ children }: { children: ReactNode }) {
  const [chrome, setChrome] = useState<PageChrome>({});
  return <Ctx.Provider value={{ chrome, setChrome }}>{children}</Ctx.Provider>;
}

// Lecture (utilisé par le Layout / la top bar).
export function usePageChrome(): PageChrome {
  const c = useContext(Ctx);
  return c ? c.chrome : {};
}

// Écriture (appelé par une page). `deps` contrôle la mise à jour.
export function useSetPageChrome(chrome: PageChrome, deps: ReadonlyArray<unknown>) {
  const c = useContext(Ctx);
  const setChrome = c?.setChrome;
  useEffect(() => {
    if (!setChrome) return;
    setChrome(chrome);
    return () => setChrome({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
