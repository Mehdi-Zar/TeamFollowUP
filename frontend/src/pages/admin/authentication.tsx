/**
 * Administration > Authentication and email: SSO, API keys, SMTP, TLS.
 *
 * Everything about how someone or something proves who it is. The SSO callback
 * URLs are DERIVED from the public base URL rather than typed (see docs/12 2.1);
 * `deriveSsoUrls` here mirrors the server's derivation so the screen can show
 * what the IdP must be given before anything is saved.
 */
import { useEffect, useState } from "react";
import { api } from "../../api";
import { useI18n } from "../../i18n";
import { Tribe } from "../../types";
import { ErrorBanner, Modal, EmptyState } from "../../components/ui";

import { useAppRestart, useErr } from "./shared";

/** Admin > SMTP: configure the outbound mail server (host/port/credentials/TLS)
 *  used for notifications and reports, with a "send test email" action. Admin only. */
export function SmtpAdmin() {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const { error, wrap } = useErr();

  useEffect(() => { api.get<any>("/api/admin/smtp-config").then(setCfg); }, []);
  if (!cfg) return <div className="spinner">{t("common.loading")}</div>;
  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });
  // Small helper to render a labelled config input bound to cfg[key].
  const fld = (label: string, key: string, type = "text") => (
    <div style={{ flex: 1, minWidth: 200 }}>
      <label>{label}</label>
      <input aria-label={label} type={type} value={cfg[key] ?? ""} onChange={(e) => set(key, e.target.value)} />
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
          {fld(t("smtp.host"), "host")}
          <div style={{ width: 110 }}><label>{t("smtp.port")}</label><input aria-label={t("smtp.port")} type="number" value={cfg.port ?? 587} onChange={(e) => set("port", Number(e.target.value))} /></div>
        </div>
        <div className="row">
          {fld(t("smtp.username"), "username")}
          {fld(t("smtp.password"), "password", "password")}
        </div>
        <div className="row">
          {fld(t("smtp.from_addr"), "from_addr")}
          {fld(t("smtp.from_name"), "from_name")}
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


/** Admin > TLS: manage the gateway certificate. Shows the active cert, and lets
 *  the admin regenerate a self-signed one, import a PEM or PFX, and manage the
 *  trusted CA store (roots/intermediates). Admin only. */
export function TlsAdmin() {
  const { t } = useI18n();
  const [st, setSt] = useState<any | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const { error, wrap } = useErr();
  const { restart, overlay } = useAppRestart();
  const [confirmRestart, setConfirmRestart] = useState(false);

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
  async function toggleTls(enabled: boolean) {
    await wrap(async () => {
      setSt(await api.post<any>("/api/admin/tls-config/enabled", { enabled }));
      flash(t("tls.applied"));
    });
  }

  const a = st.active || {};
  // enabled: whether the app should terminate TLS itself (the toggle's value).
  // pending: the running server is still in the other mode until the next restart.
  const enabled = st.tls_enabled !== false;
  const inactive = !enabled;
  const pending = st.tls_running != null && st.tls_enabled !== st.tls_running;
  // Expiry badge colour: red if expired, orange if under 30 days, else green.
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
        <button className="btn-danger btn-sm" onClick={() => removeCa(c.id)} disabled={inactive}>{t("action.delete")}</button>
      </div>
    </div>
  );

  return (
    <div className="stack" style={{ maxWidth: 760 }}>
      {error && <ErrorBanner message={error} />}

      {/* Master toggle: does the app terminate TLS itself, or the infrastructure? */}
      <div className="card stack" style={{ gap: 8 }}>
        <div className="between">
          <span className="strong">{t("tls.toggle_title")}</span>
          <label className="switch">
            <input type="checkbox" checked={enabled} onChange={(e) => toggleTls(e.target.checked)} />
            <span className="track"><span className="knob" /></span>
            <span className="small">{enabled ? t("tls.toggle_on") : t("tls.toggle_off")}</span>
          </label>
        </div>
        <div className="small muted">{t("tls.toggle_hint")}</div>
        {pending && (
          <div className="banner" style={{ borderLeft: "4px solid var(--orange)" }}>
            <div className="between" style={{ gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <span>⚠️ {t("tls.pending_restart")}</span>
              <button className="btn-danger btn-sm" onClick={() => setConfirmRestart(true)}>{t("ops.restart_btn")}</button>
            </div>
          </div>
        )}
        {confirmRestart && (
          <div className="modal-overlay" onClick={() => setConfirmRestart(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <h3>{t("ops.restart_confirm_title")}</h3>
              <p className="small">{t("ops.restart_confirm_body")}</p>
              <div className="inline" style={{ justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
                <button className="btn-secondary" onClick={() => setConfirmRestart(false)}>{t("action.cancel")}</button>
                <button className="btn-danger" onClick={async () => { setConfirmRestart(false); await restart(); }}>{t("ops.restart_confirm_yes")}</button>
              </div>
            </div>
          </div>
        )}
        {overlay}
      </div>

      {!enabled && <div className="banner" style={{ borderLeft: "4px solid var(--orange)" }}>{t("tls.infra_managed")}</div>}

      {enabled && <>
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
            <div className="small"><b>SAN:</b> {(a.sans || []).join(", ") || "-"}</div>
            <div className="small"><b>{t("tls.valid_until")}:</b> {a.not_after?.slice(0, 10)}</div>
            <div className="small muted" style={{ wordBreak: "break-all" }}><b>SHA-256:</b> {a.fingerprint_sha256}</div>
            {st.chain_len > 0 && <div className="small muted">{t("tls.chain_len", { n: st.chain_len })}</div>}
          </div>
        )}
        <div className="inline">
          <a className="btn-secondary btn-sm" href="/api/admin/tls-config/active/download">{t("tls.download_active")}</a>
        </div>
      </div>

      {/* Self-signed */}
      <div className="card stack" style={{ gap: 10 }}>
        <span className="strong">{t("tls.self_signed_title")}</span>
        <div className="small muted">{t("tls.self_signed_hint")}</div>
        <div className="row">
          <div style={{ flex: 1, minWidth: 180 }}><label>{t("tls.cn")}</label>
            <input aria-label={t("tls.cn")} value={cn} onChange={(e) => setCn(e.target.value)} /></div>
          <div style={{ flex: 2, minWidth: 220 }}><label>{t("tls.sans")}</label>
            <input aria-label={t("tls.sans")} value={sans} onChange={(e) => setSans(e.target.value)} placeholder="host.example.com, 10.0.0.5" /></div>
        </div>
        <div><button className="btn-secondary" onClick={regen} disabled={inactive}>{t("tls.generate")}</button></div>
      </div>

      {/* Import PEM */}
      <div className="card stack" style={{ gap: 10 }}>
        <span className="strong">{t("tls.import_pem_title")}</span>
        <div className="small muted">{t("tls.import_pem_hint")}</div>
        <div className="row">
          <div style={{ flex: 1, minWidth: 220 }}>
            <label>{t("tls.cert_file")}</label>
            <input aria-label={t("tls.cert_file")} type="file" accept=".pem,.crt,.cer" onChange={(e) => setCertFile(e.target.files?.[0] ?? null)} />
          </div>
          <div style={{ flex: 1, minWidth: 220 }}>
            <label>{t("tls.key_file")}</label>
            <input type="file" accept=".pem,.key" aria-label={t("a11y.choose_file")} onChange={(e) => setKeyFile(e.target.files?.[0] ?? null)} />
          </div>
        </div>
        {!certFile && <textarea rows={4} aria-label={t("tls.cert_paste")} placeholder={t("tls.cert_paste")} value={certText} onChange={(e) => setCertText(e.target.value)} style={{ fontFamily: "monospace", fontSize: 12 }} />}
        {!keyFile && <textarea rows={4} aria-label={t("tls.key_paste")} placeholder={t("tls.key_paste")} value={keyText} onChange={(e) => setKeyText(e.target.value)} style={{ fontFamily: "monospace", fontSize: 12 }} />}
        <div className="row">
          <div style={{ width: 260 }}><label>{t("tls.key_passphrase")}</label>
            <input aria-label={t("tls.key_passphrase")} type="password" value={pemPass} onChange={(e) => setPemPass(e.target.value)} /></div>
        </div>
        <div><button onClick={importPem} disabled={inactive}>{t("tls.install")}</button></div>
      </div>

      {/* Import PFX */}
      <div className="card stack" style={{ gap: 10 }}>
        <span className="strong">{t("tls.import_pfx_title")}</span>
        <div className="small muted">{t("tls.import_pfx_hint")}</div>
        <div className="row">
          <div style={{ flex: 1, minWidth: 220 }}>
            <label>{t("tls.pfx_file")}</label>
            <input aria-label={t("tls.pfx_file")} type="file" accept=".pfx,.p12" onChange={(e) => setPfxFile(e.target.files?.[0] ?? null)} />
          </div>
          <div style={{ width: 260 }}><label>{t("tls.pfx_password")}</label>
            <input aria-label={t("tls.pfx_password")} type="password" value={pfxPass} onChange={(e) => setPfxPass(e.target.value)} /></div>
        </div>
        <div><button onClick={importPfx} disabled={inactive}>{t("tls.install")}</button></div>
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
            <input aria-label={t("tls.ca_file")} type="file" accept=".pem,.crt,.cer" onChange={(e) => setCaFile(e.target.files?.[0] ?? null)} />
          </div>
          <div style={{ flex: 1, minWidth: 180 }}>
            <label>{t("tls.ca_name")}</label>
            <input aria-label={t("tls.ca_name")} value={caName} onChange={(e) => setCaName(e.target.value)} />
          </div>
          <button className="btn-secondary" onClick={addCa} disabled={inactive}>{t("tls.add_ca")}</button>
        </div>
      </div>
      </>}

      {msg && <div className="small" style={{ color: "var(--green)" }}>{msg}</div>}
    </div>
  );
}


/** Fixed API paths behind each SSO callback URL. Mirrors SSO_URL_PATHS in the
 *  backend (app/authconfig.py): the IdP-facing URLs are always the public base
 *  URL plus one of these, so only the base URL is ever configured. */
export const SSO_URL_PATHS: Record<string, string> = {
  oidc_redirect_uri: "/api/auth/oidc/callback",
  saml_sp_entity_id: "/api/auth/saml/metadata",
  saml_acs_url: "/api/auth/saml/acs",
};


/** Reduce a typed URL to scheme://host[:port] (same rule as the backend's
 *  normalize_base_url), so the previewed callback URLs stay valid while typing. */
export function normalizeBaseUrl(value: string): string {
  let v = (value || "").trim();
  if (!v) return "";
  if (!v.includes("://")) v = "https://" + v;
  const [scheme, rest] = v.split("://", 2);
  return `${scheme.toLowerCase()}://${(rest || "").split("/")[0]}`.replace(/\/$/, "");
}


export function deriveSsoUrls(baseUrl: string): Record<string, string> {
  const base = normalizeBaseUrl(baseUrl);
  const out: Record<string, string> = {};
  for (const [k, path] of Object.entries(SSO_URL_PATHS)) out[k] = base ? base + path : "";
  return out;
}


/** Admin > Auth: SSO configuration - OIDC and/or SAML (PingFederate) settings,
 *  group->role mappings, and self-service access rules (approval requirement +
 *  allowed email domains). Admin only.
 *
 *  The IdP-facing URLs are never typed by hand: the admin sets the app's public
 *  URL once and the redirect URI / entity ID / ACS URL are shown ready to copy
 *  into the IdP. The per-URL overrides live under "Advanced" for the rare IdP
 *  registration that mandates a specific value. */
export function AuthAdmin() {
  const { t, role: roleLabel } = useI18n();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  // Per-provider connectivity test: "running" while in flight, then the report.
  const [tests, setTests] = useState<Record<string, any>>({});
  const { error, wrap } = useErr();
  const roles = ["admin", "tribe_leader", "squad_leader", "member"];
  const origin = typeof window !== "undefined" ? window.location.origin : "";

  useEffect(() => {
    api.get<any>("/api/admin/auth-config").then((c) => {
      // The API returns the SSO URLs already resolved. Blank the ones that merely
      // restate the derivation so the "Advanced" fields mean what they say: empty
      // = follow the public URL, filled = a deliberate override.
      const next = { ...c };
      const derived = deriveSsoUrls(c.base_url_effective || "");
      for (const k of Object.keys(SSO_URL_PATHS)) if ((next[k] || "") === derived[k]) next[k] = "";
      setCfg(next);
    });
  }, []);
  if (!cfg) return <div className="spinner">{t("common.loading")}</div>;

  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });
  const fld = (label: string, key: string, type = "text") => (
    <div style={{ flex: 1, minWidth: 220 }}>
      <label>{label}</label>
      <input aria-label={label} type={type} value={cfg[key] ?? ""} onChange={(e) => set(key, e.target.value)} />
    </div>
  );

  // Live preview: what the IdP must be given, based on what is typed right now.
  const baseUrl = normalizeBaseUrl(cfg.public_base_url) || cfg.base_url_effective || origin;
  const derived = deriveSsoUrls(baseUrl);
  const effectiveUrl = (key: string) => (cfg[key] || "").trim() || derived[key];

  const copy = (value: string) => {
    navigator.clipboard?.writeText(value);
    setCopied(value);
    setTimeout(() => setCopied((c) => (c === value ? null : c)), 1800);
  };

  /** A read-only URL to hand over to the IdP, with a one-click copy. */
  const urlBox = (label: string, key: string) => {
    const value = effectiveUrl(key);
    return (
      <div>
        <label>{label}</label>
        <div className="inline" style={{ gap: 6 }}>
          <input className="grow" aria-label={label} readOnly value={value} onFocus={(e) => e.currentTarget.select()} style={{ fontFamily: "ui-monospace, monospace" }} />
          <button type="button" className="btn-secondary btn-sm" onClick={() => copy(value)}>
            {copied === value ? t("auth.copied") : t("auth.copy")}
          </button>
        </div>
      </div>
    );
  };

  /** Probe the IdP with what is currently on screen, saved or not, so a change can
   *  be checked before it is committed. */
  async function runTest(provider: "oidc" | "saml") {
    setTests((prev) => ({ ...prev, [provider]: { running: true } }));
    try {
      const out = await api.post<any>("/api/admin/auth-config/test", { provider, config: cfg });
      setTests((prev) => ({ ...prev, [provider]: out }));
    } catch (e: any) {
      const failed = { ok: false, checks: [{ label: t("auth.test_failed"), ok: false, level: "error", detail: e?.message || "" }] };
      setTests((prev) => ({ ...prev, [provider]: failed }));
    }
  }

  /** The test button plus its report. Each line names the step that was checked,
   *  so a failure points at the field to fix rather than at "connection error". */
  const testPanel = (provider: "oidc" | "saml") => {
    const res = tests[provider];
    return (
      <div className="stack" style={{ gap: 8, marginTop: 12 }}>
        <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
          <button type="button" className="btn-secondary btn-sm" disabled={!!res?.running}
            onClick={() => runTest(provider)}>
            {res?.running ? t("auth.testing") : t("auth.test_button")}
          </button>
          {res && !res.running && (
            <span className="strong" style={{ color: res.ok ? "var(--ok, #1c7a6e)" : "var(--danger, #b03a3a)" }}>
              {res.ok ? t("auth.test_ok") : t("auth.test_ko")}
            </span>
          )}
        </div>
        <div className="small muted">{t("auth.test_hint")}</div>
        {res?.checks && (
          <div className="stack" style={{ gap: 4, marginTop: 4 }}>
            {res.checks.map((c: any, i: number) => (
              <div key={i} className="inline" style={{ gap: 8, alignItems: "baseline" }}>
                <span className="small strong" style={{
                  minWidth: 58, textAlign: "center",
                  color: c.level === "error" ? "var(--danger, #b03a3a)" : c.level === "warn" ? "var(--warn, #b06a1a)" : "var(--ok, #1c7a6e)",
                }}>
                  {c.level === "error" ? t("auth.check_ko") : c.level === "warn" ? t("auth.check_info") : t("auth.check_ok")}
                </span>
                <span className="small">
                  {c.label}
                  {c.detail && <span className="muted" style={{ marginLeft: 6, wordBreak: "break-all" }}>{c.detail}</span>}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  /** Optional per-URL override, empty meaning "keep following the public URL". */
  const overrideFld = (label: string, key: string) => (
    <div style={{ flex: 1, minWidth: 260 }}>
      <label>{label}</label>
      <input aria-label={label} value={cfg[key] ?? ""} placeholder={derived[key]} onChange={(e) => set(key, e.target.value)} />
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
      // Same normalisation as on load: keep the override fields empty unless they
      // really override something (see the useEffect above).
      const next = { ...out };
      const fresh = deriveSsoUrls(out.base_url_effective || "");
      for (const k of Object.keys(SSO_URL_PATHS)) if ((next[k] || "") === fresh[k]) next[k] = "";
      setCfg(next);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }

  return (
    <div className="stack">
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("auth.intro")}</div>

      <div className="card stack" style={{ gap: 10 }}>
        <h3>{t("auth.base_url_title")}</h3>
        <div className="small muted">{t("auth.base_url_hint")}</div>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <label>{t("auth.base_url_label")}</label>
            <input aria-label={t("auth.base_url_label")} value={cfg.public_base_url ?? ""} placeholder={origin || "https://teamfollowup.exemple.com"}
              onChange={(e) => set("public_base_url", e.target.value)} />
          </div>
          <button type="button" className="btn-secondary btn-sm" onClick={() => set("public_base_url", origin)}>
            {t("auth.base_url_use_current")}
          </button>
        </div>
        <div className="small muted">
          {normalizeBaseUrl(cfg.public_base_url)
            ? t("auth.base_url_set", { url: normalizeBaseUrl(cfg.public_base_url) })
            : t("auth.base_url_auto", { url: baseUrl || origin })}
        </div>
      </div>

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
          {fld("Scopes", "oidc_scopes")}
        </div>
        <div className="row">
          {fld("Groups claim", "oidc_groups_claim")}
        </div>
        <div className="banner stack" style={{ gap: 8, marginTop: 12 }}>
          <div className="strong">{t("auth.idp_side_title")}</div>
          <div className="small">{t("auth.idp_side_oidc")}</div>
          {urlBox(t("auth.oidc_redirect_label"), "oidc_redirect_uri")}
        </div>
        {testPanel("oidc")}
        <details style={{ marginTop: 10 }}>
          <summary className="small muted">{t("auth.advanced")}</summary>
          <div className="row" style={{ marginTop: 8 }}>
            {overrideFld(t("auth.oidc_redirect_label"), "oidc_redirect_uri")}
          </div>
          <div className="small muted" style={{ marginTop: 6 }}>{t("auth.override_hint")}</div>
        </details>
      </div>

      <div className="card">
        <label className="switch" style={{ marginBottom: 10 }}>
          <input type="checkbox" checked={!!cfg.saml_enabled} onChange={(e) => set("saml_enabled", e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="strong">SAML (PingFederate)</span>
        </label>
        <div className="row">
          {fld("IdP metadata URL", "saml_idp_metadata_url")}
          {fld("Groups attribute", "saml_groups_attr")}
        </div>
        <div className="banner stack" style={{ gap: 8, marginTop: 12 }}>
          <div className="strong">{t("auth.idp_side_title")}</div>
          <div className="small">{t("auth.idp_side_saml")}</div>
          {urlBox(t("auth.saml_entity_label"), "saml_sp_entity_id")}
          {urlBox(t("auth.saml_acs_label"), "saml_acs_url")}
          <div className="small">
            {t("auth.test")} : <a href="/api/auth/saml/metadata" target="_blank">/api/auth/saml/metadata</a>
          </div>
        </div>
        {testPanel("saml")}
        <details style={{ marginTop: 10 }}>
          <summary className="small muted">{t("auth.advanced")}</summary>
          <div className="row" style={{ marginTop: 8 }}>
            {overrideFld(t("auth.saml_entity_label"), "saml_sp_entity_id")}
            {overrideFld(t("auth.saml_acs_label"), "saml_acs_url")}
          </div>
          <div className="small muted" style={{ marginTop: 6 }}>{t("auth.override_hint")}</div>
        </details>
      </div>

      <div className="card">
        <h3>{t("auth.mappings")}</h3>
        <div className="small muted" style={{ marginBottom: 10 }}>{t("auth.mappings_hint")}</div>
        {mappings.map((m, i) => (
          <div key={i} className="item-row">
            <input className="grow" aria-label={t("auth.group")} placeholder={t("auth.group")} value={m.group} onChange={(e) => setMapping(i, { group: e.target.value })} />
            <select className="w-auto" aria-label={t("admin.role")} value={m.role} onChange={(e) => setMapping(i, { role: e.target.value })}>
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
          <textarea aria-label={t("auth.allowed_domains")} rows={2} placeholder="exemple.com&#10;groupe.fr"
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


// ---------------------------------------------------------------------------
// API keys: machine credentials for the read-only API.
// The secret lives in this component's state for exactly as long as the modal is
// open - it is never stored, never re-fetchable, and the server only ever keeps
// its argon2 hash. Everything else about a key (prefix, scopes, usage) is public.
// ---------------------------------------------------------------------------
export type ApiScope = { key: string; label: string; desc: string };


export type ApiKeyRow = {
  id: number; name: string; prefix: string; scopes: string[]; tribe_id: number | null;
  created_at: string; expires_at: string | null; last_used_at: string | null;
  revoked_at: string | null; live: boolean;
};


/** Admin > API: issue and manage machine API keys for the read-only API. Creating
 *  a key returns its secret exactly once (shown in a modal, never re-fetchable);
 *  the server keeps only the hash. Keys can be scoped, tribe-limited, given an
 *  expiry, and later revoked or deleted. Admin only. */
export function ApiAdmin() {
  const { t, lang } = useI18n();
  const [scopes, setScopes] = useState<ApiScope[]>([]);
  const [keys, setKeys] = useState<ApiKeyRow[] | null>(null);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<{ name: string; secret: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const { error, wrap } = useErr();

  // Draft of the key being minted.
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [tribeId, setTribeId] = useState<string>("");
  const [expires, setExpires] = useState<string>("365");

  async function load() {
    const out = await api.get<{ scopes: ApiScope[]; keys: ApiKeyRow[] }>("/api/admin/api-keys");
    setScopes(out.scopes);
    setKeys(out.keys);
  }
  useEffect(() => {
    load();
    api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => setTribes([]));
  }, []);

  const fmt = (iso: string | null) =>
    iso ? new Date(iso).toLocaleDateString(lang === "en" ? "en-GB" : "fr-FR") : "-";

  async function create() {
    await wrap(async () => {
      const out = await api.post<ApiKeyRow & { secret: string }>("/api/admin/api-keys", {
        name: name.trim(),
        scopes: picked,
        tribe_id: tribeId ? Number(tribeId) : null,
        expires_in_days: expires ? Number(expires) : null,
      });
      setSecret({ name: out.name, secret: out.secret });   // the one and only time it exists client-side
      setCreating(false);
      setName(""); setPicked([]); setTribeId(""); setExpires("365");
      await load();
    });
  }

  async function revoke(k: ApiKeyRow) {
    if (!window.confirm(t("api.revoke_confirm", { name: k.name }))) return;
    await wrap(async () => { await api.post(`/api/admin/api-keys/${k.id}/revoke`, {}); await load(); });
  }
  async function remove(k: ApiKeyRow) {
    if (!window.confirm(t("api.delete_confirm", { name: k.name }))) return;
    await wrap(async () => { await api.del(`/api/admin/api-keys/${k.id}`); await load(); });
  }

  if (!keys) return <div className="spinner">{t("common.loading")}</div>;

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div>
        <h3>{t("api.title")}</h3>
        <p className="small muted">{t("api.intro")}</p>
      </div>
      {error && <ErrorBanner message={error} />}

      {/* Interactive API docs (Swagger) + how-to guide */}
      <div className="card stack" style={{ gap: 10, padding: 16 }}>
        <span className="strong">{t("api.docs_title")}</span>
        <div className="small muted">{t("api.docs_intro")}</div>
        <div className="inline" style={{ gap: 8 }}>
          <a className="btn btn-secondary btn-sm" href="/docs" target="_blank" rel="noopener noreferrer">{t("api.docs_open_swagger")}</a>
          <a className="btn btn-secondary btn-sm" href="/openapi.json" target="_blank" rel="noopener noreferrer">{t("api.docs_openapi")}</a>
        </div>
        <ol className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.6 }}>
          <li>{t("api.guide_1")}</li>
          <li>{t("api.guide_2")}</li>
          <li>{t("api.guide_3")}</li>
          <li>{t("api.guide_4")}</li>
        </ol>
        <div className="small muted">{t("api.guide_curl")}</div>
        <code style={{ display: "block", padding: 10, background: "rgba(127,127,127,.12)",
                       borderRadius: 6, wordBreak: "break-all", fontSize: 12 }}>
          curl -H "Authorization: Bearer &lt;clé&gt;" {window.location.origin}/api/otds
        </code>
      </div>

      {secret && (
        <Modal
          title={t("api.created_title")}
          onClose={() => { setSecret(null); setCopied(false); }}
          footer={<button className="btn" onClick={() => { setSecret(null); setCopied(false); }}>{t("api.close")}</button>}
        >
          <div className="stack" style={{ gap: 12 }}>
            <ErrorBanner message={t("api.shown_once")} />
            <code style={{ display: "block", padding: 12, background: "rgba(127,127,127,.12)",
                           borderRadius: 6, wordBreak: "break-all", fontSize: 13 }}>
              {secret.secret}
            </code>
            <button className="btn btn-secondary btn-sm" style={{ alignSelf: "flex-start" }}
                    onClick={() => { navigator.clipboard?.writeText(secret.secret); setCopied(true); }}>
              {copied ? t("api.copied") : t("api.copy")}
            </button>
            <div className="small muted">{t("api.usage_hint")}</div>
          </div>
        </Modal>
      )}

      {!creating && (
        <button className="btn" style={{ alignSelf: "flex-start" }} onClick={() => setCreating(true)}>
          {t("api.new")}
        </button>
      )}

      {creating && (
        <div className="card stack" style={{ gap: 12, padding: 16 }}>
          <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <label>{t("api.name")}</label>
              <input aria-label={t("api.name")} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("api.name_ph")} />
            </div>
            <div style={{ minWidth: 200 }}>
              <label>{t("api.tribe")}</label>
              <select aria-label={t("api.tribe")} value={tribeId} onChange={(e) => setTribeId(e.target.value)}>
                <option value="">{t("api.tribe_all")}</option>
                {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
              </select>
            </div>
            <div style={{ minWidth: 160 }}>
              <label>{t("api.expires")}</label>
              <input aria-label={t("api.expires")} type="number" min={1} value={expires} onChange={(e) => setExpires(e.target.value)} />
            </div>
          </div>

          <div>
            <label>{t("api.scopes")}</label>
            <div className="stack" style={{ gap: 6, marginTop: 6 }}>
              {scopes.map((s) => (
                <label key={s.key} className="row" style={{ gap: 8, alignItems: "flex-start" }}>
                  <input
                    type="checkbox"
                    checked={picked.includes(s.key)}
                    onChange={(e) => setPicked(e.target.checked ? [...picked, s.key] : picked.filter((x) => x !== s.key))}
                  />
                  <span>
                    <code className="small">{s.key}</code> {"-"} {s.label}
                    <div className="small muted">{s.desc}</div>
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="row" style={{ gap: 8 }}>
            <button className="btn" disabled={!name.trim() || picked.length === 0} onClick={create}>
              {t("api.create")}
            </button>
            <button className="btn btn-secondary" onClick={() => setCreating(false)}>{t("api.cancel")}</button>
          </div>
        </div>
      )}

      {keys.length === 0 && !creating && <EmptyState message={t("api.empty")} />}

      {keys.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>{t("api.name")}</th>
              <th>{t("api.key")}</th>
              <th>{t("api.scopes")}</th>
              <th>{t("api.tribe")}</th>
              <th>{t("api.created")}</th>
              <th>{t("api.last_used")}</th>
              <th>{t("api.expires_at")}</th>
              <th>{t("api.status")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id} style={{ opacity: k.live ? 1 : 0.55 }}>
                <td>{k.name}</td>
                <td><code className="small">{k.prefix}{"…"}</code></td>
                <td className="small">{k.scopes.join(", ")}</td>
                <td className="small">
                  {k.tribe_id ? (tribes.find((tr) => tr.id === k.tribe_id)?.name ?? k.tribe_id) : t("api.tribe_all")}
                </td>
                <td className="small">{fmt(k.created_at)}</td>
                <td className="small">{k.last_used_at ? fmt(k.last_used_at) : t("api.never_used")}</td>
                <td className="small">{fmt(k.expires_at)}</td>
                <td className="small">
                  {k.revoked_at ? t("api.revoked") : k.live ? t("api.active") : t("api.expired")}
                </td>
                <td className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
                  {k.live && (
                    <button className="btn btn-secondary btn-sm" onClick={() => revoke(k)}>{t("api.revoke")}</button>
                  )}
                  <button className="btn btn-danger btn-sm" onClick={() => remove(k)}>{t("api.delete")}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
