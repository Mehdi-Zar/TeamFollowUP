import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { useConfig, moduleOn } from "./config";
import { ModuleKey } from "./types";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import SquadDetailPage from "./pages/SquadDetailPage";
import EntryPage from "./pages/EntryPage";
import OrgPage from "./pages/OrgPage";
import FeedPage from "./pages/FeedPage";
import TribesPage from "./pages/TribesPage";
import PreferencesPage from "./pages/PreferencesPage";
import AdminPage from "./pages/AdminPage";
import MySquadsPage from "./pages/MySquadsPage";
import GettingStartedPage from "./pages/GettingStartedPage";
import ReviewPage from "./pages/ReviewPage";
import PrintSquadPage from "./pages/PrintSquadPage";
import PrintDashboardPage from "./pages/PrintDashboardPage";
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
  { module: "review", path: "/revue" },
  { module: "reporting", path: "/saisie" },
];

function ModuleGuard({ module, children }: { module: ModuleKey; children: JSX.Element }) {
  const { modules } = useConfig();
  if (moduleOn(modules, module)) return children;
  const fallback = MODULE_HOME.find((m) => m.path !== location.pathname && moduleOn(modules, m.module));
  return <Navigate to={fallback ? fallback.path : "/preferences"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route path="/print/squad/:id" element={<Protected><PrintSquadPage /></Protected>} />
      <Route path="/print/dashboard" element={<Protected><PrintDashboardPage /></Protected>} />

      <Route element={<PageChromeProvider><Protected><Layout /></Protected></PageChromeProvider>}>
        <Route path="/" element={<ModuleGuard module="dashboard"><DashboardPage /></ModuleGuard>} />
        <Route path="/squads/:id" element={<SquadDetailPage />} />
        <Route path="/fil" element={<ModuleGuard module="feed"><FeedPage /></ModuleGuard>} />
        <Route path="/revue" element={<ModuleGuard module="review"><ReviewPage /></ModuleGuard>} />
        <Route path="/preferences" element={<PreferencesPage />} />
        <Route path="/prise-en-main" element={<GettingStartedPage />} />
        <Route path="/saisie" element={<ModuleGuard module="reporting"><EntryPage /></ModuleGuard>} />
        <Route path="/organigramme" element={<ModuleGuard module="org"><OrgPage /></ModuleGuard>} />
        <Route path="/tribus" element={<Protected adminOnly><TribesPage /></Protected>} />
        <Route path="/mes-squads" element={<Protected manageSquads><MySquadsPage /></Protected>} />
        <Route path="/admin" element={<Protected adminPage><AdminPage /></Protected>} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
