import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Spinner } from "./components/ui";
import { useConfig, moduleOn } from "./config";
import { Capability, ModuleKey } from "./types";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
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
const PrintSquadPage = lazy(() => import("./pages/PrintSquadPage"));
const PrintDashboardPage = lazy(() => import("./pages/PrintDashboardPage"));
import { PageChromeProvider } from "./components/pageChrome";

function Protected({ children, adminOnly, adminPage, manageSquads }: { children: JSX.Element; adminOnly?: boolean; adminPage?: boolean; manageSquads?: boolean }) {
  const { user, loading, effectiveRole } = useAuth();
  if (loading) return <div className="spinner">Chargement…</div>;
  if (!user) return <Navigate to="/login" replace />;
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

function ModuleGuard({ module, children }: { module: ModuleKey; children: JSX.Element }) {
  const { modules } = useConfig();
  if (moduleOn(modules, module)) return children;
  const fallback = MODULE_HOME.find((m) => m.path !== location.pathname && moduleOn(modules, m.module));
  return <Navigate to={fallback ? fallback.path : "/preferences"} replace />;
}

// A navigable section: requires its module (if any) AND the persona capability
// (Admin → Personas). Capability denial lands on /preferences (always reachable).
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
        <Route path="/squads/:id" element={<SquadDetailPage />} />
        <Route path="/fil" element={<Section module="feed" cap="feed"><FeedPage /></Section>} />
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
