// LoginPage - unauthenticated entry point of the app.
//
// The screen is built around ONE primary way in. Enterprise sign-in pages all
// converged on that shape, and for a good reason: a company that signs in with its
// IdP but is shown an email and password form teaches the wrong gesture to every
// new arrival, who then asks for a password nobody will ever give them. What the
// deployment configured is what the page offers, in the order it was configured,
// with the wording and the logo it chose.
//
// The local form follows the `password_mode` the administrator picked:
//   visible   - shown under the SSO buttons, as before
//   collapsed - folded behind a discreet link ("other options")
//   secret    - not shown at all, unless the URL carries the secret link's token
//
// Hiding it is discoverability, not access control: `POST /login` keeps working
// (the break-glass account must always be usable) and is guarded by the per-IP
// throttle. What the mode removes is the invitation.
import { FormEvent, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig } from "../config";
import { ApiError } from "../api";

type Method = { key: string; label?: string; hint?: string; logo?: string; primary?: boolean };

const SSO_HREF: Record<string, string> = {
  oidc: "/api/auth/oidc/login",
  saml: "/api/auth/saml/login",
};

export default function LoginPage() {
  const { user, loading, config, login } = useAuth();
  const { t } = useI18n();
  const { app_name, branding } = useConfig();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showLocal, setShowLocal] = useState(false);

  // Already signed in: skip the form entirely and go home.
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

  // The server resolved the secret link already (it compared the token without
  // returning it), so the page only has to read the mode it was handed.
  const cfg = config as any;
  const methods: Method[] = (cfg.methods?.length ? cfg.methods : [
    ...(config.oidc_enabled ? [{ key: "oidc", primary: true }] : []),
    ...(config.saml_enabled ? [{ key: "saml" }] : []),
    { key: "password", primary: !config.oidc_enabled && !config.saml_enabled },
  ]) as Method[];
  const mode: string = cfg.password_mode ?? "visible";
  const sso = methods.filter((m) => m.key !== "password");
  const localMethod = methods.find((m) => m.key === "password");
  // Folded away with nothing else on the page would be a card holding a single
  // link to itself: when no SSO is offered, the form is what the page is for.
  const localOpen = !!localMethod && (mode === "visible" || showLocal || sso.length === 0);

  const label = (m: Method) => m.label || t(`login.${m.key}`);

  const ssoButton = (m: Method) => (
    <a key={m.key} className={`btn ${m.primary ? "" : "btn-secondary"} login-method`}
       href={SSO_HREF[m.key] ?? "/"}>
      {m.logo ? <img src={m.logo} alt="" className="login-logo" /> : null}
      <span>{label(m)}</span>
    </a>
  );

  return (
    <div className="login-page"
         style={branding?.login_background
           ? { backgroundImage: `url(${branding.login_background})`, backgroundSize: "cover",
               backgroundPosition: "center" }
           : undefined}>
      <div className="card login-card">
        {branding?.logo && <img src={branding.logo} alt="" className="login-brand" />}
        <h1 style={{ fontSize: 22, marginBottom: 2 }}>{app_name}</h1>
        <p className="muted small" style={{ marginTop: 0 }}>{cfg.intro || t("login.subtitle")}</p>

        {/* The configured ways in, in order. The primary one is the filled button. */}
        <div className="stack" style={{ gap: 10, marginTop: 16 }}>
          {sso.map((m) => (
            <div key={m.key} className="stack" style={{ gap: 4 }}>
              {ssoButton(m)}
              {m.hint && <div className="small muted" style={{ textAlign: "center" }}>{m.hint}</div>}
            </div>
          ))}
        </div>

        {/* Local credentials: inline, folded, or absent, per the configured mode. */}
        {localMethod && localOpen && (
          <form onSubmit={onSubmit} className="stack"
                style={{ marginTop: sso.length ? 16 : 8, gap: 10 }}>
            {sso.length > 0 && <div className="login-sep"><span>{t("login.or")}</span></div>}
            {localMethod.hint && <div className="small muted">{localMethod.hint}</div>}
            <div>
              {/* htmlFor/id rather than aria-label: this form is a singleton, so the
                  ids cannot collide, and the association also makes clicking the
                  label focus the field. */}
              <label htmlFor="login-email">{t("login.email")}</label>
              <input id="login-email" type="email" autoComplete="username" value={email}
                     onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div>
              <label htmlFor="login-password">{t("login.password")}</label>
              <input id="login-password" type="password" autoComplete="current-password" value={password}
                     onChange={(e) => setPassword(e.target.value)} required />
            </div>
            {error && <div className="error-text">{error}</div>}
            <button type="submit" disabled={submitting} style={{ width: "100%" }}>
              {submitting ? t("login.connecting") : (localMethod.label || t("login.submit"))}
            </button>
          </form>
        )}

        {localMethod && !localOpen && mode === "collapsed" && (
          <button type="button" className="btn-ghost btn-sm login-other"
                  onClick={() => setShowLocal(true)}>
            {t("login.other_options")}
          </button>
        )}

        {/* Nothing configured at all: say so, rather than showing an empty card. */}
        {methods.length === 0 && <div className="small muted">{t("login.nothing_configured")}</div>}

        {/* The secret link was followed but the token did not match: same silence
            as a wrong password, no hint that a token even exists. */}
        {params.get("k") && mode === "secret" && (
          <div className="small muted" style={{ marginTop: 12 }}>{t("login.secret_refused")}</div>
        )}
      </div>
    </div>
  );
}
