/**
 * Administration > Annuaire: the corporate directory the screens search people
 * in (Microsoft Entra ID, Active Directory, another LDAP, Google Workspace), and
 * SCIM 2.0 provisioning, where the identity provider creates and deactivates accounts.
 *
 * The page is a list: the search sources, then SCIM provisioning, one line each
 * with its protocol, its endpoint and its state. "Configure" opens the connector
 * in a window built like the Steerco report's (StepLayout: steps on the left,
 * the current one on the right): what it needs, the connection, the search
 * (LDAP, AD), the test, the activation. A step rail and a connector table on the
 * page itself read as a form to fill before knowing what it was for.
 *
 * The test is a diagnostic, not a yes/no: each step (configuration, connection,
 * authentication, query, attributes) comes back with its outcome, duration and
 * what to change, with the people found and, for LDAP and AD, a raw entry to fill
 * the attribute mapping from. It runs with what is on screen, saved or not.
 * Secrets come back masked and a mask sent back keeps the stored value. The SCIM
 * token is shown once, when it is generated; only its hash is kept.
 *
 * The SCIM URL hangs off the application's public URL, the very setting OIDC and
 * SAML callbacks are built on (Administration > Authentification): it is shown and
 * editable here too, and saved there.
 */
import { ReactNode, useEffect, useState } from "react";
import { api } from "../../api";
import { useI18n } from "../../i18n";
import { Tribe } from "../../types";
import { ErrorBanner, Modal } from "../../components/ui";
import { StepLayout, StepSection } from "../../components/StepLayout";
import { invalidateDirectoryStatus } from "../../components/DirectorySearch";

import { useErr, useLoadState } from "./shared";

type Connector = "entra" | "ad" | "ldap" | "google" | "scim";
type Idp = "entra" | "okta" | "ping" | "other";
const IDPS: Idp[] = ["entra", "okta", "ping", "other"];

type Check = { key: string; status: "ok" | "warn" | "fail" | "skip"; detail: string; ms: number | null };
type TestMode = "user" | "group" | "custom";
const TEST_MODES: TestMode[] = ["user", "group", "custom"];
type Group = { name: string; email?: string | null; description?: string | null; kind?: string; members?: number | null; id?: string };
type RawEntry = { dn: string; attributes: Record<string, string> };
type TestResult = {
  ok: boolean; error?: string | null; steps: Check[]; count?: number; mode?: TestMode;
  groups?: Group[] | null; entries?: RawEntry[] | null; body?: { status: number; text: string } | null;
  sample?: { name: string; email: string; title?: string; department?: string }[];
  raw?: { dn: string; attributes: Record<string, string> } | null;
  calls?: { at: string; method: string; path: string; query?: string; outcome: string; client?: string; agent?: string }[];
  events?: { at: string; action: string; entity_id?: string }[];
};
/** done = rien a faire, todo = a remplir, info = a lire, fail = test en echec. */
type StepState = "done" | "todo" | "info" | "fail" | "on" | "off";
type Step = { key: string; state: StepState; node: ReactNode };

const MARK: Record<Check["status"], [string, string]> = {
  ok: ["OK", "badge-green"], warn: ["!", "badge-orange"], fail: ["X", "badge-red"], skip: ["-", "badge-grey"],
};
const DONE = new Set<StepState>(["done", "on"]);

/** scheme://host[:port], the same reduction the server applies (authconfig.normalize_base_url). */
const normBase = (v: string) => {
  let s = (v || "").trim();
  if (!s) return "";
  if (!s.includes("://")) s = `https://${s}`;
  const [scheme, rest] = s.split("://");
  return `${scheme.toLowerCase()}://${rest.split("/")[0]}`.replace(/\/$/, "");
};

