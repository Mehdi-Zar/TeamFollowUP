/**
 * Authentication & authorization context.
 *
 * Single source of truth for "who is the current user, what may they see, and
 * are they being impersonated". Exposes the session user, their persona
 * capabilities (section-level access), the SSO access-review queue state, and
 * imperative actions (login/logout/impersonate/refresh). Consumed via the
 * {@link useAuth} hook. Security posture is fail-CLOSED: {@link can} grants
 * nothing unless the backend explicitly returned the capability.
 */
import { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { setCustomRoleLabels, useI18n } from "./i18n";
import { api, ApiError } from "./api";
import { AuthConfig, Capability, Role, User } from "./types";

/** Everything the auth context exposes to the app (session, permissions, actions). */
interface AuthState {
  user: User | null;
  loading: boolean;
  config: AuthConfig;
  /** The role the UI renders for. With real impersonation this is just the
   *  (impersonated) session user's role. */
  effectiveRole: Role | null;
  isPreview: boolean; // true while an admin views the app as another user
  impersonating: boolean;
  impersonatorName: string | null;
  /** Persona section-access capabilities for the current (effective) user. */
  capabilities: Record<string, boolean> | null;
  /** The Administration tabs this user holds (Admin > Personas); none = no admin. */
  adminTabs: string[];
  /** May the user open the SSO access-request queue, and how many are pending. */
  canReviewAccess: boolean;
  pendingAccessCount: number;
  can: (cap: Capability | string) => boolean;
  impersonate: (userId: number) => Promise<void>;
  stopImpersonation: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

/**
 * Provides {@link AuthState} to the tree. On mount it fetches the auth config
 * and the current session (`/api/auth/me`), then keeps user + permissions in
 * React state as login/logout/impersonation happen.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<AuthConfig>({ oidc_enabled: false, saml_enabled: false });
  const [impersonating, setImpersonating] = useState(false);
  const [impersonatorName, setImpersonatorName] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<Record<string, boolean> | null>(null);
  const [adminTabs, setAdminTabs] = useState<string[]>([]);
  const [canReviewAccess, setCanReviewAccess] = useState(false);
  const [pendingAccessCount, setPendingAccessCount] = useState(0);

  /**
   * Fetch the effective user's permissions (persona capabilities, impersonation
   * state, access-review queue). On failure, reset everything to the most
   * restrictive values - the UI must never assume access when this call fails.
   */
  async function loadPermissions() {
    try {
      const p = await api.get<any>("/api/auth/me/permissions");
      setImpersonating(!!p.impersonating);
      setImpersonatorName(p.impersonator_name ?? null);
      setCapabilities(p.capabilities ?? null);
      setCustomRoleLabels(p.persona_labels);
      setAdminTabs(p.admin_tabs ?? []);
      setCanReviewAccess(!!p.can_review_access);
      setPendingAccessCount(p.pending_access_count ?? 0);
    } catch {
      setImpersonating(false);
      setImpersonatorName(null);
      setCapabilities(null);
      setAdminTabs([]);
      setCanReviewAccess(false);
      setPendingAccessCount(0);
    }
  }

  /**
   * Re-read the current session and its permissions. A 401 means the session is
   * gone (expired/logged out elsewhere), so clear the user; other errors are
   * left transient and the previous state is kept.
   */
  async function refresh() {
    try {
      const me = await api.get<User>("/api/auth/me");
      setUser(me);
      setSessionLost(false);
      setUnreachable(false);
      await loadPermissions();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setUser(null);
      // No answer at all (or a 5xx): the server is down, not the password wrong.
      else if (e instanceof ApiError && (e.status === 0 || e.status >= 500)) setUnreachable(true);
    }
  }

  // The session ended while a page was open (expiry, logout in another tab):
  // say so above the page instead of unmounting it, so what was typed stays.
  const [sessionLost, setSessionLost] = useState(false);
  // At start-up the server did not answer: a retry screen, not the login form.
  const [unreachable, setUnreachable] = useState(false);
  useEffect(() => {
    const lost = () => setSessionLost(true);
    // Account disabled or put back on hold meanwhile: re-read it, the app then
    // shows the access screen instead of raw "access_disabled" errors.
    const changed = () => { refresh(); };
    window.addEventListener("app:session-lost", lost);
    window.addEventListener("app:access-changed", changed);
    // Another tab signed in again, or switched who is simulated: follow it.
    let bc: BroadcastChannel | null = null;
    try {
      bc = new BroadcastChannel("auth");
      bc.onmessage = (ev) => { if (ev.data === "switched") window.location.reload(); else refresh(); };
    } catch { /* old browser: each tab stays on its own */ }
    // Back on this tab after signing in elsewhere: pick the new session up.
    const onFocus = () => { if (sessionLostRef.current) refresh(); };
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("app:session-lost", lost);
      window.removeEventListener("app:access-changed", changed);
      window.removeEventListener("focus", onFocus);
      bc?.close();
    };
  }, []);
  const sessionLostRef = useRef(false);
  sessionLostRef.current = sessionLost;
  function broadcast(msg: "signed-in" | "signed-out" | "switched") {
    try { const bc = new BroadcastChannel("auth"); bc.postMessage(msg); bc.close(); } catch { /* ignore */ }
  }

  // Boot sequence: load SSO config (which buttons to show), then resolve the
  // session. `loading` flips false only once done, so guards can fail closed
  // (show a spinner) until permissions are known.
  useEffect(() => {
    (async () => {
      try {
        // The secret link's token travels to the server, which compares it and
        // answers whether the local form opens. It is never returned, so it
        // cannot be read back out of the config.
        const k = new URLSearchParams(window.location.search).get("k");
        setConfig(await api.get<AuthConfig>(`/api/auth/config${k ? `?k=${encodeURIComponent(k)}` : ""}`));
      } catch {
        /* ignore */
      }
      await refresh();
      setLoading(false);
    })();
  }, []);

  /** Local (email/password) login. Sets the session user and loads permissions. */
  async function login(email: string, password: string) {
    const u = await api.post<User>("/api/auth/login", { email, password });
    setUser(u);
    setSessionLost(false);
    await loadPermissions();
    broadcast("signed-in");
  }

  /** End the session server-side and clear the local user. */
  async function logout() {
    // Signed out here even if the network fails: the button always works.
    try { await api.post("/api/auth/logout"); } catch { /* the cookie expires anyway */ }
    finally { setUser(null); broadcast("signed-out"); }
  }

  // Impersonation changes the backend session - a full reload re-initialises the
  // whole app (config, permissions, data) as the new session user, so the
  // simulation is faithful "all the way down". Force a reload even when already
  // on "/" (assigning the same URL would otherwise be a no-op).
  function reloadHome() {
    if (window.location.pathname === "/") window.location.reload();
    else window.location.assign("/");
  }
  /** Admin action: start viewing the app as `userId`, then hard-reload as them. */
  async function impersonate(userId: number) {
    await api.post("/api/auth/impersonate", { user_id: userId });
    broadcast("switched");
    reloadHome();
  }
  /** Exit impersonation and hard-reload back as the real (admin) user. */
  async function stopImpersonation() {
    // Already stopped in another tab: this one still comes back as the admin.
    try { await api.post("/api/auth/stop-impersonation"); } catch { /* nothing left to stop */ }
    broadcast("switched");
    reloadHome();
  }

  const effectiveRole: Role | null = user ? user.role : null;
  // Fail CLOSED. `loading` stays true until loadPermissions() has run, and every
  // guarded surface renders behind <Protected>, which shows a spinner while
  // loading - so a null `capabilities` here never means "not fetched yet", it
  // means the permissions call FAILED. Granting access in that case would show
  // sections the persona is denied (the API still refuses them, but the UI must
  // not invite the click).
  const can = (cap: Capability | string) => (capabilities ? !!capabilities[cap] : false);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        config,
        effectiveRole,
        isPreview: impersonating,
        impersonating,
        impersonatorName,
        capabilities,
        adminTabs,
        canReviewAccess,
        pendingAccessCount,
        can,
        impersonate,
        stopImpersonation,
        login,
        logout,
        refresh,
      }}
    >
      {unreachable && !user ? <ServerDown onRetry={() => { setLoading(true); refresh().finally(() => setLoading(false)); }} /> : children}
      {sessionLost && user && <SessionLost />}
    </AuthContext.Provider>
  );
}

/**
 * Access the auth context. Throws if used outside {@link AuthProvider}, which
 * turns a missing-provider mistake into a clear error instead of silent nulls.
 */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Shown above the page when the session ended: sign in again in another tab
 *  (the page and what was typed stay here), then come back and save again. */
function SessionLost() {
  const { t } = useI18n();
  const next = window.location.pathname + window.location.search;
  return (
    <div className="banner banner-red session-lost" role="alert">
      <span>{t("session.lost")}</span>
      <a className="btn btn-sm" href={`/login?next=${encodeURIComponent(next)}`} target="_blank" rel="noopener">
        {t("session.relogin")}
      </a>
    </div>
  );
}

/** The server did not answer at start-up: said as such, with a retry. */
function ServerDown({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="login-wrap">
      <div className="card" style={{ maxWidth: 420, margin: "80px auto", textAlign: "center" }} role="alert">
        <h2 style={{ marginTop: 0 }}>{t("server.down_title")}</h2>
        <p className="muted">{t("server.down_text")}</p>
        <button className="btn" onClick={onRetry}>{t("common.retry")}</button>
      </div>
    </div>
  );
}
