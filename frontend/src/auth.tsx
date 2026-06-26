import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, ApiError } from "./api";
import { AuthConfig, Capability, Role, User } from "./types";

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
  can: (cap: Capability | string) => boolean;
  impersonate: (userId: number) => Promise<void>;
  stopImpersonation: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<AuthConfig>({ oidc_enabled: false, saml_enabled: false });
  const [impersonating, setImpersonating] = useState(false);
  const [impersonatorName, setImpersonatorName] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<Record<string, boolean> | null>(null);

  async function loadPermissions() {
    try {
      const p = await api.get<any>("/api/auth/me/permissions");
      setImpersonating(!!p.impersonating);
      setImpersonatorName(p.impersonator_name ?? null);
      setCapabilities(p.capabilities ?? null);
    } catch {
      setImpersonating(false);
      setImpersonatorName(null);
      setCapabilities(null);
    }
  }

  async function refresh() {
    try {
      const me = await api.get<User>("/api/auth/me");
      setUser(me);
      await loadPermissions();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setUser(null);
    }
  }

  useEffect(() => {
    (async () => {
      try {
        setConfig(await api.get<AuthConfig>("/api/auth/config"));
      } catch {
        /* ignore */
      }
      await refresh();
      setLoading(false);
    })();
  }, []);

  async function login(email: string, password: string) {
    const u = await api.post<User>("/api/auth/login", { email, password });
    setUser(u);
    await loadPermissions();
  }

  async function logout() {
    await api.post("/api/auth/logout");
    setUser(null);
  }

  // Impersonation changes the backend session - a full reload re-initialises the
  // whole app (config, permissions, data) as the new session user, so the
  // simulation is faithful "all the way down". Force a reload even when already
  // on "/" (assigning the same URL would otherwise be a no-op).
  function reloadHome() {
    if (window.location.pathname === "/") window.location.reload();
    else window.location.assign("/");
  }
  async function impersonate(userId: number) {
    await api.post("/api/auth/impersonate", { user_id: userId });
    reloadHome();
  }
  async function stopImpersonation() {
    await api.post("/api/auth/stop-impersonation");
    reloadHome();
  }

  const effectiveRole: Role | null = user ? user.role : null;
  // Optimistic before load (avoid hiding the whole nav on first paint).
  const can = (cap: Capability | string) => (capabilities ? !!capabilities[cap] : true);

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
        can,
        impersonate,
        stopImpersonation,
        login,
        logout,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
