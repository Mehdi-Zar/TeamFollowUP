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
import { Fragment, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useModule, useReloadConfig } from "../config";
import { useAuth } from "../auth";
import { AuditEntry, AuditPage, LeaveConfig, LeaveType, ModuleKey, Permissions, Persona, Role, Squad, SquadDetail, Tribe, User } from "../types";
import { ErrorBanner, Spinner, Dot, Modal, EmptyState } from "../components/ui";
import { ADMIN_TABS_BY_ROLE, ALL_ROLES } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";

// Label key for each admin tab (server decides which a role may open).
import { ApiAdmin, AuthAdmin, SmtpAdmin, TlsAdmin } from "./admin/authentication";
import { LeavesAdmin, ModulesAdmin, ReportingAdmin, SettingsAdmin } from "./admin/configuration";
import { ImportOrgAdmin, ImportSteercoAdmin, PptxTemplateAdmin } from "./admin/imports";
import { MySquadsAdmin, PersonasAdmin, SquadsAdmin, TribeSelfAdmin, TribesAdmin, UsersAdmin } from "./admin/organisation";
import { AuditAdmin, LogExportAdmin, ModerationAdmin, OpsAdmin } from "./admin/oversight";

const TAB_LABEL: Record<string, string> = {
  tribes: "admin.tab.tribes",
  import: "admin.tab.import",
  tribe: "admin.tab.my_tribe",
  squads: "admin.tab.squads",
  users: "admin.tab.users",
  personas: "admin.tab.personas",
  my_squads: "admin.tab.my_squads",
  modules: "admin.tab.modules",
  moderation: "admin.tab.moderation",
  auth: "admin.tab.auth",
  api: "admin.tab.api",
  smtp: "admin.tab.smtp",
  tls: "admin.tab.tls",
  report: "admin.tab.report",
  leaves: "admin.tab.leaves",
  logs: "admin.tab.logs",
  settings: "admin.tab.settings",
  audit: "admin.tab.audit",
  ops: "admin.tab.ops",
};

// Admin sections grouped by purpose (only the items a role may open are shown).
const ADMIN_GROUPS: { titleKey: string; items: string[] }[] = [
  { titleKey: "admin.group.org", items: ["tribes", "import", "tribe", "squads", "my_squads", "users", "personas"] },
  { titleKey: "admin.group.config", items: ["modules", "report", "leaves", "settings"] },
  { titleKey: "admin.group.access", items: ["auth", "api", "smtp", "tls"] },
  { titleKey: "admin.group.oversight", items: ["moderation", "logs", "audit", "ops"] },
];

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
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Erreur"));
  }, []);

  // When an admin previews another role, reflect that role's scoped tab set
  // (the backend still enforces the real account's permissions on every call).
  const tabKeys =
    perms && effectiveRole && effectiveRole !== perms.role
      ? ADMIN_TABS_BY_ROLE[effectiveRole] ?? []
      : perms?.admin_tabs ?? [];

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
        {tab === "import" && <ImportSteercoAdmin />}
        {tab === "import" && <PptxTemplateAdmin />}
        {tab === "tribe" && <TribeSelfAdmin perms={perms} />}
        {tab === "squads" && <SquadsAdmin perms={perms} />}
        {tab === "users" && <UsersAdmin perms={perms} />}
        {tab === "personas" && <PersonasAdmin />}
        {tab === "my_squads" && <MySquadsAdmin />}
        {tab === "modules" && <ModulesAdmin />}
        {tab === "report" && <ReportingAdmin />}
        {tab === "leaves" && <LeavesAdmin perms={perms} />}
        {tab === "moderation" && <ModerationAdmin />}
        {tab === "auth" && <AuthAdmin />}
        {tab === "api" && <ApiAdmin />}
        {tab === "smtp" && <SmtpAdmin />}
        {tab === "tls" && <TlsAdmin />}
        {tab === "logs" && <LogExportAdmin />}
        {tab === "settings" && <SettingsAdmin />}
        {tab === "audit" && <AuditAdmin />}
        {tab === "ops" && <OpsAdmin />}
      </div>
    </div>
  );
}
