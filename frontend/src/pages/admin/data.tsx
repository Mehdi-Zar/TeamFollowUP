// Admin > Data: erase what you choose, and take or restore a point-in-time copy.
//
// The screen is built around one idea: nothing destructive happens before the
// person has seen the real numbers. The domain list shows how many rows each one
// holds, ticking a domain shows what it drags along, and the confirmation repeats
// the total. A copy is taken by default before erasing or restoring, so the worst
// outcome of a mis-click is a restore rather than a loss.
import { useEffect, useState } from "react";
import { api, ApiError } from "../../api";
import { useI18n } from "../../i18n";
import { ErrorBanner, Modal, Spinner, EmptyState } from "../../components/ui";

type Domain = { total: number; tables: Record<string, number>; implies: string[] };
type Domains = { domains: Record<string, Domain>; never_erased: string[] };
type Snapshot = {
  id: number; name: string; kind: "manual" | "auto"; created_at: string | null;
  created_by: string | null; size_bytes: number; rows: number;
};
type SnapshotConfig = { enabled: boolean; interval_days: number; keep: number };

const fmtSize = (n: number) => (n < 1024 ? `${n} o` : n < 1024 * 1024 ? `${Math.round(n / 1024)} ko` : `${(n / 1048576).toFixed(1)} Mo`);
const fmtDate = (s: string | null) => (s ? s.slice(0, 16).replace("T", " ") : "-");

