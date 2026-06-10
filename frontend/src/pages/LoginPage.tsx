import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig } from "../config";
import { ApiError } from "../api";

export default function LoginPage() {
  const { user, loading, config, login } = useAuth();
  const { t } = useI18n();
  const { app_name } = useConfig();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("login.failed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "linear-gradient(135deg,#141B47,#1E2761)", padding: 16 }}>
      <div className="card" style={{ width: "100%", maxWidth: 380 }}>
        <h1 style={{ fontSize: 22 }}>{app_name}</h1>
        <p className="muted small" style={{ marginTop: -6 }}>
          {t("login.subtitle")}
        </p>
        <form onSubmit={onSubmit} className="stack" style={{ marginTop: 16 }}>
          <div>
            <label>{t("login.email")}</label>
            <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div>
            <label>{t("login.password")}</label>
            <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error && <div className="error-text">{error}</div>}
          <button type="submit" disabled={submitting} style={{ width: "100%" }}>
            {submitting ? t("login.connecting") : t("login.submit")}
          </button>
        </form>

        {(config.oidc_enabled || config.saml_enabled) && (
          <div className="stack" style={{ marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 14 }}>
            {config.oidc_enabled && (
              <a className="btn btn-secondary" style={{ width: "100%", textAlign: "center" }} href="/api/auth/oidc/login">
                {t("login.oidc")}
              </a>
            )}
            {config.saml_enabled && (
              <a className="btn btn-secondary" style={{ width: "100%", textAlign: "center" }} href="/api/auth/saml/login">
                {t("login.saml")}
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
