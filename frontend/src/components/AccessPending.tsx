import { useAuth } from "../auth";
import { useI18n } from "../i18n";

/** Shown to an authenticated-but-not-validated account. SSO proved who they are;
 *  a manager must still grant access. Disabled accounts see the revoked variant. */
export default function AccessPending() {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const disabled = user?.status === "disabled";

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div className="card stack" style={{ gap: 14, maxWidth: 460, textAlign: "center", padding: 28 }}>
        <h2 style={{ margin: 0 }}>{t(disabled ? "access.revoked_title" : "access.pending_title")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {t(disabled ? "access.revoked_body" : "access.pending_body")}
        </p>
        {user && (
          <div className="small muted">
            {t("access.signed_in_as")} <span className="strong">{user.email}</span>
          </div>
        )}
        <div className="inline" style={{ justifyContent: "center", marginTop: 4 }}>
          <button className="btn-secondary" onClick={() => logout()}>{t("action.logout")}</button>
        </div>
      </div>
    </div>
  );
}
