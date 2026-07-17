/**
 * Root router and route-guarding layer.
 *
 * Declares every application route and wraps them in guards that enforce three
 * independent gates before a screen renders: authentication ({@link Protected}),
 * whether the feature module is enabled ({@link ModuleGuard}), and the user's
 * persona capability ({@link Section}). Screens are lazily imported for
 * per-route code splitting.
 */
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
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
const TribesPage = lazy(() => import("./pages/TribesPage"));
const PreferencesPage = lazy(() => import("./pages/PreferencesPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const MySquadsPage = lazy(() => import("./pages/MySquadsPage"));
const GettingStartedPage = lazy(() => import("./pages/GettingStartedPage"));
const RoadmapPage = lazy(() => import("./pages/RoadmapPage"));
const InitiativesPage = lazy(() => import("./pages/InitiativesPage"));
const LeavesPage = lazy(() => import("./pages/LeavesPage"));
const AccessRequestsPage = lazy(() => import("./pages/AccessRequestsPage"));
const PrintSquadPage = lazy(() => import("./pages/PrintSquadPage"));
const PrintDashboardPage = lazy(() => import("./pages/PrintDashboardPage"));
import { PageChromeProvider } from "./components/pageChrome";

/**
 * Authentication + role gate. Renders `children` only for a logged-in, active
 * user; otherwise redirects to /login, shows the access screen (pending/revoked
 * SSO account), or bounces to "/" when the optional role flags aren't met.
 *
 * @param adminOnly Restrict to the admin role.
 * @param adminPage Restrict to roles allowed on the Admin page (admin, tribe leader).
 * @param manageSquads Restrict to roles that manage squads (admin, tribe/squad leader).
 */
function Protected({ children, adminOnly, adminPage, manageSquads }: { children: JSX.Element; adminOnly?: boolean; adminPage?: boolean; manageSquads?: boolean }) {
  const { user, loading, effectiveRole } = useAuth();
  if (loading) return <div className="spinner">Chargement…</div>;
  if (!user) return <Navigate to="/login" replace />;
  // Authenticated but not validated (SSO provisioning awaiting approval, or
  // revoked): no app access, show the access screen instead.
  if (user.status && user.status !== "active") return <AccessPending />;
  if (adminOnly && effectiveRole !== "admin") return <Navigate to="/" replace />;
  // Admin page is role-scoped: admins and tribe leaders may open it.
  if (adminPage && !["admin", "tribe_leader"].includes(effectiveRole ?? "")) {
    return <Navigate to="/" replace />;
  }
  // "My squads" page: admins, tribe leaders and squad leaders.
  if (manageSquads && !["admin", "tribe_leader", "squad_leader"].includes(effectiveRole ?? "")) {
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
  if (!can(cap)) return <Navigate to="/preferences" replace />;
  return children;
}

/**
 * Application route table. Public /login, standalone /print/* pages, and the
 * main app shell (guarded {@link Layout} with nested section routes). Unknown
 * paths redirect home.
 */
export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route path="/print/squad/:id" element={<Protected><PrintSquadPage /></Protected>} />
      <Route path="/print/dashboard" element={<Protected><PrintDashboardPage /></Protected>} />

      <Route element={<PageChromeProvider><Protected><Layout /></Protected></PageChromeProvider>}>
        <Route path="/" element={<Section module="dashboard" cap="dashboard"><DashboardPage /></Section>} />
        <Route path="/roadmap" element={<Section module="squad_content" feature="roadmap" cap="roadmap"><RoadmapPage /></Section>} />
        <Route path="/initiatives" element={<Protected><InitiativesPage /></Protected>} />
        <Route path="/acces" element={<Protected><AccessRequestsPage /></Protected>} />
        <Route path="/squads/:id" element={<SquadDetailPage />} />
        <Route path="/fil" element={<Section module="feed" cap="feed"><FeedPage /></Section>} />
        <Route path="/conges" element={<Section module="leaves" cap="leaves"><LeavesPage /></Section>} />
        <Route path="/preferences" element={<PreferencesPage />} />
        <Route path="/prise-en-main" element={<ModuleGuard module="getting_started"><GettingStartedPage /></ModuleGuard>} />
        <Route path="/saisie" element={<Section module="reporting" cap="reporting"><EntryPage /></Section>} />
        <Route path="/organigramme" element={<Section module="org" cap="org"><OrgPage /></Section>} />
        <Route path="/tribus" element={<Protected adminOnly><TribesPage /></Protected>} />
        <Route path="/mes-squads" element={<Section cap="mysquads"><MySquadsPage /></Section>} />
        <Route path="/admin" element={<Protected adminPage><AdminPage /></Protected>} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
  );
}
