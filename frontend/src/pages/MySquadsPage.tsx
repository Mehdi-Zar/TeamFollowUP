import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { Budget, Member, Squad, SquadDetail, Tribe, User } from "../types";
import { ErrorBanner, Spinner, Dot, Modal, EmptyState } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";
import { useModule } from "../config";
import { OtdPanel } from "../components/OtdPanel";

const RAGS: Array<"green" | "amber" | "red"> = ["green", "amber", "red"];

/** Persona-aware: squad leaders manage their squad's team; tribe leaders/admins
 *  manage KPIs + annual objectives. */
export default function MySquadsPage() {
  const { user } = useAuth();
  if (user?.role === "squad_leader") return <SquadLeaderSquads />;
  return <TribeLeaderSquads />;
}

/** Tribe-leader / admin view: KPIs on/off + annual objectives per squad. */
function TribeLeaderSquads() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [squads, setSquads] = useState<Squad[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  async function load() {
    try {
      setSquads(await api.get<Squad[]>("/api/squads"));
      setUsers(await api.get<User[]>("/api/admin/users"));
      const tr = await api.get<Tribe[]>("/api/tribes");
      setTribes(isAdmin ? tr : tr.filter((x) => x.id === user?.tribe_id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  }
  useEffect(() => { load(); }, []);

  const leaders = users.filter((u) => ["squad_leader", "tribe_leader", "admin"].includes(u.role));

  useSetPageChrome(
    { title: t("mysquads.title"), actions: <button className="btn btn-sm" onClick={() => setCreating(true)}>+ {t("mysquads.new")}</button> },
    [t]
  );

  if (error && !squads) return <ErrorBanner message={error} />;
  if (!squads) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {error && <ErrorBanner message={error} />}
      <div className="muted small">{t("mysquads.intro")}</div>

      {squads.length === 0 && <EmptyState message={t("mysquads.empty")} />}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
        {squads.map((s) => (
          <SquadCard key={s.id} squadId={s.id} leaders={leaders} onChanged={load} onError={setError} />
        ))}
      </div>

      {creating && (
        <CreateSquadModal
          isAdmin={isAdmin}
          tribes={tribes}
          leaders={leaders}
          defaultTribeId={user?.tribe_id ?? null}
          onClose={() => setCreating(false)}
          onCreated={() => { setCreating(false); load(); }}
          onError={setError}
        />
      )}
    </div>
  );
}

function SquadCard({ squadId, leaders, onChanged, onError }: {
  squadId: number; leaders: User[]; onChanged: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const [d, setD] = useState<SquadDetail | null>(null);
  const [edit, setEdit] = useState(false);

  async function load() {
    try { setD(await api.get<SquadDetail>(`/api/squads/${squadId}`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  useEffect(() => { load(); }, [squadId]);
  const kpisOn = useModule()("squad_content", "kpis");
  if (!d) return <div className="card spinner">{t("common.loading")}</div>;

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div className="strong" style={{ fontSize: 16 }}>{d.name}</div>
        <button className="btn-secondary btn-sm" onClick={() => setEdit(true)}>✎ {t("action.edit")}</button>
      </div>

      <div className="small muted">{t("squad.squad_leader")} : <span className="strong">{d.leader?.display_name || "-"}</span></div>

      <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
        {kpisOn && (
          <span className={`badge ${d.kpis_enabled ? "badge-green" : "badge-grey"}`}>
            {d.kpis_enabled ? t("mysquads.kpis_on") : t("mysquads.kpis_off")}
          </span>
        )}
        {d.budget_enabled && <span className="badge badge-navy">{t("budget.title")}</span>}
      </div>

      {edit && (
        <EditSquadModal
          detail={d}
          leaders={leaders}
          onClose={() => { setEdit(false); load(); onChanged(); }}
          onError={onError}
        />
      )}
    </div>
  );
}

function EditSquadModal({ detail, leaders, onClose, onError }: {
  detail: SquadDetail; leaders: User[]; onClose: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const kpisOn = useModule()("squad_content", "kpis");
  const [d, setD] = useState<SquadDetail>(detail);
  const [step, setStep] = useState(0);

  async function reload() {
    try { setD(await api.get<SquadDetail>(`/api/squads/${detail.id}`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  async function run(fn: () => Promise<any>) {
    try { await fn(); await reload(); } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  const patch = (p: any) => run(() => api.put(`/api/squads/${d.id}`, p));

  // One clean step at a time instead of one crowded form. The OTD is the squad's
  // single dated annual commitment (there is no separate "objective" concept).
  const steps = [
    t("mysquads.step.infos"),
    t("mysquads.step.otd"),
    t("mysquads.step.budget"),
  ];
  const last = steps.length - 1;

  return (
    <Modal
      width={680}
      title={`${t("action.edit")} - ${d.name}`}
      onClose={onClose}
      footer={
        <div className="between" style={{ width: "100%", alignItems: "center" }}>
          <button className="btn-danger btn-sm" onClick={() => { if (confirm(t("mysquads.del_confirm"))) run(async () => { await api.del(`/api/squads/${d.id}`); onClose(); }); }}>
            {t("action.delete")}
          </button>
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-secondary btn-sm" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>‹ {t("common.prev")}</button>
            {step < last
              ? <button className="btn-sm" onClick={() => setStep((s) => Math.min(last, s + 1))}>{t("common.next")} ›</button>
              : <button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}
          </div>
        </div>
      }
    >
      {/* Step chips: shows where you are and lets you jump. */}
      <div className="inline" style={{ gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {steps.map((label, i) => (
          <button key={i} onClick={() => setStep(i)}
            className={`badge ${i === step ? "badge-navy" : "badge-grey"}`}
            style={{ cursor: "pointer", border: 0 }}>
            {i + 1}. {label}
          </button>
        ))}
      </div>

      {/* Step 1 - Infos */}
      {step === 0 && (
        <div className="stack" style={{ gap: 14 }}>
          <div className="row" style={{ gap: 12 }}>
            <div style={{ flex: 1, minWidth: 180 }}>
              <label>{t("admin.name")}</label>
              <input defaultValue={d.name} onBlur={(e) => e.target.value !== d.name && patch({ name: e.target.value })} />
            </div>
            <div style={{ flex: 1, minWidth: 160 }}>
              <label>{t("admin.responsible")}</label>
              <select value={d.leader_user_id ?? ""} onChange={(e) => patch({ leader_user_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">-</option>
                {leaders.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
              </select>
            </div>
            <div style={{ flex: 1, minWidth: 160 }}>
              <label>{t("squad.type")}</label>
              <SquadTypeField value={d.squad_type ?? "product"} onChange={(v) => patch({ squad_type: v })} t={t} />
            </div>
          </div>
          <div className="row" style={{ gap: 12 }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label>{t("squad.products")}</label>
              <TagListEditor value={d.products ?? []} placeholder={t("squad.products_ph")}
                             onChange={(v) => patch({ products: v })} />
            </div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label>{t("squad.hardware")}</label>
              <TagListEditor value={d.hardware ?? []} placeholder={t("squad.hardware_ph")}
                             onChange={(v) => patch({ hardware: v })} />
            </div>
          </div>
        </div>
      )}

      {/* Step 2 - OTD (On-Time Delivery): the squad's single dated annual commitment */}
      {step === 1 && (
        <OtdPanel squad={d} canManage onChange={reload} />
      )}

      {/* Step 3 - Budget & KPIs */}
      {step === 2 && (
        <div className="stack" style={{ gap: 14 }}>
          {kpisOn && (
            <label className="switch">
              <input type="checkbox" checked={!!d.kpis_enabled} onChange={(e) => patch({ kpis_enabled: e.target.checked })} />
              <span className="track"><span className="knob" /></span>
              <span className="small">{t("admin.kpis_enabled")}</span>
            </label>
          )}
          <div className="stack" style={{ gap: 6 }}>
            <div className="small strong">{t("budget.title")}</div>
            <BudgetEditor
              squadId={d.id} year={d.year}
              enabled={!!d.budget_enabled} budget={d.budget}
              canToggle onToggle={(v) => patch({ budget_enabled: v })}
              onError={onError}
            />
          </div>
        </div>
      )}
    </Modal>
  );
}

function CreateSquadModal({ isAdmin, tribes, leaders, defaultTribeId, onClose, onCreated, onError }: {
  isAdmin: boolean; tribes: Tribe[]; leaders: User[]; defaultTribeId: number | null;
  onClose: () => void; onCreated: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState<{ name: string; leader_user_id: string; tribe_id: string; products: string[]; hardware: string[] }>(
    { name: "", leader_user_id: "", tribe_id: isAdmin ? "" : String(defaultTribeId ?? ""), products: [], hardware: [] });

  async function create() {
    try {
      await api.post("/api/squads", {
        name: form.name.trim(),
        tribe_id: form.tribe_id ? Number(form.tribe_id) : (isAdmin ? null : defaultTribeId),
        leader_user_id: form.leader_user_id ? Number(form.leader_user_id) : null,
        products: form.products,
        hardware: form.hardware,
      });
      onCreated();
    } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }

  return (
    <Modal
      title={t("mysquads.new")}
      onClose={onClose}
      footer={
        <>
          <button className="btn-secondary btn-sm" onClick={onClose}>{t("action.cancel")}</button>
          <button className="btn-sm" onClick={create} disabled={!form.name.trim() || (isAdmin && !form.tribe_id)}>{t("admin.create")}</button>
        </>
      }
    >
      <div className="stack" style={{ gap: 12 }}>
        <div>
          <label>{t("admin.name")}</label>
          <input autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        {isAdmin && (
          <div>
            <label>{t("admin.tribe")}</label>
            <select value={form.tribe_id} onChange={(e) => setForm({ ...form, tribe_id: e.target.value })}>
              <option value="">-</option>
              {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
            </select>
          </div>
        )}
        <div>
          <label>{t("admin.responsible")}</label>
          <select value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
            <option value="">-</option>
            {leaders.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
        </div>
        <div>
          <label>{t("squad.products")}</label>
          <TagListEditor value={form.products} placeholder={t("squad.products_ph")}
                         onChange={(v) => setForm({ ...form, products: v })} />
        </div>
        <div>
          <label>{t("squad.hardware")}</label>
          <TagListEditor value={form.hardware} placeholder={t("squad.hardware_ph")}
                         onChange={(v) => setForm({ ...form, hardware: v })} />
        </div>
      </div>
    </Modal>
  );
}

/* ----------------------------- Squad-leader view ----------------------------- */

/** Squad-leader view: manage the team (members) of the squads they lead. */
function SquadLeaderSquads() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [squads, setSquads] = useState<Squad[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const all = await api.get<Squad[]>("/api/squads");
      setSquads(all.filter((s) => s.leader_user_id === user?.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  }
  useEffect(() => { load(); }, []);
  useSetPageChrome({ title: t("mysquad.title") }, [t]);

  if (error && !squads) return <ErrorBanner message={error} />;
  if (!squads) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {error && <ErrorBanner message={error} />}
      <div className="muted small">{t("mysquad.intro")}</div>
      {squads.length === 0 && <div className="card muted">{t("mysquad.empty")}</div>}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
        {squads.map((s) => <SLSquadCard key={s.id} squadId={s.id} onError={setError} />)}
      </div>
    </div>
  );
}

function SLSquadCard({ squadId, onError }: { squadId: number; onError: (m: string) => void }) {
  const { t } = useI18n();
  const [d, setD] = useState<SquadDetail | null>(null);
  const [open, setOpen] = useState(false);

  async function load() {
    try { setD(await api.get<SquadDetail>(`/api/squads/${squadId}`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  useEffect(() => { load(); }, [squadId]);
  if (!d) return <div className="card spinner">{t("common.loading")}</div>;

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div className="strong" style={{ fontSize: 16 }}>{d.name}</div>
        <button className="btn-secondary btn-sm" onClick={() => setOpen(true)}>✎ {t("mysquad.manage_team")}</button>
      </div>
      <span className="badge badge-navy">{t("squad.team_collapsed_hint", { n: d.members.length }).split(" - ")[0]}</span>
      {d.members.length === 0 && <div className="small muted">{t("squad.no_members")}</div>}
      <div className="stack" style={{ gap: 4 }}>
        {d.members.slice(0, 5).map((m) => (
          <div key={m.id} className="inline small" style={{ gap: 6 }}>
            <span className="strong">{m.full_name}</span>
            {m.role_title && <span className="muted">· {m.role_title}</span>}
          </div>
        ))}
        {d.members.length > 5 && <div className="small muted">+{d.members.length - 5}…</div>}
      </div>

      {open && <TeamModal detail={d} onClose={() => { setOpen(false); load(); }} onError={onError} />}
    </div>
  );
}

function TeamModal({ detail, onClose, onError }: { detail: SquadDetail; onClose: () => void; onError: (m: string) => void }) {
  const { t } = useI18n();
  const [members, setMembers] = useState<Member[]>(detail.members);
  const [name, setName] = useState(detail.name);
  const [add, setAdd] = useState({ full_name: "", role_title: "" });

  async function reload() {
    try {
      const sd = await api.get<SquadDetail>(`/api/squads/${detail.id}`);
      setMembers(sd.members);
    } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  async function run(fn: () => Promise<any>) {
    try { await fn(); await reload(); } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  const managerOptions = (mid: number) => members.filter((m) => m.id !== mid);

  return (
    <Modal
      title={`${t("mysquad.manage_team")} - ${detail.name}`}
      onClose={onClose}
      footer={<button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}
    >
      <div className="stack" style={{ gap: 14 }}>
        <div>
          <label>{t("admin.squad")}</label>
          <input defaultValue={name} onBlur={(e) => { if (e.target.value !== name) { setName(e.target.value); run(() => api.put(`/api/squads/${detail.id}`, { name: e.target.value })); } }} />
        </div>

        <div className="stack" style={{ gap: 6, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <div className="small strong">{t("budget.title")}</div>
          <BudgetEditor
            squadId={detail.id} year={detail.year}
            enabled={!!detail.budget_enabled} budget={detail.budget}
            canToggle={false} onToggle={() => {}}
            onError={onError}
          />
        </div>

        <div>
          <div className="small muted" style={{ marginBottom: 6 }}>{t("admin.members")} ({members.length})</div>
          {members.length === 0 && <div className="small muted">{t("squad.no_members")}</div>}
          <div className="stack" style={{ gap: 8 }}>
            {members.map((m) => (
              <div key={m.id} className="row" style={{ gap: 8, alignItems: "flex-end" }}>
                <div style={{ flex: 1, minWidth: 120 }}>
                  <label className="small muted">{t("admin.member_name")}</label>
                  <input defaultValue={m.full_name} onBlur={(e) => e.target.value !== m.full_name && run(() => api.put(`/api/members/${m.id}`, { full_name: e.target.value }))} />
                </div>
                <div style={{ flex: 1, minWidth: 110 }}>
                  <label className="small muted">{t("admin.member_role")}</label>
                  <input defaultValue={m.role_title ?? ""} onBlur={(e) => e.target.value !== (m.role_title ?? "") && run(() => api.put(`/api/members/${m.id}`, { role_title: e.target.value }))} />
                </div>
                <div style={{ width: 130 }}>
                  <label className="small muted">{t("mysquad.reports_to")}</label>
                  <select className="w-auto" value={m.manager_id ?? ""} onChange={(e) => run(() => api.put(`/api/members/${m.id}`, { manager_id: e.target.value ? Number(e.target.value) : null }))}>
                    <option value="">-</option>
                    {managerOptions(m.id).map((mm) => <option key={mm.id} value={mm.id}>{mm.full_name}</option>)}
                  </select>
                </div>
                <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => run(() => api.del(`/api/members/${m.id}`))}>✕</button>
              </div>
            ))}
          </div>

          <div className="row" style={{ gap: 8, alignItems: "flex-end", marginTop: 10, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <div style={{ flex: 1, minWidth: 120 }}>
              <label className="small">{t("mysquad.add_member")}</label>
              <input placeholder={t("admin.member_name")} value={add.full_name} onChange={(e) => setAdd({ ...add, full_name: e.target.value })} />
            </div>
            <div style={{ flex: 1, minWidth: 110 }}>
              <input placeholder={t("admin.member_role")} value={add.role_title} onChange={(e) => setAdd({ ...add, role_title: e.target.value })} />
            </div>
            <button className="btn-sm" disabled={!add.full_name.trim()}
                    onClick={() => run(async () => { await api.post("/api/members", { squad_id: detail.id, full_name: add.full_name.trim(), role_title: add.role_title.trim() || null }); setAdd({ full_name: "", role_title: "" }); })}>
              {t("admin.add")}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

/** Budget management, reusable in Manage-my-squads. Tribe leaders/admins can
 *  toggle tracking on/off (canToggle); the squad leader fills total/spent.
 *  Saves on blur and keeps its own readout from the API response. */
const BUDGET_BADGE: Record<string, string> = { on_track: "badge-green", at_risk: "badge-orange", over: "badge-red" };

function BudgetEditor({ squadId, year, enabled, budget, canToggle, onToggle, onError }: {
  squadId: number; year: number; enabled: boolean; budget?: Budget | null;
  canToggle: boolean; onToggle: (v: boolean) => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const [b, setB] = useState<Budget | null | undefined>(budget);
  const [total, setTotal] = useState(budget?.total != null ? String(budget.total) : "");
  const [spent, setSpent] = useState(budget?.spent != null ? String(budget.spent) : "");
  const [forecast, setForecast] = useState(budget?.forecast != null ? String(budget.forecast) : "");
  const [comment, setComment] = useState(budget?.comment ?? "");
  const fmt = (n?: number | null) => (n == null ? "-" : `${n.toLocaleString()} €`);

  // canToggle == tribe leader / admin: they own the envelope (total). A squad
  // leader only reports spent / forecast / comment, and sees total read-only.
  const save = async () => {
    try {
      const res = await api.put<Budget>(`/api/squads/${squadId}/budget?year=${year}`, {
        total: total === "" ? null : Number(total),   // ignored server-side unless tribe/admin
        spent: spent === "" ? null : Number(spent),
        forecast: forecast === "" ? null : Number(forecast),
        comment: comment.trim() || null,
      });
      setB(res);
    } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  };

  return (
    <div className="stack" style={{ gap: 8 }}>
      {canToggle && (
        <label className="switch">
          <input type="checkbox" checked={enabled} onChange={(e) => onToggle(e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="small">{t("budget.enable_label")}</span>
        </label>
      )}
      {enabled ? (
        <>
          <div className="small muted">{t("budget.hint")}</div>
          <div className="row" style={{ gap: 8 }}>
            <div style={{ flex: 1, minWidth: 100 }}>
              <label className="small muted">{t("budget.total")}</label>
              {canToggle
                ? <input type="number" value={total} onChange={(e) => setTotal(e.target.value)} onBlur={save} />
                : <input type="number" value={total} disabled title={t("budget.total_locked")} />}
            </div>
            <div style={{ flex: 1, minWidth: 100 }}>
              <label className="small muted" title={t("budget.spent_hint")}>{t("budget.spent")}</label>
              <input type="number" value={spent} onChange={(e) => setSpent(e.target.value)} onBlur={save} />
            </div>
            <div style={{ flex: 1, minWidth: 100 }}>
              <label className="small muted" title={t("budget.forecast_hint")}>{t("budget.forecast")}</label>
              <input type="number" value={forecast} onChange={(e) => setForecast(e.target.value)} onBlur={save} />
            </div>
          </div>
          <label className="small muted">{t("budget.comment")}
            <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} onBlur={save} />
          </label>
          {b && (b.total != null && (b.spent != null || b.forecast != null)) && (
            <span className={`badge ${BUDGET_BADGE[b.status] ?? "badge-grey"}`}>
              {t(`budget.status.${b.status}`)}
              {b.status === "over" && ` ${t("budget.overrun_val", { amount: fmt(b.overrun), pct: b.overrun_pct })}`}
            </span>
          )}
        </>
      ) : (
        !canToggle && <div className="small muted">{t("budget.disabled")}</div>
      )}
    </div>
  );
}

/** Edit a list of names (products / hardware) as removable chips + an add input. */
function TagListEditor({ value, onChange, placeholder }: {
  value: string[]; onChange: (v: string[]) => void; placeholder?: string;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const add = () => {
    const v = text.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setText("");
  };
  return (
    <div className="stack" style={{ gap: 6 }}>
      {value.length > 0 && (
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          {value.map((p) => (
            <span key={p} className="badge badge-navy" style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
              {p}
              <button className="btn-ghost btn-sm" style={{ padding: "0 3px", lineHeight: 1 }}
                      aria-label={t("action.delete")} onClick={() => onChange(value.filter((x) => x !== p))}>×</button>
            </span>
          ))}
        </div>
      )}
      <div className="inline" style={{ gap: 6 }}>
        <input style={{ flex: 1 }} value={text} placeholder={placeholder}
               onChange={(e) => setText(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }} />
        <button className="btn-secondary btn-sm" onClick={add} disabled={!text.trim()}>{t("action.add")}</button>
      </div>
    </div>
  );
}

const KNOWN_SQUAD_TYPES = ["product", "transverse"];

/** Squad type picker: the built-in types, plus a "custom…" option that lets you
 *  define a new type key - the model is open-ended (future-proofing). */
function SquadTypeField({ value, onChange, t }: { value: string; onChange: (v: string) => void; t: any }) {
  const [custom, setCustom] = useState(!!value && !KNOWN_SQUAD_TYPES.includes(value));
  return (
    <div className="stack" style={{ gap: 6 }}>
      <select
        value={custom ? "__custom" : value || "product"}
        onChange={(e) => {
          if (e.target.value === "__custom") setCustom(true);
          else { setCustom(false); onChange(e.target.value); }
        }}
      >
        <option value="product">{t("squad.type_product")}</option>
        <option value="transverse">{t("squad.type_transverse")}</option>
        <option value="__custom">{t("squad.type_custom")}</option>
      </select>
      {custom && (
        <input
          autoFocus
          defaultValue={KNOWN_SQUAD_TYPES.includes(value) ? "" : value}
          placeholder={t("squad.type_custom_ph")}
          onBlur={(e) => { const v = e.target.value.trim(); if (v) onChange(v); }}
        />
      )}
    </div>
  );
}
