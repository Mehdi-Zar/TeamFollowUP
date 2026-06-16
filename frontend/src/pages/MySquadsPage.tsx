import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { Member, Squad, SquadDetail, Tribe, User } from "../types";
import { ErrorBanner, Spinner, Dot, Modal } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";

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

      {squads.length === 0 && <div className="card muted">{t("mysquads.empty")}</div>}
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

function ragCounts(objs: { rag_status: string }[]) {
  return { green: objs.filter((o) => o.rag_status === "green").length,
           amber: objs.filter((o) => o.rag_status === "amber").length,
           red: objs.filter((o) => o.rag_status === "red").length };
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
  if (!d) return <div className="card spinner">{t("common.loading")}</div>;

  const counts = ragCounts(d.objectives);

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div className="strong" style={{ fontSize: 16 }}>{d.name}</div>
        <button className="btn-secondary btn-sm" onClick={() => setEdit(true)}>✎ {t("action.edit")}</button>
      </div>

      <div className="small muted">{t("squad.squad_leader")} : <span className="strong">{d.leader?.display_name || "—"}</span></div>

      <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
        <span className={`badge ${d.kpis_enabled ? "badge-green" : "badge-grey"}`}>
          {d.kpis_enabled ? t("mysquads.kpis_on") : t("mysquads.kpis_off")}
        </span>
        <span className="badge badge-navy">{t("mysquads.n_objectives", { n: d.objectives.length })}</span>
        {counts.red > 0 && <span className="inline small" style={{ gap: 3 }}><Dot status="red" />{counts.red}</span>}
        {counts.amber > 0 && <span className="inline small" style={{ gap: 3 }}><Dot status="amber" />{counts.amber}</span>}
        {counts.green > 0 && <span className="inline small" style={{ gap: 3 }}><Dot status="green" />{counts.green}</span>}
      </div>

      {d.objectives.length > 0 && (
        <div className="stack" style={{ gap: 4 }}>
          {d.objectives.slice(0, 3).map((o) => (
            <div key={o.id} className="inline small" style={{ gap: 6 }}>
              <Dot status={o.rag_status} /><span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{o.title}</span>
            </div>
          ))}
          {d.objectives.length > 3 && <div className="small muted">+{d.objectives.length - 3}…</div>}
        </div>
      )}

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
  const { t, rag } = useI18n();
  const [d, setD] = useState<SquadDetail>(detail);
  const [newObj, setNewObj] = useState("");

  async function reload() {
    try { setD(await api.get<SquadDetail>(`/api/squads/${detail.id}`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  async function run(fn: () => Promise<any>) {
    try { await fn(); await reload(); } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  const patch = (p: any) => run(() => api.put(`/api/squads/${d.id}`, p));
  const addObj = () => { if (newObj.trim()) run(async () => { await api.post("/api/objectives", { squad_id: d.id, year: d.year, title: newObj.trim(), rag_status: "green" }); setNewObj(""); }); };

  return (
    <Modal
      title={`${t("action.edit")} — ${d.name}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn-danger btn-sm" onClick={() => { if (confirm(t("mysquads.del_confirm"))) run(async () => { await api.del(`/api/squads/${d.id}`); onClose(); }); }}>
            {t("action.delete")}
          </button>
          <button className="btn-sm" onClick={onClose}>{t("action.close")}</button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <div className="row" style={{ gap: 12 }}>
          <div style={{ flex: 1, minWidth: 180 }}>
            <label>{t("admin.name")}</label>
            <input defaultValue={d.name} onBlur={(e) => e.target.value !== d.name && patch({ name: e.target.value })} />
          </div>
          <div style={{ flex: 1, minWidth: 160 }}>
            <label>{t("admin.responsible")}</label>
            <select value={d.leader_user_id ?? ""} onChange={(e) => patch({ leader_user_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">—</option>
              {leaders.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
            </select>
          </div>
        </div>

        <label className="switch">
          <input type="checkbox" checked={!!d.kpis_enabled} onChange={(e) => patch({ kpis_enabled: e.target.checked })} />
          <span className="track"><span className="knob" /></span>
          <span className="small">{t("admin.kpis_enabled")}</span>
        </label>

        <div>
          <div className="small muted" style={{ marginBottom: 6 }}>
            {t("squad.objectives", { year: d.year })} — {t("admin.objectives_hint")}
          </div>
          {d.objectives.length === 0 && <div className="small muted">{t("squad.no_obj")}</div>}
          {d.objectives.map((o) => (
            <div key={o.id} className="item-row" style={{ gap: 8 }}>
              <Dot status={o.rag_status} />
              <input style={{ flex: 1 }} defaultValue={o.title} onBlur={(e) => e.target.value !== o.title && run(() => api.put(`/api/objectives/${o.id}`, { title: e.target.value }))} />
              <select className="w-auto" value={o.rag_status} onChange={(e) => run(() => api.put(`/api/objectives/${o.id}`, { rag_status: e.target.value }))}>
                {RAGS.map((r) => <option key={r} value={r}>{rag(r)}</option>)}
              </select>
              <button className="btn-ghost btn-sm" onClick={() => run(() => api.del(`/api/objectives/${o.id}`))}>✕</button>
            </div>
          ))}
          <div className="inline" style={{ gap: 8, marginTop: 8 }}>
            <input style={{ flex: 1 }} placeholder={t("admin.new_objective")} value={newObj}
                   onChange={(e) => setNewObj(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addObj()} />
            <button className="btn-sm" onClick={addObj} disabled={!newObj.trim()}>{t("admin.add")}</button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function CreateSquadModal({ isAdmin, tribes, leaders, defaultTribeId, onClose, onCreated, onError }: {
  isAdmin: boolean; tribes: Tribe[]; leaders: User[]; defaultTribeId: number | null;
  onClose: () => void; onCreated: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState({ name: "", leader_user_id: "", tribe_id: isAdmin ? "" : String(defaultTribeId ?? "") });

  async function create() {
    try {
      await api.post("/api/squads", {
        name: form.name.trim(),
        tribe_id: form.tribe_id ? Number(form.tribe_id) : (isAdmin ? null : defaultTribeId),
        leader_user_id: form.leader_user_id ? Number(form.leader_user_id) : null,
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
              <option value="">—</option>
              {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
            </select>
          </div>
        )}
        <div>
          <label>{t("admin.responsible")}</label>
          <select value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
            <option value="">—</option>
            {leaders.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
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
      <span className="badge badge-navy">{t("squad.team_collapsed_hint", { n: d.members.length }).split(" — ")[0]}</span>
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
      title={`${t("mysquad.manage_team")} — ${detail.name}`}
      onClose={onClose}
      footer={<button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}
    >
      <div className="stack" style={{ gap: 14 }}>
        <div>
          <label>{t("admin.squad")}</label>
          <input defaultValue={name} onBlur={(e) => { if (e.target.value !== name) { setName(e.target.value); run(() => api.put(`/api/squads/${detail.id}`, { name: e.target.value })); } }} />
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
                    <option value="">—</option>
                    {managerOptions(m.id).map((mm) => <option key={mm.id} value={mm.id}>{mm.full_name}</option>)}
                  </select>
                </div>
                <button className="btn-ghost btn-sm" onClick={() => run(() => api.del(`/api/members/${m.id}`))}>✕</button>
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
