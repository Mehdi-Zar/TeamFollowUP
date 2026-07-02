import { Fragment, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useModule, useReloadConfig } from "../config";
import { useAuth } from "../auth";
import { AuditEntry, LeaveConfig, LeaveType, ModuleKey, Permissions, Persona, Role, Squad, SquadDetail, Tribe, User } from "../types";
import { ErrorBanner, Spinner, Dot } from "../components/ui";
import { ADMIN_TABS_BY_ROLE, ALL_ROLES } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";

// Label key for each admin tab (server decides which a role may open).
const TAB_LABEL: Record<string, string> = {
  tribes: "admin.tab.tribes",
  tribe: "admin.tab.my_tribe",
  squads: "admin.tab.squads",
  users: "admin.tab.users",
  personas: "admin.tab.personas",
  my_squads: "admin.tab.my_squads",
  modules: "admin.tab.modules",
  moderation: "admin.tab.moderation",
  auth: "admin.tab.auth",
  smtp: "admin.tab.smtp",
  tls: "admin.tab.tls",
  report: "admin.tab.report",
  leaves: "admin.tab.leaves",
  logs: "admin.tab.logs",
  settings: "admin.tab.settings",
  audit: "admin.tab.audit",
};

// Admin sections grouped by purpose (only the items a role may open are shown).
const ADMIN_GROUPS: { titleKey: string; items: string[] }[] = [
  { titleKey: "admin.group.org", items: ["tribes", "tribe", "squads", "my_squads", "users", "personas"] },
  { titleKey: "admin.group.config", items: ["modules", "report", "leaves", "settings"] },
  { titleKey: "admin.group.access", items: ["auth", "smtp", "tls"] },
  { titleKey: "admin.group.oversight", items: ["moderation", "logs", "audit"] },
];

