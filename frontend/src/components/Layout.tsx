import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig } from "../config";
import { Role } from "../types";
import { ALL_ROLES, canSeeAdmin, canSeeSaisie } from "../perms";
import NotificationBell from "./NotificationBell";

function navStyle({ isActive }: { isActive: boolean }): React.CSSProperties {
  return {
    padding: "8px 14px",
    borderRadius: 10,
    fontWeight: 600,
    fontSize: 14,
    color: isActive ? "#fff" : "#CADCFC",
    background: isActive ? "rgba(255,255,255,.14)" : "transparent",
  };
}

const whiteSelect: React.CSSProperties = {
  width: "auto",
  background: "rgba(255,255,255,.12)",
  color: "#fff",
  border: "1px solid rgba(255,255,255,.25)",
};

export default function Layout() {
  const { user, logout, effectiveRole, isPreview, previewRole, setPreviewRole } = useAuth();
  const { t, role: roleLabel, lang, setLang } = useI18n();
  const { app_name } = useConfig();
  const navigate = useNavigate();
  const role = (effectiveRole ?? "member") as Role;

  async function onLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div style={{ minHeight: "100vh" }}>
      <header
        style={{
          background: "linear-gradient(90deg,#141B47,#1E2761)",
          color: "#fff",
          padding: "12px 24px",
          display: "flex",
          alignItems: "center",
          gap: 18,
          flexWrap: "wrap",
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 17, cursor: "pointer" }} onClick={() => navigate("/")}>
          {app_name}
        </div>
        <nav style={{ display: "flex", gap: 6, flex: 1, flexWrap: "wrap" }}>
          <NavLink to="/" end style={navStyle}>
            {t("nav.dashboard")}
          </NavLink>
          <NavLink to="/organigramme" style={navStyle}>
            {t("nav.org")}
          </NavLink>
          {canSeeAdmin(role) && (
            <NavLink to="/tribus" style={navStyle}>
              {t("nav.tribes")}
            </NavLink>
          )}
          {canSeeSaisie(role) && (
            <NavLink to="/saisie" style={navStyle}>
              {t("nav.entry")}
            </NavLink>
          )}
          <NavLink to="/fil" style={navStyle}>
            {t("nav.feed")}
          </NavLink>
          {canSeeAdmin(role) && (
            <NavLink to="/admin" style={navStyle}>
              {t("nav.admin")}
            </NavLink>
          )}
        </nav>

        {user?.role === "admin" && (
          <div className="inline" style={{ gap: 6 }}>
            <span style={{ fontSize: 12, color: "#CADCFC" }}>{t("preview.as")}</span>
            <select
              value={previewRole ?? "admin"}
              onChange={(e) => setPreviewRole(e.target.value === "admin" ? null : (e.target.value as Role))}
              style={whiteSelect}
            >
              {ALL_ROLES.map((r) => (
                <option key={r} value={r} style={{ color: "#1E293B" }}>
                  {roleLabel(r)}
                </option>
              ))}
            </select>
          </div>
        )}

        <NotificationBell />

        <select value={lang} onChange={(e) => setLang(e.target.value as any)} style={whiteSelect}>
          <option value="fr" style={{ color: "#1E293B" }}>FR</option>
          <option value="en" style={{ color: "#1E293B" }}>EN</option>
        </select>

        <div style={{ fontSize: 13, opacity: 0.95, textAlign: "right", cursor: "pointer" }} onClick={() => navigate("/preferences")} title={t("prefs.title")}>
          <div style={{ fontWeight: 600 }}>{user?.display_name}</div>
          <div style={{ opacity: 0.7, fontSize: 12 }}>{user ? roleLabel(user.role) : ""}</div>
        </div>
        <button className="btn-ghost" style={{ color: "#fff", borderColor: "rgba(255,255,255,.3)" }} onClick={onLogout}>
          {t("action.logout")}
        </button>
      </header>

      {isPreview && (
        <div
          className="no-print"
          style={{ background: "#FEF3C7", color: "#92400E", padding: "8px 24px", fontSize: 13, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}
        >
          <span>
            {t("preview.as")} <strong>{roleLabel(previewRole as Role)}</strong> — {t("preview.banner")}
          </span>
          <button className="btn-secondary btn-sm" onClick={() => setPreviewRole(null)}>
            {t("preview.back")}
          </button>
        </div>
      )}

      <main style={{ maxWidth: 1180, margin: "0 auto", padding: "24px 20px 60px" }}>
        <Outlet />
      </main>
    </div>
  );
}
