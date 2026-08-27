/**
 * Administration > Organisation: tribes, squads, users and personas.
 *
 * The panels that describe WHO is in the organisation and what they may do.
 * Several render editable rows inside tables, where the column header is the
 * visible label and the control carries it as `aria-label`.
 */
import { Fragment, useEffect, useState } from "react";
import { api } from "../../api";
import { useI18n } from "../../i18n";
import { useModule } from "../../config";
import { useAuth } from "../../auth";
import { Permissions, Persona, Role, Squad, SquadDetail, Tribe, User } from "../../types";
import { ErrorBanner, Dot } from "../../components/ui";
import { ALL_ROLES } from "../../perms";

import { useErr } from "./shared";

// Tribe-leader / admin per-squad settings: KPIs on/off + annual objectives.
// (No team management here - that's the squad leader's job in reporting.)
export const RAGS: Array<"green" | "amber" | "red"> = ["green", "amber", "red"];


/** Expandable per-squad settings row inside SquadsAdmin: toggle KPIs on/off and
 *  manage the squad's annual objectives (title + deadline; RAG is auto-derived). */
export function SquadParamsPanel({ squadId }: { squadId: number }) {
  const { t, rag } = useI18n();
  const kpisModuleOn = useModule()("squad_content", "kpis");
  const [squad, setSquad] = useState<SquadDetail | null>(null);
  const [newObj, setNewObj] = useState("");
  const { error, wrap } = useErr();

  async function load() {
    const d = await wrap(() => api.get<SquadDetail>(`/api/squads/${squadId}`));
    if (d) setSquad(d);
  }
  useEffect(() => { load(); }, [squadId]);
  if (!squad) return <div className="small muted">{t("common.loading")}</div>;

  const toggleKpis = (on: boolean) => wrap(async () => { await api.put(`/api/squads/${squadId}`, { kpis_enabled: on }); await load(); });
  const addObj = () => wrap(async () => {
    if (!newObj.trim()) return;
    await api.post("/api/objectives", { squad_id: squadId, year: squad.year, title: newObj.trim() });
    setNewObj("");
    await load();
  });
  const updObj = (id: number, patch: any) => wrap(async () => { await api.put(`/api/objectives/${id}`, patch); await load(); });
  const delObj = (id: number) => wrap(async () => { await api.del(`/api/objectives/${id}`); await load(); });

  return (
    <div className="stack" style={{ gap: 14, padding: "6px 2px" }}>
      {error && <ErrorBanner message={error} />}
      {kpisModuleOn && (
        <label className="switch">
          <input type="checkbox" checked={!!squad.kpis_enabled} onChange={(e) => toggleKpis(e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="small strong">{t("admin.kpis_enabled")}</span>
        </label>
      )}

      <div>
        <div className="small muted" style={{ marginBottom: 6 }}>{t("squad.objectives", { year: squad.year })} - {t("admin.objectives_hint")}</div>
        {squad.objectives.length === 0 && <div className="small muted">{t("squad.no_obj")}</div>}
        {squad.objectives.map((o) => (
          <div key={o.id} className="item-row" style={{ gap: 8 }}>
            <Dot status={o.rag_status} />
            <input style={{ flex: 1 }} aria-label={t("a11y.objective_title")} defaultValue={o.title} onBlur={(e) => e.target.value !== o.title && updObj(o.id, { title: e.target.value })} />
            <span className="small muted" style={{ minWidth: 56 }}>{rag(o.rag_status)}</span>
            <input type="date" className="w-auto" style={{ maxWidth: 150 }} title={t("obj.deadline")} aria-label={t("obj.deadline")}
                   value={o.target_date ? o.target_date.slice(0, 10) : ""}
                   onChange={(e) => updObj(o.id, { target_date: e.target.value || null })} />
            <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => delObj(o.id)}>✕</button>
          </div>
        ))}
        <div className="small muted" style={{ marginTop: 2 }}>{t("obj.status_auto")}</div>
        <div className="row" style={{ alignItems: "flex-end", marginTop: 8 }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label>{t("admin.new_objective")}</label>
            <input aria-label={t("admin.new_objective")} value={newObj} onChange={(e) => setNewObj(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addObj()} />
          </div>
          <button className="btn-sm" onClick={addObj} disabled={!newObj.trim()}>{t("admin.add")}</button>
        </div>
      </div>
    </div>
  );
}


/** Admin > Squads: table of squads (name, tribe, leader, order) with inline edit,
 *  an expandable params panel, and a create form. A tribe leader is scoped to
 *  their own tribe (tribe column read-only, create fixed to their tribe); an
 *  admin can move squads across tribes. */
export function SquadsAdmin({ perms }: { perms: Permissions }) {
  const { t } = useI18n();
  const isAdmin = perms.role === "admin";
  const [squads, setSquads] = useState<Squad[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const { error, wrap } = useErr();
  const [form, setForm] = useState({ name: "", leader_user_id: "", tribe_id: isAdmin ? "" : String(perms.tribe_id ?? "") });
  const [paramsId, setParamsId] = useState<number | null>(null);

  async function load() {
    setSquads(await api.get<Squad[]>("/api/squads"));
    setUsers(await api.get<User[]>("/api/admin/users"));
    const allTribes = await api.get<Tribe[]>("/api/tribes");
    setTribes(isAdmin ? allTribes : allTribes.filter((tr) => tr.id === perms.tribe_id));
  }
  useEffect(() => {
    load();
  }, []);

  const leaders = users.filter((u) => u.role === "squad_leader" || u.role === "tribe_leader" || u.role === "admin");
  const tribeName = (id: number) => tribes.find((tr) => tr.id === id)?.name || "-";

  async function create() {
    await wrap(async () => {
      await api.post("/api/squads", {
        name: form.name,
        tribe_id: form.tribe_id ? Number(form.tribe_id) : null,
        leader_user_id: form.leader_user_id ? Number(form.leader_user_id) : null,
      });
      setForm({ name: "", leader_user_id: "", tribe_id: "" });
      await load();
    });
  }
  async function update(s: Squad, patch: Partial<Squad>) {
    await wrap(async () => {
      await api.put(`/api/squads/${s.id}`, patch);
      await load();
    });
  }
  async function remove(s: Squad) {
    await wrap(async () => {
      await api.del(`/api/squads/${s.id}`);
      await load();
    });
  }

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>{t("admin.squad")}</th>
              <th>{t("admin.tribe")}</th>
              <th>{t("admin.responsible")}</th>
              <th>{t("admin.order")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {squads.map((s) => (
              <Fragment key={s.id}>
              <tr>
                <td className="strong">
                  <input aria-label={t("admin.squad")} defaultValue={s.name} onBlur={(e) => e.target.value !== s.name && update(s, { name: e.target.value })} />
                </td>
                <td>
                  {isAdmin ? (
                    <select className="w-auto" aria-label={t("admin.tribe")} value={s.tribe_id} onChange={(e) => update(s, { tribe_id: Number(e.target.value) } as any)}>
                      {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
                    </select>
                  ) : (
                    <span className="muted">{tribeName(s.tribe_id)}</span>
                  )}
                </td>
                <td>
                  <select className="w-auto" aria-label={t("admin.responsible")} value={s.leader_user_id ?? ""} onChange={(e) => update(s, { leader_user_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">-</option>
                    {leaders.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.display_name}
                      </option>
                    ))}
                  </select>
                </td>
                <td style={{ width: 90 }}>
                  <input type="number" aria-label={t("admin.order")} defaultValue={s.display_order} onBlur={(e) => Number(e.target.value) !== s.display_order && update(s, { display_order: Number(e.target.value) })} />
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <button className="btn-secondary btn-sm" style={{ marginRight: 6 }}
                          onClick={() => setParamsId(paramsId === s.id ? null : s.id)}>
                    {t("admin.squad_params")}
                  </button>
                  <button className="btn-danger btn-sm" onClick={() => remove(s)}>
                    {t("action.delete")}
                  </button>
                </td>
              </tr>
              {paramsId === s.id && (
                <tr>
                  <td colSpan={5} style={{ background: "var(--ice-soft)" }}>
                    <SquadParamsPanel squadId={s.id} />
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>{t("admin.new_squad")}</h3>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ width: 200 }}>
            <label>{t("admin.name")}</label>
            <input aria-label={t("admin.name")} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          {isAdmin && (
            <div style={{ width: 200 }}>
              <label>{t("admin.tribe")}</label>
              <select aria-label={t("admin.tribe")} value={form.tribe_id} onChange={(e) => setForm({ ...form, tribe_id: e.target.value })}>
                <option value="">-</option>
                {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
              </select>
            </div>
          )}
          <div style={{ width: 200 }}>
            <label>{t("admin.responsible")}</label>
            <select aria-label={t("admin.responsible")} value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
              <option value="">-</option>
              {leaders.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name}
                </option>
              ))}
            </select>
          </div>
          <button onClick={create} disabled={!form.name.trim() || !form.tribe_id}>
            {t("admin.create")}
          </button>
        </div>
      </div>
    </div>
  );
}


/** Admin > Users: list/create/update/delete users and reset passwords. A
 *  non-admin manager may only act on users whose role is within their grant
 *  (`assignable_roles`) and is scoped to their tribe; break-glass accounts are
 *  never editable here. Custom persona labels decorate the role dropdowns. */
export function UsersAdmin({ perms }: { perms: Permissions }) {
  const { t, role: roleLabel, formatDateTime } = useI18n();
  const isAdmin = perms.role === "admin";
  // Roles this manager may assign (falls back to all roles for a full admin).
  const roleOptions = perms.assignable_roles.length ? perms.assignable_roles : ALL_ROLES;
  const [users, setUsers] = useState<User[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [personaLabels, setPersonaLabels] = useState<Record<string, string>>({});
  const labelFor = (key: string) => personaLabels[key] ?? roleLabel(key);
  const { error, wrap } = useErr();
  const [form, setForm] = useState({
    email: "", display_name: "", role: roleOptions[roleOptions.length - 1] as Role,
    password: "", tribe_id: isAdmin ? "" : String(perms.tribe_id ?? ""),
  });

  async function load() {
    setUsers(await api.get<User[]>("/api/admin/users"));
    const allTribes = await api.get<Tribe[]>("/api/tribes");
    setTribes(isAdmin ? allTribes : allTribes.filter((tr) => tr.id === perms.tribe_id));
    if (isAdmin) {
      // Custom persona labels for the role dropdowns.
      try {
        const out = await api.get<{ personas: Persona[] }>("/api/admin/personas");
        setPersonaLabels(Object.fromEntries(out.personas.filter((p) => !p.builtin).map((p) => [p.key, p.label])));
      } catch { /* ignore */ }
    }
  }
  useEffect(() => {
    load();
  }, []);

  // A non-admin manager may only act on users whose role is within their grant.
  const canManage = (u: User) => !u.is_break_glass && (isAdmin || roleOptions.includes(u.role));

  async function create() {
    await wrap(async () => {
      await api.post("/api/admin/users", {
        email: form.email, display_name: form.display_name, role: form.role,
        tribe_id: form.tribe_id ? Number(form.tribe_id) : (isAdmin ? null : perms.tribe_id),
        password: form.password || null,
      });
      setForm({ email: "", display_name: "", role: roleOptions[roleOptions.length - 1] as Role, password: "", tribe_id: isAdmin ? "" : String(perms.tribe_id ?? "") });
      await load();
    });
  }
  async function update(u: User, patch: any) {
    await wrap(async () => {
      await api.put(`/api/admin/users/${u.id}`, patch);
      await load();
    });
  }
  async function remove(u: User) {
    await wrap(async () => {
      await api.del(`/api/admin/users/${u.id}`);
      await load();
    });
  }
  async function resetPassword(u: User) {
    const pw = prompt(`${t("admin.password")} - ${u.display_name}`);
    if (pw) await update(u, { password: pw });
  }

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>{t("admin.user")}</th>
              <th>{t("admin.email")}</th>
              <th>{t("admin.role")}</th>
              <th>{t("admin.tribe")}</th>
              <th>{t("admin.last_login")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td className="strong">
                  {u.display_name}
                  {u.is_break_glass && <span className="badge badge-orange" style={{ marginLeft: 8 }}>{t("admin.breakglass")}</span>}
                </td>
                <td>{u.email}</td>
                <td>
                  <select className="w-auto" aria-label={t("admin.role")} value={u.role} disabled={!canManage(u)} onChange={(e) => update(u, { role: e.target.value as Role })}>
                    {(isAdmin ? roleOptions : Array.from(new Set([u.role, ...roleOptions]))).map((r) => (
                      <option key={r} value={r}>
                        {labelFor(r)}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  {isAdmin ? (
                    <select className="w-auto" aria-label={t("admin.tribe")} value={u.tribe_id ?? ""} onChange={(e) => update(u, { tribe_id: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">{t("admin.no_tribe")}</option>
                      {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
                    </select>
                  ) : (
                    <span className="muted">{tribes.find((tr) => tr.id === u.tribe_id)?.name ?? "-"}</span>
                  )}
                </td>
                <td className="muted">{formatDateTime(u.last_login_at)}</td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {canManage(u) && (
                    <button className="btn-secondary btn-sm" onClick={() => resetPassword(u)} style={{ marginRight: 6 }}>
                      {t("admin.password")}
                    </button>
                  )}
                  {canManage(u) && (
                    <button className="btn-danger btn-sm" onClick={() => remove(u)}>
                      {t("action.delete")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={6} className="muted" style={{ textAlign: "center", padding: 20 }}>{t("admin.no_users")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>{t("admin.new_user")}</h3>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ width: 180 }}>
            <label htmlFor="nu-name">{t("admin.name")}</label>
            <input id="nu-name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </div>
          <div style={{ width: 200 }}>
            <label htmlFor="nu-email">{t("admin.email")}</label>
            <input id="nu-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div style={{ width: 150 }}>
            <label htmlFor="nu-role">{t("admin.role")}</label>
            <select id="nu-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {roleOptions.map((r) => (
                <option key={r} value={r}>
                  {labelFor(r)}
                </option>
              ))}
            </select>
          </div>
          {isAdmin && (
            <div style={{ width: 160 }}>
              <label htmlFor="nu-tribe">{t("admin.tribe")}</label>
              <select id="nu-tribe" value={form.tribe_id} onChange={(e) => setForm({ ...form, tribe_id: e.target.value })}>
                <option value="">{t("admin.no_tribe")}</option>
                {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
              </select>
            </div>
          )}
          <div style={{ width: 150 }}>
            <label htmlFor="nu-pass">{t("admin.password_local")}</label>
            <input id="nu-pass" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          <button onClick={create} disabled={!form.email.trim() || !form.display_name.trim()}>
            {t("admin.create")}
          </button>
        </div>
      </div>
    </div>
  );
}


// Personas & permissions: a single matrix of persona × section-access toggles,
// plus custom persona creation. Mirrors Admin → Modules wiring.
/** Admin > Personas: the persona x capability matrix. Built-in roles show a fixed
 *  label; custom personas are renameable and deletable. The "admin" persona is
 *  locked all-on (superuser). Saving persists the whole set. Admin only. */
export function PersonasAdmin() {
  const { t, role: roleLabel } = useI18n();
  const [caps, setCaps] = useState<string[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [newLabel, setNewLabel] = useState("");
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  async function load() {
    const out = await wrap(() => api.get<{ capabilities: string[]; personas: Persona[] }>("/api/admin/personas"));
    if (out) { setCaps(out.capabilities); setPersonas(out.personas); }
  }
  useEffect(() => { load(); }, []);

  const setCap = (key: string, cap: string, val: boolean) =>
    setPersonas((ps) => ps.map((p) => (p.key === key ? { ...p, caps: { ...p.caps, [cap]: val } } : p)));
  const setLabel = (key: string, label: string) =>
    setPersonas((ps) => ps.map((p) => (p.key === key ? { ...p, label } : p)));
  const removePersona = (key: string) => setPersonas((ps) => ps.filter((p) => p.key !== key));
  function addPersona() {
    if (!newLabel.trim()) return;
    setPersonas((ps) => [...ps, { key: newLabel.trim(), label: newLabel.trim(), builtin: false,
      caps: Object.fromEntries(caps.map((c) => [c, false])) }]);
    setNewLabel("");
  }
  async function save() {
    const out = await wrap(() => api.put<{ capabilities: string[]; personas: Persona[] }>("/api/admin/personas", { personas }));
    if (out) { setCaps(out.capabilities); setPersonas(out.personas); setSaved(true); setTimeout(() => setSaved(false), 1500); }
  }

  return (
    <div className="stack" style={{ gap: 14, maxWidth: 920 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("personas.intro")}</div>
      <div style={{ overflowX: "auto" }}>
        <table className="persona-matrix">
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>{t("personas.persona")}</th>
              {caps.map((c) => <th key={c}>{t(`cap.${c}`)}</th>)}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {personas.map((p) => {
              const locked = p.key === "admin";  // superuser stays all-on
              return (
                <tr key={p.key}>
                  <td style={{ textAlign: "left" }}>
                    {p.builtin
                      ? <span className="strong">{roleLabel(p.key)}</span>
                      : <input style={{ width: 150 }} aria-label={t("a11y.persona_label")} value={p.label} onChange={(e) => setLabel(p.key, e.target.value)} />}
                  </td>
                  {caps.map((c) => (
                    <td key={c} style={{ textAlign: "center" }}>
                      <input type="checkbox" checked={locked ? true : !!p.caps[c]} disabled={locked}
                             aria-label={`${p.builtin ? roleLabel(p.key) : p.label} - ${t(`cap.${c}`)}`}
                             onChange={(e) => setCap(p.key, c, e.target.checked)} />
                    </td>
                  ))}
                  <td style={{ textAlign: "center" }}>
                    {!p.builtin && <button className="btn-ghost btn-sm" title={t("action.delete")}
                                           aria-label={`${t("action.delete")} - ${p.label}`}
                                           onClick={() => removePersona(p.key)}>✕</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="inline" style={{ gap: 8 }}>
        <input aria-label={t("personas.new_ph")} placeholder={t("personas.new_ph")} value={newLabel}
               onChange={(e) => setNewLabel(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addPersona()} />
        <button className="btn-secondary btn-sm" onClick={addPersona} disabled={!newLabel.trim()}>{t("personas.add")}</button>
      </div>
      <div className="inline">
        <button onClick={save}>{t("action.save")}</button>
        {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
      </div>
    </div>
  );
}


/** Admin > Tribes: full CRUD over tribes (name, description, tribe leader).
 *  Inline edits save on blur; a form at the bottom creates new tribes. Admin only. */
export function TribesAdmin() {
  const { t } = useI18n();
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const { error, wrap } = useErr();
  const [form, setForm] = useState({ name: "", description: "", leader_user_id: "" });

  async function load() {
    setTribes(await api.get<Tribe[]>("/api/tribes"));
    setUsers(await api.get<User[]>("/api/admin/users"));
  }
  useEffect(() => { load(); }, []);

  async function create() {
    await wrap(async () => {
      await api.post("/api/tribes", {
        name: form.name, description: form.description || null,
        leader_user_id: form.leader_user_id ? Number(form.leader_user_id) : null,
      });
      setForm({ name: "", description: "", leader_user_id: "" });
      await load();
    });
  }
  async function update(tr: Tribe, patch: Partial<Tribe>) {
    await wrap(async () => { await api.put(`/api/tribes/${tr.id}`, patch); await load(); });
  }
  async function remove(tr: Tribe) {
    await wrap(async () => { await api.del(`/api/tribes/${tr.id}`); await load(); });
  }

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead><tr><th>{t("admin.tribe")}</th><th>{t("admin.tribe_desc")}</th><th /></tr></thead>
          <tbody>
            {tribes.map((tr) => (
              <tr key={tr.id}>
                <td><input aria-label={t("admin.tribe")} defaultValue={tr.name} onBlur={(e) => e.target.value !== tr.name && update(tr, { name: e.target.value })} /></td>
                <td><input aria-label={t("admin.tribe_desc")} defaultValue={tr.description ?? ""} onBlur={(e) => e.target.value !== (tr.description ?? "") && update(tr, { description: e.target.value })} /></td>
                <td style={{ textAlign: "right" }}><button className="btn-danger btn-sm" onClick={() => remove(tr)}>{t("action.delete")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>{t("admin.new_tribe")}</h3>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ width: 220 }}><label>{t("admin.name")}</label><input aria-label={t("admin.name")} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div className="col"><label>{t("admin.tribe_desc")}</label><input aria-label={t("admin.tribe_desc")} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
          <div style={{ width: 200 }}>
            <label>{t("admin.tribe_leader")}</label>
            <select aria-label={t("admin.tribe_leader")} value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
              <option value="">{t("admin.tribe_leader_none")}</option>
              {users.filter((u) => !u.is_break_glass).map((u) => (
                <option key={u.id} value={u.id}>{u.display_name}</option>
              ))}
            </select>
          </div>
          <button onClick={create} disabled={!form.name.trim()}>{t("admin.create")}</button>
        </div>
        <div className="small muted" style={{ marginTop: 6 }}>{t("admin.tribe_leader_hint")}</div>
      </div>
    </div>
  );
}


// Tribe leader: edit their own tribe (name / description). No create/delete.
export function TribeSelfAdmin({ perms }: { perms: Permissions }) {
  const { t } = useI18n();
  const [tribe, setTribe] = useState<Tribe | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  useEffect(() => {
    api.get<Tribe[]>("/api/tribes").then((list) => setTribe(list.find((tr) => tr.id === perms.tribe_id) ?? null));
  }, []);

  if (!perms.tribe_id) return <div className="banner">{t("admin.no_tribe_assigned")}</div>;
  if (!tribe) return <div className="spinner">{t("common.loading")}</div>;

  async function save(patch: Partial<Tribe>) {
    await wrap(async () => {
      const out = await api.put<Tribe>(`/api/tribes/${tribe!.id}`, patch);
      setTribe(out);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    });
  }

  return (
    <div className="stack" style={{ maxWidth: 560 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("admin.my_tribe_intro")}</div>
      <div className="card stack" style={{ gap: 12 }}>
        <div><label>{t("admin.name")}</label>
          <input aria-label={t("admin.name")} defaultValue={tribe.name} onBlur={(e) => e.target.value !== tribe.name && save({ name: e.target.value })} /></div>
        <div><label>{t("admin.tribe_desc")}</label>
          <input aria-label={t("admin.tribe_desc")} defaultValue={tribe.description ?? ""} onBlur={(e) => e.target.value !== (tribe.description ?? "") && save({ description: e.target.value })} /></div>
      </div>
      {saved && <div className="small" style={{ color: "var(--green)" }}>{t("admin.saved")}</div>}
    </div>
  );
}


// Squad leader: manage the squads they lead (name, KPIs on/off, members).
export function MySquadsAdmin() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [squads, setSquads] = useState<Squad[]>([]);
  const { error, wrap } = useErr();

  async function load() {
    const all = await wrap(() => api.get<Squad[]>("/api/squads"));
    if (all) setSquads(all.filter((s) => s.leader_user_id === user?.id));
  }
  useEffect(() => { load(); }, []);

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("admin.my_squads_intro")}</div>
      {squads.length === 0 && <div className="card muted">{t("admin.no_led_squad")}</div>}
      {squads.map((s) => <SquadSelfCard key={s.id} squadId={s.id} />)}
    </div>
  );
}


/** One squad card in the squad-leader "my squads" admin: rename the squad and
 *  add/remove its members. Reloads its own detail after each change. */
export function SquadSelfCard({ squadId }: { squadId: number }) {
  const { t } = useI18n();
  const [squad, setSquad] = useState<SquadDetail | null>(null);
  const [newMember, setNewMember] = useState({ full_name: "", role_title: "" });
  const { error, wrap } = useErr();

  async function load() {
    const d = await wrap(() => api.get<SquadDetail>(`/api/squads/${squadId}`));
    if (d) setSquad(d);
  }
  useEffect(() => { load(); }, [squadId]);
  if (!squad) return <div className="card spinner">{t("common.loading")}</div>;

  const patchSquad = (patch: any) => wrap(async () => { await api.put(`/api/squads/${squadId}`, patch); await load(); });
  const addMember = () => wrap(async () => {
    if (!newMember.full_name.trim()) return;
    await api.post("/api/members", { squad_id: squadId, full_name: newMember.full_name.trim(), role_title: newMember.role_title.trim() || null });
    setNewMember({ full_name: "", role_title: "" });
    await load();
  });
  const delMember = (id: number) => wrap(async () => { await api.del(`/api/members/${id}`); await load(); });

  return (
    <div className="card stack" style={{ gap: 12 }}>
      {error && <ErrorBanner message={error} />}
      <div className="row" style={{ alignItems: "flex-end" }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label>{t("admin.squad")}</label>
          <input aria-label={t("admin.squad")} defaultValue={squad.name} onBlur={(e) => e.target.value !== squad.name && patchSquad({ name: e.target.value })} />
        </div>
      </div>

      <div>
        <div className="small muted" style={{ marginBottom: 6 }}>{t("admin.members")}</div>
        {squad.members.length === 0 && <div className="small muted">{t("squad.no_members")}</div>}
        {squad.members.map((m) => (
          <div key={m.id} className="item-row">
            <span className="grow">{m.full_name}{m.role_title ? <span className="muted small">, {m.role_title}</span> : null}</span>
            <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => delMember(m.id)}>✕</button>
          </div>
        ))}
        <div className="row" style={{ alignItems: "flex-end", marginTop: 8 }}>
          <div style={{ flex: 1, minWidth: 160 }}><label>{t("admin.member_name")}</label>
            <input aria-label={t("admin.member_name")} value={newMember.full_name} onChange={(e) => setNewMember({ ...newMember, full_name: e.target.value })} /></div>
          <div style={{ flex: 1, minWidth: 140 }}><label>{t("admin.member_role")}</label>
            <input aria-label={t("admin.member_role")} value={newMember.role_title} onChange={(e) => setNewMember({ ...newMember, role_title: e.target.value })} /></div>
          <button className="btn-sm" onClick={addMember} disabled={!newMember.full_name.trim()}>{t("admin.add")}</button>
        </div>
      </div>
    </div>
  );
}