export default function AdminPage() {
  const { t } = useI18n();
  const { effectiveRole } = useAuth();
  const [perms, setPerms] = useState<Permissions | null>(null);
  const [tab, setTab] = useState<string>("");
  const [params] = useSearchParams();

  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    api.get<Permissions>("/api/auth/me/permissions")
      .then((p) => setPerms(p))
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Erreur"));
  }, []);

  // When an admin previews another role, reflect that role's scoped tab set
  // (the backend still enforces the real account's permissions on every call).
  const tabKeys =
    perms && effectiveRole && effectiveRole !== perms.role
      ? ADMIN_TABS_BY_ROLE[effectiveRole] ?? []
      : perms?.admin_tabs ?? [];

  useEffect(() => {
    const want = params.get("section");
    setTab((cur) => {
      if (want && tabKeys.includes(want)) return want;
      return cur && tabKeys.includes(cur) ? cur : tabKeys[0] ?? "";
    });
  }, [tabKeys.join(","), params]);
  useSetPageChrome({ title: t("admin.title") }, [perms, t]);

  if (loadError) return <ErrorBanner message={loadError} />;
  if (!perms) return <Spinner />;

  // Keep only groups/items the current role may open; drop empty groups.
  const groups = ADMIN_GROUPS
    .map((g) => ({ ...g, items: g.items.filter((k) => tabKeys.includes(k)) }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="admin-layout">
      <nav className="admin-nav" aria-label={t("admin.title")}>
        {groups.map((g) => (
          <div key={g.titleKey} className="admin-nav-group">
            <div className="admin-nav-title">{t(g.titleKey)}</div>
            {g.items.map((k) => (
              <button key={k} className={`admin-nav-item ${tab === k ? "active" : ""}`}
                      onClick={() => setTab(k)} aria-current={tab === k ? "page" : undefined}>
                {t(TAB_LABEL[k] ?? k)}
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="admin-content stack" style={{ gap: 16 }}>
        {tab === "tribes" && <TribesAdmin />}
        {tab === "tribe" && <TribeSelfAdmin perms={perms} />}
        {tab === "squads" && <SquadsAdmin perms={perms} />}
        {tab === "users" && <UsersAdmin perms={perms} />}
        {tab === "personas" && <PersonasAdmin />}
        {tab === "my_squads" && <MySquadsAdmin />}
        {tab === "modules" && <ModulesAdmin />}
        {tab === "report" && <ReportingAdmin />}
        {tab === "leaves" && <LeavesAdmin perms={perms} />}
        {tab === "moderation" && <ModerationAdmin />}
        {tab === "auth" && <AuthAdmin />}
        {tab === "smtp" && <SmtpAdmin />}
        {tab === "tls" && <TlsAdmin />}
        {tab === "logs" && <LogExportAdmin />}
        {tab === "settings" && <SettingsAdmin />}
        {tab === "audit" && <AuditAdmin />}
      </div>
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

function TlsAdmin() {
  const { t } = useI18n();
  const [st, setSt] = useState<any | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const { error, wrap } = useErr();

  // Self-signed form
  const [cn, setCn] = useState("localhost");
  const [sans, setSans] = useState("localhost, 127.0.0.1");
  // PEM import
  const [certFile, setCertFile] = useState<File | null>(null);
  const [keyFile, setKeyFile] = useState<File | null>(null);
  const [certText, setCertText] = useState("");
  const [keyText, setKeyText] = useState("");
  const [pemPass, setPemPass] = useState("");
  // PFX import
  const [pfxFile, setPfxFile] = useState<File | null>(null);
  const [pfxPass, setPfxPass] = useState("");
  // CA add
  const [caFile, setCaFile] = useState<File | null>(null);
  const [caName, setCaName] = useState("");

  const load = () => api.get<any>("/api/admin/tls-config").then(setSt);
  useEffect(() => { load(); }, []);
  if (!st) return <div className="spinner">{t("common.loading")}</div>;

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 2500); };

  async function toggleRedirect(v: boolean) {
    await wrap(async () => { setSt(await api.put<any>("/api/admin/tls-config", { redirect_http: v })); });
  }
  async function regen() {
    await wrap(async () => {
      setSt(await api.post<any>("/api/admin/tls-config/self-signed", { cn, sans }));
      flash(t("tls.applied"));
    });
  }
  async function importPem() {
    await wrap(async () => {
      const f = new FormData();
      if (certFile) f.append("cert", certFile); else f.append("cert_pem", certText);
      if (keyFile) f.append("key", keyFile); else f.append("key_pem", keyText);
      if (pemPass) f.append("passphrase", pemPass);
      setSt(await api.postForm<any>("/api/admin/tls-config/import-pem", f));
      setCertFile(null); setKeyFile(null); setCertText(""); setKeyText(""); setPemPass("");
      flash(t("tls.applied"));
    });
  }
  async function importPfx() {
    await wrap(async () => {
      if (!pfxFile) throw new Error(t("tls.pfx_required"));
      const f = new FormData();
      f.append("file", pfxFile);
      if (pfxPass) f.append("password", pfxPass);
      setSt(await api.postForm<any>("/api/admin/tls-config/import-pfx", f));
      setPfxFile(null); setPfxPass("");
      flash(t("tls.applied"));
    });
  }
  async function addCa() {
    await wrap(async () => {
      const f = new FormData();
      if (caFile) f.append("ca", caFile); else throw new Error(t("tls.ca_required"));
      if (caName) f.append("name", caName);
      setSt(await api.postForm<any>("/api/admin/tls-config/ca", f));
      setCaFile(null); setCaName("");
      flash(t("tls.applied"));
    });
  }
  async function removeCa(id: string) {
    await wrap(async () => { setSt(await api.del<any>(`/api/admin/tls-config/ca/${id}`)); });
  }

  const a = st.active || {};
  const expClass = a.expired ? "badge-red" : (a.days_remaining != null && a.days_remaining < 30 ? "badge-orange" : "badge-green");

  const caRow = (c: any) => (
    <div key={c.id} className="card stack" style={{ gap: 4, padding: 10 }}>
      <div className="between">
        <span className="strong">{c.name}</span>
        <span className={`badge ${c.kind === "root" ? "badge-navy" : "badge-grey"}`}>{t(`tls.kind.${c.kind}`)}</span>
      </div>
      <div className="small muted">{t("tls.issuer")}: {c.issuer}</div>
      <div className="small muted">{t("tls.expires")}: {c.not_after?.slice(0, 10)}</div>
      <div className="inline" style={{ gap: 8 }}>
        <a className="btn-secondary btn-sm" href={`/api/admin/tls-config/ca/${c.id}/download`}>{t("tls.download")}</a>
        <button className="btn-danger btn-sm" onClick={() => removeCa(c.id)}>{t("action.delete")}</button>
      </div>
    </div>
  );

  return (
    <div className="stack" style={{ maxWidth: 760 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("tls.intro")}</div>

      {/* Active certificate */}
      <div className="card stack" style={{ gap: 8 }}>
        <div className="between">
          <span className="strong">{t("tls.active")}</span>
          <span className="inline" style={{ gap: 8 }}>
            <span className={`badge ${st.mode === "self_signed" ? "badge-orange" : "badge-green"}`}>
              {t(st.mode === "self_signed" ? "tls.mode.self_signed" : "tls.mode.custom")}
            </span>
            {a.days_remaining != null && <span className={`badge ${expClass}`}>{t("tls.days_left", { n: a.days_remaining })}</span>}
          </span>
        </div>
        {a.error ? <div className="small" style={{ color: "var(--red)" }}>{a.error}</div> : (
          <div className="stack" style={{ gap: 2 }}>
            <div className="small"><b>{t("tls.subject")}:</b> {a.subject}</div>
            <div className="small"><b>{t("tls.issuer")}:</b> {a.issuer}</div>
            <div className="small"><b>SAN:</b> {(a.sans || []).join(", ") || "—"}</div>
            <div className="small"><b>{t("tls.valid_until")}:</b> {a.not_after?.slice(0, 10)}</div>
            <div className="small muted" style={{ wordBreak: "break-all" }}><b>SHA-256:</b> {a.fingerprint_sha256}</div>
            {st.chain_len > 0 && <div className="small muted">{t("tls.chain_len", { n: st.chain_len })}</div>}
          </div>
        )}
        <div className="inline">
          <a className="btn-secondary btn-sm" href="/api/admin/tls-config/active/download">{t("tls.download_active")}</a>
        </div>
      </div>

      {/* Options */}
      <div className="card stack" style={{ gap: 10 }}>
        <label className="switch">
          <input type="checkbox" checked={!!st.redirect_http} onChange={(e) => toggleRedirect(e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="strong">{t("tls.redirect_http")}</span>
        </label>
        <div className="small muted">{t("tls.redirect_hint")}</div>
      </div>

      {/* Self-signed */}
      <div className="card stack" style={{ gap: 10 }}>
        <span className="strong">{t("tls.self_signed_title")}</span>
        <div className="small muted">{t("tls.self_signed_hint")}</div>
        <div className="row">
          <div style={{ flex: 1, minWidth: 180 }}><label>{t("tls.cn")}</label>
            <input value={cn} onChange={(e) => setCn(e.target.value)} /></div>
          <div style={{ flex: 2, minWidth: 220 }}><label>{t("tls.sans")}</label>
            <input value={sans} onChange={(e) => setSans(e.target.value)} placeholder="host.example.com, 10.0.0.5" /></div>
        </div>
        <div><button className="btn-secondary" onClick={regen}>{t("tls.generate")}</button></div>
      </div>

      {/* Import PEM */}
      <div className="card stack" style={{ gap: 10 }}>
        <span className="strong">{t("tls.import_pem_title")}</span>
        <div className="small muted">{t("tls.import_pem_hint")}</div>
        <div className="row">
          <div style={{ flex: 1, minWidth: 220 }}>
            <label>{t("tls.cert_file")}</label>
            <input type="file" accept=".pem,.crt,.cer" onChange={(e) => setCertFile(e.target.files?.[0] ?? null)} />
          </div>
          <div style={{ flex: 1, minWidth: 220 }}>
            <label>{t("tls.key_file")}</label>
            <input type="file" accept=".pem,.key" onChange={(e) => setKeyFile(e.target.files?.[0] ?? null)} />
          </div>
        </div>
        {!certFile && <textarea rows={4} placeholder={t("tls.cert_paste")} value={certText} onChange={(e) => setCertText(e.target.value)} style={{ fontFamily: "monospace", fontSize: 12 }} />}
        {!keyFile && <textarea rows={4} placeholder={t("tls.key_paste")} value={keyText} onChange={(e) => setKeyText(e.target.value)} style={{ fontFamily: "monospace", fontSize: 12 }} />}
        <div className="row">
          <div style={{ width: 260 }}><label>{t("tls.key_passphrase")}</label>
            <input type="password" value={pemPass} onChange={(e) => setPemPass(e.target.value)} /></div>
        </div>
        <div><button onClick={importPem}>{t("tls.install")}</button></div>
      </div>

      {/* Import PFX */}
      <div className="card stack" style={{ gap: 10 }}>
        <span className="strong">{t("tls.import_pfx_title")}</span>
        <div className="small muted">{t("tls.import_pfx_hint")}</div>
        <div className="row">
          <div style={{ flex: 1, minWidth: 220 }}>
            <label>{t("tls.pfx_file")}</label>
            <input type="file" accept=".pfx,.p12" onChange={(e) => setPfxFile(e.target.files?.[0] ?? null)} />
          </div>
          <div style={{ width: 260 }}><label>{t("tls.pfx_password")}</label>
            <input type="password" value={pfxPass} onChange={(e) => setPfxPass(e.target.value)} /></div>
        </div>
        <div><button onClick={importPfx}>{t("tls.install")}</button></div>
      </div>

      {/* CA store */}
      <div className="card stack" style={{ gap: 10 }}>
        <span className="strong">{t("tls.ca_title")}</span>
        <div className="small muted">{t("tls.ca_hint")}</div>
        <div className="stack" style={{ gap: 6 }}>
          <div className="small strong">{t("tls.roots")}</div>
          {st.roots?.length ? st.roots.map(caRow) : <div className="small muted">{t("tls.none")}</div>}
          <div className="small strong" style={{ marginTop: 8 }}>{t("tls.intermediates")}</div>
          {st.intermediates?.length ? st.intermediates.map(caRow) : <div className="small muted">{t("tls.none")}</div>}
        </div>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <label>{t("tls.ca_file")}</label>
            <input type="file" accept=".pem,.crt,.cer" onChange={(e) => setCaFile(e.target.files?.[0] ?? null)} />
          </div>
          <div style={{ flex: 1, minWidth: 180 }}>
            <label>{t("tls.ca_name")}</label>
            <input value={caName} onChange={(e) => setCaName(e.target.value)} />
          </div>
          <button className="btn-secondary" onClick={addCa}>{t("tls.add_ca")}</button>
        </div>
      </div>

      {msg && <div className="small" style={{ color: "var(--green)" }}>{msg}</div>}
    </div>
  );
}

const MODULE_TREE: { key: ModuleKey; features: string[] }[] = [
  { key: "dashboard", features: [] },
  { key: "org", features: [] },
  { key: "reporting", features: [] },
  { key: "feed", features: ["reactions", "replies", "pin", "kinds"] },
  { key: "review", features: ["weekly_report"] },
  { key: "squad_content", features: ["objectives", "roadmap", "kpis"] },
  { key: "committees", features: [] },
  { key: "notifications", features: ["inapp", "email"] },
  { key: "exports_csv", features: [] },
  { key: "getting_started", features: [] },
  { key: "leaves", features: ["overlap_alert"] },
];

function ModulesAdmin() {
  const { t } = useI18n();
  const reloadConfig = useReloadConfig();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  useEffect(() => { api.get<any>("/api/admin/modules-config").then(setCfg); }, []);
  if (!cfg) return <div className="spinner">{t("common.loading")}</div>;

  async function apply(next: any) {
    setCfg(next);
    await wrap(async () => {
      const out = await api.put<any>("/api/admin/modules-config", next);
      setCfg(out);
      reloadConfig();
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    });
  }
  const setModule = (key: string, enabled: boolean) => apply({ ...cfg, [key]: { ...cfg[key], enabled } });
  const setFeature = (key: string, feat: string, val: boolean) =>
    apply({ ...cfg, [key]: { ...cfg[key], [feat]: val } });

  const Switch = ({ checked, onChange, label, strong }: any) => (
    <label className="switch">
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track"><span className="knob" /></span>
      <span className={strong ? "strong" : "small"}>{label}</span>
    </label>
  );

  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("modules.intro")}</div>
      <div className="stack" style={{ gap: 12 }}>
        {MODULE_TREE.map(({ key, features }) => {
          const mod = cfg[key] || {};
          const on = mod.enabled !== false;
          return (
            <div key={key} className="card stack" style={{ gap: 10, opacity: on ? 1 : 0.7 }}>
              <div className="between">
                <Switch checked={on} strong label={t(`mod.${key}`)} onChange={(v: boolean) => setModule(key, v)} />
                {!on && <span className="badge badge-red">{t("modules.off")}</span>}
              </div>
              {features.length > 0 && (
                <div className="small muted">{t(`mod.${key}.desc`)}</div>
              )}
              {features.length > 0 && on && (
                <div className="stack" style={{ gap: 8, paddingLeft: 14, borderLeft: "2px solid var(--line)" }}>
                  {features.map((f) => (
                    <Switch key={f} checked={mod[f] !== false} label={t(`mod.${key}.${f}`)}
                            onChange={(v: boolean) => setFeature(key, f, v)} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {saved && <div className="small" style={{ color: "var(--green)" }}>{t("admin.saved")}</div>}
    </div>
  );
}

/* ---------- Leave / absence administration ---------- */
function LeavesAdmin({ perms }: { perms: Permissions }) {
  const isAdmin = perms.role === "admin";
  return (
    <div className="stack" style={{ gap: 20, maxWidth: 760 }}>
      <LeaveSettingsAdmin isAdmin={isAdmin} />
      {isAdmin && <LeaveTypesAdmin />}
    </div>
  );
}

function LeaveSettingsAdmin({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useI18n();
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeId, setTribeId] = useState<number | "">("");
  const [cfg, setCfg] = useState<LeaveConfig | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  useEffect(() => {
    if (isAdmin) {
      api.get<Tribe[]>("/api/tribes").then((ts) => { setTribes(ts); if (ts[0]) setTribeId(ts[0].id); }).catch(() => {});
    } else {
      wrap(async () => setCfg(await api.get<LeaveConfig>("/api/leaves/config")));
    }
  }, [isAdmin]);
  useEffect(() => {
    if (isAdmin && tribeId !== "") api.get<LeaveConfig>(`/api/leaves/config?tribe_id=${tribeId}`).then(setCfg).catch(() => setCfg(null));
  }, [isAdmin, tribeId]);

  async function save() {
    if (!cfg) return;
    const qs = isAdmin && tribeId !== "" ? `?tribe_id=${tribeId}` : "";
    await wrap(async () => {
      const out = await api.put<LeaveConfig>(`/api/leaves/config${qs}`,
        { require_approval: cfg.require_approval, overlap_threshold: cfg.overlap_threshold });
      setCfg(out); setSaved(true); setTimeout(() => setSaved(false), 1500);
    });
  }

  return (
    <div className="card stack" style={{ gap: 14 }}>
      <h2 style={{ margin: 0 }}>{t("leaves.admin_settings")}</h2>
      {error && <ErrorBanner message={error} />}
      {isAdmin && (
        <div style={{ maxWidth: 300 }}>
          <label className="field-label">{t("leaves.tribe_pick")}</label>
          <select value={tribeId} onChange={(e) => setTribeId(Number(e.target.value))}>
            {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
          </select>
        </div>
      )}
      {cfg && (
        <>
          <label className="switch">
            <input type="checkbox" checked={cfg.require_approval}
                   onChange={(e) => setCfg({ ...cfg, require_approval: e.target.checked })} />
            <span className="track"><span className="knob" /></span>
            <span className="strong">{t("leaves.require_approval")}</span>
          </label>
          <div style={{ maxWidth: 300 }}>
            <label className="field-label">{t("leaves.overlap_threshold")}</label>
            <input type="number" min={1} max={99} value={cfg.overlap_threshold}
                   onChange={(e) => setCfg({ ...cfg, overlap_threshold: Number(e.target.value) })} />
          </div>
          <div className="inline">
            <button onClick={save}>{t("action.save")}</button>
            {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
          </div>
        </>
      )}
    </div>
  );
}

function LeaveTypesAdmin() {
  const { t } = useI18n();
  const [types, setTypes] = useState<LeaveType[]>([]);
  const { error, wrap } = useErr();
  const load = () => api.get<LeaveType[]>("/api/leaves/types?include_inactive=true").then(setTypes).catch(() => {});
  useEffect(() => { load(); }, []);

  const upd = (id: number, patch: Partial<LeaveType>) =>
    setTypes((ts) => ts.map((x) => (x.id === id ? { ...x, ...patch } : x)));

  async function addType() {
    await wrap(async () => {
      await api.post("/api/leaves/types", { label: t("leaves.add_type"), color: "#6B7280", display_order: types.length + 1 });
      load();
    });
  }
  async function saveType(tp: LeaveType) {
    await wrap(async () => {
      await api.put(`/api/leaves/types/${tp.id}`,
        { label: tp.label, color: tp.color, display_order: tp.display_order, is_active: tp.is_active, requires_detail: tp.requires_detail });
      load();
    });
  }
  async function delType(id: number) {
    if (!confirm(t("leaves.delete_confirm"))) return;
    await wrap(async () => { await api.del(`/api/leaves/types/${id}`); load(); });
  }

  return (
    <div className="card stack" style={{ gap: 12 }}>
      <div className="between">
        <h2 style={{ margin: 0 }}>{t("leaves.admin_types")}</h2>
        <button className="btn-secondary btn-sm" onClick={addType}>+ {t("leaves.add_type")}</button>
      </div>
      {error && <ErrorBanner message={error} />}
      <div className="stack" style={{ gap: 8 }}>
        {types.map((tp) => (
          <div key={tp.id} className="inline" style={{ gap: 8, opacity: tp.is_active ? 1 : 0.6 }}>
            <input type="color" value={tp.color} onChange={(e) => upd(tp.id, { color: e.target.value })}
                   style={{ width: 44, height: 38, padding: 2 }} aria-label={t("leaves.type_color")} />
            <input value={tp.label} onChange={(e) => upd(tp.id, { label: e.target.value })} style={{ flex: 1 }} />
            <label className="inline small" style={{ gap: 6 }}>
              <input type="checkbox" checked={tp.is_active} onChange={(e) => upd(tp.id, { is_active: e.target.checked })} />
              {t("leaves.type_active")}
            </label>
            <label className="inline small" style={{ gap: 6 }} title={t("leaves.type_requires_detail_hint")}>
              <input type="checkbox" checked={tp.requires_detail} onChange={(e) => upd(tp.id, { requires_detail: e.target.checked })} />
              {t("leaves.type_requires_detail")}
            </label>
            <button className="btn-secondary btn-sm" onClick={() => saveType(tp)}>{t("action.save")}</button>
            <button className="btn-danger btn-sm" onClick={() => delType(tp.id)} aria-label={t("action.delete")}>✕</button>
          </div>
        ))}
      </div>
    </div>
  );
}

const WEEKDAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/** Single, unified reporting menu: automatic report + change notifications,
 *  one full (advanced) view — no simple/advanced toggle. Shown in the Admin
 *  "Reporting" tab and inside the reporting popup for admins. */
export function ReportingAdmin() {
  const { t } = useI18n();
  const [rep, setRep] = useState<any | null>(null);
  const [chg, setChg] = useState<any | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [saved, setSaved] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const { error, wrap } = useErr();

  useEffect(() => {
    api.get<any>("/api/admin/report-config").then(setRep).catch(() => {});
    api.get<any>("/api/admin/change-notify-config").then(setChg).catch(() => {});
    api.get<Squad[]>("/api/squads").then(setSquads).catch(() => {});
  }, []);
  if (!rep || !chg) return <div className="spinner">{t("common.loading")}</div>;

  const setR = (k: string, v: any) => setRep({ ...rep, [k]: v });
  const setC = (k: string, v: any) => setChg({ ...chg, [k]: v });
  const repRecipients = Array.isArray(rep.recipients) ? rep.recipients.join("\n") : (rep.recipients ?? "");
  const chgRecipients = Array.isArray(chg.recipients) ? chg.recipients.join("\n") : (chg.recipients ?? "");
  const weekdays: number[] = rep.weekdays ?? [rep.weekday ?? 0];
  const toggleWeekday = (i: number) => setR("weekdays", weekdays.includes(i) ? weekdays.filter((x) => x !== i) : [...weekdays, i].sort());
  const events: string[] = chg._all_events ?? ["progress", "roadmap", "objectives", "budget", "key_message"];
  const toggleEvent = (e: string) => setC("events", (chg.events ?? []).includes(e) ? chg.events.filter((x: string) => x !== e) : [...(chg.events ?? []), e]);
  const toggleSquad = (id: number) => setC("scope_squads", (chg.scope_squads ?? []).includes(id) ? chg.scope_squads.filter((x: number) => x !== id) : [...(chg.scope_squads ?? []), id]);
  const Chip = ({ on, onClick, children }: any) => (
    <label className={`rm-pick-chip${on ? " on" : ""}`} onClick={(e) => { e.preventDefault(); onClick(); }}>
      <input type="checkbox" checked={on} readOnly /><span className="rm-pick-name">{children}</span>
    </label>
  );

  async function save() {
    await wrap(async () => {
      const [r, c] = await Promise.all([
        api.put<any>("/api/admin/report-config", rep),
        api.put<any>("/api/admin/change-notify-config", chg),
      ]);
      setRep(r); setChg({ ...c, _all_events: chg._all_events });
      setSaved(true); setTimeout(() => setSaved(false), 2000);
    });
  }
  async function testWeekly() {
    setTestMsg(null);
    try { const r = await api.post<any>("/api/admin/report-config/test", {}); setTestMsg(r.ok ? t("report.test_ok", { to: r.to }) : t("report.test_fail")); }
    catch (e: any) { setTestMsg(e.message); }
  }
  async function testChange() {
    setTestMsg(null);
    try { const r = await api.post<any>("/api/admin/change-notify-config/test", {}); setTestMsg(r.ok ? t("changenotify.test_ok", { to: r.to, squad: r.squad }) : t("changenotify.test_fail")); }
    catch (e: any) { setTestMsg(e.message); }
  }

  // One shared recipients list and one shared "attach PPTX", written to both
  // delivery triggers — that's the whole point of merging the two menus.
  const recipients = Array.isArray(rep.recipients) ? rep.recipients.join("\n") : (rep.recipients ?? "");
  const setRecipients = (text: string) => {
    const list = text.split("\n");
    setRep({ ...rep, recipients: list });
    setChg({ ...chg, recipients: list });
  };
  const setAttach = (v: boolean) => { setRep({ ...rep, attach_pptx: v }); setChg({ ...chg, attach_pptx: v }); };
  const sep = { borderTop: "1px solid var(--line)", paddingTop: 12 } as const;

  return (
    <div className="stack" style={{ maxWidth: 700 }}>
      {error && <ErrorBanner message={error} />}
      <div className="between" style={{ alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>{t("reporting.title")}</h2>
      </div>

      <div className="card stack" style={{ gap: 14 }}>
        <div className="small muted">{t("reporting.merged_hint")}</div>

        {/* Shared recipients */}
        <div>
          <label>{t("changenotify.recipients")}</label>
          <textarea rows={2} value={recipients} placeholder="dir@exemple.com&#10;copil@exemple.com"
                    onChange={(e) => setRecipients(e.target.value)} />
          <div className="small muted">{t("reporting.recipients_hint")}</div>
        </div>

        <div className="strong" style={{ marginTop: 2 }}>{t("reporting.when")}</div>

        {/* Trigger 1 — scheduled */}
        <div className="stack" style={{ gap: 10, ...sep }}>
          <label className="switch">
            <input type="checkbox" checked={!!rep.enabled} onChange={(e) => setR("enabled", e.target.checked)} />
            <span className="track"><span className="knob" /></span>
            <span className="strong">{t("reporting.sched_enabled")}</span>
          </label>
          {rep.enabled && (
            <>
              <div>
                <label>{t("reporting.days")}</label>
                <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                  {WEEKDAY_KEYS.map((k, i) => <Chip key={i} on={weekdays.includes(i)} onClick={() => toggleWeekday(i)}>{t(`reporting.day.${k}`)}</Chip>)}
                </div>
              </div>
              <div className="row" style={{ gap: 12 }}>
                <div style={{ width: 120 }}><label>{t("report.hour")}</label>
                  <input type="number" min={0} max={23} value={rep.hour ?? 8} onChange={(e) => setR("hour", Number(e.target.value))} /></div>
                <div style={{ width: 150 }}><label>{t("report.since_days")}</label>
                  <input type="number" min={1} max={120} value={rep.since_days ?? 7} onChange={(e) => setR("since_days", Number(e.target.value))} /></div>
              </div>
              <div className="inline">
                <button className="btn-secondary btn-sm" onClick={testWeekly}>{t("reporting.test_sched")}</button>
                {rep.last_sent_day && <span className="small muted">{t("reporting.last_sent_day", { date: rep.last_sent_day })}</span>}
              </div>
            </>
          )}
        </div>

        {/* Trigger 2 — on change */}
        <div className="stack" style={{ gap: 10, ...sep }}>
          <label className="switch">
            <input type="checkbox" checked={!!chg.enabled} onChange={(e) => setC("enabled", e.target.checked)} />
            <span className="track"><span className="knob" /></span>
            <span className="strong">{t("reporting.change_enabled")}</span>
          </label>
          {chg.enabled && (
            <>
              <div>
                <label>{t("changenotify.events")}</label>
                <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                  {events.map((e) => <Chip key={e} on={(chg.events ?? []).includes(e)} onClick={() => toggleEvent(e)}>{t(`changenotify.event.${e}`)}</Chip>)}
                </div>
              </div>
              <div className="row" style={{ gap: 12 }}>
                <div style={{ width: 180 }}><label>{t("changenotify.interval")}</label>
                  <input type="number" min={0} max={1440} value={chg.min_interval_minutes ?? 0} onChange={(e) => setC("min_interval_minutes", Number(e.target.value))} /></div>
                <label className="inline small" style={{ gap: 6, alignSelf: "flex-end" }}>
                  <input type="checkbox" checked={chg.current_year_only !== false} onChange={(e) => setC("current_year_only", e.target.checked)} />{t("changenotify.current_year_only")}</label>
              </div>
              <div>
                <label>{t("changenotify.scope")}</label>
                <div className="small muted" style={{ marginBottom: 4 }}>{t("changenotify.scope_all_hint")}</div>
                <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                  {squads.map((s) => <Chip key={s.id} on={(chg.scope_squads ?? []).includes(s.id)} onClick={() => toggleSquad(s.id)}>{s.name}</Chip>)}
                </div>
              </div>
              <div className="inline"><button className="btn-secondary btn-sm" onClick={testChange}>{t("reporting.test_change")}</button></div>
            </>
          )}
        </div>

        {/* Shared option */}
        {(rep.enabled || chg.enabled) && (
          <div style={sep}>
            <label className="switch">
              <input type="checkbox" checked={rep.attach_pptx !== false} onChange={(e) => setAttach(e.target.checked)} />
              <span className="track"><span className="knob" /></span>
              <span className="strong">{t("reporting.attach_pptx")}</span>
            </label>
          </div>
        )}
      </div>

      <div className="inline">
        <button onClick={save}>{t("action.save")}</button>
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
          <div className="row">
            {fld(t("logs.universe"), "universe_domain", "text", "googleapis.com")}
          </div>
        )}
        {(dest === "gcs" || dest === "bigquery") && (
          <div className="small muted" style={{ marginTop: -4 }}>{t("logs.universe_hint")}</div>
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

// Tribe leader: edit their own tribe (name / description). No create/delete.
function TribeSelfAdmin({ perms }: { perms: Permissions }) {
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
          <input defaultValue={tribe.name} onBlur={(e) => e.target.value !== tribe.name && save({ name: e.target.value })} /></div>
        <div><label>{t("admin.tribe_desc")}</label>
          <input defaultValue={tribe.description ?? ""} onBlur={(e) => e.target.value !== (tribe.description ?? "") && save({ description: e.target.value })} /></div>
      </div>
      {saved && <div className="small" style={{ color: "var(--green)" }}>{t("admin.saved")}</div>}
    </div>
  );
}

// Squad leader: manage the squads they lead (name, KPIs on/off, members).
function MySquadsAdmin() {
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

function SquadSelfCard({ squadId }: { squadId: number }) {
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
          <input defaultValue={squad.name} onBlur={(e) => e.target.value !== squad.name && patchSquad({ name: e.target.value })} />
        </div>
      </div>

      <div>
        <div className="small muted" style={{ marginBottom: 6 }}>{t("admin.members")}</div>
        {squad.members.length === 0 && <div className="small muted">{t("squad.no_members")}</div>}
        {squad.members.map((m) => (
          <div key={m.id} className="item-row">
            <span className="grow">{m.full_name}{m.role_title ? <span className="muted small"> · {m.role_title}</span> : null}</span>
            <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => delMember(m.id)}>✕</button>
          </div>
        ))}
        <div className="row" style={{ alignItems: "flex-end", marginTop: 8 }}>
          <div style={{ flex: 1, minWidth: 160 }}><label>{t("admin.member_name")}</label>
            <input value={newMember.full_name} onChange={(e) => setNewMember({ ...newMember, full_name: e.target.value })} /></div>
          <div style={{ flex: 1, minWidth: 140 }}><label>{t("admin.member_role")}</label>
            <input value={newMember.role_title} onChange={(e) => setNewMember({ ...newMember, role_title: e.target.value })} /></div>
          <button className="btn-sm" onClick={addMember} disabled={!newMember.full_name.trim()}>{t("admin.add")}</button>
        </div>
      </div>
    </div>
  );
}

function TribesAdmin() {
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
          <div style={{ width: 220 }}><label>{t("admin.name")}</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div className="col"><label>{t("admin.tribe_desc")}</label><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
          <div style={{ width: 200 }}>
            <label>{t("admin.tribe_leader")}</label>
            <select value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
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
                  <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => delReply(r.id)}>✕</button>
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
            <button className="btn-danger btn-sm" aria-label={t("action.delete")} onClick={() => set("group_role_mappings", mappings.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button className="btn-secondary btn-sm" style={{ marginTop: 8 }} onClick={() => set("group_role_mappings", [...mappings, { group: "", role: "member" }])}>
          {t("auth.add_mapping")}
        </button>
      </div>

      <div className="card stack" style={{ gap: 12 }}>
        <h3>{t("auth.access_title")}</h3>
        <div className="banner stack" style={{ gap: 6 }}>
          <div className="strong">{t("auth.access_how")}</div>
          <div className="small">{t("auth.access_hint")}</div>
          <ul style={{ margin: "2px 0 0", paddingLeft: 18 }} className="small">
            <li>{t("auth.access_p1")}</li>
            <li>{t("auth.access_p2")}</li>
            <li>{t("auth.access_p3")}</li>
            <li>{t("auth.access_p4")}</li>
          </ul>
        </div>
        <label className="switch">
          <input type="checkbox" checked={cfg.require_approval !== false} onChange={(e) => set("require_approval", e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="strong">{t("auth.require_approval")}</span>
        </label>
        <div>
          <label>{t("auth.allowed_domains")}</label>
          <textarea rows={2} placeholder="exemple.com&#10;groupe.fr"
            value={(cfg.allowed_email_domains || []).join("\n")}
            onChange={(e) => set("allowed_email_domains", e.target.value.split(/[\s,;]+/).filter(Boolean))} />
          <div className="small muted">{t("auth.allowed_domains_hint")}</div>
        </div>
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
  const wrap = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
      return undefined;
    }
  };
  return { error, wrap };
}

// Tribe-leader / admin per-squad settings: KPIs on/off + annual objectives.
// (No team management here - that's the squad leader's job in reporting.)
const RAGS: Array<"green" | "amber" | "red"> = ["green", "amber", "red"];

function SquadParamsPanel({ squadId }: { squadId: number }) {
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
            <input style={{ flex: 1 }} defaultValue={o.title} onBlur={(e) => e.target.value !== o.title && updObj(o.id, { title: e.target.value })} />
            <span className="small muted" style={{ minWidth: 56 }}>{rag(o.rag_status)}</span>
            <input type="date" className="w-auto" style={{ maxWidth: 150 }} title={t("obj.deadline")}
                   value={o.target_date ? o.target_date.slice(0, 10) : ""}
                   onChange={(e) => updObj(o.id, { target_date: e.target.value || null })} />
            <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => delObj(o.id)}>✕</button>
          </div>
        ))}
        <div className="small muted" style={{ marginTop: 2 }}>{t("obj.status_auto")}</div>
        <div className="row" style={{ alignItems: "flex-end", marginTop: 8 }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label>{t("admin.new_objective")}</label>
            <input value={newObj} onChange={(e) => setNewObj(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addObj()} />
          </div>
          <button className="btn-sm" onClick={addObj} disabled={!newObj.trim()}>{t("admin.add")}</button>
        </div>
      </div>
    </div>
  );
}

function SquadsAdmin({ perms }: { perms: Permissions }) {
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
                  <input defaultValue={s.name} onBlur={(e) => e.target.value !== s.name && update(s, { name: e.target.value })} />
                </td>
                <td>
                  {isAdmin ? (
                    <select className="w-auto" value={s.tribe_id} onChange={(e) => update(s, { tribe_id: Number(e.target.value) } as any)}>
                      {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
                    </select>
                  ) : (
                    <span className="muted">{tribeName(s.tribe_id)}</span>
                  )}
                </td>
                <td>
                  <select className="w-auto" value={s.leader_user_id ?? ""} onChange={(e) => update(s, { leader_user_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">-</option>
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
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          {isAdmin && (
            <div style={{ width: 200 }}>
              <label>{t("admin.tribe")}</label>
              <select value={form.tribe_id} onChange={(e) => setForm({ ...form, tribe_id: e.target.value })}>
                <option value="">-</option>
                {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
              </select>
            </div>
          )}
          <div style={{ width: 200 }}>
            <label>{t("admin.responsible")}</label>
            <select value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
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

function UsersAdmin({ perms }: { perms: Permissions }) {
  const { t, role: roleLabel, formatDateTime } = useI18n();
  const isAdmin = perms.role === "admin";
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
                  <select className="w-auto" value={u.role} disabled={!canManage(u)} onChange={(e) => update(u, { role: e.target.value as Role })}>
                    {(isAdmin ? roleOptions : Array.from(new Set([u.role, ...roleOptions]))).map((r) => (
                      <option key={r} value={r}>
                        {labelFor(r)}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  {isAdmin ? (
                    <select className="w-auto" value={u.tribe_id ?? ""} onChange={(e) => update(u, { tribe_id: e.target.value ? Number(e.target.value) : null })}>
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
function PersonasAdmin() {
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
                      : <input style={{ width: 150 }} value={p.label} onChange={(e) => setLabel(p.key, e.target.value)} />}
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
        <input placeholder={t("personas.new_ph")} value={newLabel}
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
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const { error, wrap } = useErr();
  useEffect(() => {
    wrap(() => api.get<AuditEntry[]>("/api/audit-log")).then((d) => d && setEntries(d));
  }, []);
  if (error) return <ErrorBanner message={error} />;
  if (!entries) return <Spinner />;
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
              <td>{e.user_id ?? "-"}</td>
              <td style={{ fontFamily: "monospace", fontSize: 12 }}>{e.action}</td>
              <td className="muted">{e.entity ? `${e.entity}${e.entity_id ? ` #${e.entity_id}` : ""}` : "-"}</td>
              <td className="muted small" style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {e.detail ? JSON.stringify(e.detail) : "-"}
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
