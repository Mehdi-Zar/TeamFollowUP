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
import { Permissions, Persona, Role, Squad, Tribe, User } from "../../types";
import { ErrorBanner } from "../../components/ui";
import { ADMIN_TABS_BY_ROLE, ALL_ROLES } from "../../perms";
import { ADMIN_GROUPS, TAB_LABEL } from "./tabs";

import { useErr, useLoadState } from "./shared";

/** Admin > Squads: the table of the squads, one row each, to see and change at a
 *  glance who leads them. Name, tribe (admin), squad leader, co-leaders,
 *  contributors, order; create; delete, confirmed on the row. Everything else
 *  about a squad (OTD, initiatives, team, budget, committees) is in "My squads". */
export function SquadsAdmin({ perms }: { perms: Permissions }) {
  const { t } = useI18n();
  const isAdmin = perms.role === "admin";
  const [squads, setSquads] = useState<Squad[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const { error, wrap } = useErr();
  const [form, setForm] = useState({ name: "", leader_user_id: "", tribe_id: isAdmin ? "" : String(perms.tribe_id ?? "") });
  // The row whose deletion waits for a second click.
  const [deleting, setDeleting] = useState<number | null>(null);
  // No access to the accounts: people cannot be picked here (said above the table).
  const [noPeople, setNoPeople] = useState(false);

  async function load() {
    // Each list on its own: without the Accounts tab the user list is refused,
    // and the squads must still show.
    const [sq, us, tr] = await Promise.allSettled([
      api.get<Squad[]>("/api/squads"), api.get<User[]>("/api/admin/users"), api.get<Tribe[]>("/api/tribes"),
    ]);
    if (sq.status === "fulfilled") setSquads(sq.value);
    else await wrap(() => Promise.reject(sq.reason));
    if (us.status === "fulfilled") setUsers(us.value);
    setNoPeople(us.status === "rejected");
    if (tr.status === "fulfilled") setTribes(isAdmin ? tr.value : tr.value.filter((x) => x.id === perms.tribe_id));
  }
  useEffect(() => { load(); }, []);

  // Anyone active may be named leader (the server promotes a member or a contributor).
  const leaders = users.filter((u) => u.status !== "disabled");
  const tribeName = (id: number) => tribes.find((tr) => tr.id === id)?.name || "-";
  // People of the squad's tribe: the only ones a co-leader or contributor may be.
  const ofTribe = (s: Squad) => users.filter((u) => u.tribe_id === s.tribe_id && u.status !== "disabled");

  async function create() {
    await wrap(async () => {
      await api.post("/api/squads", {
        name: form.name,
        tribe_id: form.tribe_id ? Number(form.tribe_id) : null,
        leader_user_id: form.leader_user_id ? Number(form.leader_user_id) : null,
      });
      setForm({ name: "", leader_user_id: "", tribe_id: isAdmin ? "" : String(perms.tribe_id ?? "") });
      await load();
    });
  }
  async function update(s: Squad, patch: Record<string, unknown>) {
    await wrap(async () => {
      await api.put(`/api/squads/${s.id}`, patch);
      await load();
    });
  }
  async function remove(s: Squad) {
    await wrap(async () => {
      await api.del(`/api/squads/${s.id}`);
      setDeleting(null);
      await load();
    });
  }

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      {noPeople && <div className="banner small">{t("admin.squads_no_accounts")}</div>}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>{t("admin.squad")}</th>
              <th>{t("admin.tribe")}</th>
              <th>{t("squad.squad_leader")}</th>
              <th>{t("squad.co_leaders")}</th>
              <th>{t("squad.contributors")}</th>
              <th>{t("admin.order")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {squads.map((s) => (
              <tr key={s.id}>
                <td className="strong">
                  <input aria-label={t("admin.squad")} defaultValue={s.name}
                         onBlur={(e) => e.target.value.trim() && e.target.value !== s.name && update(s, { name: e.target.value.trim() })} />
                </td>
                <td>
                  {isAdmin ? (
                    <select className="w-auto" aria-label={t("admin.tribe")} value={s.tribe_id} onChange={(e) => update(s, { tribe_id: Number(e.target.value) })}>
                      {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
                    </select>
                  ) : (
                    <span className="muted">{tribeName(s.tribe_id)}</span>
                  )}
                </td>
                <td>
                  <select className="w-auto" aria-label={t("squad.squad_leader")} value={s.leader_user_id ?? ""}
                          onChange={(e) => update(s, { leader_user_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">-</option>
                    {leaders.filter((u) => isAdmin || u.tribe_id === s.tribe_id || u.id === s.leader_user_id)
                      .map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
                  </select>
                </td>
                <td>
                  <PeopleCell label={t("squad.co_leaders")} people={ofTribe(s).filter((u) => u.id !== s.leader_user_id)}
                              value={s.co_leader_user_ids ?? []}
                              onChange={(v) => update(s, { co_leader_user_ids: v })} />
                </td>
                <td>
                  <PeopleCell label={t("squad.contributors")}
                              people={ofTribe(s).filter((u) => u.id !== s.leader_user_id && !(s.co_leader_user_ids ?? []).includes(u.id))}
                              value={s.contributor_user_ids ?? []}
                              onChange={(v) => update(s, { contributor_user_ids: v })} />
                </td>
                <td style={{ width: 90 }}>
                  <input type="number" aria-label={t("admin.order")} defaultValue={s.display_order}
                         onBlur={(e) => Number(e.target.value) !== s.display_order && update(s, { display_order: Number(e.target.value) })} />
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {deleting === s.id ? (
                    <span className="inline" style={{ gap: 6 }}>
                      <span className="small">{t("mysquads.del_confirm")}</span>
                      <button className="btn-danger btn-sm" onClick={() => remove(s)}>{t("action.delete")}</button>
                      <button className="btn-secondary btn-sm" onClick={() => setDeleting(null)}>{t("action.cancel")}</button>
                    </span>
                  ) : (
                    <button className="btn-danger btn-sm" onClick={() => setDeleting(s.id)}>{t("action.delete")}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>{t("mysquads.new")}</h3>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ width: 200 }}>
            <label htmlFor="new-squad-name">{t("admin.name")}</label>
            <input id="new-squad-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          {isAdmin && (
            <div style={{ width: 200 }}>
              <label htmlFor="new-squad-tribe">{t("admin.tribe")}</label>
              <select id="new-squad-tribe" value={form.tribe_id} onChange={(e) => setForm({ ...form, tribe_id: e.target.value })}>
                <option value="">-</option>
                {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
              </select>
            </div>
          )}
          <div style={{ width: 200 }}>
            <label htmlFor="new-squad-leader">{t("squad.squad_leader")}</label>
            <select id="new-squad-leader" value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
              <option value="">-</option>
              {leaders.filter((u) => !form.tribe_id || u.tribe_id == null || String(u.tribe_id) === String(form.tribe_id)).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
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

/** People in a table cell: who is there (with a remove cross) and a list to add one. */
function PeopleCell({ label, people, value, onChange }: {
  label: string; people: User[]; value: number[]; onChange: (v: number[]) => void;
}) {
  const { t } = useI18n();
  const name = (id: number) => people.find((u) => u.id === id)?.display_name ?? `#${id}`;
  const left = people.filter((u) => !value.includes(u.id));
  return (
    <div className="stack" style={{ gap: 4, minWidth: 180 }}>
      {value.length > 0 && (
        <div className="inline" style={{ gap: 4, flexWrap: "wrap" }}>
          {value.map((id) => (
            <span key={id} className="badge badge-navy">
              {name(id)}{" "}
              <button type="button" className="btn-ghost btn-sm" style={{ padding: 0, minHeight: 0 }}
                      aria-label={`${t("action.delete")} ${name(id)}`}
                      onClick={() => onChange(value.filter((x) => x !== id))}>×</button>
            </span>
          ))}
        </div>
      )}
      {left.length > 0 && (
        <select className="w-auto" aria-label={`${label} : ${t("admin.add")}`} value=""
                onChange={(e) => e.target.value && onChange([...value, Number(e.target.value)])}>
          <option value="">{t("admin.add")}…</option>
          {left.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
        </select>
      )}
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
      setDeletingUser(null);
      await load();
    });
  }
  // The account whose deletion waits for a second click, with what it leads.
  const [deletingUser, setDeletingUser] = useState<number | null>(null);
  const [ledNames, setLedNames] = useState<Record<number, string[]>>({});
  useEffect(() => {
    api.get<Squad[]>("/api/squads").then((sq) => {
      const m: Record<number, string[]> = {};
      for (const s of sq) {
        for (const id of [s.leader_user_id, ...(s.co_leader_user_ids ?? [])]) {
          if (id) (m[id] = m[id] ?? []).push(s.name);
        }
      }
      setLedNames(m);
    }).catch(() => {});
  }, []);
  async function resetPassword(u: User) {
    const pw = prompt(`${t("admin.password")}${t("common.colon")}${u.display_name}`);
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
                  {canManage(u) && (deletingUser === u.id ? (
                      <span className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
                        <span className="small">{(ledNames[u.id]?.length ? t("admin.user_delete_leads", { squads: ledNames[u.id].join(", ") }) + " " : "") + t("admin.user_delete_confirm")}</span>
                        <button className="btn-danger btn-sm" onClick={() => remove(u)}>{t("action.delete")}</button>
                        <button className="btn-ghost btn-sm" onClick={() => setDeletingUser(null)}>{t("action.cancel")}</button>
                      </span>
                    ) : (
                      <button className="btn-danger btn-sm" onClick={() => setDeletingUser(u.id)}>
                      {t("action.delete")}
                    </button>
                  ))}
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
  const [tabs, setTabs] = useState<string[]>([]);
  // Tabs that are the whole administration by nature (SSO, trusted authorities):
  // shown, but only the administrator's.
  const [adminOnly, setAdminOnly] = useState<Set<string>>(new Set());
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [newLabel, setNewLabel] = useState("");
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  type Out = { capabilities: string[]; admin_tab_options: string[]; admin_only_tabs?: string[]; personas: Persona[] };
  function apply(out: Out) {
    setCaps(out.capabilities); setTabs(out.admin_tab_options ?? []); setPersonas(out.personas);
    setAdminOnly(new Set(out.admin_only_tabs ?? []));
  }
  async function load() {
    const out = await wrap(() => api.get<Out>("/api/admin/personas"));
    if (out) apply(out);
  }
  useEffect(() => { load(); }, []);

  const setCap = (key: string, cap: string, val: boolean) =>
    setPersonas((ps) => ps.map((p) => (p.key === key ? { ...p, caps: { ...p.caps, [cap]: val } } : p)));
  const setTab = (key: string, tab: string, val: boolean) =>
    setPersonas((ps) => ps.map((p) => (p.key === key
      ? { ...p, admin_tabs: val ? [...(p.admin_tabs ?? []), tab] : (p.admin_tabs ?? []).filter((x) => x !== tab) } : p)));
  const setLabel = (key: string, label: string) =>
    setPersonas((ps) => ps.map((p) => (p.key === key ? { ...p, label } : p)));
  const removePersona = (key: string) => setPersonas((ps) => ps.filter((p) => p.key !== key));
  function addPersona() {
    if (!newLabel.trim()) return;
    setPersonas((ps) => [...ps, { key: newLabel.trim(), label: newLabel.trim(), builtin: false,
      caps: Object.fromEntries(caps.map((c) => [c, false])), admin_tabs: [] }]);
    setNewLabel("");
  }
  async function save() {
    const out = await wrap(() => api.put<Out>("/api/admin/personas", { personas }));
    if (out) { apply(out); setSaved(true); setTimeout(() => setSaved(false), 1500); }
  }

  // One table: a row per option, grouped like the menus (the app sections, then
  // the four families of Administration), a column per persona. Everything is the
  // admin's choice; only the administrator's own column is locked, so nobody can
  // lock the application out of its own settings.
  const who = (p: Persona) => (p.builtin ? roleLabel(p.key) : p.label);
  const adminHas = new Set(ADMIN_TABS_BY_ROLE.admin);
  const groups = ADMIN_GROUPS
    .map((g) => ({ titleKey: g.titleKey, items: g.items.filter((k) => tabs.includes(k)) }))
    .filter((g) => g.items.length > 0);
  const cols = personas.length + 1;

  const cell = (p: Persona, checked: boolean, onChange: (v: boolean) => void, label: string, lockedValue?: boolean) =>
    lockedValue === undefined ? (
      <input type="checkbox" checked={checked} aria-label={`${who(p)}, ${label}`}
             onChange={(e) => onChange(e.target.checked)} />
    ) : lockedValue ? (
      <input type="checkbox" checked disabled aria-label={`${who(p)}, ${label}`} />
    ) : <span className="muted" title={t("personas.not_applicable")}>-</span>;

  return (
    <div className="stack" style={{ gap: 14, maxWidth: 980 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("personas.intro")}</div>
      {/* No overflow wrapper here: it would become the scroll box and the header
          would stop sticking under the top bar while the page scrolls. */}
      <div>
        <table className="persona-matrix persona-matrix--rows">
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}></th>
              {personas.map((p) => (
                <th key={p.key}>
                  {p.builtin ? who(p) : (
                    <span className="inline" style={{ gap: 4, justifyContent: "center" }}>
                      <input style={{ width: 110 }} aria-label={t("a11y.persona_label")} value={p.label}
                             onChange={(e) => setLabel(p.key, e.target.value)} />
                      <button className="btn-ghost btn-sm" title={t("action.delete")}
                              aria-label={`${t("action.delete")} ${p.label}`}
                              onClick={() => removePersona(p.key)}>✕</button>
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="persona-group-row"><th colSpan={cols}>{t("personas.group_sections")}</th></tr>
            {caps.map((c) => (
              <tr key={c}>
                <td className="persona-option">{t(`cap.${c}`)}</td>
                {personas.map((p) => (
                  <td key={p.key}>
                    {cell(p, !!p.caps[c], (v) => setCap(p.key, c, v), t(`cap.${c}`), p.key === "admin" ? true : undefined)}
                  </td>
                ))}
              </tr>
            ))}
            {groups.map((g) => (
              <Fragment key={g.titleKey}>
                <tr className="persona-group-row"><th colSpan={cols}>{t("personas.group_admin")}{t("common.colon")}{t(g.titleKey)}</th></tr>
                {g.items.map((tab) => {
                  const label = t(TAB_LABEL[tab] ?? `admin.tab.${tab}`);
                  return (
                    <tr key={tab}>
                      <td className="persona-option">{label}</td>
                      {personas.map((p) => (
                        <td key={p.key}>
                          {adminOnly.has(tab) && p.key !== "admin" ? (
                            <span className="muted" title={t("personas.admin_only")}>{t("personas.admin_only_short")}</span>
                          ) : cell(p, (p.admin_tabs ?? []).includes(tab), (v) => setTab(p.key, tab, v), label,
                                   p.key === "admin" ? adminHas.has(tab) : undefined)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <div className="small muted">{t("personas.scope_hint")}</div>
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
  const [deletingTribe, setDeletingTribe] = useState<number | null>(null);

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead><tr><th>{t("admin.tribe")}</th><th>{t("admin.tribe_desc")}</th><th>{t("admin.tribe_leaders")}</th><th /></tr></thead>
          <tbody>
            {tribes.map((tr) => (
              <tr key={tr.id}>
                <td><input aria-label={t("admin.tribe")} defaultValue={tr.name} onBlur={(e) => {
                  // A tribe keeps a name: an emptied field is put back, not sent.
                  const v = e.target.value.trim();
                  if (!v) { e.target.value = tr.name; return; }
                  if (v !== tr.name) update(tr, { name: v });
                }} /></td>
                <td><input aria-label={t("admin.tribe_desc")} defaultValue={tr.description ?? ""} onBlur={(e) => e.target.value !== (tr.description ?? "") && update(tr, { description: e.target.value })} /></td>
                <td className="small">
                  {(tr as any).leaders?.length ? (tr as any).leaders.join(", ") : <span className="muted">{t("admin.tribe_no_leader")}</span>}
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {deletingTribe === tr.id ? (
                    <span className="inline" style={{ gap: 6 }}>
                      <span className="small">{t("admin.tribe_delete_confirm")}</span>
                      <button className="btn-danger btn-sm" onClick={() => { setDeletingTribe(null); remove(tr); }}>{t("action.delete")}</button>
                      <button className="btn-ghost btn-sm" onClick={() => setDeletingTribe(null)}>{t("action.cancel")}</button>
                    </span>
                  ) : (
                    <button className="btn-danger btn-sm" onClick={() => setDeletingTribe(tr.id)}>{t("action.delete")}</button>
                  )}
                </td>
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

  const ls = useLoadState();
  const loadTribe = () => {
    api.get<Tribe[]>("/api/tribes").then((list) => setTribe(list.find((tr) => tr.id === perms.tribe_id) ?? null)).catch(ls.fail);
  };
  useEffect(loadTribe, []);

  if (!perms.tribe_id) return <div className="banner">{t("admin.no_tribe_assigned")}</div>;
  if (!tribe) return ls.waiting(loadTribe);

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


