/**
 * Public application configuration context.
 *
 * Holds the server-provided {@link PublicConfig} (branding, default language/
 * year, feed settings, and the enabled/disabled module map). It lets any screen
 * ask "is this module/feature on?" and the admin refresh config after toggling
 * modules. Ships with sensible defaults so the UI renders before the fetch
 * resolves and never flickers features off by mistake.
 */
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api } from "./api";
import { useI18n } from "./i18n";
import { Branding, ModuleKey, ModulesConfig, PublicConfig } from "./types";

/** Default module map: everything on except committees, steerco and squad KPIs. Used
 *  until the server config loads, and as the fallback when config is missing. */
export const DEFAULT_MODULES: ModulesConfig = {
  dashboard: { enabled: true },
  org: { enabled: true },
  reporting: { enabled: true },
  feed: { enabled: true, reactions: true, replies: true, pin: true, kinds: true },
  review: { enabled: true, weekly_report: true },
  squad_content: { enabled: true, objectives: true, roadmap: true, kpis: false },
  committees: { enabled: false },
  steerco: { enabled: false },
  notifications: { enabled: true, inapp: true, email: true },
  getting_started: { enabled: true },
  leaves: { enabled: true, overlap_alert: true },
};

/** Full default config used as the initial context value before /api/config loads. */
const DEFAULTS: PublicConfig = {
  app_name: "TeamFollowUP",
  app_subtitle: "Pilotage de la tribe",
  default_lang: "fr",
  default_year: new Date().getFullYear(),
  feed_post_scope: "leaders",
  smtp_enabled: false,
  modules: DEFAULT_MODULES,
};

// Two separate contexts so consumers of the config value don't re-render just
// because the (stable) reload function is provided alongside it.
const ConfigContext = createContext<PublicConfig>(DEFAULTS);
const ReloadContext = createContext<() => void>(() => {});

/**
 * Applique le theme publie par le serveur.
 *
 * Les variables sont ecrites sur l'element racine plutot que dans une balise
 * <style> injectee: pas de feuille a nettoyer, pas d'ordre de cascade a arbitrer,
 * et un reglage retire revient tout seul a la valeur de theme.css. Le serveur a
 * deja valide chaque valeur par forme, ce qui est ce qui rend l'operation sure.
 */
function applyBranding(branding?: Branding) {
  const root = document.documentElement;
  // Ce qui a ete pose au passage precedent est retire d'abord, sinon une couleur
  // remise par defaut resterait a l'ecran jusqu'au rechargement suivant.
  for (const name of Array.from(root.style)) {
    if (name.startsWith("--")) root.style.removeProperty(name);
  }
  for (const [name, value] of Object.entries(branding?.css ?? {})) {
    root.style.setProperty(name, value);
  }
  root.dataset.density = branding?.density ?? "comfortable";
  if (branding?.favicon) {
    let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.href = branding.favicon;
  }
}

/** Fetches /api/config on mount and exposes it (plus a reload fn) to the tree. */
export function ConfigProvider({ children }: { children: ReactNode }) {
  const { applyServerDefault } = useI18n();
  const [cfg, setCfg] = useState<PublicConfig>(DEFAULTS);

  function load() {
    api
      .get<PublicConfig>("/api/config")
      .then((c) => {
        setCfg(c);
        // Applique des le premier chargement: la page de connexion doit deja
        // porter les couleurs du deploiement, sans clignoter par le theme livre.
        applyBranding(c.branding);
        // The instance's default language, applied only while the viewer has
        // made no choice of their own. The "has the viewer chosen" test lives in
        // i18n.tsx, next to the storage key it depends on.
        if (c.default_lang) applyServerDefault(c.default_lang);
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

/** Read the current public config. */
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
