/**
 * Root router and route-guarding layer.
 *
 * Declares every application route and wraps them in guards that enforce three
 * independent gates before a screen renders: authentication ({@link Protected}),
 * whether the feature module is enabled ({@link ModuleGuard}), and the user's
 * persona capability ({@link Section}). Screens are lazily imported for
 * per-route code splitting.
 */
// React 19 removed the GLOBAL JSX namespace from @types/react; it is exported
// from the module instead. Type-only import, so it costs nothing at runtime.
import type { JSX } from "react";
import { lazy, Suspense } from "react";
import ErrorBoundary from "./components/ErrorBoundary";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { useI18n } from "./i18n";
import { Spinner } from "./components/ui";
import { useConfig, moduleOn } from "./config";
import { Capability, ModuleKey } from "./types";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import AccessPending from "./components/AccessPending";
// Route-level code splitting: each screen is its own chunk, loaded on demand
// (Layout wraps <Outlet/> in <Suspense>). Keeps the initial bundle small.
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const SquadDetailPage = lazy(() => import("./pages/SquadDetailPage"));
const EntryPage = lazy(() => import("./pages/EntryPage"));
const OrgPage = lazy(() => import("./pages/OrgPage"));
const FeedPage = lazy(() => import("./pages/FeedPage"));
const PreferencesPage = lazy(() => import("./pages/PreferencesPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const MySquadsPage = lazy(() => import("./pages/MySquadsPage"));
const GettingStartedPage = lazy(() => import("./pages/GettingStartedPage"));
const RoadmapPage = lazy(() => import("./pages/RoadmapPage"));
const InitiativesPage = lazy(() => import("./pages/InitiativesPage"));
const LeavesPage = lazy(() => import("./pages/LeavesPage"));
const AccessRequestsPage = lazy(() => import("./pages/AccessRequestsPage"));
import { PageChromeProvider } from "./components/pageChrome";

/**
 * Authentication + role gate. Renders `children` only for a logged-in, active
 * user; otherwise redirects to /login, shows the access screen (pending/revoked
 * SSO account), or bounces to "/" when the optional role flags aren't met.
 *
 * @param adminPage Restrict to whoever holds an Administration tab.
 */
function Protected({ children, adminPage }: { children: JSX.Element; adminPage?: boolean }) {
  const { user, loading, effectiveRole, adminTabs, isPreview } = useAuth();
  const location = useLocation();
  const { t } = useI18n();
  if (loading) return <div className="spinner">{t("common.loading")}</div>;
  // Signed out: the login page brings back to this very page afterwards.
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  // Authenticated but not validated (SSO provisioning awaiting approval, or
  // revoked): no app access, show the access screen instead.
  if (user.status && user.status !== "active") return <AccessPending />;
  // The admin page opens for whoever holds at least one Administration tab
  // (Admin > Personas), the same rule as the menu entry; the role list only
  // serves the admin's "view as" preview.
  const mayOpenAdmin = isPreview ? ["admin", "tribe_leader"].includes(effectiveRole ?? "") : adminTabs.length > 0;
  if (adminPage && !mayOpenAdmin) {
    return <Navigate to="/" replace />;
  }
  return children;
}

// Fallback landing when the requested module is disabled: first enabled module.
const MODULE_HOME: { module: ModuleKey; path: string }[] = [
  { module: "dashboard", path: "/" },
  { module: "org", path: "/organigramme" },
  { module: "feed", path: "/fil" },
  { module: "reporting", path: "/saisie" },
];

/**
 * Renders `children` only if `module` is enabled; otherwise redirects to the
 * first other enabled module home (or /preferences, which is always reachable).
 */
function ModuleGuard({ module, children }: { module: ModuleKey; children: JSX.Element }) {
  const { modules } = useConfig();
  if (moduleOn(modules, module)) return children;
  const fallback = MODULE_HOME.find((m) => m.path !== location.pathname && moduleOn(modules, m.module));
  return <Navigate to={fallback ? fallback.path : "/preferences"} replace />;
}

// A navigable section: requires its module (if any) AND the persona capability
// (Admin → Personas). Capability denial lands on /preferences (always reachable).
/**
 * Combined guard for a navigable section: the feature module (and optional
 * sub-feature) must be enabled AND the persona must hold the `cap` capability.
 * Module-off redirects to another module home; capability-denied lands on
 * /preferences (always reachable).
 */
function Section({ module, feature, cap, children }: { module?: ModuleKey; feature?: string; cap: Capability; children: JSX.Element }) {
  const { modules } = useConfig();
  const { can } = useAuth();
  if (module && !moduleOn(modules, module, feature)) {
    const fallback = MODULE_HOME.find((m) => m.path !== location.pathname && moduleOn(modules, m.module));
    return <Navigate to={fallback ? fallback.path : "/preferences"} replace />;
  }
  // A section this profile does not open says so, instead of a silent jump to
  // the preferences (the dashboard's own back link used to land there).
  if (!can(cap)) return <SectionClosed />;
  return children;
}

/** The access-requests screen: for whoever may review access (the same flag as
 *  its menu entry and as the server). */
function ReviewGuard({ children }: { children: JSX.Element }) {
  const { canReviewAccess, loading } = useAuth();
  if (loading) return <Spinner />;
  return canReviewAccess ? children : <SectionClosed />;
}

/** Shown where a section is not open to this profile. */
function SectionClosed() {
  const { t } = useI18n();
  return (
    <div className="card stack" style={{ gap: 8, maxWidth: 560 }}>
      <h2 style={{ margin: 0 }}>{t("closed.title")}</h2>
      <div className="small muted">{t("closed.body")}</div>
      <div><Link to="/preferences" className="btn btn-secondary btn-sm">{t("closed.prefs")}</Link></div>
    </div>
  );
}

/**
 * Application route table. Public /login and the main app shell (guarded
 * {@link Layout} with nested section routes). Unknown paths redirect home.
 */
export default function App() {
  return (
    <ErrorBoundary>
    <Suspense fallback={<Spinner />}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<PageChromeProvider><Protected><Layout /></Protected></PageChromeProvider>}>
        <Route path="/" element={<Section module="dashboard" cap="dashboard"><DashboardPage /></Section>} />
        <Route path="/roadmap" element={<Section module="squad_content" feature="roadmap" cap="roadmap"><RoadmapPage /></Section>} />
        <Route path="/initiatives" element={<Section module="dashboard" cap="dashboard"><InitiativesPage /></Section>} />
        <Route path="/acces" element={<ReviewGuard><AccessRequestsPage /></ReviewGuard>} />
        <Route path="/squads/:id" element={<SquadDetailPage />} />
        <Route path="/fil" element={<Section module="feed" cap="feed"><FeedPage /></Section>} />
        <Route path="/conges" element={<Section module="leaves" cap="leaves"><LeavesPage /></Section>} />
        <Route path="/preferences" element={<PreferencesPage />} />
        <Route path="/prise-en-main" element={<ModuleGuard module="getting_started"><GettingStartedPage /></ModuleGuard>} />
        <Route path="/saisie" element={<Section module="reporting" cap="reporting"><EntryPage /></Section>} />
        <Route path="/organigramme" element={<Section module="org" cap="org"><OrgPage /></Section>} />

        <Route path="/mes-squads" element={<Section cap="mysquads"><MySquadsPage /></Section>} />
        <Route path="/admin" element={<Protected adminPage><AdminPage /></Protected>} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
    </ErrorBoundary>
  );
}
