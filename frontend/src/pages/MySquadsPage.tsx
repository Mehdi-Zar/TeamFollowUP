import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { Squad, SquadDetail, Tribe, User } from "../types";
import { ErrorBanner, Spinner, Dot } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";

const RAGS: Array<"green" | "amber" | "red"> = ["green", "amber", "red"];

/** Dedicated page where a tribe leader manages their squads: KPIs on/off and
 *  annual objectives (set by the tribe leader). Separate from Administration. */
export default function MySquadsPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [squads, setSquads] = useState<Squad[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", leader_user_id: "", tribe_id: isAdmin ? "" : String(user?.tribe_id ?? "") });

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

  useSetPageChrome({ title: t("mysquads.title") }, [t]);

  const leaders = users.filter((u) => ["squad_leader", "tribe_leader", "admin"].includes(u.role));

  async function create() {
    try {
      await api.post("/api/squads", {
        name: form.name.trim(),
        tribe_id: form.tribe_id ? Number(form.tribe_id) : (isAdmin ? null : user?.tribe_id),
        leader_user_id: form.leader_user_id ? Number(form.leader_user_id) : null,
      });
      setForm({ name: "", leader_user_id: "", tribe_id: isAdmin ? "" : String(user?.tribe_id ?? "") });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  }

  if (error && !squads) return <ErrorBanner message={error} />;
  if (!squads) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {error && <ErrorBanner message={error} />}
      <div className="muted small">{t("mysquads.intro")}</div>

      {squads.length === 0 && <div className="card muted">{t("mysquads.empty")}</div>}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: 16 }}>
        {squads.map((s) => (
          <SquadManageCard key={s.id} squadId={s.id} leaders={leaders} onChange={load} onError={setError} />
        ))}
      </div>

      <div className="card">
        <h3>{t("mysquads.new")}</h3>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label>{t("admin.name")}</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          {isAdmin && (
            <div style={{ width: 200 }}>
              <label>{t("admin.tribe")}</label>
              <select value={form.tribe_id} onChange={(e) => setForm({ ...form, tribe_id: e.target.value })}>
                <option value="">—</option>
                {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
              </select>
            </div>
          )}
          <div style={{ width: 200 }}>
            <label>{t("admin.responsible")}</label>
            <select value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
              <option value="">—</option>
              {leaders.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
            </select>
          </div>
          <button onClick={create} disabled={!form.name.trim() || (isAdmin && !form.tribe_id)}>{t("admin.create")}</button>
        </div>
      </div>
    </div>
  );
}

function SquadManageCard({ squadId, leaders, onChange, onError }: {
  squadId: number; leaders: User[]; onChange: () => void; onError: (m: string) => void;
}) {
  const { t, rag } = useI18n();
  const [squad, setSquad] = useState<SquadDetail | null>(null);
  const [newObj, setNewObj] = useState("");

  async function load() {
    try { setSquad(await api.get<SquadDetail>(`/api/squads/${squadId}`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  useEffect(() => { load(); }, [squadId]);

  async function run(fn: () => Promise<any>) {
    try { await fn(); await load(); onChange(); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  if (!squad) return <div className="card spinner">{t("common.loading")}</div>;

  const patch = (p: any) => run(() => api.put(`/api/squads/${squadId}`, p));
  const addObj = () => { if (newObj.trim()) run(async () => { await api.post("/api/objectives", { squad_id: squadId, year: squad.year, title: newObj.trim(), rag_status: "green" }); setNewObj(""); }); };

  return (
    <div className="card stack" style={{ gap: 12 }}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <input className="strong" defaultValue={squad.name} style={{ fontSize: 16 }}
                 onBlur={(e) => e.target.value !== squad.name && patch({ name: e.target.value })} />
        </div>
        <button className="btn-danger btn-sm" onClick={() => { if (confirm(t("mysquads.del_confirm"))) run(() => api.del(`/api/squads/${squadId}`)); }}>
          {t("action.delete")}
        </button>
      </div>

      <div className="row" style={{ alignItems: "flex-end", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 160 }}>
          <label>{t("admin.responsible")}</label>
          <select value={squad.leader_user_id ?? ""} onChange={(e) => patch({ leader_user_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">—</option>
            {leaders.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
        </div>
        <label className="switch" style={{ marginBottom: 4 }}>
          <input type="checkbox" checked={!!squad.kpis_enabled} onChange={(e) => patch({ kpis_enabled: e.target.checked })} />
          <span className="track"><span className="knob" /></span>
          <span className="small">{t("admin.kpis_enabled")}</span>
        </label>
      </div>

      <div>
        <div className="small muted" style={{ marginBottom: 6 }}>
          {t("squad.objectives", { year: squad.year })} — {t("admin.objectives_hint")}
        </div>
        {squad.objectives.length === 0 && <div className="small muted">{t("squad.no_obj")}</div>}
        {squad.objectives.map((o) => (
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
  );
}
