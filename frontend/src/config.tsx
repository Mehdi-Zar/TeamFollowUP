import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api } from "./api";
import { useI18n } from "./i18n";
import { PublicConfig } from "./types";

const DEFAULTS: PublicConfig = {
  app_name: "Tribe Cockpit",
  app_subtitle: "Pilotage de la tribe",
  default_lang: "fr",
  default_year: new Date().getFullYear(),
  feed_post_scope: "leaders",
  feed_kinds: ["incident", "info", "success"],
  smtp_enabled: false,
};

const ConfigContext = createContext<PublicConfig>(DEFAULTS);

export function ConfigProvider({ children }: { children: ReactNode }) {
  const { setLang } = useI18n();
  const [cfg, setCfg] = useState<PublicConfig>(DEFAULTS);

  useEffect(() => {
    api
      .get<PublicConfig>("/api/config")
      .then((c) => {
        setCfg(c);
        if (!localStorage.getItem("trt_lang") && c.default_lang) setLang(c.default_lang);
      })
      .catch(() => {});
  }, []);

  return <ConfigContext.Provider value={cfg}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  return useContext(ConfigContext);
}
