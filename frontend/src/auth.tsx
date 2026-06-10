import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, ApiError } from "./api";
import { AuthConfig, Role, User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  config: AuthConfig;
  /** The role the UI renders for. Equals the real role unless an admin previews a persona. */
  effectiveRole: Role | null;
  previewRole: Role | null;
  isPreview: boolean;
  setPreviewRole: (r: Role | null) => void;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<AuthConfig>({ oidc_enabled: false, saml_enabled: false });
  const [previewRole, setPreviewRole] = useState<Role | null>(null);

  async function refresh() {
    try {
      const me = await api.get<User>("/api/auth/me");
      setUser(me);
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
    setPreviewRole(null);
  }

  async function logout() {
    await api.post("/api/auth/logout");
    setUser(null);
    setPreviewRole(null);
  }

  // Only a real admin may preview another persona.
  const canPreview = user?.role === "admin";
  const effectivePreview = canPreview ? previewRole : null;
  const effectiveRole: Role | null = user ? (effectivePreview ?? user.role) : null;

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        config,
        effectiveRole,
        previewRole: effectivePreview,
        isPreview: effectivePreview !== null,
        setPreviewRole: (r) => setPreviewRole(r),
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
