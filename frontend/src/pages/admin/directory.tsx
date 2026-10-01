/**
 * Administration > Annuaire: the corporate directory the screens search people
 * in (Microsoft Entra ID, LDAP / Active Directory, Google Workspace), and SCIM 2.0
 * provisioning, where the identity provider creates and deactivates accounts.
 *
 * One form over GET/PUT /api/admin/directory-config. Secrets come back masked and
 * a mask sent back keeps the stored value. Each source has a test button that
 * searches with what is on screen, saved or not. The SCIM token is shown once,
 * when it is generated; only its hash is kept.
 */
import { useEffect, useState } from "react";
import { api } from "../../api";
import { useI18n } from "../../i18n";
import { Tribe } from "../../types";
import { ErrorBanner } from "../../components/ui";
import { invalidateDirectoryStatus } from "../../components/DirectorySearch";

import { useErr, useLoadState } from "./shared";

type Source = "entra" | "ldap" | "google";

export function DirectoryAdmin() {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<any | null>(null);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [personas, setPersonas] = useState<{ key: string; label?: string }[]>([]);
  const [saved, setSaved] = useState(false);
  const [testQ, setTestQ] = useState("");
  const [tests, setTests] = useState<Record<string, string>>({});
  const [token, setToken] = useState<string | null>(null);
  const { error, wrap } = useErr();

  const ls = useLoadState();
  const load = () => { api.get<any>("/api/admin/directory-config").then(setCfg).catch(ls.fail); };
  useEffect(() => {
    load();
    api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => setTribes([]));
    api.get<any>("/api/admin/personas").then((r) => setPersonas((r.personas ?? []).filter((p: any) => p.key !== "admin")))
      .catch(() => setPersonas([]));
  }, []);
  if (!cfg) return ls.waiting(load);
  const set = (k: string, v: any) => setCfg((p: any) => ({ ...p, [k]: v }));

  const fld = (key: string, label: string, type = "text", ph?: string) => (
    <div style={{ flex: 1, minWidth: 200 }}>
      <label>{label}</label>
      <input aria-label={label} type={type} value={cfg[key] ?? ""} placeholder={ph}
             onChange={(e) => set(key, e.target.value)} />
    </div>
  );
  const toggle = (key: string, label: string) => (
    <label className="switch">
      <input type="checkbox" checked={!!cfg[key]} onChange={(e) => set(key, e.target.checked)} />
      <span className="track"><span className="knob" /></span>
      <span className="strong">{label}</span>
    </label>
  );

  async function save() {
    await wrap(async () => {
      setCfg(await api.put<any>("/api/admin/directory-config", cfg));
      invalidateDirectoryStatus();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }
  async function test(source: Source) {
    setTests((p) => ({ ...p, [source]: t("directory.searching") }));
    try {
      const r = await api.post<any>("/api/admin/directory-config/test", { source, q: testQ, config: cfg });
      const msg = r.ok
        ? t("directory.test_ok", { n: r.count }) + (r.sample?.length ? `${t("common.colon")}${r.sample.map((p: any) => p.email).join(", ")}` : "")
        : `${t("directory.test_fail")} (${r.error})`;
      setTests((p) => ({ ...p, [source]: msg }));
    } catch (e: any) {
      setTests((p) => ({ ...p, [source]: e.message }));
    }
  }
  async function newToken() {
    await wrap(async () => {
      const r = await api.post<{ token: string }>("/api/admin/directory-config/scim-token", {});
      setToken(r.token);
      load();
    });
  }
  const testRow = (source: Source) => (
    <div className="inline" style={{ gap: 8 }}>
      <button className="btn-secondary btn-sm" onClick={() => test(source)}>{t("directory.test")}</button>
      {tests[source] && <span className="small muted">{tests[source]}</span>}
    </div>
  );

  return (
    <div className="stack" style={{ maxWidth: 760 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("directory.intro")}</div>

      <div className="card stack" style={{ gap: 12 }}>
        <h3>{t("directory.source.entra")}</h3>
        <div className="small muted">{t("directory.entra_hint")}</div>
        {toggle("entra_enabled", t("directory.enabled"))}
        <div className="row">
          {fld("entra_tenant_id", t("directory.entra_tenant"))}
          {fld("entra_client_id", t("directory.entra_client"))}
        </div>
        <div className="row">
          {fld("entra_client_secret", t("directory.entra_secret"), "password")}
          {fld("entra_graph_host", t("directory.entra_graph_host"))}
          {fld("entra_login_host", t("directory.entra_login_host"))}
        </div>
        {testRow("entra")}
      </div>

      <div className="card stack" style={{ gap: 12 }}>
        <h3>{t("directory.source.ldap")}</h3>
        <div className="small muted">{t("directory.ldap_hint")}</div>
        {toggle("ldap_enabled", t("directory.enabled"))}
        <div className="row">
          {fld("ldap_url", t("directory.ldap_url"), "text", "ldaps://ad.example.com:636")}
          <label className="switch" style={{ alignSelf: "flex-end" }}>
            <input type="checkbox" checked={!!cfg.ldap_start_tls} onChange={(e) => set("ldap_start_tls", e.target.checked)} />
            <span className="track"><span className="knob" /></span><span className="small">StartTLS</span>
          </label>
        </div>
        <div className="row">
          {fld("ldap_bind_dn", t("directory.ldap_bind_dn"))}
          {fld("ldap_bind_password", t("directory.ldap_bind_password"), "password")}
        </div>
        <div className="row">
          {fld("ldap_base_dn", t("directory.ldap_base_dn"), "text", "dc=example,dc=com")}
          {fld("ldap_user_filter", t("directory.ldap_user_filter"))}
        </div>
        {fld("ldap_search_attrs", t("directory.ldap_search_attrs"))}
        <div className="small muted">{t("directory.ldap_mapping")}</div>
        <div className="row">
          {fld("ldap_attr_name", t("directory.attr.name"))}
          {fld("ldap_attr_email", t("directory.attr.email"))}
          {fld("ldap_attr_first_name", t("directory.attr.first_name"))}
        </div>
        <div className="row">
          {fld("ldap_attr_last_name", t("directory.attr.last_name"))}
          {fld("ldap_attr_title", t("directory.attr.title"))}
          {fld("ldap_attr_department", t("directory.attr.department"))}
        </div>
        {testRow("ldap")}
      </div>

      <div className="card stack" style={{ gap: 12 }}>
        <h3>{t("directory.source.google")}</h3>
        <div className="small muted">{t("directory.google_hint")}</div>
        {toggle("google_enabled", t("directory.enabled"))}
        <div>
          <label>{t("directory.google_key")}</label>
          <textarea rows={3} aria-label={t("directory.google_key")} value={cfg.google_service_account_json ?? ""}
                    placeholder='{"type": "service_account", ...}'
                    onChange={(e) => set("google_service_account_json", e.target.value)} />
        </div>
        <div className="row">
          {fld("google_admin_subject", t("directory.google_subject"), "email")}
          {fld("google_customer", t("directory.google_customer"))}
        </div>
        {testRow("google")}
      </div>

      <div className="card stack" style={{ gap: 12 }}>
        <h3>{t("directory.scim")}</h3>
        <div className="small muted">{t("directory.scim_hint")}</div>
        {toggle("scim_enabled", t("directory.enabled"))}
        <div>
          <label>{t("directory.scim_url")}</label>
          <input readOnly aria-label={t("directory.scim_url")} value={cfg.scim_base_url ?? ""} />
        </div>
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
        <div className="inline" style={{ gap: 8 }}>
          <button className="btn-secondary btn-sm" onClick={newToken}>
            {cfg.scim_token_set ? t("directory.scim_regen") : t("directory.scim_gen")}
          </button>
          {cfg.scim_token_set && !token && <span className="small muted">{t("directory.scim_token_set", { hint: cfg.scim_token_hint ?? "" })}</span>}
        </div>
        {token && (
          <div className="banner">
            <div className="small strong">{t("directory.scim_token_once")}</div>
            <code style={{ wordBreak: "break-all" }}>{token}</code>
          </div>
        )}
      </div>

      <div className="inline">
        <button onClick={save}>{t("action.save")}</button>
        <div style={{ minWidth: 220 }}>
          <input aria-label={t("directory.test_q")} placeholder={t("directory.test_q")} value={testQ}
                 onChange={(e) => setTestQ(e.target.value)} />
        </div>
        {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
      </div>
    </div>
  );
}