/** Admin > Data. Admin only, and every call here is audited server-side. */
export function DataAdmin() {
  const { t } = useI18n();
  const [cat, setCat] = useState<Domains | null>(null);
  const [snaps, setSnaps] = useState<Snapshot[] | null>(null);
  const [cfg, setCfg] = useState<SnapshotConfig | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    setErr(null);
    try {
      const [c, s, k] = await Promise.all([
        api.get<Domains>("/api/admin/data/domains"),
        api.get<Snapshot[]>("/api/admin/data/snapshots"),
        api.get<SnapshotConfig>("/api/admin/data/snapshot-config"),
      ]);
      setCat(c); setSnaps(s); setCfg(k);
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Erreur"); }
  }
  useEffect(() => { load(); }, []);

  // What ticking these boxes really erases, computed the same way as the server
  // (transitive closure of `implies`), so the confirmation cannot understate it.
  function expand(keys: string[]): string[] {
    const all = cat?.domains ?? {};
    const out = new Set<string>();
    const queue = [...keys];
    while (queue.length) {
      const k = queue.pop()!;
      if (out.has(k) || !all[k]) continue;
      out.add(k);
      queue.push(...(all[k].implies ?? []));
    }
    return Object.keys(all).filter((k) => out.has(k));
  }

  const effective = expand(picked);
  const totalRows = effective.reduce((n, k) => n + (cat?.domains[k]?.total ?? 0), 0);

  async function run<T>(fn: () => Promise<T>, done: string) {
    setBusy(true); setErr(null); setMsg(null);
    try { await fn(); setMsg(done); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Erreur"); }
    finally { setBusy(false); }
  }

  const reset = (snapshotFirst: boolean) => run(
    () => api.post("/api/admin/data/reset", { domains: picked, confirm: true, snapshot_first: snapshotFirst }),
    t("data.reset_done"),
  ).then(() => { setConfirming(false); setPicked([]); });

  if (err && !cat) return <ErrorBanner message={err} />;
  if (!cat || !snaps || !cfg) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {err && <ErrorBanner message={err} />}
      {msg && <div className="banner banner-green">{msg}</div>}

      {/* ---- Erase ---------------------------------------------------------- */}
      <div className="card stack" style={{ gap: 12 }}>
        <div>
          <h2 style={{ margin: 0 }}>{t("data.reset_title")}</h2>
          <div className="small muted">{t("data.reset_hint")}</div>
        </div>

        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 36 }}></th>
              <th>{t("data.domain")}</th>
              <th style={{ width: 100 }}>{t("data.rows")}</th>
              <th>{t("data.also_erases")}</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(cat.domains).map(([key, d]) => {
              const dragged = effective.includes(key) && !picked.includes(key);
              return (
                <tr key={key} style={dragged ? { background: "var(--amber-bg, #FBF0D9)" } : undefined}>
                  <td>
                    <input type="checkbox" aria-label={t(`data.domain.${key}`)}
                           checked={picked.includes(key)}
                           onChange={() => setPicked((p) => p.includes(key) ? p.filter((x) => x !== key) : [...p, key])} />
                  </td>
                  <td>
                    <div className="strong">{t(`data.domain.${key}`)}</div>
                    <div className="small muted">{Object.keys(d.tables).join(", ")}</div>
                  </td>
                  <td className={d.total ? "strong" : "muted"}>{d.total}</td>
                  <td className="small muted">
                    {(d.implies ?? []).map((k) => t(`data.domain.${k}`)).join(", ") || "-"}
                    {dragged && <div className="small">{t("data.dragged")}</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="small muted">{t("data.never_erased", { list: cat.never_erased.join(", ") })}</div>
        <div className="inline" style={{ gap: 10, justifyContent: "flex-end" }}>
          <button className="btn-sm" disabled={!picked.length || busy} onClick={() => setConfirming(true)}>
            {t("data.reset_btn")}
          </button>
        </div>
      </div>

      {/* ---- Snapshots ------------------------------------------------------ */}
      <div className="card stack" style={{ gap: 12 }}>
        <div className="between" style={{ alignItems: "center" }}>
          <div>
            <h2 style={{ margin: 0 }}>{t("data.snapshots_title")}</h2>
            <div className="small muted">{t("data.snapshots_hint")}</div>
          </div>
          <div className="inline" style={{ gap: 8 }}>
            <label className="btn-secondary btn-sm" style={{ cursor: "pointer" }}>
              {t("data.import")}
              <input type="file" accept=".gz,.json.gz" style={{ display: "none" }}
                     onChange={(e) => {
                       const f = e.target.files?.[0];
                       e.target.value = "";
                       if (!f) return;
                       const form = new FormData();
                       form.append("file", f);
                       run(() => api.postForm("/api/admin/data/snapshots/import", form), t("data.import_done"));
                     }} />
            </label>
            <button className="btn-sm" disabled={busy}
                    onClick={() => {
                      const name = window.prompt(t("data.snapshot_name"), "");
                      if (name === null) return;
                      run(() => api.post("/api/admin/data/snapshots", { name }), t("data.snapshot_done"));
                    }}>
              {t("data.snapshot_btn")}
            </button>
          </div>
        </div>

        {snaps.length === 0 ? <EmptyState message={t("data.no_snapshot")} /> : (
          <table className="table">
            <thead>
              <tr>
                <th>{t("data.snapshot")}</th>
                <th style={{ width: 160 }}>{t("data.taken_at")}</th>
                <th style={{ width: 110 }}>{t("data.rows")}</th>
                <th style={{ width: 90 }}>{t("data.size")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {snaps.map((s) => (
                <tr key={s.id}>
                  <td>
                    <div className="strong">{s.name}</div>
                    <div className="small muted">
                      <span className={`badge ${s.kind === "auto" ? "badge-grey" : "badge-navy"}`}>
                        {t(`data.kind.${s.kind}`)}
                      </span>
                      {s.created_by ? ` ${s.created_by}` : ""}
                    </div>
                  </td>
                  <td className="small">{fmtDate(s.created_at)}</td>
                  <td className="small">{s.rows}</td>
                  <td className="small">{fmtSize(s.size_bytes)}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <a className="btn-secondary btn-sm" href={`/api/admin/data/snapshots/${s.id}/download`}>
                      {t("data.download")}
                    </a>{" "}
                    <button className="btn-secondary btn-sm" disabled={busy}
                            onClick={() => {
                              if (!window.confirm(t("data.restore_confirm", { name: s.name }))) return;
                              run(() => api.post(`/api/admin/data/snapshots/${s.id}/restore`,
                                                 { confirm: true, snapshot_first: true }), t("data.restore_done"));
                            }}>
                      {t("data.restore")}
                    </button>{" "}
                    <button className="btn-ghost btn-sm" disabled={busy}
                            onClick={() => {
                              if (!window.confirm(t("data.delete_confirm", { name: s.name }))) return;
                              run(() => api.del(`/api/admin/data/snapshots/${s.id}`), t("data.delete_done"));
                            }}>
                      {t("action.delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ---- Automatic ------------------------------------------------------ */}
      <div className="card stack" style={{ gap: 10 }}>
        <div>
          <h2 style={{ margin: 0 }}>{t("data.auto_title")}</h2>
          <div className="small muted">{t("data.auto_hint")}</div>
        </div>
        <div className="row" style={{ gap: 14, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label className="switch">
            <input type="checkbox" checked={cfg.enabled}
                   onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} />
            <span className="track"><span className="knob" /></span>
            <span className="small">{t("data.auto_enabled")}</span>
          </label>
          <div style={{ width: 150 }}>
            <label htmlFor="auto-interval">{t("data.auto_interval")}</label>
            <input id="auto-interval" type="number" min={1} value={cfg.interval_days}
                   onChange={(e) => setCfg({ ...cfg, interval_days: Number(e.target.value) })} />
          </div>
          <div style={{ width: 150 }}>
            <label htmlFor="auto-keep">{t("data.auto_keep")}</label>
            <input id="auto-keep" type="number" min={1} value={cfg.keep}
                   onChange={(e) => setCfg({ ...cfg, keep: Number(e.target.value) })} />
          </div>
          <button className="btn-sm" disabled={busy}
                  onClick={() => run(() => api.put("/api/admin/data/snapshot-config", cfg), t("data.auto_saved"))}>
            {t("action.save")}
          </button>
        </div>
        <div className="small muted">{t("data.auto_manual_kept")}</div>
      </div>

      {/* ---- Confirmation --------------------------------------------------- */}
      {confirming && (
        <Modal
          width={620}
          title={t("data.confirm_title")}
          onClose={() => setConfirming(false)}
          footer={
            <div className="between" style={{ width: "100%" }}>
              <button className="btn-secondary btn-sm" onClick={() => setConfirming(false)}>
                {t("action.cancel")}
              </button>
              <div className="inline" style={{ gap: 8 }}>
                <button className="btn-secondary btn-sm" disabled={busy} onClick={() => reset(false)}>
                  {t("data.confirm_without_copy")}
                </button>
                <button className="btn-sm" disabled={busy} onClick={() => reset(true)}>
                  {t("data.confirm_with_copy")}
                </button>
              </div>
            </div>
          }
        >
          <div className="stack" style={{ gap: 10 }}>
            <div>{t("data.confirm_intro", { n: String(totalRows) })}</div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {effective.map((k) => (
                <li key={k} className="small">
                  <span className="strong">{t(`data.domain.${k}`)}</span> : {cat.domains[k].total} {t("data.rows").toLowerCase()}
                  {!picked.includes(k) && <span className="muted"> {t("data.dragged")}</span>}
                </li>
              ))}
            </ul>
            <div className="small muted">{t("data.confirm_kept", { list: cat.never_erased.join(", ") })}</div>
          </div>
        </Modal>
      )}
    </div>
  );
}
