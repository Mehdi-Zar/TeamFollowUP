import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { AuditEntry, Role, Squad, Tribe, User } from "../types";
import { ErrorBanner } from "../components/ui";
import { ALL_ROLES } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";

type Tab = "tribes" | "squads" | "users" | "moderation" | "auth" | "smtp" | "logs" | "settings" | "audit";

export default function AdminPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("tribes");
  const tabs: Array<[Tab, string]> = [
    ["tribes", t("admin.tab.tribes")],
    ["squads", t("admin.tab.squads")],
    ["users", t("admin.tab.users")],
    ["moderation", t("admin.tab.moderation")],
    ["auth", t("admin.tab.auth")],
    ["smtp", t("admin.tab.smtp")],
    ["logs", t("admin.tab.logs")],
    ["settings", t("admin.tab.settings")],
    ["audit", t("admin.tab.audit")],
  ];

  useSetPageChrome(
    {
      title: t("admin.title"),
      tabs: tabs.map(([key, label]) => ({ key, label })),
      activeTab: tab,
      onTab: (k) => setTab(k as Tab),
    },
    [tab, t]
  );

  return (
    <div className="stack" style={{ gap: 16 }}>
      {tab === "tribes" && <TribesAdmin />}
      {tab === "squads" && <SquadsAdmin />}
      {tab === "users" && <UsersAdmin />}
      {tab === "moderation" && <ModerationAdmin />}
      {tab === "auth" && <AuthAdmin />}
      {tab === "smtp" && <SmtpAdmin />}
      {tab === "logs" && <LogExportAdmin />}
      {tab === "settings" && <SettingsAdmin />}
      {tab === "audit" && <AuditAdmin />}
    </div>
  );
}

