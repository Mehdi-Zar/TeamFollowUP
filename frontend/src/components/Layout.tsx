import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig, moduleOn } from "../config";
import { ModuleKey, Role } from "../types";
import { canSeeAdmin, canSeeSaisie, isGlobalAdmin } from "../perms";
import NotificationBell from "./NotificationBell";
import { usePageChrome } from "./pageChrome";
import {
  IconAdmin,
  IconCollapse,
  IconDashboard,
  IconEntry,
  IconExpand,
  IconFeed,
  IconOrg,
  IconReview,
  IconTribes,
} from "./icons";

type NavItem = {
  to: string;
  end?: boolean;
  labelKey: string;
  titleKey: string;
  Icon: (p: { size?: number }) => JSX.Element;
  visible: (role: Role) => boolean;
  /** When set, the entry is hidden if that module is disabled in the admin. */
  module?: ModuleKey;
};

const NAV: NavItem[] = [
  { to: "/", end: true, labelKey: "nav.dashboard", titleKey: "nav.dashboard", Icon: IconDashboard, visible: () => true, module: "dashboard" },
  { to: "/organigramme", labelKey: "nav.org", titleKey: "nav.org", Icon: IconOrg, visible: () => true, module: "org" },
  { to: "/tribus", labelKey: "nav.tribes", titleKey: "nav.tribes", Icon: IconTribes, visible: isGlobalAdmin },
  { to: "/saisie", labelKey: "nav.entry", titleKey: "nav.entry", Icon: IconEntry, visible: canSeeSaisie, module: "reporting" },
  { to: "/fil", labelKey: "nav.feed", titleKey: "nav.feed", Icon: IconFeed, visible: () => true, module: "feed" },
  { to: "/revue", labelKey: "nav.review", titleKey: "review.title", Icon: IconReview, visible: (r) => r === "admin" || r === "tribe_leader", module: "review" },
  { to: "/admin", labelKey: "nav.admin", titleKey: "nav.admin", Icon: IconAdmin, visible: canSeeAdmin },
];

const COLLAPSE_KEY = "sidebar.collapsed";

const whiteSelect: React.CSSProperties = {
  width: "auto",
  background: "rgba(255,255,255,.12)",
  color: "#fff",
  border: "1px solid rgba(255,255,255,.25)",
};

export default function Layout() {
  const { user, logout, effectiveRole, isPreview, impersonate, stopImpersonation } = useAuth();
  const { t, role: roleLabel, lang, setLang } = useI18n();
  const { app_name, modules } = useConfig();
  const [people, setPeople] = useState<{ id: number; display_name: string; role: string }[]>([]);
  // Only a real admin (not already impersonating) may pick someone to view as.
  const canImpersonate = user?.role === "admin" && !isPreview;
  useEffect(() => {
    if (canImpersonate) api.get<any[]>("/api/admin/users").then(setPeople).catch(() => {});
  }, [canImpersonate]);
  const navVisible = (n: NavItem) => n.visible(role) && (!n.module || moduleOn(modules, n.module));
  const navigate = useNavigate();
  const location = useLocation();
  const chrome = usePageChrome();
  const role = (effectiveRole ?? "member") as Role;

  const [collapsed, setCollapsed] = useState<boolean>(() => localStorage.getItem(COLLAPSE_KEY) === "1");
  function toggleCollapsed() {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  }

  async function onLogout() {
    await logout();
    navigate("/login");
  }

  // Titre de la page : priorité au chrome poussé par la page, sinon dérivé de la route.
  const routeItem = NAV.find((n) => (n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)));
  const pageTitle =
    chrome.title ??
    (location.pathname.startsWith("/preferences")
      ? t("prefs.title")
      : routeItem
      ? t(routeItem.titleKey)
      : app_name);

  return (
    <div className={`app-shell${collapsed ? " collapsed" : ""}`}>
      <aside className="sidebar no-print">
        <div className="sidebar-brand" onClick={() => navigate("/")} title={app_name}>
          <span className="sidebar-logo">{app_name.slice(0, 1).toUpperCase()}</span>
          {!collapsed && <span className="sidebar-brand-text">{app_name}</span>}
        </div>

        <nav className="sidebar-nav">
          {NAV.filter(navVisible).map(({ to, end, labelKey, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}
              title={collapsed ? t(labelKey) : undefined}
            >
              <Icon size={19} />
              {!collapsed && <span className="sidebar-link-text">{t(labelKey)}</span>}
            </NavLink>
          ))}
        </nav>

        <button className="sidebar-collapse-btn" onClick={toggleCollapsed} title={collapsed ? t("nav.expand") : t("nav.collapse")}>
          {collapsed ? <IconExpand size={18} /> : <IconCollapse size={18} />}
          {!collapsed && <span>{t("nav.collapse")}</span>}
        </button>
      </aside>

      <div className="app-main">
        <header className="topbar no-print">
          <div className="topbar-row">
            <h1 className="topbar-title">{pageTitle}</h1>

            <div className="topbar-actions">
              {canImpersonate && (
                <div className="inline" style={{ gap: 6 }}>
                  <span style={{ fontSize: 12, color: "var(--grey)" }}>{t("preview.as")}</span>
                  <select
                    value=""
                    onChange={(e) => e.target.value && impersonate(Number(e.target.value))}
                    className="w-auto"
                  >
                    <option value="">{t("preview.pick")}</option>
                    {people
                      .filter((p) => p.id !== user?.id)
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.display_name} — {roleLabel(p.role as Role)}
                        </option>
                      ))}
                  </select>
                </div>
              )}

              <NotificationBell />

              <select value={lang} onChange={(e) => setLang(e.target.value as any)} className="w-auto">
                <option value="fr">FR</option>
                <option value="en">EN</option>
              </select>

              <div className="topbar-user" onClick={() => navigate("/preferences")} title={t("prefs.title")}>
                <div className="topbar-user-name">{user?.display_name}</div>
                <div className="topbar-user-role">{user ? roleLabel(user.role) : ""}</div>
              </div>
              <button className="btn-ghost btn-sm" onClick={onLogout}>
                {t("action.logout")}
              </button>
            </div>
          </div>

          {((chrome.tabs && chrome.tabs.length > 0) || chrome.actions) && (
            <div className="topbar-subbar">
              {chrome.tabs && chrome.tabs.length > 0 ? (
                <div className="tabs topbar-tabs">
                  {chrome.tabs.map((tab) => (
                    <button
                      key={tab.key}
                      className={chrome.activeTab === tab.key ? "active" : ""}
                      onClick={() => chrome.onTab?.(tab.key)}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              ) : (
                <span />
              )}
              {chrome.actions && <div className="topbar-page-actions">{chrome.actions}</div>}
            </div>
          )}
        </header>

        {isPreview && (
          <div className="no-print preview-banner">
            <span>
              {t("preview.viewing_as")} <strong>{user?.display_name}</strong>
              {" "}({user ? roleLabel(user.role) : ""}) — {t("preview.banner")}
            </span>
            <button className="btn-secondary btn-sm" onClick={() => stopImpersonation()}>
              {t("preview.back")}
            </button>
          </div>
        )}

        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
