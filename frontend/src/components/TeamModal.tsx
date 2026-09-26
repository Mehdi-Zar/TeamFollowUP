/**
 * TeamEditor / TeamModal - add, edit and remove the members of one squad.
 *
 * One editor, opened from every place where a squad's team shows up: the squad
 * page, the org chart and "Mes squads". Each field saves on blur/change and the
 * list reloads from the server afterwards. Errors are shown inside the editor:
 * a page banner sits behind the modal overlay, so a failed save used to look like
 * a click that did nothing. Server permissions (deps.can_edit_squad) stay
 * authoritative; callers only decide whether to show the button.
 *
 * A member is added by email, the key to the person's login account: an account
 * of the tribe is linked at once (the tribe's accounts are suggested while typing),
 * otherwise the server links it at the person's first sign-in (backend
 * memberlink). First and last name are optional. Each line says whether it is
 * linked, because that link is what sends the person's leaves to their squad
 * leader and the squad's reports to them.
 */
import { useEffect, useState } from "react";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { Member, SquadDetail } from "../types";
import { ErrorBanner, Modal, Spinner } from "./ui";

/** An account of the squad's tribe that can be picked (GET /api/members/candidates). */
interface Candidate { id: number; display_name: string; email: string; in_squad: boolean }

const looksLikeEmail = (v: string) => /^[^@\s]+@[^@\s]+$/.test(v.trim());
const EMPTY_ADD = { email: "", first_name: "", last_name: "", role_title: "" };

/** Member list with inline edit, "reports to" and an add row. Calls `onChange`
 *  after every successful write so the caller can refresh its own view. */