function SmtpAdmin() {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const { error, wrap } = useErr();

  useEffect(() => { api.get<any>("/api/admin/smtp-config").then(setCfg); }, []);
  if (!cfg) return <div className="spinner">{t("common.loading")}</div>;
  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });
  const fld = (label: string, key: string, type = "text") => (
    <div style={{ flex: 1, minWidth: 200 }}>
      <label>{label}</label>
      <input type={type} value={cfg[key] ?? ""} onChange={(e) => set(key, e.target.value)} />
    </div>
  );

  async function save() {
    await wrap(async () => {
      const out = await api.put<any>("/api/admin/smtp-config", cfg);
      setCfg(out);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }
  async function test() {
    setTestMsg(null);
    try {
      const r = await api.post<any>("/api/admin/smtp-config/test", {});
      setTestMsg(r.ok ? t("smtp.test_ok") : t("smtp.test_fail"));
    } catch (e: any) {
      setTestMsg(e.message);
    }
  }

  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("smtp.intro")}</div>
      <div className="card stack" style={{ gap: 12 }}>
        <label className="switch">
          <input type="checkbox" checked={!!cfg.enabled} onChange={(e) => set("enabled", e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="strong">{t("smtp.enabled")}</span>
        </label>
        <div className="row">
          {fld("Hôte SMTP", "host")}
          <div style={{ width: 110 }}><label>Port</label><input type="number" value={cfg.port ?? 587} onChange={(e) => set("port", Number(e.target.value))} /></div>
        </div>
        <div className="row">
          {fld("Utilisateur", "username")}
          {fld("Mot de passe", "password", "password")}
        </div>
        <div className="row">
          {fld("Adresse d'expéditeur", "from_addr")}
          {fld("Nom d'expéditeur", "from_name")}
        </div>
        <div className="inline" style={{ gap: 18 }}>
          <label className="switch"><input type="checkbox" checked={!!cfg.use_tls} onChange={(e) => set("use_tls", e.target.checked)} /><span className="track"><span className="knob" /></span><span className="small">STARTTLS</span></label>
          <label className="switch"><input type="checkbox" checked={!!cfg.use_ssl} onChange={(e) => set("use_ssl", e.target.checked)} /><span className="track"><span className="knob" /></span><span className="small">SSL</span></label>
        </div>
      </div>
      <div className="inline">
        <button onClick={save}>{t("action.save")}</button>
        <button className="btn-secondary" onClick={test} disabled={!cfg.enabled}>{t("smtp.test")}</button>
        {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
        {testMsg && <span className="small muted">{testMsg}</span>}
      </div>
    </div>
  );
}

function LogExportAdmin() {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const { error, wrap } = useErr();

  useEffect(() => { api.get<any>("/api/admin/log-export-config").then(setCfg); }, []);
  if (!cfg) return <div className="spinner">{t("common.loading")}</div>;
  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });
  const dest = cfg.destination as string;

  const fld = (label: string, key: string, type = "text", placeholder = "") => (
    <div style={{ flex: 1, minWidth: 200 }}>
      <label>{label}</label>
      <input type={type} value={cfg[key] ?? ""} placeholder={placeholder} onChange={(e) => set(key, e.target.value)} />
    </div>
  );

  async function save() {
    await wrap(async () => {
      const out = await api.put<any>("/api/admin/log-export-config", cfg);
      setCfg(out);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }
  async function run(action: "test" | "flush") {
    setMsg(null);
    try {
      const r = await api.post<any>(`/api/admin/log-export-config/${action}`, {});
      setMsg({ ok: !!r.ok, text: r.message || (r.ok ? t("logs.run_ok") : t("logs.run_fail")) });
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    }
  }

  return (
    <div className="stack" style={{ maxWidth: 680 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("logs.intro")}</div>
      <div className="card stack" style={{ gap: 12 }}>
        <label className="switch">
          <input type="checkbox" checked={!!cfg.enabled} onChange={(e) => set("enabled", e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="strong">{t("logs.enabled")}</span>
        </label>

        <div style={{ maxWidth: 280 }}>
          <label>{t("logs.destination")}</label>
          <select value={dest} onChange={(e) => set("destination", e.target.value)}>
            <option value="syslog">{t("logs.dest.syslog")}</option>
            <option value="gcs">{t("logs.dest.gcs")}</option>
            <option value="bigquery">{t("logs.dest.bigquery")}</option>
          </select>
        </div>

        {dest === "syslog" && (
          <>
            <div className="row">
              {fld(t("logs.syslog_host"), "syslog_host", "text", "logs.example.com")}
              <div style={{ width: 110 }}>
                <label>{t("logs.port")}</label>
                <input type="number" value={cfg.syslog_port ?? 514} onChange={(e) => set("syslog_port", Number(e.target.value))} />
              </div>
            </div>
            <div className="row">
              <div style={{ width: 160 }}>
                <label>{t("logs.protocol")}</label>
                <select value={cfg.syslog_protocol} onChange={(e) => set("syslog_protocol", e.target.value)}>
                  <option value="udp">UDP</option>
                  <option value="tcp">TCP</option>
                </select>
              </div>
              {fld(t("logs.app_name"), "syslog_app_name")}
            </div>
          </>
        )}

        {dest === "gcs" && (
          <div className="row">
            {fld(t("logs.gcs_bucket"), "gcs_bucket", "text", "mon-bucket-logs")}
            {fld(t("logs.gcs_prefix"), "gcs_prefix", "text", "audit-logs")}
          </div>
        )}

        {dest === "bigquery" && (
          <div className="row">
            {fld(t("logs.bq_project"), "bq_project", "text", "mon-projet-gcp")}
            {fld(t("logs.bq_dataset"), "bq_dataset", "text", "observability")}
            {fld(t("logs.bq_table"), "bq_table", "text", "audit_log")}
          </div>
        )}

        {(dest === "gcs" || dest === "bigquery") && (
          <div>
            <label>
              {t("logs.gcp_creds")}
              {cfg.gcp_credentials_json_set && <span className="badge badge-green" style={{ marginLeft: 8 }}>{t("logs.creds_set")}</span>}
            </label>
            <textarea
              rows={4}
              placeholder={t("logs.gcp_creds_ph")}
              value={cfg.gcp_credentials_json ?? ""}
              onChange={(e) => set("gcp_credentials_json", e.target.value)}
            />
            <div className="small muted" style={{ marginTop: 4 }}>{t("logs.gcp_creds_hint")}</div>
          </div>
        )}
      </div>

      <div className="inline">
        <button onClick={save}>{t("action.save")}</button>
        <button className="btn-secondary" onClick={() => run("test")} disabled={!cfg.enabled}>{t("logs.test")}</button>
        <button className="btn-secondary" onClick={() => run("flush")} disabled={!cfg.enabled}>{t("logs.flush")}</button>
        {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
        {msg && <span className="small" style={{ color: msg.ok ? "var(--green)" : "var(--red)" }}>{msg.text}</span>}
      </div>
    </div>
  );
}

function TribesAdmin() {
  const { t } = useI18n();
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const { error, wrap } = useErr();
  const [form, setForm] = useState({ name: "", description: "" });

  async function load() {
    setTribes(await api.get<Tribe[]>("/api/tribes"));
  }
  useEffect(() => { load(); }, []);

  async function create() {
    await wrap(async () => {
      await api.post("/api/tribes", { name: form.name, description: form.description || null });
      setForm({ name: "", description: "" });
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
                <td><input defaultValue={tr.name} onBlur={(e) => e.target.value !== tr.name && update(tr, { name: e.target.value })} /></td>
                <td><input defaultValue={tr.description ?? ""} onBlur={(e) => e.target.value !== (tr.description ?? "") && update(tr, { description: e.target.value })} /></td>
                <td style={{ textAlign: "right" }}><button className="btn-danger btn-sm" onClick={() => remove(tr)}>{t("action.delete")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h3>{t("admin.new_tribe")}</h3>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ width: 240 }}><label>{t("admin.name")}</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div className="col"><label>{t("admin.tribe_desc")}</label><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
          <button onClick={create} disabled={!form.name.trim()}>{t("admin.create")}</button>
        </div>
      </div>
    </div>
  );
}

function ModerationAdmin() {
  const { t, formatDateTime } = useI18n();
  const [posts, setPosts] = useState<any[]>([]);
  function load() {
    api.get<any[]>("/api/feed").then(setPosts).catch(() => {});
  }
  useEffect(() => { load(); }, []);
  async function delPost(id: number) { await api.del(`/api/feed/${id}`); load(); }
  async function delReply(id: number) { await api.del(`/api/feed/replies/${id}`); load(); }
  async function pin(p: any) { await api.put(`/api/feed/${p.id}/pin`, { is_pinned: !p.is_pinned }); load(); }

  return (
    <div className="stack">
      <div className="banner">{t("mod.title")}</div>
      {posts.length === 0 && <div className="card muted">{t("mod.none")}</div>}
      {posts.map((p) => (
        <div key={p.id} className={`card feed-post k-${p.kind}`}>
          <div className="between">
            <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
              <span className={`feed-kind k-${p.kind}`}>{t(`feed.kind.${p.kind}`)}</span>
              <span className="strong">{p.author?.display_name || "?"}</span>
              {p.squad_name && <span className="pill-cat">{p.squad_name}</span>}
              {p.is_pinned && <span className="badge badge-navy">{t("feed.pinned")}</span>}
              <span className="small muted">{formatDateTime(p.created_at)}</span>
            </div>
            <div className="inline" style={{ gap: 6 }}>
              <button className="btn-secondary btn-sm" onClick={() => pin(p)}>{p.is_pinned ? t("feed.unpin") : t("feed.pin")}</button>
              <button className="btn-danger btn-sm" onClick={() => delPost(p.id)}>{t("action.delete")}</button>
            </div>
          </div>
          <div style={{ marginTop: 6 }}>{p.content}</div>
          {p.replies.length > 0 && (
            <div className="stack" style={{ marginTop: 8, gap: 6 }}>
              {p.replies.map((r: any) => (
                <div key={r.id} className="feed-reply between">
                  <span className="small"><span className="strong">{r.author?.display_name || "?"}</span> · {r.content}</span>
                  <button className="btn-ghost btn-sm" onClick={() => delReply(r.id)}>✕</button>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function AuthAdmin() {
  const { t, role: roleLabel } = useI18n();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();
  const roles = ["admin", "tribe_leader", "squad_leader", "member"];

  useEffect(() => {
    api.get<any>("/api/admin/auth-config").then(setCfg);
  }, []);
  if (!cfg) return <div className="spinner">{t("common.loading")}</div>;

  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });
  const fld = (label: string, key: string, type = "text") => (
    <div style={{ flex: 1, minWidth: 220 }}>
      <label>{label}</label>
      <input type={type} value={cfg[key] ?? ""} onChange={(e) => set(key, e.target.value)} />
    </div>
  );

  const mappings: Array<{ group: string; role: string }> = cfg.group_role_mappings || [];
  const setMapping = (i: number, patch: any) => {
    const next = mappings.map((m, j) => (j === i ? { ...m, ...patch } : m));
    set("group_role_mappings", next);
  };

  async function save() {
    await wrap(async () => {
      const out = await api.put<any>("/api/admin/auth-config", cfg);
      setCfg(out);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("auth.intro")}</div>

      <div className="card">
        <label className="switch" style={{ marginBottom: 10 }}>
          <input type="checkbox" checked={!!cfg.oidc_enabled} onChange={(e) => set("oidc_enabled", e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="strong">OIDC</span>
        </label>
        <div className="row">
          {fld("Issuer URL", "oidc_issuer_url")}
          {fld("Client ID", "oidc_client_id")}
        </div>
        <div className="row">
          {fld("Client secret", "oidc_client_secret", "password")}
          {fld("Redirect URI", "oidc_redirect_uri")}
        </div>
        <div className="row">
          {fld("Scopes", "oidc_scopes")}
          {fld("Groups claim", "oidc_groups_claim")}
        </div>
      </div>

      <div className="card">
        <label className="switch" style={{ marginBottom: 10 }}>
          <input type="checkbox" checked={!!cfg.saml_enabled} onChange={(e) => set("saml_enabled", e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="strong">SAML (PingFederate)</span>
        </label>
        <div className="row">
          {fld("IdP metadata URL", "saml_idp_metadata_url")}
          {fld("SP entity ID", "saml_sp_entity_id")}
        </div>
        <div className="row">
          {fld("ACS URL", "saml_acs_url")}
          {fld("Groups attribute", "saml_groups_attr")}
        </div>
        <div className="small muted" style={{ marginTop: 6 }}>
          {t("auth.test")} : <a href="/api/auth/saml/metadata" target="_blank">/api/auth/saml/metadata</a>
        </div>
      </div>

      <div className="card">
        <h3>{t("auth.mappings")}</h3>
        <div className="small muted" style={{ marginBottom: 10 }}>{t("auth.mappings_hint")}</div>
        {mappings.map((m, i) => (
          <div key={i} className="item-row">
            <input className="grow" placeholder={t("auth.group")} value={m.group} onChange={(e) => setMapping(i, { group: e.target.value })} />
            <select className="w-auto" value={m.role} onChange={(e) => setMapping(i, { role: e.target.value })}>
              {roles.map((r) => (<option key={r} value={r}>{roleLabel(r)}</option>))}
            </select>
            <button className="btn-danger btn-sm" onClick={() => set("group_role_mappings", mappings.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button className="btn-secondary btn-sm" style={{ marginTop: 8 }} onClick={() => set("group_role_mappings", [...mappings, { group: "", role: "member" }])}>
          {t("auth.add_mapping")}
        </button>
      </div>

      <div className="inline">
        <button onClick={save}>{t("auth.save")}</button>
        {saved && <span style={{ color: "var(--green)" }}>{t("auth.saved")}</span>}
      </div>
    </div>
  );
}

function useErr() {
  const [error, setError] = useState<string | null>(null);
  const wrap = async (fn: () => Promise<void>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  };
  return { error, wrap };
}

function SquadsAdmin() {
  const { t } = useI18n();
  const [squads, setSquads] = useState<Squad[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const { error, wrap } = useErr();
  const [form, setForm] = useState({ name: "", leader_user_id: "", tribe_id: "" });

  async function load() {
    setSquads(await api.get<Squad[]>("/api/squads"));
    setUsers(await api.get<User[]>("/api/admin/users"));
    setTribes(await api.get<Tribe[]>("/api/tribes"));
  }
  useEffect(() => {
    load();
  }, []);

  const leaders = users.filter((u) => u.role === "squad_leader" || u.role === "tribe_leader" || u.role === "admin");
  const tribeName = (id: number) => tribes.find((tr) => tr.id === id)?.name || "—";

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
              <tr key={s.id}>
                <td className="strong">{s.name}</td>
                <td>
                  <select className="w-auto" value={s.tribe_id} onChange={(e) => update(s, { tribe_id: Number(e.target.value) } as any)}>
                    {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
                  </select>
                </td>
                <td>
                  <select className="w-auto" value={s.leader_user_id ?? ""} onChange={(e) => update(s, { leader_user_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">—</option>
                    {leaders.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.display_name}
                      </option>
                    ))}
                  </select>
                </td>
                <td style={{ width: 90 }}>
                  <input type="number" defaultValue={s.display_order} onBlur={(e) => Number(e.target.value) !== s.display_order && update(s, { display_order: Number(e.target.value) })} />
                </td>
                <td style={{ textAlign: "right" }}>
                  <button className="btn-danger btn-sm" onClick={() => remove(s)}>
                    {t("action.delete")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>{t("admin.new_squad")}</h3>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ width: 200 }}>
            <label>{t("admin.name")}</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div style={{ width: 200 }}>
            <label>{t("admin.tribe")}</label>
            <select value={form.tribe_id} onChange={(e) => setForm({ ...form, tribe_id: e.target.value })}>
              <option value="">—</option>
              {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
            </select>
          </div>
          <div style={{ width: 200 }}>
            <label>{t("admin.responsible")}</label>
            <select value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
              <option value="">—</option>
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

function UsersAdmin() {
  const { t, role: roleLabel, formatDateTime } = useI18n();
  const [users, setUsers] = useState<User[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const { error, wrap } = useErr();
  const [form, setForm] = useState({ email: "", display_name: "", role: "member" as Role, password: "", tribe_id: "" });

  async function load() {
    setUsers(await api.get<User[]>("/api/admin/users"));
    setTribes(await api.get<Tribe[]>("/api/tribes"));
  }
  useEffect(() => {
    load();
  }, []);

  async function create() {
    await wrap(async () => {
      await api.post("/api/admin/users", {
        email: form.email, display_name: form.display_name, role: form.role,
        tribe_id: form.tribe_id ? Number(form.tribe_id) : null, password: form.password || null,
      });
      setForm({ email: "", display_name: "", role: "member", password: "", tribe_id: "" });
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
    const pw = prompt(`${t("admin.password")} — ${u.display_name}`);
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
                  <select className="w-auto" value={u.role} disabled={u.is_break_glass} onChange={(e) => update(u, { role: e.target.value as Role })}>
                    {ALL_ROLES.map((r) => (
                      <option key={r} value={r}>
                        {roleLabel(r)}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <select className="w-auto" value={u.tribe_id ?? ""} onChange={(e) => update(u, { tribe_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">{t("admin.no_tribe")}</option>
                    {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
                  </select>
                </td>
                <td className="muted">{formatDateTime(u.last_login_at)}</td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <button className="btn-secondary btn-sm" onClick={() => resetPassword(u)} style={{ marginRight: 6 }}>
                    {t("admin.password")}
                  </button>
                  {!u.is_break_glass && (
                    <button className="btn-danger btn-sm" onClick={() => remove(u)}>
                      {t("action.delete")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>{t("admin.new_user")}</h3>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ width: 180 }}>
            <label>{t("admin.name")}</label>
            <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </div>
          <div style={{ width: 200 }}>
            <label>{t("admin.email")}</label>
            <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div style={{ width: 150 }}>
            <label>{t("admin.role")}</label>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ALL_ROLES.map((r) => (
                <option key={r} value={r}>
                  {roleLabel(r)}
                </option>
              ))}
            </select>
          </div>
          <div style={{ width: 160 }}>
            <label>{t("admin.tribe")}</label>
            <select value={form.tribe_id} onChange={(e) => setForm({ ...form, tribe_id: e.target.value })}>
              <option value="">{t("admin.no_tribe")}</option>
              {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
            </select>
          </div>
          <div style={{ width: 150 }}>
            <label>{t("admin.password_local")}</label>
            <input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          <button onClick={create} disabled={!form.email.trim() || !form.display_name.trim()}>
            {t("admin.create")}
          </button>
        </div>
      </div>
    </div>
  );
}

function SettingsAdmin() {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  useEffect(() => {
    api.get<any>("/api/admin/settings").then(setCfg);
  }, []);
  if (!cfg) return <div className="spinner">{t("common.loading")}</div>;
  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });

  async function save() {
    await wrap(async () => {
      const out = await api.put<any>("/api/admin/settings", cfg);
      setCfg(out);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }

  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      {error && <ErrorBanner message={error} />}

      <div className="card">
        <h3>{t("set.section.brand")}</h3>
        <div className="row">
          <div className="col"><label>{t("set.app_name")}</label><input value={cfg.app_name ?? ""} onChange={(e) => set("app_name", e.target.value)} /></div>
          <div className="col"><label>{t("set.app_subtitle")}</label><input value={cfg.app_subtitle ?? ""} onChange={(e) => set("app_subtitle", e.target.value)} /></div>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <div style={{ width: 200 }}>
            <label>{t("set.lang")}</label>
            <select value={cfg.default_lang} onChange={(e) => set("default_lang", e.target.value)}>
              <option value="fr">Français</option>
              <option value="en">English</option>
            </select>
          </div>
          <div style={{ width: 160 }}>
            <label>{t("set.year")}</label>
            <input type="number" value={cfg.default_year ?? ""} onChange={(e) => set("default_year", Number(e.target.value))} />
          </div>
        </div>
      </div>

      <div className="card">
        <h3>{t("set.section.fresh")}</h3>
        <div className="small muted" style={{ marginBottom: 8 }}>{t("admin.threshold_hint")}</div>
        <div style={{ width: 160 }}>
          <label>{t("admin.days")}</label>
          <input type="number" min={1} max={365} value={cfg.staleness_threshold_days ?? ""} onChange={(e) => set("staleness_threshold_days", Number(e.target.value))} />
        </div>
      </div>

      <div className="card">
        <h3>{t("set.section.feed")}</h3>
        <div className="row">
          <div style={{ width: 240 }}>
            <label>{t("set.feed_scope")}</label>
            <select value={cfg.feed_post_scope} onChange={(e) => set("feed_post_scope", e.target.value)}>
              <option value="leaders">{t("set.feed_scope.leaders")}</option>
              <option value="everyone">{t("set.feed_scope.everyone")}</option>
            </select>
          </div>
          <div style={{ width: 240 }}>
            <label>{t("set.feed_retention")}</label>
            <input type="number" min={0} value={cfg.feed_retention_days ?? 0} onChange={(e) => set("feed_retention_days", Number(e.target.value))} />
          </div>
        </div>
      </div>

      <div className="inline">
        <button onClick={save}>{t("action.save")}</button>
        {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
      </div>
    </div>
  );
}

function AuditAdmin() {
  const { t, formatDateTime } = useI18n();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  useEffect(() => {
    api.get<AuditEntry[]>("/api/audit-log").then(setEntries).catch(() => {});
  }, []);
  return (
    <div className="card" style={{ padding: 0, overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>{t("admin.ts")}</th>
            <th>{t("admin.user_col")}</th>
            <th>{t("admin.action")}</th>
            <th>{t("admin.entity")}</th>
            <th>{t("admin.detail")}</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id}>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>{formatDateTime(e.timestamp)}</td>
              <td>{e.user_id ?? "—"}</td>
              <td style={{ fontFamily: "monospace", fontSize: 12 }}>{e.action}</td>
              <td className="muted">{e.entity ? `${e.entity}${e.entity_id ? ` #${e.entity_id}` : ""}` : "—"}</td>
              <td className="muted small" style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {e.detail ? JSON.stringify(e.detail) : "—"}
              </td>
            </tr>
          ))}
          {entries.length === 0 && (
            <tr>
              <td className="muted" colSpan={5}>
                {t("admin.no_audit")}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
