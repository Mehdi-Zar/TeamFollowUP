/**
 * Administration > Authentication and email: SSO, API keys, SMTP, trusted
 * certificate authorities.
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

import { useErr } from "./shared";

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


/** Admin > Certificate authorities. The authorities the application trusts when
 *  it CALLS something: OIDC/SAML IdP, SMTP relay, log export. Importing an
 *  internal authority here is what makes a privately issued endpoint reachable,
 *  and nothing on this screen can turn verification off. The certificate served
 *  to browsers is not here and never was the app's business: a load balancer
 *  terminates TLS in front of it (ADR 0013). Admin only. */
export function TrustAdmin() {
  const { t } = useI18n();
  const [st, setSt] = useState<any | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const { error, wrap } = useErr();
  const [caFile, setCaFile] = useState<File | null>(null);
  const [caName, setCaName] = useState("");

  const load = () => api.get<any>("/api/admin/trust-store").then(setSt);
  useEffect(() => { load(); }, []);
  if (!st) return <div className="spinner">{t("common.loading")}</div>;

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 2500); };

  async function addCa() {
    await wrap(async () => {
      const f = new FormData();
      if (caFile) f.append("ca", caFile); else throw new Error(t("trust.ca_required"));
      if (caName) f.append("name", caName);
      setSt(await api.postForm<any>("/api/admin/trust-store/ca", f));
      setCaFile(null); setCaName("");
      flash(t("trust.applied"));
    });
  }
  async function removeCa(id: string) {
    await wrap(async () => { setSt(await api.del<any>(`/api/admin/trust-store/ca/${id}`)); });
  }

  const caRow = (c: any) => (
    <div key={c.id} className="card stack" style={{ gap: 4, padding: 10 }}>
      <div className="between">
        <span className="strong">{c.name}</span>
        <span className={`badge ${c.kind === "root" ? "badge-navy" : "badge-grey"}`}>{t(`trust.kind.${c.kind}`)}</span>
      </div>
      <div className="small muted">{t("trust.issuer")}: {c.issuer}</div>
      <div className="small muted">{t("trust.expires")}: {c.not_after?.slice(0, 10)}</div>
      <div className="inline" style={{ gap: 8 }}>
        <a className="btn-secondary btn-sm" href={`/api/admin/trust-store/ca/${c.id}/download`}>{t("trust.download")}</a>
        <button className="btn-danger btn-sm" onClick={() => removeCa(c.id)}>{t("action.delete")}</button>
      </div>
    </div>
  );

  return (
    <div className="stack" style={{ maxWidth: 760 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("trust.intro")}</div>

      <div className="card stack" style={{ gap: 10 }}>
        <span className="strong">{t("trust.ca_title")}</span>
        <div className="small muted">{t("trust.ca_hint")}</div>
        <div className="stack" style={{ gap: 6 }}>
          <div className="small strong">{t("trust.roots")}</div>
          {st.roots?.length ? st.roots.map(caRow) : <div className="small muted">{t("trust.none")}</div>}
          <div className="small strong" style={{ marginTop: 8 }}>{t("trust.intermediates")}</div>
          {st.intermediates?.length ? st.intermediates.map(caRow) : <div className="small muted">{t("trust.none")}</div>}
        </div>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <label>{t("trust.ca_file")}</label>
            <input aria-label={t("trust.ca_file")} type="file" accept=".pem,.crt,.cer" onChange={(e) => setCaFile(e.target.files?.[0] ?? null)} />
          </div>
          <div style={{ flex: 1, minWidth: 180 }}>
            <label>{t("trust.ca_name")}</label>
            <input aria-label={t("trust.ca_name")} value={caName} onChange={(e) => setCaName(e.target.value)} />
          </div>
          <button className="btn-secondary" onClick={addCa}>{t("trust.add_ca")}</button>
        </div>
      </div>

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

      <LoginScreenPanel cfg={cfg} set={set} t={t} copy={copy} copied={copied} />

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


/**
 * Administration > Authentification > Ecran de connexion.
 *
 * Ce que la page de connexion propose, dans quel ordre, et comment chaque entree
 * se lit. Le probleme qu'il resout est concret: une organisation qui se connecte
 * par son IdP mais dont l'ecran affiche un formulaire email/mot de passe apprend
 * le mauvais geste a chaque nouvel arrivant, qui reclame ensuite un mot de passe
 * que personne ne lui donnera.
 *
 * Le mot de passe local a trois etats: visible, replie derriere un lien, ou
 * reserve a qui detient le lien secret. Le masquer releve de la lisibilite, pas
 * du controle d'acces: le compte de secours doit rester utilisable, et c'est la
 * limitation par IP qui le protege.
 */
function LoginScreenPanel({ cfg, set, t, copy, copied }: {
  cfg: any; set: (k: string, v: any) => void; t: (k: string, p?: any) => string;
  copy: (v: string) => void; copied: string | null;
}) {
  const methods: any[] = cfg.login_methods ?? [];
  const mode: string = cfg.password_mode ?? "visible";

  const update = (key: string, patch: any) =>
    set("login_methods", methods.map((m) => (m.key === key ? { ...m, ...patch } : m)));

  const move = (i: number, delta: number) => {
    const next = [...methods];
    const j = i + delta;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    set("login_methods", next.map((m, k) => ({ ...m, order: k })));
  };

  // Le logo part en data URI dans la configuration: pas de stockage de fichier a
  // gerer, et il suit les sauvegardes comme le reste du reglage. Plafonne, parce
  // qu'un PNG de 4 Mo rendrait chaque lecture de la config aussi lourde que lui.
  const onLogo = (key: string, file?: File) => {
    if (!file) return;
    if (file.size > 200 * 1024) { window.alert(t("auth.login_logo_too_big")); return; }
    const reader = new FileReader();
    reader.onload = () => update(key, { logo: String(reader.result || "") });
    reader.readAsDataURL(file);
  };

  const secretUrl = cfg.password_secret
    ? `${(cfg.base_url_effective || window.location.origin).replace(/\/$/, "")}/login?k=${cfg.password_secret}`
    : "";

  return (
    <div className="card stack" style={{ gap: 12 }}>
      <div>
        <h3 style={{ margin: 0 }}>{t("auth.login_title")}</h3>
        <div className="small muted">{t("auth.login_hint")}</div>
      </div>

      <div>
        <label htmlFor="login-intro">{t("auth.login_intro_label")}</label>
        <input id="login-intro" value={cfg.login_intro ?? ""} placeholder={t("auth.login_intro_ph")}
               onChange={(e) => set("login_intro", e.target.value)} />
      </div>

      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 70 }}>{t("auth.login_order")}</th>
            <th>{t("auth.login_method")}</th>
            <th style={{ width: 90 }}>{t("auth.login_shown")}</th>
            <th style={{ width: 90 }}>{t("auth.login_primary")}</th>
          </tr>
        </thead>
        <tbody>
          {methods.map((m, i) => (
            <tr key={m.key}>
              <td>
                <button className="btn-ghost btn-sm" aria-label={t("auth.login_up")}
                        disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                <button className="btn-ghost btn-sm" aria-label={t("auth.login_down")}
                        disabled={i === methods.length - 1} onClick={() => move(i, 1)}>↓</button>
              </td>
              <td>
                <div className="strong">{t(`login.${m.key}`)}</div>
                <div className="row" style={{ gap: 8, marginTop: 4, flexWrap: "wrap" }}>
                  <input style={{ flex: 1, minWidth: 160 }} placeholder={t("auth.login_label_ph")}
                         aria-label={t("auth.login_label_ph")} value={m.label ?? ""}
                         onChange={(e) => update(m.key, { label: e.target.value })} />
                  <input style={{ flex: 2, minWidth: 200 }} placeholder={t("auth.login_hint_ph")}
                         aria-label={t("auth.login_hint_ph")} value={m.hint ?? ""}
                         onChange={(e) => update(m.key, { hint: e.target.value })} />
                </div>
                {m.key !== "password" && (
                  <div className="inline" style={{ gap: 8, marginTop: 6, alignItems: "center" }}>
                    {m.logo ? <img src={m.logo} alt="" style={{ height: 20 }} /> : null}
                    <label className="btn-secondary btn-sm" style={{ cursor: "pointer" }}>
                      {t("auth.login_logo")}
                      <input type="file" accept="image/*" style={{ display: "none" }}
                             onChange={(e) => { onLogo(m.key, e.target.files?.[0]); e.target.value = ""; }} />
                    </label>
                    {m.logo && (
                      <button className="btn-ghost btn-sm" onClick={() => update(m.key, { logo: "" })}>
                        {t("action.delete")}
                      </button>
                    )}
                  </div>
                )}
              </td>
              <td>
                <input type="checkbox" aria-label={t("auth.login_shown")}
                       checked={m.enabled !== false}
                       onChange={(e) => update(m.key, { enabled: e.target.checked })} />
              </td>
              <td>
                <input type="radio" name="login-primary" aria-label={t("auth.login_primary")}
                       checked={!!m.primary}
                       onChange={() => set("login_methods", methods.map((x) => ({ ...x, primary: x.key === m.key })))} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="stack" style={{ gap: 6 }}>
        <label htmlFor="pwd-mode">{t("auth.login_password_mode")}</label>
        <select id="pwd-mode" style={{ maxWidth: 320 }} value={mode}
                onChange={(e) => set("password_mode", e.target.value)}>
          <option value="visible">{t("auth.login_mode_visible")}</option>
          <option value="collapsed">{t("auth.login_mode_collapsed")}</option>
          <option value="secret">{t("auth.login_mode_secret")}</option>
        </select>
        <div className="small muted">{t(`auth.login_mode_${mode}_hint`)}</div>
      </div>

      {mode === "secret" && (
        <div className="banner stack" style={{ gap: 6 }}>
          <div className="strong">{t("auth.login_secret_title")}</div>
          <div className="small">{t("auth.login_secret_hint")}</div>
          {secretUrl ? (
            <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
              <code className="small" style={{ wordBreak: "break-all" }}>{secretUrl}</code>
              <button className="btn-secondary btn-sm" onClick={() => copy(secretUrl)}>
                {copied === secretUrl ? t("action.copied") : t("action.copy")}
              </button>
              <button className="btn-ghost btn-sm" onClick={() => set("password_secret", "")}>
                {t("auth.login_secret_renew")}
              </button>
            </div>
          ) : (
            <div className="small muted">{t("auth.login_secret_pending")}</div>
          )}
        </div>
      )}
    </div>
  );
}
