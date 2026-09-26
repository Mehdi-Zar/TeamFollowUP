// Layout: the app chrome wrapping every authenticated route. Collapsible left
// sidebar (nav), top bar (page title, notifications, language, admin
// "view-as" impersonation, logout), an optional contextual sub-bar (tabs +
// actions pushed by the current page via pageChrome), the impersonation banner,
// the first-login welcome modal, and the command palette. The routed page renders
// through <Outlet/>. Nav visibility is filtered by role, enabled modules, and
// persona capabilities.
// React 19 removed the GLOBAL JSX namespace from @types/react; it is exported
// from the module instead. Type-only import, so it costs nothing at runtime.
import type { JSX } from "react";
import { useEffect, useRef, useState } from "react";
import ErrorBoundary from "./ErrorBoundary";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig, moduleOn } from "../config";
import { Capability, ModuleKey, Role } from "../types";
import { canSeeAdmin } from "../perms";
import NotificationBell from "./NotificationBell";
import { GettingStartedGuide } from "../pages/GettingStartedPage";
import CommandPalette from "./CommandPalette";
import { Modal } from "./ui";
import { usePageChrome } from "./pageChrome";
import {
  IconAdmin,
  IconCalendar,
  IconCollapse,
  IconDashboard,
  IconEntry,
  IconExpand,
  IconFeed,
  IconHelp,
  IconOrg,
  IconRoadmap,
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
  /** Optional sub-feature of `module` (e.g. squad_content → roadmap). */
  feature?: string;
  /** When set, the entry needs that persona capability (Admin → Personas). */
  cap?: Capability;
};

// The ordered sidebar entries. Each row is filtered at render time by navVisible()
// against the effective role, enabled modules/features, and persona capabilities.
const NAV: NavItem[] = [
  { to: "/", end: true, labelKey: "nav.dashboard", titleKey: "nav.dashboard", Icon: IconDashboard, visible: () => true, module: "dashboard", cap: "dashboard" },
  { to: "/roadmap", labelKey: "nav.roadmap", titleKey: "nav.roadmap", Icon: IconRoadmap, visible: () => true, module: "squad_content", feature: "roadmap", cap: "roadmap" },
  { to: "/organigramme", labelKey: "nav.org", titleKey: "nav.org", Icon: IconOrg, visible: () => true, module: "org", cap: "org" },
  { to: "/saisie", labelKey: "nav.entry", titleKey: "nav.entry", Icon: IconEntry, visible: () => true, module: "reporting", cap: "reporting" },
  { to: "/fil", labelKey: "nav.feed", titleKey: "nav.feed", Icon: IconFeed, visible: () => true, module: "feed", cap: "feed" },
  { to: "/conges", labelKey: "nav.leaves", titleKey: "nav.leaves", Icon: IconCalendar, visible: () => true, module: "leaves", cap: "leaves" },
  { to: "/mes-squads", labelKey: "nav.mysquads", titleKey: "mysquads.title", Icon: IconTribes, visible: () => true, cap: "mysquads" },
  { to: "/acces", labelKey: "nav.access", titleKey: "access.title", Icon: IconAdmin, visible: () => true },
  { to: "/admin", labelKey: "nav.admin", titleKey: "nav.admin", Icon: IconAdmin, visible: canSeeAdmin },
];

// localStorage key persisting the sidebar collapsed/expanded preference.
const COLLAPSE_KEY = "sidebar.collapsed";

/** Root layout for authenticated routes: renders the sidebar + top bar chrome and
 *  hosts the current page through <Outlet/>. Owns cross-page UI state (sidebar
 *  collapse, mobile drawer, admin impersonation picker, first-login welcome). */
