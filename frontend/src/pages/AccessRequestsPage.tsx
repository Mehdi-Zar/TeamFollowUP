// AccessRequestsPage - approval queue for pending (typically SSO-provisioned)
// accounts. An approver assigns a role and the appropriate tribe/squad, or denies
// the request. The set of grantable roles/tribes/squads and whether denial is
// allowed all come from the backend, which enforces the same scope server-side.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { AccessOptions, AccessRequest, Role } from "../types";
import { Spinner, ErrorBanner, EmptyState } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";

/**
 * Manager queue to validate SSO-provisioned accounts. Each approver only sees the
 * roles / squads / tribes they may grant (the backend enforces the same scope).
 *
 * Business logic:
 * - Guarded by `canReviewAccess`: users without it get an "not allowed" state and
 *   no fetch is made.
 * - Loads `/api/access-requests`, which returns both the pending requests and the
 *   grantable options (roles/tribes/squads, whether deny is permitted).
 * - `act()` wraps every approve/deny call: it shows a result message, reloads the
 *   queue, and refreshes auth (the approver's own scope may have changed).
 *
 * Access: reviewers only (managers / leaders with the access-review capability).
 */
export default function AccessRequestsPage() {
  const { t, role: roleLabel } = useI18n();
  const { canReviewAccess, refresh } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<AccessOptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useSetPageChrome({ title: t("access.title") }, [t]);

  async function load() {
    try { setData(await api.get<AccessOptions>("/api/access-requests")); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  useEffect(() => { if (canReviewAccess) load(); }, [canReviewAccess]);

  if (!canReviewAccess) return <EmptyState message={t("access.not_allowed")} />;
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Spinner />;

  // Run an approve/deny mutation, then reflect the result and re-sync state.
  // refresh() re-pulls auth because approving may alter the approver's own scope.
  async function act(fn: () => Promise<unknown>, okKey: string) {
    setMsg(null);
    try { await fn(); setMsg(t(okKey)); await load(); await refresh(); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : "Erreur"); }
  }

  return (
    <div className="stack" style={{ gap: 16, maxWidth: 900 }}>
      <div className="banner">{t("access.intro")}</div>
      {msg && <div className="small muted">{msg}</div>}
      {data.requests.length === 0 ? (
        <EmptyState message={t("access.none")} />
      ) : (
        <div className="stack" style={{ gap: 12 }}>
          {data.requests.map((r) => (
            <RequestRow key={r.id} req={r} opts={data} roleLabel={roleLabel} t={t}
              onApprove={(body) => act(() => api.post(`/api/access-requests/${r.id}/approve`, body), "access.approved")}
              onDeny={() => act(() => api.post(`/api/access-requests/${r.id}/deny`, {}), "access.denied")} />
          ))}
        </div>
      )}
      <button className="btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => navigate("/")}>← {t("action.close")}</button>
    </div>
  );
}

/**
 * One pending request card with inline role / tribe / squad selectors and the
 * approve (and optionally deny) actions.
 *
 * Field visibility is driven by the approver's granted `opts`:
 * - Tribe selector appears only when the approver isn't locked to a single tribe.
 * - Squad selector appears whenever squads are offered; it becomes *required*
 *   when a squad leader (no deny right, tribe locked) must place the person into
 *   one of their own squads - the Approve button stays disabled until chosen.
 *
 * @param req       the account awaiting validation (name, email, SSO flag)
 * @param opts      grantable roles/tribes/squads and permission flags
 * @param onApprove approve with the chosen role and optional tribe/squad ids
 * @param onDeny    reject the request (only rendered when `opts.can_deny`)
 */
function RequestRow({ req, opts, roleLabel, t, onApprove, onDeny }: {
  req: AccessRequest; opts: AccessOptions; roleLabel: (r: Role) => string; t: (k: string) => string;
  onApprove: (body: { role: Role; tribe_id?: number | null; squad_id?: number | null }) => void;
  onDeny: () => void;
}) {
  const [role, setRole] = useState<Role>(opts.roles[0]);
  const [tribeId, setTribeId] = useState<number | "">(opts.tribes[0]?.id ?? "");
  const [squadId, setSquadId] = useState<number | "">("");
  // A squad leader must place the person into one of their squads.
  const squadRequired = !opts.can_deny && opts.tribe_locked && opts.squads.length > 0;

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between" style={{ alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <div>
          <div className="strong">{req.display_name}</div>
          <div className="small muted">{req.email}{req.auth_subject ? " · SSO" : ""}</div>
        </div>
        <span className="badge">{t("access.proposed")}: {roleLabel(req.role)}</span>
      </div>

      <div className="inline" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div>
          <label>{t("access.role")}</label>
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {opts.roles.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
          </select>
        </div>
        {!opts.tribe_locked && opts.tribes.length > 0 && (
          <div>
            <label>{t("access.tribe")}</label>
            <select value={tribeId} onChange={(e) => setTribeId(e.target.value ? Number(e.target.value) : "")}>
              {opts.tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
            </select>
          </div>
        )}
        {opts.squads.length > 0 && (
          <div>
            <label>{t("access.squad")}{squadRequired ? " *" : ""}</label>
            <select value={squadId} onChange={(e) => setSquadId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">{squadRequired ? t("access.choose_squad") : "-"}</option>
              {opts.squads.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
        )}
        <button className="btn" disabled={squadRequired && !squadId}
          onClick={() => onApprove({ role, tribe_id: tribeId === "" ? null : tribeId, squad_id: squadId === "" ? null : squadId })}>
          {t("access.approve")}
        </button>
        {opts.can_deny && <button className="btn-secondary" onClick={onDeny}>{t("access.deny")}</button>}
      </div>
    </div>
  );
}