export function TeamEditor({ squadId, onChange }: { squadId: number; onChange?: () => void }) {
  const { t } = useI18n();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [add, setAdd] = useState(EMPTY_ADD);
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown) => setError(errorText(e));

  async function reload() {
    try { setMembers((await api.get<SquadDetail>(`/api/squads/${squadId}`)).members); }
    catch (e) { fail(e); }
    // Suggestions only: without them the email still works.
    api.get<Candidate[]>(`/api/members/candidates?squad_id=${squadId}`).then(setCandidates).catch(() => setCandidates([]));
  }
  useEffect(() => { reload(); }, [squadId]);

  /** True when the write went through. A field whose write failed puts its saved
   *  value back: the list reloads, but an input keeps what was typed. */
  async function run(fn: () => Promise<unknown>): Promise<boolean> {
    setError(null);
    try { await fn(); await reload(); onChange?.(); return true; } catch (e) { fail(e); return false; }
  }
  async function saveField(input: HTMLInputElement, saved: string, fn: () => Promise<unknown>) {
    if (!(await run(fn))) input.value = saved;
  }
  // The member whose removal waits for a second click.
  const [removingMember, setRemovingMember] = useState<number | null>(null);
  async function addMember(userId?: number) {
    // An email links the account; a name alone is enough for someone without one.
    const hasName = !!(add.first_name.trim() || add.last_name.trim());
    if (!userId && !looksLikeEmail(add.email) && !(hasName && !add.email.trim())) return;
    await run(async () => {
      await api.post("/api/members", {
        squad_id: squadId,
        ...(userId ? { user_id: userId } : {
          email: add.email.trim() || null,
          first_name: add.first_name.trim() || null,
          last_name: add.last_name.trim() || null,
        }),
        role_title: add.role_title.trim() || null,
      });
      setAdd(EMPTY_ADD);
    });
  }

  if (!members) return error ? <ErrorBanner message={error} /> : <Spinner />;
  // Nobody reports to themselves.
  const managerOptions = (mid: number) => members.filter((m) => m.id !== mid);
  // Accounts matching what is typed (name or email), not already in the team.
  const q = add.email.trim().toLowerCase();
  const suggestions = q.length < 2 ? [] : candidates
    .filter((c) => !c.in_squad && (c.email.toLowerCase().includes(q) || c.display_name.toLowerCase().includes(q)))
    .slice(0, 6);
  const linkState = (m: Member) =>
    m.user_id ? { cls: "badge-green", label: t("team.linked") }
      : m.email ? { cls: "badge-orange", label: t("team.pending") }
        : { cls: "badge-grey", label: t("team.no_email") };

  return (
    <div className="stack" style={{ gap: 8 }}>
      {error && <ErrorBanner message={error} />}
      <div className="small muted">{t("admin.members")} ({members.length})</div>
      {members.length === 0 && <div className="small muted">{t("squad.no_members")}</div>}
      {members.map((m) => {
        const link = linkState(m);
        return (
          <div key={m.id} className="stack" style={{ gap: 4, paddingBottom: 6, borderBottom: "1px solid var(--line)" }}>
            <div className="row" style={{ gap: 8, alignItems: "flex-end" }}>
              <div style={{ flex: 1, minWidth: 120 }}>
                <label className="small muted">{t("admin.member_name")}</label>
                <input defaultValue={m.full_name}
                       onBlur={(e) => {
                         const input = e.target, v = input.value.trim();
                         if (!v) { input.value = m.full_name; return; }  // a member keeps a name
                         if (v !== m.full_name) saveField(input, m.full_name, () => api.put(`/api/members/${m.id}`, { full_name: v }));
                       }} />
              </div>
              <div style={{ flex: 1, minWidth: 150 }}>
                <label className="small muted">{t("team.email")}</label>
                <input type="email" defaultValue={m.email ?? ""} placeholder={t("team.email_ph")}
                       onBlur={(e) => {
                         const input = e.target, v = input.value.trim().toLowerCase();
                         if (v === (m.email ?? "")) return;
                         if (v && !looksLikeEmail(v)) { input.value = m.email ?? ""; return; }
                         saveField(input, m.email ?? "", () => api.put(`/api/members/${m.id}`, { email: v || null }));
                       }} />
              </div>
              <div style={{ flex: 1, minWidth: 110 }}>
                <label className="small muted">{t("admin.member_role")}</label>
                <input defaultValue={m.role_title ?? ""}
                       onBlur={(e) => {
                         const input = e.target, v = input.value.trim();
                         if (v !== (m.role_title ?? "")) saveField(input, m.role_title ?? "", () => api.put(`/api/members/${m.id}`, { role_title: v || null }));
                       }} />
              </div>
              <div style={{ width: 130 }}>
                <label className="small muted">{t("mysquad.reports_to")}</label>
                <select className="w-auto" value={m.manager_id ?? ""}
                        onChange={(e) => run(() => api.put(`/api/members/${m.id}`, { manager_id: e.target.value ? Number(e.target.value) : null }))}>
                  <option value="">-</option>
                  {managerOptions(m.id).map((mm) => <option key={mm.id} value={mm.id}>{mm.full_name}</option>)}
                </select>
              </div>
              {removingMember === m.id ? (
                <span className="inline" style={{ gap: 4 }}>
                  <button className="btn-danger btn-sm" onClick={() => { setRemovingMember(null); run(() => api.del(`/api/members/${m.id}`)); }}>{t("action.delete")}</button>
                  <button className="btn-ghost btn-sm" onClick={() => setRemovingMember(null)}>{t("action.cancel")}</button>
                </span>
              ) : (
                <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => setRemovingMember(m.id)}>✕</button>
              )}
            </div>
            <div><span className={`badge ${link.cls}`}>{link.label}</span></div>
          </div>
        );
      })}

      <form className="stack" style={{ gap: 6, marginTop: 6, paddingTop: 4 }}
            onSubmit={(e) => { e.preventDefault(); addMember(); }}>
        <label className="small strong">{t("mysquad.add_member")}</label>
        <div className="small muted">{t("team.add_hint")}</div>
        <div className="row" style={{ gap: 8, alignItems: "flex-end" }}>
          <div style={{ flex: 2, minWidth: 180, position: "relative" }}>
            <input type="text" inputMode="email" autoComplete="off" placeholder={t("team.email_ph")}
                   aria-label={t("team.email")} value={add.email}
                   onChange={(e) => setAdd({ ...add, email: e.target.value })} />
            {suggestions.length > 0 && (
              <div className="card" style={{ position: "absolute", zIndex: 5, left: 0, right: 0, marginTop: 2, padding: 4 }}>
                <div className="small muted" style={{ padding: "2px 6px" }}>{t("team.suggestions")}</div>
                {suggestions.map((c) => (
                  <button type="button" key={c.id} className="btn-ghost btn-sm"
                          style={{ display: "block", width: "100%", textAlign: "left" }}
                          onClick={() => addMember(c.id)}>
                    {c.display_name} <span className="muted">({c.email})</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div style={{ flex: 1, minWidth: 100 }}>
            <input placeholder={t("team.first_name")} aria-label={t("team.first_name")} value={add.first_name}
                   onChange={(e) => setAdd({ ...add, first_name: e.target.value })} />
          </div>
          <div style={{ flex: 1, minWidth: 100 }}>
            <input placeholder={t("team.last_name")} aria-label={t("team.last_name")} value={add.last_name}
                   onChange={(e) => setAdd({ ...add, last_name: e.target.value })} />
          </div>
          <div style={{ flex: 1, minWidth: 110 }}>
            <input placeholder={t("admin.member_role")} aria-label={t("admin.member_role")} value={add.role_title}
                   onChange={(e) => setAdd({ ...add, role_title: e.target.value })} />
          </div>
          <button type="submit" className="btn-sm"
                  disabled={!(looksLikeEmail(add.email) || (!add.email.trim() && (add.first_name.trim() || add.last_name.trim())))}>
            {t("admin.add")}
          </button>
        </div>
      </form>
    </div>
  );
}

/** TeamEditor in a modal window, titled with the squad name. */
export function TeamModal({ squadId, squadName, onClose, onChange }: {
  squadId: number; squadName: string; onClose: () => void; onChange?: () => void;
}) {
  const { t } = useI18n();
  return (
    <Modal title={`${t("mysquad.manage_team")}${t("common.colon")}${squadName}`} onClose={onClose}
           footer={<button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}>
      <TeamEditor squadId={squadId} onChange={onChange} />
    </Modal>
  );
}