export function DirectoryAdmin() {
  const { t, formatDateTime } = useI18n();
  const [cfg, setCfg] = useState<any | null>(null);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [personas, setPersonas] = useState<{ key: string; label?: string }[]>([]);
  const [saved, setSaved] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [sel, setSel] = useState<Connector | null>(null);
  const [at, setAt] = useState(0);
  const [idp, setIdp] = useState<Idp>("entra");
  const [publicUrl, setPublicUrl] = useState("");
  const [testQ, setTestQ] = useState("");
  // Le test: une recherche de personnes, de groupes, ou la requete de l'administrateur.
  const [mode, setMode] = useState<TestMode>("user");
  const [custom, setCustom] = useState<Record<string, string>>({ scope: "sub", filter: "", attributes: "*", limit: "10", base: "", path: "" });
  const setC = (k: string, v: string) => setCustom((c) => ({ ...c, [k]: v }));
  const [scimTok, setScimTok] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const { error, wrap } = useErr();
  const origin = typeof window !== "undefined" ? window.location.origin : "";

  const ls = useLoadState();
  const load = () => {
    api.get<any>("/api/admin/directory-config").then((c) => {
      setCfg(c);
      setPublicUrl(c.public_base_url ?? "");
      // Open on the connector in use, the one an administrator comes back to.
    }).catch(ls.fail);
  };
  useEffect(() => {
    load();
    api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => setTribes([]));
    api.get<any>("/api/admin/personas").then((r) => setPersonas((r.personas ?? []).filter((p: any) => p.key !== "admin")))
      .catch(() => setPersonas([]));
  }, []);
  if (!cfg) return ls.waiting(load);
  const set = (k: string, v: any) => { setCfg((p: any) => ({ ...p, [k]: v })); setDirty(true); };
  const choose = (c: Connector) => { setSel(c); setResult(null); setAt(0); setMode("user"); setC("path", ""); };

  const filled = (...keys: string[]) => keys.every((k) => String(cfg[k] ?? "").trim() !== "");
  const urlChanged = normBase(publicUrl) !== normBase(cfg.public_base_url ?? "");
  const scimBase = (normBase(publicUrl) || (cfg.scim_base_url ?? "").replace(/\/scim\/v2$/, "") || origin) + "/scim/v2";

  const fld = (key: string, label: string, type = "text", ph?: string) => (
    <div style={{ flex: 1, minWidth: 200 }}>
      <label>{label}</label>
      <input aria-label={label} type={type} value={cfg[key] ?? ""} placeholder={ph}
             onChange={(e) => set(key, e.target.value)} />
    </div>
  );

  async function save() {
    await wrap(async () => {
      if (urlChanged) await api.put<any>("/api/admin/auth-config", { public_base_url: publicUrl });
      const out = await api.put<any>("/api/admin/directory-config", cfg);
      setCfg(out);
      setPublicUrl(out.public_base_url ?? "");
      invalidateDirectoryStatus();
      setDirty(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }
  async function runTest() {
    setBusy(true); setResult(null);
    try {
      setResult(sel === "scim"
        ? await api.post<TestResult>("/api/admin/directory-config/scim-test", { token: scimTok })
        : await api.post<TestResult>("/api/admin/directory-config/test", { source: sel, q: testQ, mode, custom, config: cfg }));
    } catch (e: any) {
      setResult({ ok: false, error: e.message, steps: [] });
    } finally { setBusy(false); }
  }
  async function newToken() {
    await wrap(async () => {
      const r = await api.post<{ token: string }>("/api/admin/directory-config/scim-token", {});
      setToken(r.token);
      setCfg((p: any) => ({ ...p, scim_token_set: true, scim_token_hint: r.token.slice(0, 9) + "..." }));
    });
  }
  const copy = (text: string) => {
    navigator.clipboard?.writeText(text).catch(() => undefined);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };
  const enabledOf = (c: Connector) => !!cfg[`${c}_enabled`];
  const when = (iso: string) => formatDateTime(iso);
  const lines = (key: string) => (
    <ol className="small" style={{ margin: 0, paddingLeft: 18 }}>
      {t(key).split("\n").filter(Boolean).map((l, i) => <li key={i} style={{ marginBottom: 6 }}>{l}</li>)}
    </ol>
  );

  // ---------- Panels ----------
  // The endpoint each connector is set to talk to (or be called on), as an
  // administrator reads it in a configuration file: the host, the tenant, the URL.
  const endpoint = (c: Connector): string => {
    if (c === "entra") return cfg.entra_tenant_id ? `${cfg.entra_graph_host || "graph.microsoft.com"}, tenant ${cfg.entra_tenant_id}` : "";
    if (c === "ad" || c === "ldap") return cfg[`${c}_base_dn`] ? `${cfg[`${c}_url`] || ""}, ${cfg[`${c}_base_dn`]}` : "";
    if (c === "google") return cfg.google_admin_subject ? `admin.googleapis.com, ${cfg.google_admin_subject}` : "";
    return cfg.scim_base_url ?? "";
  };
  const stateOf = (c: Connector): ["on" | "off" | "unset", string] =>
    enabledOf(c) ? ["on", "badge-green"] : (c === "scim" ? cfg.scim_token_set : endpoint(c)) ? ["off", "badge-grey"] : ["unset", "badge-orange"];

  const ldapConnection = (p: "ad" | "ldap") => (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row">
        {fld(`${p}_url`, t("directory.ldap_url"), "text", p === "ad" ? "ldaps://dc.entreprise.local:636" : "ldaps://ldap.example.com:636")}
        <label className="switch" style={{ alignSelf: "flex-end" }}>
          <input type="checkbox" checked={!!cfg[`${p}_start_tls`]} onChange={(e) => set(`${p}_start_tls`, e.target.checked)} />
          <span className="track"><span className="knob" /></span><span className="small">StartTLS</span>
        </label>
      </div>
      <div className="row">
        {fld(`${p}_bind_dn`, t("directory.ldap_bind_dn"), "text", p === "ad" ? "svc-teamfollowup@entreprise.local" : "cn=svc,ou=services,dc=example,dc=com")}
        {fld(`${p}_bind_password`, t("directory.ldap_bind_password"), "password")}
      </div>
    </div>
  );
  const ldapSearch = (p: "ad" | "ldap") => (
    <div className="stack" style={{ gap: 12 }}>
      {fld(`${p}_base_dn`, t("directory.ldap_base_dn"), "text", p === "ad" ? "DC=entreprise,DC=local" : "ou=people,dc=example,dc=com")}
      {fld(`${p}_user_filter`, t("directory.ldap_user_filter"))}
      {fld(`${p}_search_attrs`, t("directory.ldap_search_attrs"))}
      <div className="strong small">{t("directory.ldap_mapping")}</div>
      <div className="small muted">{t("directory.mapping_hint")}</div>
      <div className="row">
        {fld(`${p}_attr_name`, t("directory.attr.name"))}
        {fld(`${p}_attr_email`, t("directory.attr.email"))}
        {fld(`${p}_attr_first_name`, t("directory.attr.first_name"))}
      </div>
      <div className="row">
        {fld(`${p}_attr_last_name`, t("directory.attr.last_name"))}
        {fld(`${p}_attr_title`, t("directory.attr.title"))}
        {fld(`${p}_attr_department`, t("directory.attr.department"))}
      </div>
    </div>
  );

  const connection: Record<Exclude<Connector, "scim">, ReactNode> = {
    entra: (
      <div className="stack" style={{ gap: 12 }}>
        <div className="row">
          {fld("entra_tenant_id", t("directory.entra_tenant"), "text", "00000000-0000-0000-0000-000000000000")}
          {fld("entra_client_id", t("directory.entra_client"), "text", "00000000-0000-0000-0000-000000000000")}
        </div>
        {fld("entra_client_secret", t("directory.entra_secret"), "password")}
        <div className="row">
          {fld("entra_graph_host", t("directory.entra_graph_host"))}
          {fld("entra_login_host", t("directory.entra_login_host"))}
        </div>
      </div>
    ),
    ad: ldapConnection("ad"),
    ldap: ldapConnection("ldap"),
    google: (
      <div className="stack" style={{ gap: 12 }}>
        <div>
          <label>{t("directory.google_key")}</label>
          <textarea rows={5} aria-label={t("directory.google_key")} value={cfg.google_service_account_json ?? ""}
                    placeholder='{"type": "service_account", ...}'
                    onChange={(e) => set("google_service_account_json", e.target.value)} />
        </div>
        <div className="row">
          {fld("google_admin_subject", t("directory.google_subject"), "email", "admin@entreprise.com")}
          {fld("google_customer", t("directory.google_customer"))}
        </div>
      </div>
    ),
  };

  const urlPanel = (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <div style={{ flex: 1, minWidth: 260 }}>
          <label>{t("auth.base_url_label")}</label>
          <input aria-label={t("auth.base_url_label")} value={publicUrl} placeholder={origin || "https://teamfollowup.exemple.com"}
                 onChange={(e) => { setPublicUrl(e.target.value); setDirty(true); }} />
        </div>
        <button type="button" className="btn-secondary btn-sm" onClick={() => { setPublicUrl(origin); setDirty(true); }}>
          {t("auth.base_url_use_current")}
        </button>
      </div>
      <div className="small muted">
        {normBase(publicUrl) ? t("directory.url_set") : t("directory.url_auto", { url: origin })}
      </div>
      <div>
        <label>{t("directory.scim_url")}</label>
        <div className="inline" style={{ gap: 6 }}>
          <input readOnly aria-label={t("directory.scim_url")} value={scimBase}
                 onFocus={(e) => e.currentTarget.select()} style={{ flex: 1, minWidth: 0, fontFamily: "ui-monospace, monospace" }} />
          <button type="button" className="btn-secondary btn-sm" onClick={() => copy(scimBase)}>
            {copied ? t("auth.copied") : t("auth.copy")}
          </button>
        </div>
      </div>
      {!scimBase.startsWith("https://") && <div className="banner banner-amber small">{t("directory.url_not_https")}</div>}
    </div>
  );

  const accountsPanel = (
    <div className="row">
      <div style={{ flex: 1, minWidth: 200 }}>
        <label>{t("directory.scim_role")}</label>
        <select aria-label={t("directory.scim_role")} value={cfg.scim_default_role ?? "member"}
                onChange={(e) => set("scim_default_role", e.target.value)}>
          {(personas.length ? personas : [{ key: "member" }]).map((p) => (
            <option key={p.key} value={p.key}>{p.label ?? p.key}</option>
          ))}
        </select>
      </div>
      <div style={{ flex: 1, minWidth: 200 }}>
        <label>{t("directory.scim_tribe")}</label>
        <select aria-label={t("directory.scim_tribe")} value={cfg.scim_default_tribe_id ?? ""}
                onChange={(e) => set("scim_default_tribe_id", e.target.value ? Number(e.target.value) : null)}>
          <option value="">{t("directory.scim_no_tribe")}</option>
          {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
        </select>
      </div>
    </div>
  );

  const tokenPanel = (
    <div className="stack" style={{ gap: 10 }}>
      <div className="inline" style={{ gap: 8 }}>
        <button className={cfg.scim_token_set ? "btn-secondary btn-sm" : "btn-sm"} onClick={newToken}>
          {cfg.scim_token_set ? t("directory.scim_regen") : t("directory.scim_gen")}
        </button>
        {cfg.scim_token_set && !token && <span className="small muted">{t("directory.scim_token_set", { hint: cfg.scim_token_hint ?? "" })}</span>}
      </div>
      {token && (
        <div className="banner">
          <div className="small strong">{t("directory.scim_token_once")}</div>
          <div className="inline" style={{ gap: 6 }}>
            <code className="grow" style={{ wordBreak: "break-all" }}>{token}</code>
            <button type="button" className="btn-secondary btn-sm" onClick={() => copy(token)}>{copied ? t("auth.copied") : t("auth.copy")}</button>
          </div>
        </div>
      )}
    </div>
  );

  const activationPanel = (
    <div className="stack" style={{ gap: 12 }}>
      <label className="switch">
        <input type="checkbox" checked={!!(sel && cfg[`${sel}_enabled`])} onChange={(e) => sel && set(`${sel}_enabled`, e.target.checked)} />
        <span className="track"><span className="knob" /></span>
        <span className="strong">{t("directory.enabled")}</span>
      </label>
      <div className="small muted">{sel === "scim" ? t("directory.activate_hint_scim") : t("directory.activate_hint")}</div>
    </div>
  );

  const isLdap = sel === "ad" || sel === "ldap";
  // What a custom test is made of, by source: an LDAP search, or a GET on the
  // directory's API. Examples in the placeholders, the usual ones a click away.
  const customForm = isLdap ? (
    <div className="stack" style={{ gap: 12 }}>
      <div className="sq-grid-2">
        <div>
          <label>{t("directory.custom.base")}</label>
          <input value={custom.base} placeholder={cfg[`${sel}_base_dn`] || "DC=entreprise,DC=local"} onChange={(e) => setC("base", e.target.value)} />
        </div>
        <div className="row" style={{ gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label>{t("directory.custom.scope")}</label>
            <select value={custom.scope} onChange={(e) => setC("scope", e.target.value)}>
              {["sub", "one", "base"].map((v) => <option key={v} value={v}>{t(`directory.custom.scope_${v}`)}</option>)}
            </select>
          </div>
          <div style={{ width: 110 }}>
            <label>{t("directory.custom.limit")}</label>
            <input type="number" min={1} max={50} value={custom.limit} onChange={(e) => setC("limit", e.target.value)} />
          </div>
        </div>
      </div>
      <div>
        <label>{t("directory.custom.filter")}</label>
        <input value={custom.filter} style={{ fontFamily: "ui-monospace, monospace" }}
               placeholder={sel === "ad" ? "(&(objectCategory=person)(sAMAccountName=jdupont))" : "(&(objectClass=inetOrgPerson)(uid=jdupont))"}
               onChange={(e) => setC("filter", e.target.value)} />
        <div className="inline" style={{ gap: 6, marginTop: 6, flexWrap: "wrap" }}>
          {(sel === "ad"
            ? ["(sAMAccountName=jdupont)", "(mail=jean.dupont@*)", "(&(objectCategory=group)(cn=*cloud*))", "(memberOf=CN=Cloud,OU=Groups,DC=entreprise,DC=local)"]
            : ["(uid=jdupont)", "(mail=jean.dupont@*)", "(objectClass=groupOfNames)", "(objectClass=posixGroup)"]
          ).map((f) => <button key={f} type="button" className="btn-ghost btn-sm sq-chip" onClick={() => setC("filter", f)}>{f}</button>)}
        </div>
      </div>
      <div>
        <label>{t("directory.custom.attributes")}</label>
        <input value={custom.attributes} placeholder="cn,mail,memberOf" onChange={(e) => setC("attributes", e.target.value)} />
      </div>
    </div>
  ) : (
    <div className="stack" style={{ gap: 12 }}>
      <div>
        <label>{sel === "entra" ? t("directory.custom.graph_path") : t("directory.custom.google_path")}</label>
        <div className="inline" style={{ gap: 6 }}>
          <span className="small muted" style={{ whiteSpace: "nowrap", fontFamily: "ui-monospace, monospace" }}>
            GET {sel === "entra" ? `https://${cfg.entra_graph_host || "graph.microsoft.com"}` : "https://admin.googleapis.com/admin/directory/v1/"}
          </span>
          <input value={custom.path} style={{ flex: 1, minWidth: 0, fontFamily: "ui-monospace, monospace" }}
                 placeholder={sel === "entra" ? "/v1.0/users?$top=5" : "users?customer=my_customer&maxResults=5"}
                 onChange={(e) => setC("path", e.target.value)} />
        </div>
        <div className="inline" style={{ gap: 6, marginTop: 6, flexWrap: "wrap" }}>
          {(sel === "entra"
            ? ["/v1.0/users?$top=5&$select=displayName,mail,jobTitle", "/v1.0/groups?$top=5", "/v1.0/users/prenom.nom@entreprise.com/memberOf",
               "/v1.0/organization"]
            : ["users?customer=my_customer&maxResults=5", "groups?customer=my_customer&maxResults=5",
               "users/prenom.nom@entreprise.com", "groups/groupe@entreprise.com/members"]
          ).map((f) => <button key={f} type="button" className="btn-ghost btn-sm sq-chip"
                               onClick={() => { setC("path", f); if (sel === "google") setC("scope", f.startsWith("groups") ? "group" : "user"); }}>{f}</button>)}
        </div>
      </div>
      {sel === "google" && (
        <div style={{ maxWidth: 360 }}>
          <label>{t("directory.custom.google_scope")}</label>
          <select value={custom.scope === "group" ? "group" : "user"} onChange={(e) => setC("scope", e.target.value)}>
            <option value="user">admin.directory.user.readonly</option>
            <option value="group">admin.directory.group.readonly</option>
          </select>
        </div>
      )}
    </div>
  );

  const testPanel = (
    <div className="stack" style={{ gap: 12 }}>
      {sel !== "scim" && (
        // Trois tests: les deux que l'on fait toujours, et le sien.
        <div className="seg" role="tablist" style={{ alignSelf: "flex-start" }}>
          {TEST_MODES.map((m) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} className={mode === m ? "active" : ""}
                    onClick={() => { setMode(m); setResult(null); }}>
              {t(`directory.mode.${m}`)}
            </button>
          ))}
        </div>
      )}
      {sel !== "scim" && <div className="small muted">{t(`directory.mode_hint.${mode}`)}</div>}
      {sel !== "scim" && mode === "custom" && <StepSection>{customForm}</StepSection>}
      <div className="inline" style={{ gap: 8 }}>
        {(sel === "scim" || mode !== "custom") && (
          <div style={{ flex: 1, minWidth: 220 }}>
            {sel === "scim"
              ? <input type="password" aria-label={t("directory.scim_test_token")} placeholder={t("directory.scim_test_token")}
                       value={scimTok} onChange={(e) => setScimTok(e.target.value)} />
              : <input aria-label={t("directory.test_q")} value={testQ}
                       placeholder={mode === "group" ? t("directory.test_q_group") : t("directory.test_q")}
                       onChange={(e) => setTestQ(e.target.value)}
                       onKeyDown={(e) => { if (e.key === "Enter") runTest(); }} />}
          </div>
        )}
        <button onClick={runTest} disabled={busy}>{busy ? t("directory.searching") : t("directory.test")}</button>
        {result && <button className="btn-ghost btn-sm"
                           onClick={() => copy(JSON.stringify({ connector: sel, at: new Date().toISOString(), ...result }, null, 2))}>
          {copied ? t("auth.copied") : t("directory.copy_diag")}</button>}
      </div>

      {result && (
        <div className="stack" style={{ gap: 10 }}>
          <div className={`banner ${result.ok ? "banner-green" : "banner-red"}`}>
            {result.ok
              ? (sel === "scim" ? t("directory.scim_ready") : t("directory.test_ok", { n: result.count ?? 0 }))
              : `${t("directory.test_fail")}${result.error ? `${t("common.colon")}${result.error}` : ""}`}
          </div>
          {result.steps.length > 0 && (
            <table className="table">
              <thead><tr>
                <th style={{ width: 44 }} />
                <th style={{ width: 170 }}>{t("directory.step")}</th>
                <th>{t("directory.detail")}</th>
                <th style={{ width: 70, textAlign: "right" }}>{t("directory.duration")}</th>
              </tr></thead>
              <tbody>
                {result.steps.map((s, i) => (
                  <tr key={i}>
                    <td><span className={`badge ${MARK[s.status][1]}`}>{MARK[s.status][0]}</span></td>
                    <td className="strong small">{t(`directory.check.${s.key}`)}</td>
                    <td className="small" style={{ wordBreak: "break-word" }}>{s.detail}</td>
                    <td className="small muted" style={{ textAlign: "right" }}>{s.ms != null ? `${s.ms} ms` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!!result.sample?.length && (
            <>
              <div className="strong small">{t("directory.sample", { n: result.sample.length })}</div>
              <table className="table">
                <thead><tr>
                  <th>{t("directory.attr.name")}</th><th>{t("directory.attr.email")}</th>
                  <th>{t("directory.attr.title")}</th><th>{t("directory.attr.department")}</th>
                </tr></thead>
                <tbody>
                  {result.sample.map((p) => (
                    <tr key={p.email}><td>{p.name}</td><td>{p.email}</td><td>{p.title ?? ""}</td><td>{p.department ?? ""}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {result.groups && result.groups.length > 0 && (
            <>
              <div className="strong small">{t("directory.groups_found", { n: result.groups.length })}</div>
              <table className="table">
                <thead><tr>
                  <th>{t("directory.group.name")}</th><th>{t("directory.attr.email")}</th>
                  <th>{t("directory.group.kind")}</th><th>{t("directory.group.members")}</th><th>{t("directory.group.description")}</th>
                </tr></thead>
                <tbody>
                  {result.groups.map((g, i) => (
                    <tr key={g.id ?? i}>
                      <td className="strong small" title={g.id}>{g.name}</td><td className="small">{g.email ?? ""}</td>
                      <td className="small">{g.kind ?? ""}</td><td className="small">{g.members ?? ""}</td>
                      <td className="small muted">{g.description ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {result.entries && (
            <>
              <div className="strong small">{t("directory.entries_found", { n: result.entries.length })}</div>
              {result.entries.map((e) => (
                <details key={e.dn} open={result.entries!.length <= 3}>
                  <summary className="small strong" style={{ cursor: "pointer", wordBreak: "break-all" }}>{e.dn}</summary>
                  <table className="table">
                    <tbody>
                      {Object.entries(e.attributes).map(([k, v]) => (
                        <tr key={k}><td className="strong small" style={{ width: 200 }}>{k}</td>
                          <td className="small" style={{ wordBreak: "break-word" }}>{v}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              ))}
            </>
          )}
          {result.body && (
            <>
              <div className="strong small">{t("directory.http_answer", { status: result.body.status })}</div>
              <pre className="sq-pre">{result.body.text}</pre>
            </>
          )}
          {result.raw && (
            <details>
              <summary className="strong small" style={{ cursor: "pointer" }}>{t("directory.raw_title")} ({result.raw.dn})</summary>
              <div className="small muted" style={{ margin: "6px 0" }}>{t("directory.raw_hint")}</div>
              <table className="table">
                <tbody>
                  {Object.entries(result.raw.attributes).map(([k, v]) => (
                    <tr key={k}><td className="strong small" style={{ width: 200 }}>{k}</td>
                      <td className="small" style={{ wordBreak: "break-word" }}>{v}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
          {sel === "scim" && (
            <>
              <div className="strong small">{t("directory.calls_title", { n: result.calls?.length ?? 0 })}</div>
              <div className="small muted">{t("directory.calls_hint")}</div>
              {result.calls?.length ? (
                <table className="table">
                  <thead><tr>
                    <th>{t("directory.when")}</th><th>{t("directory.request")}</th>
                    <th>{t("directory.outcome")}</th><th>{t("directory.caller")}</th>
                  </tr></thead>
                  <tbody>
                    {result.calls.map((c, i) => (
                      <tr key={i}>
                        <td className="small">{when(c.at)}</td>
                        <td className="small" style={{ wordBreak: "break-all" }}>{c.method} {c.path}{c.query ? `?${c.query}` : ""}</td>
                        <td><span className={`badge ${c.outcome === "accepted" ? "badge-green" : "badge-red"}`}>{t(`directory.call.${c.outcome}`)}</span></td>
                        <td className="small muted">{[c.client, c.agent].filter(Boolean).join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <div className="small muted">{t("directory.no_calls")}</div>}
              <div className="strong small">{t("directory.events_title", { n: result.events?.length ?? 0 })}</div>
              {result.events?.length ? (
                <table className="table">
                  <tbody>
                    {result.events.map((e, i) => (
                      <tr key={i}><td className="small" style={{ width: 170 }}>{when(e.at)}</td>
                        <td className="small">{t(`directory.event.${e.action}`)}</td>
                        <td className="small muted">#{e.entity_id}</td></tr>
                    ))}
                  </tbody>
                </table>
              ) : <div className="small muted">{t("directory.no_events")}</div>}
            </>
          )}
        </div>
      )}
    </div>
  );

  const prereqPanel = sel === "scim" ? (
    <div className="stack" style={{ gap: 12 }}>
      <div className="inline" style={{ gap: 6, flexWrap: "wrap" }} role="tablist">
        {IDPS.map((k) => (
          <button key={k} type="button" role="tab" aria-selected={idp === k}
                  className={idp === k ? "btn-sm" : "btn-secondary btn-sm"} onClick={() => setIdp(k)}>
            {t(`directory.idp.${k}`)}
          </button>
        ))}
      </div>
      {lines(`directory.idp_info.${idp}`)}
      <div className="small muted">{t("directory.scim_scope")}</div>
    </div>
  ) : sel ? lines(`directory.info.${sel}`) : null;

  // ---------- The connector's window ----------
  const testState: StepState = result ? (result.ok ? "done" : "fail") : "todo";
  let steps: Step[] = [];
  if (sel === "scim") {
    steps = [
      { key: "prereq", state: "info", node: prereqPanel },
      { key: "url", state: cfg.base_url_source === "configured" && !urlChanged ? "done" : "todo", node: urlPanel },
      { key: "accounts", state: "done", node: accountsPanel },
      { key: "token", state: cfg.scim_token_set ? "done" : "todo", node: tokenPanel },
      { key: "activate", state: enabledOf("scim") ? "on" : "off", node: activationPanel },
      { key: "test", state: testState, node: testPanel }];
  } else if (sel) {
    const connDone = sel === "entra" ? filled("entra_tenant_id", "entra_client_id", "entra_client_secret")
      : sel === "google" ? filled("google_service_account_json", "google_admin_subject")
        : filled(`${sel}_url`);
    steps = [
      { key: "prereq", state: "info", node: prereqPanel },
      { key: "connection", state: connDone ? "done" : "todo", node: connection[sel] },
      ...(sel === "ad" || sel === "ldap"
        ? [{ key: "search", state: (filled(`${sel}_base_dn`) ? "done" : "todo") as StepState, node: ldapSearch(sel) }] : []),
      { key: "test", state: testState, node: testPanel },
      { key: "activate", state: enabledOf(sel) ? "on" : "off", node: activationPanel }];
  }
  const cur = Math.min(at, Math.max(0, steps.length - 1));
  const current = steps[cur];
  const kind = sel === "scim" ? "scim" : "src";
  const descKey = current && ["prereq", "test", "activate"].includes(current.key)
    ? `directory.stepd.${current.key}_${kind}` : `directory.stepd.${current?.key}`;
  // Closing without saving puts the stored settings back: what the list shows is
  // always what is saved.
  const close = () => { if (dirty) load(); setDirty(false); setSel(null); setResult(null); setToken(null); };

  // One line per connector: what it is, how it talks, whether it is on. The
  // settings open in a window, as the Steerco report does: the page stays a list.
  const row = (c: Connector) => {
    const [st, cls] = stateOf(c);
    return (
      <div key={c} className="admin-list-row">
        <div className="admin-list-main">
          <span className="admin-list-text">
            <span className="strong">{t(`directory.source.${c}`)}</span>
            <span className="small muted">{t(`directory.proto.${c}`)}{endpoint(c) ? `, ${endpoint(c)}` : ""}</span>
          </span>
          <span className="inline" style={{ gap: 10 }}>
            <span className={`badge ${cls}`}>{t(`directory.st.${st}`)}</span>
            <button type="button" className="btn-secondary btn-sm" onClick={() => choose(c)}>{t("directory.configure")}</button>
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="stack" style={{ gap: 16, maxWidth: 980 }}>
      {error && !sel && <ErrorBanner message={error} />}
      {saved && !sel && <div className="small" style={{ color: "var(--green)" }}>{t("admin.saved")}</div>}

      <StepSection title={t("directory.group_search")} hint={t("directory.group_search_hint")}>
        <div className="admin-list" style={{ padding: 0 }}>
          {(["entra", "ad", "ldap", "google"] as Connector[]).map(row)}
        </div>
      </StepSection>
      <StepSection title={t("directory.group_prov")} hint={t("directory.group_prov_hint")}>
        <div className="admin-list" style={{ padding: 0 }}>{row("scim")}</div>
      </StepSection>

      {sel && current && (
        <Modal
          width={1240}
          dirty={dirty}
          onClose={close}
          title={
            <span className="sq-title">
              <span>{t(`directory.source.${sel}`)}</span>
              <span className="sq-title-sub">{t(`directory.proto.${sel}`)}</span>
            </span>
          }
          footer={
            <div className="between" style={{ width: "100%", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span className="inline" style={{ gap: 10 }}>
                {dirty && !saved && <span className="small" style={{ color: "var(--orange)" }}>{t("directory.unsaved")}</span>}
                {saved && <span className="small" style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
              </span>
              <div className="inline" style={{ gap: 8 }}>
                <button className="btn-secondary btn-sm" onClick={close}>{t("action.close")}</button>
                <button className="btn-secondary btn-sm" disabled={cur === 0} onClick={() => setAt(cur - 1)}>‹ {t("common.prev")}</button>
                {cur < steps.length - 1 && <button className="btn-secondary btn-sm" onClick={() => setAt(cur + 1)}>{t("common.next")} ›</button>}
                <button className="btn-sm" onClick={save} disabled={!dirty}>{t("action.save")}</button>
              </div>
            </div>
          }
        >
          <StepLayout ariaLabel={t(`directory.source.${sel}`)} at={cur} onGo={setAt} desc={t(descKey)}
                      steps={steps.map((x) => ({ key: x.key, title: t(`directory.stept.${x.key}`),
                                                  meta: t(`directory.state.${x.state}`), done: DONE.has(x.state) }))}>
            {error && <ErrorBanner message={error} />}
            {current.node}
          </StepLayout>
        </Modal>
      )}
    </div>
  );
}
