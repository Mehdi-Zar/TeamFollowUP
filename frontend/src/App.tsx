import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
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
import PrintSquadPage from "./pages/PrintSquadPage";
import PrintDashboardPage from "./pages/PrintDashboardPage";

function Protected({ children, adminOnly }: { children: JSX.Element; adminOnly?: boolean }) {
  const { user, loading, effectiveRole } = useAuth();
  if (loading) return <div className="spinner">Chargement…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && effectiveRole !== "admin") return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route path="/print/squad/:id" element={<Protected><PrintSquadPage /></Protected>} />
      <Route path="/print/dashboard" element={<Protected><PrintDashboardPage /></Protected>} />

      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/squads/:id" element={<SquadDetailPage />} />
        <Route path="/fil" element={<FeedPage />} />
        <Route path="/preferences" element={<PreferencesPage />} />
        <Route path="/saisie" element={<EntryPage />} />
        <Route path="/organigramme" element={<OrgPage />} />
        <Route path="/tribus" element={<Protected adminOnly><TribesPage /></Protected>} />
        <Route path="/admin" element={<Protected adminOnly><AdminPage /></Protected>} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