export default function Layout() {
  const { user, logout, effectiveRole, isPreview, impersonate, stopImpersonation, can, pendingAccessCount, adminTabs, canReviewAccess, securityAlerts } = useAuth();
  const { t, role: roleLabel, lang, setLang } = useI18n();
  // A save that failed after its field was left (see api.reportSaveError).
  const [saveError, setSaveError] = useState<string | null>(null);
  useEffect(() => {
    const on = (e: Event) => setSaveError(String((e as CustomEvent).detail || ""));
    window.addEventListener("app:save-error", on);
    return () => window.removeEventListener("app:save-error", on);
  }, []);
  const { app_name, modules, branding, lang_switch } = useConfig();
  const [people, setPeople] = useState<{ id: number; display_name: string; role: string }[]>([]);
  // Only a real admin (not already impersonating) may pick someone to view as.
  const canImpersonate = user?.role === "admin" && !isPreview;
  useEffect(() => {
    if (canImpersonate) api.get<any[]>("/api/admin/users").then(setPeople).catch(() => {});
  }, [canImpersonate]);

  // The top bar is sticky and its height varies (sub-bar of tabs or not): publish
  // it as --topbar-h so a table header can stick right under it while scrolling.
  const topbarRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const el = topbarRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const set = () => document.documentElement.style.setProperty("--topbar-h", `${el.offsetHeight}px`);
    set();
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // The getting-started guide: a window when the app opens (once per session),
  // unless the person ticked "don't show at startup", and at any time from the
  // "?" button of the top bar. Both choices are kept in this browser, per user.
  const guideOn = moduleOn(modules, "getting_started");
  const hideKey = user ? `gs_hide_on_start_${user.id}` : "";
  const [guide, setGuide] = useState(false);
  const [hideOnStart, setHideOnStart] = useState(false);
  useEffect(() => {
    if (!user || isPreview || !guideOn) return;
    let hidden = false, shown = false;
    try {
      hidden = localStorage.getItem(hideKey) === "1";
      shown = sessionStorage.getItem(`gs_shown_${user.id}`) === "1";
      sessionStorage.setItem(`gs_shown_${user.id}`, "1");
    } catch { /* storage blocked: just show nothing automatically */ shown = true; }
    setHideOnStart(hidden);
    if (!hidden && !shown) setGuide(true);
  }, [user?.id, isPreview, guideOn]);
  function toggleHideOnStart(v: boolean) {
    setHideOnStart(v);
    try { v ? localStorage.setItem(hideKey, "1") : localStorage.removeItem(hideKey); } catch { /* ignore */ }
  }
  // Administration shows for whoever holds at least one tab (Admin > Personas),
  // whatever their role; the role table only drives the admin's "preview as".
  const navVisible = (n: NavItem) =>
    (n.to === "/admin" && !isPreview ? adminTabs.length > 0
      : n.to === "/acces" ? canReviewAccess : n.visible(role)) &&
    (!n.module || moduleOn(modules, n.module, n.feature)) &&
    (!n.cap || can(n.cap));
  const navigate = useNavigate();
  const location = useLocation();
  const chrome = usePageChrome();
  const role = (effectiveRole ?? "member") as Role;

  const [collapsed, setCollapsed] = useState<boolean>(() => localStorage.getItem(COLLAPSE_KEY) === "1");
  const [mobileOpen, setMobileOpen] = useState(false);
  // Close the mobile drawer whenever the route changes.
  useEffect(() => { setMobileOpen(false); }, [location.pathname]);
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
  // The browser tab and the history say which page it is, not only the app name.
  useEffect(() => {
    document.title = typeof pageTitle === "string" && pageTitle !== app_name ? `${pageTitle} | ${app_name}` : app_name;
  }, [pageTitle, app_name]);
  // Escape closes the mobile menu.
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMobileOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  return (
    <div className={`app-shell${collapsed ? " collapsed" : ""}${mobileOpen ? " mobile-open" : ""}`}>
      {mobileOpen && <div className="sidebar-overlay no-print" onClick={() => setMobileOpen(false)} />}
      <aside className={`sidebar no-print${mobileOpen ? " mobile-open" : ""}`}>
        <div className="sidebar-brand" role="link" onClick={() => navigate("/")} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate("/"); } }} title={app_name}>
          {/* Le logo televerse remplace l'initiale. Une initiale est un defaut
              acceptable, pas une identite: une organisation qui a un logo veut le
              voir la. */}
          {branding?.logo
            ? <img className="sidebar-logo-img" src={branding.logo} alt="" />
            : <span className="sidebar-logo">{app_name.slice(0, 1).toUpperCase()}</span>}
          {!collapsed && <span className="sidebar-brand-text">{app_name}</span>}
        </div>

        <nav className="sidebar-nav">
          {NAV.filter(navVisible).map(({ to, end, labelKey, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              // The Initiatives tab lives under the dashboard: keep its entry lit.
              className={({ isActive }) => `sidebar-link${isActive || (to === "/" && location.pathname.startsWith("/initiatives")) ? " active" : ""}`}
              title={collapsed ? t(labelKey) : undefined}
              onClick={() => setMobileOpen(false)}
            >
              <Icon size={19} />
              {!collapsed && <span className="sidebar-link-text">{t(labelKey)}</span>}
              {to === "/acces" && pendingAccessCount > 0 && (
                <span className="nav-count" style={{ marginLeft: "auto", background: "var(--red)", color: "#fff",
                  borderRadius: 10, padding: "0 7px", fontSize: 11, fontWeight: 700, lineHeight: "17px" }}>
                  {pendingAccessCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <button className="sidebar-collapse-btn" onClick={toggleCollapsed} title={collapsed ? t("nav.expand") : t("nav.collapse")}>
          {collapsed ? <IconExpand size={18} /> : <IconCollapse size={18} />}
          {!collapsed && <span>{t("nav.collapse")}</span>}
        </button>
      </aside>

      <div className="app-main">
        <header className="topbar no-print" ref={topbarRef}>
          <div className="topbar-row">
            <button className="topbar-hamburger" aria-label={t("nav.menu")} aria-expanded={mobileOpen} onClick={() => setMobileOpen(true)}>☰</button>
            <h1 className="topbar-title">{pageTitle}</h1>

            <div className="topbar-actions">
              {canImpersonate && (
                <div className="inline" style={{ gap: 6 }}>
                  <span style={{ fontSize: 12, color: "var(--grey)" }}>{t("preview.as")}</span>
                  <select
                    value=""
                    onChange={(e) => e.target.value && impersonate(Number(e.target.value))}
                    className="w-auto" aria-label={t("preview.as")}
                  >
                    <option value="">{t("preview.pick")}</option>
                    {people
                      .filter((p) => p.id !== user?.id)
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.display_name} ({roleLabel(p.role as Role)})
                        </option>
                      ))}
                  </select>
                </div>
              )}

              {guideOn && (
                <button className="btn-ghost btn-sm topbar-help" onClick={() => setGuide(true)}
                        title={t("gs.help")} aria-label={t("gs.help")}>
                  <IconHelp size={18} />
                </button>
              )}
              <NotificationBell />

              {lang_switch !== false && (
                <select value={lang} onChange={(e) => setLang(e.target.value as any)} className="w-auto"
                        aria-label={t("set.lang_pick")}>
                  <option value="fr">FR</option>
                  <option value="en">EN</option>
                </select>
              )}

              <Link className="topbar-user" to="/preferences" title={t("prefs.title")}>
                <div className="topbar-user-name">{user?.display_name}</div>
                <div className="topbar-user-role">{user ? roleLabel(user.role) : ""}</div>
              </Link>
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

        {securityAlerts.includes("secret_key") && (
          <div className="no-print banner banner-red stack" role="alert" style={{ margin: "8px 16px", gap: 6 }}>
            <strong>{t("sec.secret_key.title")}</strong>
            <span className="small">{t("sec.secret_key.why")}</span>
            <ol className="small" style={{ margin: 0, paddingLeft: 20 }}>
              <li>{t("sec.secret_key.step1")} <code>python -c "import secrets; print(secrets.token_urlsafe(48))"</code></li>
              <li>{t("sec.secret_key.step2")}</li>
              <li>{t("sec.secret_key.step3")}</li>
            </ol>
          </div>
        )}
        {saveError && (
          <div className="no-print banner banner-red between" role="alert" style={{ margin: "8px 16px", alignItems: "center" }}>
            <span className="small">{t("common.save_failed", { msg: saveError })}</span>
            <button className="btn-ghost btn-sm" onClick={() => setSaveError(null)} aria-label={t("action.close")}>✕</button>
          </div>
        )}
        {isPreview && (
          <div className="no-print preview-banner">
            <span>
              {t("preview.viewing_as")} <strong>{user?.display_name}</strong>
              {" "}({user ? roleLabel(user.role) : ""}). {t("preview.banner")}
            </span>
            <button className="btn-secondary btn-sm" onClick={() => stopImpersonation()}>
              {t("preview.back")}
            </button>
          </div>
        )}

        <main className="app-content">
          {/* A page that fails shows a message here, the menu stays; a new page
              starts afresh (keyed on the path). */}
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>

        {guide && (
          <Modal
            title={t("gs.welcome_title")}
            onClose={() => setGuide(false)}
            width={760}
            footer={
              <div className="between" style={{ width: "100%", alignItems: "center" }}>
                <label className="inline small" style={{ gap: 6 }}>
                  <input type="checkbox" checked={hideOnStart} onChange={(e) => toggleHideOnStart(e.target.checked)} />
                  {t("gs.dont_show")}
                </label>
                <button className="btn-sm" onClick={() => setGuide(false)}>{t("action.close")}</button>
              </div>
            }
          >
            <GettingStartedGuide onGo={() => setGuide(false)} />
            <div className="small muted" style={{ marginTop: 12 }}>{t("gs.reopen_hint")}</div>
          </Modal>
        )}
      </div>

      <CommandPalette pages={[
        ...NAV.filter(navVisible).map((n) => ({ to: n.to, label: t(n.labelKey) })),
        // Reached from a tab or a button, not from the menu: the palette finds them too.
        ...(can("dashboard") && moduleOn(modules, "dashboard") ? [{ to: "/initiatives", label: t("nav.initiatives") }] : []),
        { to: "/prise-en-main", label: t("gs.title") },
        { to: "/preferences", label: t("prefs.title") },
      ]} />
    </div>
  );
}
