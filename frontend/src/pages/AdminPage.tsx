/**
 * AdminPage - the administration console: a left-nav shell hosting many panels.
 *
 * This file is the SHELL only. It loads the current user's permissions, resolves
 * which tabs that role may open (honouring role preview and a `?section=` deep
 * link), and renders the navigation plus the active panel. The panels themselves
 * live in ./admin, one module per group of the navigation:
 *
 *   admin/organisation    tribes, squads, users, personas
 *   admin/imports         org import, Steerco import, PPTX template
 *   admin/configuration   modules, weekly report, leave, general settings
 *   admin/authentication  SSO, API keys, SMTP, TLS
 *   admin/oversight       moderation, log export, audit, ops
 *   admin/shared          the two hooks more than one panel needs
 *
 * The server is always authoritative: the SPA merely hides what a role cannot
 * use, and every panel's own API calls are re-checked server-side.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { useModule } from "../config";
import { useAuth } from "../auth";
import { ModuleKey, Permissions } from "../types";
import { ErrorBanner, Spinner } from "../components/ui";
import { ADMIN_TABS_BY_ROLE } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";

// Label key for each admin tab (server decides which a role may open).
import { ApiAdmin, AuthAdmin, SmtpAdmin, TrustAdmin } from "./admin/authentication";
import { LeavesAdmin, ModulesAdmin, ReportingAdmin, SettingsAdmin } from "./admin/configuration";
import { ImportOrgAdmin, PptxTemplateAdmin } from "./admin/imports";
import { PersonasAdmin, SquadsAdmin, TribeSelfAdmin, TribesAdmin, UsersAdmin } from "./admin/organisation";
import { PlatformsAdmin } from "./admin/platforms";
import { DataAdmin } from "./admin/data";
import { BrandingAdmin } from "./admin/branding";
import { AuditAdmin, LogExportAdmin, ModerationAdmin, OpsAdmin } from "./admin/oversight";
import { ADMIN_GROUPS, TAB_LABEL } from "./admin/tabs";



// L'onglet d'un service coupe n'a rien a montrer: ses routes sont gardees par le
// meme module et repondent 404. Le proposer quand meme donne un ecran vide et deux
// erreurs dans la console. Il revient des que le service est rallume, depuis
// « Services actifs », qui ne depend lui-meme d'aucun module.
const TAB_MODULE: Record<string, [ModuleKey] | [ModuleKey, string]> = {
  leaves: ["leaves"],
  moderation: ["feed"],
  platforms: ["steerco"],
  report: ["review", "weekly_report"],
};



/**
 * Admin shell: fetches permissions, resolves the allowed tab set (honouring role
 * preview and a `?section=` deep link), and renders the nav + the active panel.
 */
export default function AdminPage() {
  const { t } = useI18n();
  const { effectiveRole } = useAuth();
  const [perms, setPerms] = useState<Permissions | null>(null);
  const [tab, setTab] = useState<string>("");
  const [params] = useSearchParams();

  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    api.get<Permissions>("/api/auth/me/permissions")
      .then((p) => setPerms(p))
      .catch((e) => setLoadError(errorText(e)));
  }, []);

  // When an admin previews another role, reflect that role's scoped tab set
  // (the backend still enforces the real account's permissions on every call).
  const granted =
    perms && effectiveRole && effectiveRole !== perms.role
      ? ADMIN_TABS_BY_ROLE[effectiveRole] ?? []
      : perms?.admin_tabs ?? [];
  // Puis retirer ceux dont le service est coupe: leurs routes repondraient 404.
  const moduleOn = useModule();
  const tabKeys = granted.filter((k) => {
    const m = TAB_MODULE[k];
    return !m || moduleOn(m[0], m[1]);
  });

  // Pick the active tab: honour a valid `?section=` deep link, else keep the
  // current tab if still allowed, else fall back to the first allowed tab.
  useEffect(() => {
    const want = params.get("section");
    setTab((cur) => {
      if (want && tabKeys.includes(want)) return want;
      return cur && tabKeys.includes(cur) ? cur : tabKeys[0] ?? "";
    });
  }, [tabKeys.join(","), params]);
  useSetPageChrome({ title: t("admin.title") }, [perms, t]);

  if (loadError) return <ErrorBanner message={loadError} />;
  if (!perms) return <Spinner />;

  // Keep only groups/items the current role may open; drop empty groups.
  const groups = ADMIN_GROUPS
    .map((g) => ({ ...g, items: g.items.filter((k) => tabKeys.includes(k)) }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="admin-layout">
      <nav className="admin-nav" aria-label={t("admin.title")}>
        <div className="admin-nav-head">{t("admin.title")}</div>
        {groups.map((g) => (
          <div key={g.titleKey} className="admin-nav-group">
            <div className="admin-nav-title">{t(g.titleKey)}</div>
            {g.items.map((k) => (
              <button key={k} className={`admin-nav-item ${tab === k ? "active" : ""}`}
                      onClick={() => setTab(k)} aria-current={tab === k ? "page" : undefined}>
                {t(TAB_LABEL[k] ?? k)}
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="admin-content stack" style={{ gap: 16 }}>
        {tab === "tribes" && <TribesAdmin />}
        {tab === "import" && <ImportOrgAdmin />}
        {tab === "tribe" && <TribeSelfAdmin perms={perms} />}
        {tab === "squads" && <SquadsAdmin perms={perms} />}
        {tab === "platforms" && <PlatformsAdmin />}
        {tab === "users" && <UsersAdmin perms={perms} />}
        {tab === "personas" && <PersonasAdmin />}
        {tab === "modules" && <ModulesAdmin />}
        {tab === "report" && <ReportingAdmin />}
        {tab === "leaves" && <LeavesAdmin perms={perms} />}
        {tab === "moderation" && <ModerationAdmin />}
        {tab === "auth" && <AuthAdmin />}
        {tab === "api" && <ApiAdmin />}
        {tab === "smtp" && <SmtpAdmin />}
        {tab === "trust" && <TrustAdmin />}
        {tab === "logs" && <LogExportAdmin />}
        {tab === "settings" && <SettingsAdmin />}
        {tab === "data" && <DataAdmin />}
        {tab === "branding" && <BrandingAdmin />}
        {/* The export template is appearance: same tab as the server checks (tabaccess). */}
        {tab === "branding" && <PptxTemplateAdmin />}
        {tab === "audit" && <AuditAdmin />}
        {tab === "ops" && <OpsAdmin />}
      </div>
    </div>
  );
}
