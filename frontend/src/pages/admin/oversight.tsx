/**
 * Administration > Oversight: moderation, log export, audit trail, ops console.
 *
 * The panels used to find out what happened. The audit screen is paginated and
 * filterable because it exists to answer a question about the past, not to list
 * the most recent rows.
 */
import { useEffect, useState } from "react";
import { api } from "../../api";
import { useI18n } from "../../i18n";
import { AuditEntry, AuditPage } from "../../types";
import { ErrorBanner, Spinner } from "../../components/ui";

import { useAppRestart, useErr } from "./shared";

/** Admin > Moderation: review every feed post (and replies) with delete + pin
 *  controls. Used to police the shared feed regardless of authorship. */
export function ModerationAdmin() {
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
                  <span className="small"><span className="strong">{r.author?.display_name || "?"}</span>, {r.content}</span>
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


/** Admin > Logs: ship the audit log to an external sink - syslog, GCS or
 *  BigQuery. The GCP sinks expose several auth methods (ADC / Workload Identity
 *  Federation / impersonation / service-account key). Test + flush actions let
 *  the admin verify the pipe. Admin only. */
export function LogExportAdmin() {
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
      <input aria-label={label} type={type} value={cfg[key] ?? ""} placeholder={placeholder} onChange={(e) => set(key, e.target.value)} />
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
          <select aria-label={t("logs.destination")} value={dest} onChange={(e) => set("destination", e.target.value)}>
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
                <input aria-label={t("logs.port")} type="number" value={cfg.syslog_port ?? 514} onChange={(e) => set("syslog_port", Number(e.target.value))} />
              </div>
            </div>
            <div className="row">
              <div style={{ width: 160 }}>
                <label>{t("logs.protocol")}</label>
                <select aria-label={t("logs.protocol")} value={cfg.syslog_protocol} onChange={(e) => set("syslog_protocol", e.target.value)}>
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
          <>
            <div className="row">
              {fld(t("logs.universe"), "universe_domain", "text", "googleapis.com")}
            </div>
            <div className="small muted" style={{ marginTop: -4 }}>{t("logs.universe_hint")}</div>

            <div style={{ maxWidth: 420 }}>
              <label>{t("logs.auth_method")}</label>
              <select aria-label={t("logs.auth_method")} value={cfg.auth_method ?? "adc"} onChange={(e) => set("auth_method", e.target.value)}>
                <option value="adc">{t("logs.auth.adc")}</option>
                <option value="wif">{t("logs.auth.wif")}</option>
                <option value="impersonation">{t("logs.auth.impersonation")}</option>
                <option value="key">{t("logs.auth.key")}</option>
              </select>
            </div>

            {cfg.auth_method === "adc" && (
              <div className="small muted">{t("logs.auth_adc_hint")}</div>
            )}

            {cfg.auth_method === "wif" && (
              <div>
                <div className="small muted" style={{ marginBottom: 4 }}>{t("logs.auth_wif_hint")}</div>
                <label>{t("logs.wif_config")}</label>
                <textarea aria-label={t("logs.wif_config")}
                  rows={4}
                  placeholder={t("logs.wif_config_ph")}
                  value={cfg.wif_config_json ?? ""}
                  onChange={(e) => set("wif_config_json", e.target.value)}
                />
              </div>
            )}

            {cfg.auth_method === "impersonation" && (
              <div>
                <div className="small muted" style={{ marginBottom: 4 }}>{t("logs.auth_impersonation_hint")}</div>
                {fld(t("logs.impersonate_sa"), "impersonate_service_account", "text", t("logs.impersonate_sa_ph"))}
              </div>
            )}

            {cfg.auth_method === "key" && (
              <>
                <div className="banner" style={{ background: "var(--red-bg, #fdecec)", color: "var(--red)" }}>
                  {t("logs.auth_key_warning")}
                </div>
                <div>
                  <label>
                    {t("logs.gcp_creds")}
                    {cfg.gcp_credentials_json_set && <span className="badge badge-green" style={{ marginLeft: 8 }}>{t("logs.creds_set")}</span>}
                  </label>
                  <textarea
                    rows={4}
                    aria-label={t("logs.gcp_creds")}
                    placeholder={t("logs.gcp_creds_ph")}
                    value={cfg.gcp_credentials_json ?? ""}
                    onChange={(e) => set("gcp_credentials_json", e.target.value)}
                  />
                  <div className="small muted" style={{ marginTop: 4 }}>{t("logs.gcp_creds_hint")}</div>
                </div>
              </>
            )}

            {/* Optional impersonation on top of ADC/WIF (not for the impersonation method, which has its own field). */}
            {(cfg.auth_method === "adc" || cfg.auth_method === "wif") && (
              <div className="row">
                {fld(t("logs.impersonate_sa_optional"), "impersonate_service_account", "text", t("logs.impersonate_sa_ph"))}
              </div>
            )}
          </>
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


/** Admin > Ops: runtime diagnostics + a self-restart button. Config such as the
 *  in-app TLS toggle binds at boot, so it only applies after a restart. In a
 *  container/Kubernetes deployment the restart works by exiting the process so the
 *  orchestrator recreates it with the new config; when no supervisor is present the
 *  panel warns that the app would stay down. Admin only. */
export function OpsAdmin() {
  const { t } = useI18n();
  const [rt, setRt] = useState<any | null>(null);
  const [confirm, setConfirm] = useState(false);
  const { restart, overlay, err: restartErr } = useAppRestart();

  const load = () => api.get<any>("/api/admin/runtime").then(setRt).catch(() => {});
  useEffect(() => { load(); }, []);

  function fmtUptime(s: number): string {
    const m = Math.floor(s / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
    if (d > 0) return `${d}j ${h % 24}h`;
    if (h > 0) return `${h}h ${m % 60}min`;
    if (m > 0) return `${m}min`;
    return `${s}s`;
  }

  async function doRestart() {
    const r = await restart();
    setConfirm(false);
    if (r && r.scheduled === false) await load();
  }

  if (!rt) return <div className="spinner">{t("common.loading")}</div>;

  const servingMode = rt.tls_running ? t("ops.mode_https") : t("ops.mode_http");
  const rows: Array<[string, any]> = [
    [t("ops.field.version"), rt.git_sha ? `${rt.version} (${rt.git_sha})` : rt.version],
    [t("ops.field.serving_mode"), servingMode],
    [t("ops.field.orchestrator"), rt.orchestrator],
    [t("ops.field.hostname"), rt.hostname],
    [t("ops.field.uptime"), fmtUptime(rt.uptime_seconds)],
    [t("ops.field.started_at"), new Date(rt.started_at).toLocaleString()],
    [t("ops.field.pid"), rt.pid],
    [t("ops.field.python"), rt.python],
    [t("ops.field.platform"), rt.platform],
  ];

  return (
    <div className="stack" style={{ maxWidth: 720, gap: 16 }}>
      {restartErr && <ErrorBanner message={restartErr} />}
      <div className="banner">{t("ops.intro")}</div>

      {rt.restart_pending && (
        <div className="banner" style={{ borderLeft: "4px solid var(--orange)" }}>
          ⚠️ {t("ops.restart_pending")}
        </div>
      )}

      {/* Shipped defaults still in use. The startup guard logs these too, but a log
          line is read once by whoever deployed and never again. */}
      {Array.isArray(rt.insecure_defaults) && rt.insecure_defaults.length > 0 && (
        <div className="card stack" style={{ gap: 8, borderLeft: "4px solid var(--red)" }}>
          <div className="strong">{t("ops.defaults_title")}</div>
          <div className="small muted">{t("ops.defaults_hint")}</div>
          {rt.insecure_defaults.map((d: any) => (
            <div key={d.key} className="between" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)", gap: 12 }}>
              <span className="small strong" style={{ fontFamily: "monospace", whiteSpace: "nowrap" }}>{d.key}</span>
              <span className="small" style={{ flex: 1 }}>{d.detail}</span>
              <span className={`badge ${d.severity === "critical" ? "badge-red" : "badge-orange"}`}>
                {d.severity === "critical" ? t("ops.defaults.critical") : t("ops.defaults.warning")}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="card stack" style={{ gap: 4 }}>
        <div className="between" style={{ marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>{t("ops.runtime_title")}</h2>
          <button className="btn-secondary btn-sm" onClick={load}>{t("ops.refresh")}</button>
        </div>
        {rows.map(([label, val]) => (
          <div key={label} className="between" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
            <span className="small muted">{label}</span>
            <span className="small strong" style={{ fontFamily: "monospace" }}>{String(val)}</span>
          </div>
        ))}
      </div>

      <div className="card stack" style={{ gap: 10 }}>
        <h2 style={{ margin: 0 }}>{t("ops.restart_title")}</h2>
        <div className="small muted">{t("ops.restart_hint")}</div>
        {!rt.auto_restart && (
          <div className="banner" style={{ borderLeft: "4px solid var(--red)" }}>
            ⚠️ {t("ops.no_supervisor_warn")}
          </div>
        )}
        <div>
          <button className="btn-danger" onClick={() => setConfirm(true)}>{t("ops.restart_btn")}</button>
        </div>
      </div>

      <LogsPanel />

      {confirm && (
        <div className="modal-overlay" onClick={() => setConfirm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{t("ops.restart_confirm_title")}</h3>
            <p className="small">{t("ops.restart_confirm_body")}</p>
            <div className="inline" style={{ justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
              <button className="btn-secondary" onClick={() => setConfirm(false)}>{t("action.cancel")}</button>
              <button className="btn-danger" onClick={doRestart}>{t("ops.restart_confirm_yes")}</button>
            </div>
          </div>
        </div>
      )}

      {overlay}
    </div>
  );
}


/** Colour per log level for the terminal-style viewer. */
export const LOG_LEVEL_COLOR: Record<string, string> = {
  DEBUG: "#8A94A6",
  INFO: "#3B82F6",
  WARNING: "#F79009",
  ERROR: "#F04438",
  CRITICAL: "#D92D20",
};


export type LogRecord = { time: string; level: string; logger: string; message: string };


export type LogsData = { level: string; levels: string[]; count: number; capacity: number; records: LogRecord[] };


/** Admin > Ops > Logs: live application-log viewer with a runtime level switch and
 *  text/JSON export. Reads the in-memory ring buffer, so it works the same in a
 *  container/Kubernetes pod where the process logs to stdout. Admin only. */
export function LogsPanel() {
  const { t } = useI18n();
  const [data, setData] = useState<LogsData | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [pendingLevel, setPendingLevel] = useState<string>("");
  const [persist, setPersist] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastAt, setLastAt] = useState<string>("");
  const { error, wrap } = useErr();

  const load = () => api.get<LogsData>(`/api/admin/logs?limit=1000${filter ? `&level=${filter}` : ""}`)
    .then((d) => { setData(d); setPendingLevel((p) => p || d.level); setLastAt(new Date().toLocaleTimeString()); })
    .catch(() => {});

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, filter]);

  async function applyLevel() {
    await wrap(async () => {
      setBusy(true);
      try {
        await api.post("/api/admin/log-level", { level: pendingLevel, persist });
        await load();
      } finally { setBusy(false); }
    });
  }
  async function clearBuf() {
    await wrap(async () => { await api.post("/api/admin/logs/clear", {}); await load(); });
  }

  if (!data) return <div className="card"><div className="spinner">{t("common.loading")}</div></div>;
  const dl = (fmt: string) => `/api/admin/logs/download?fmt=${fmt}${filter ? `&level=${filter}` : ""}`;

  return (
    <div className="card stack" style={{ gap: 12 }}>
      <div className="between" style={{ flexWrap: "wrap", gap: 8 }}>
        <h2 style={{ margin: 0 }}>{t("ops.logs_title")}</h2>
        <span className="small muted inline" style={{ gap: 10 }}>
          {autoRefresh && <span style={{ color: "var(--green)" }}>● {t("ops.logs_live")}</span>}
          {lastAt && <span>{t("ops.logs_updated_at", { time: lastAt })}</span>}
          <span>{t("ops.logs_count", { n: data.count, total: data.capacity })}</span>
        </span>
      </div>
      <div className="small muted">{t("ops.logs_hint")}</div>
      {error && <ErrorBanner message={error} />}

      {/* Runtime level control */}
      <div className="row" style={{ gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ minWidth: 150 }}>
          <label>{t("ops.log_level")}</label>
          <select aria-label={t("ops.log_level")} value={pendingLevel} onChange={(e) => setPendingLevel(e.target.value)}>
            {data.levels.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <label className="switch" style={{ marginBottom: 6 }}>
          <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="small">{t("ops.log_persist")}</span>
        </label>
        <button className="btn-sm" disabled={busy || (pendingLevel === data.level && !persist)} onClick={applyLevel}>
          {t("ops.log_apply")}
        </button>
        <span className="small muted">{t("ops.log_current")} : <span className="strong" style={{ color: LOG_LEVEL_COLOR[data.level] }}>{data.level}</span></span>
      </div>

      {/* Viewer toolbar */}
      <div className="row" style={{ gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ minWidth: 150 }}>
          <label>{t("ops.logs_filter")}</label>
          <select aria-label={t("ops.logs_filter")} value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">{t("ops.logs_all")}</option>
            {data.levels.map((l) => <option key={l} value={l}>{l}+</option>)}
          </select>
        </div>
        <label className="switch" style={{ marginBottom: 6 }}>
          <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="small">{t("ops.logs_auto")}</span>
        </label>
        <button className="btn-secondary btn-sm" onClick={load}>{t("ops.refresh")}</button>
        <a className="btn-secondary btn-sm" href={dl("txt")}>{t("ops.logs_dl_txt")}</a>
        <a className="btn-secondary btn-sm" href={dl("json")}>{t("ops.logs_dl_json")}</a>
        <button className="btn-ghost btn-sm" onClick={clearBuf}>{t("ops.logs_clear")}</button>
      </div>

      {/* Terminal-style viewer */}
      <div style={{
        background: "#0B1020", color: "#E4E7EC", borderRadius: 8, padding: 12,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12,
        lineHeight: 1.5, maxHeight: 440, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word",
      }}>
        {data.records.length === 0 ? (
          <span style={{ color: "#8A94A6" }}>
            {t("ops.logs_empty")}
            {(data.count === 0 && data.level !== "DEBUG") && (
              <><br />{t("ops.logs_empty_hint", { level: data.level })}</>
            )}
          </span>
        ) : data.records.map((r, i) => (
          <div key={i}>
            <span style={{ color: "#667085" }}>{r.time.replace("T", " ").slice(0, 19)} </span>
            <span style={{ color: LOG_LEVEL_COLOR[r.level] ?? "#E4E7EC", fontWeight: 600 }}>{r.level.padEnd(8)}</span>
            <span style={{ color: "#98A2B3" }}>{r.logger}: </span>
            <span>{r.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}


/** Admin > Audit: the audit log, paginated and filterable. Admin only.
 *
 *  It used to render "the last 200 entries", which on an instance that has been
 *  running for a year answers no question at all: what an administrator actually
 *  needs is "who disabled this account" or "what happened on the 12th". Hence the
 *  filters, and a total that says how much is NOT being shown. */
export function AuditAdmin() {
  const { t, formatDateTime } = useI18n();
  const [page, setPage] = useState<AuditPage | null>(null);
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const { error, wrap } = useErr();

  // Debounced so typing in the action box does not fire a request per keystroke.
  useEffect(() => {
    const handle = setTimeout(() => {
      const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      if (action.trim()) q.set("action", action.trim());
      if (entity.trim()) q.set("entity", entity.trim());
      // <input type="date"> gives YYYY-MM-DD; widen it to cover the whole day.
      if (since) q.set("since", `${since}T00:00:00`);
      if (until) q.set("until", `${until}T23:59:59`);
      wrap(() => api.get<AuditPage>(`/api/audit-log?${q.toString()}`)).then((d) => d && setPage(d));
    }, 250);
    return () => clearTimeout(handle);
  }, [action, entity, since, until, limit, offset]);

  // Any filter change invalidates the current position in the list.
  const onFilter = (setter: (v: string) => void) => (v: string) => { setOffset(0); setter(v); };

  const reset = () => { setAction(""); setEntity(""); setSince(""); setUntil(""); setOffset(0); };

  if (error) return <ErrorBanner message={error} />;
  if (!page) return <Spinner />;

  const pages = Math.max(1, Math.ceil(page.total / page.limit));
  const current = Math.floor(page.offset / page.limit) + 1;
  const hasFilter = !!(action || entity || since || until);

  /** Who acted: a name if we still have the account, otherwise say so plainly
   *  rather than showing a bare id nobody can resolve. */
  const who = (e: AuditEntry) => {
    if (e.user_name || e.user_email) return e.user_name || e.user_email;
    if (e.user_id == null) return t("admin.audit_system");
    return t("admin.audit_deleted_user");
  };

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="card inline" style={{ gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="stack" style={{ gap: 4 }}>
          <span className="small muted">{t("admin.audit_filter_action")}</span>
          <input value={action} onChange={(e) => onFilter(setAction)(e.target.value)}
                 placeholder="login, user.update..." style={{ minWidth: 180 }} />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span className="small muted">{t("admin.audit_filter_entity")}</span>
          <input value={entity} onChange={(e) => onFilter(setEntity)(e.target.value)}
                 placeholder="user, squad..." style={{ minWidth: 140 }} />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span className="small muted">{t("admin.audit_from")}</span>
          <input type="date" value={since} onChange={(e) => onFilter(setSince)(e.target.value)} />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span className="small muted">{t("admin.audit_to")}</span>
          <input type="date" value={until} onChange={(e) => onFilter(setUntil)(e.target.value)} />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span className="small muted">{t("admin.audit_per_page")}</span>
          <select value={limit} onChange={(e) => { setOffset(0); setLimit(Number(e.target.value)); }}>
            {[25, 50, 100, 200].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        {hasFilter && (
          <button className="btn-ghost btn-sm" onClick={reset}>{t("admin.audit_reset")}</button>
        )}
        <div className="small muted" style={{ marginLeft: "auto" }}>
          {t("admin.audit_count", { shown: String(page.items.length), total: String(page.total) })}
        </div>
      </div>

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
            {page.items.map((e) => (
              <tr key={e.id}>
                <td className="muted" style={{ whiteSpace: "nowrap" }}>{formatDateTime(e.timestamp)}</td>
                <td>{who(e)}</td>
                <td style={{ fontFamily: "monospace", fontSize: 12 }}>{e.action}</td>
                <td className="muted">{e.entity ? `${e.entity}${e.entity_id ? ` #${e.entity_id}` : ""}` : "-"}</td>
                <td className="muted small" style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    title={e.detail ? JSON.stringify(e.detail) : ""}>
                  {e.detail ? JSON.stringify(e.detail) : "-"}
                </td>
              </tr>
            ))}
            {page.items.length === 0 && (
              <tr>
                <td className="muted" colSpan={5}>{t("admin.no_audit")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="inline" style={{ gap: 10, alignItems: "center", justifyContent: "center" }}>
          <button className="btn-secondary btn-sm" disabled={page.offset <= 0}
                  onClick={() => setOffset(Math.max(0, page.offset - page.limit))}>
            {t("admin.audit_prev")}
          </button>
          <span className="small muted">
            {t("admin.audit_page", { page: String(current), pages: String(pages) })}
          </span>
          <button className="btn-secondary btn-sm" disabled={page.offset + page.limit >= page.total}
                  onClick={() => setOffset(page.offset + page.limit)}>
            {t("admin.audit_next")}
          </button>
        </div>
      )}
    </div>
  );
}
