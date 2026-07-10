import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api } from "./api";
import { useI18n } from "./i18n";
import { ModuleKey, ModulesConfig, PublicConfig } from "./types";

export const DEFAULT_MODULES: ModulesConfig = {
  dashboard: { enabled: true },
  org: { enabled: true },
  reporting: { enabled: true },
  feed: { enabled: true, reactions: true, replies: true, pin: true, kinds: true },
  review: { enabled: true, weekly_report: true },
  squad_content: { enabled: true, objectives: true, roadmap: true, kpis: false },
  committees: { enabled: false },
  notifications: { enabled: true, inapp: true, email: true },
  getting_started: { enabled: true },
  leaves: { enabled: true, overlap_alert: true },
};

const DEFAULTS: PublicConfig = {
  app_name: "Tribe Cockpit",
  app_subtitle: "Pilotage de la tribe",
  default_lang: "fr",
  default_year: new Date().getFullYear(),
  feed_post_scope: "leaders",
  feed_kinds: ["incident", "info", "success"],
  smtp_enabled: false,
  modules: DEFAULT_MODULES,
};

const ConfigContext = createContext<PublicConfig>(DEFAULTS);
const ReloadContext = createContext<() => void>(() => {});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const { setLang } = useI18n();
  const [cfg, setCfg] = useState<PublicConfig>(DEFAULTS);

  function load() {
    api
      .get<PublicConfig>("/api/config")
      .then((c) => {
        setCfg(c);
        if (!localStorage.getItem("trt_lang") && c.default_lang) setLang(c.default_lang);
      })
      .catch(() => {});
  }

  useEffect(() => { load(); }, []);

  return (
    <ReloadContext.Provider value={load}>
      <ConfigContext.Provider value={cfg}>{children}</ConfigContext.Provider>
    </ReloadContext.Provider>
  );
}

export function useConfig() {
  return useContext(ConfigContext);
}

/** Re-fetch /api/config (e.g. after an admin toggles modules). */
export function useReloadConfig() {
  return useContext(ReloadContext);
}

/** True if a module (and optional sub-feature) is enabled. Defaults to enabled
 *  when the config hasn't loaded yet, so the UI never flickers off wrongly. */
export function moduleOn(mods: ModulesConfig | undefined, module: ModuleKey, feature?: string): boolean {
  const m = (mods ?? DEFAULT_MODULES)[module] as any;
  if (!m || m.enabled === false) return false;
  if (!feature) return true;
  return m[feature] !== false;
}

/** Hook form: `const on = useModule(); on("feed", "reactions")`. */
export function useModule() {
  const { modules } = useConfig();
  return (module: ModuleKey, feature?: string) => moduleOn(modules, module, feature);
}
