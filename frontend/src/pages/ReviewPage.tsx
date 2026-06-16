import { ReactNode, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { ProgressReviewRow, ReviewAction } from "../types";
import { Dot, Spinner, ErrorBanner, ProgressBar, Modal } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";
import { ChangeList } from "../components/progress";
import ExportMenu from "../components/ExportMenu";

const PERIODS = [7, 14, 30];

type Verdict = "blocked" | "tension" | "ontrack";
function verdictOf(r: ProgressReviewRow): Verdict {
  if (r.blocked_count > 0) return "blocked";
  if (r.at_risk_count > 0 || r.progress_delta < 0) return "tension";
  return "ontrack";
}
const VERDICT_RAG: Record<Verdict, "red" | "amber" | "green"> = { blocked: "red", tension: "amber", ontrack: "green" };

/** Big, explicit "this week's move" badge. */
function Delta({ value }: { value: number }) {
  const { t } = useI18n();
  const up = value > 0, down = value < 0;
  const color = up ? "var(--green)" : down ? "var(--red)" : "var(--grey)";
  const arrow = up ? "▲" : down ? "▼" : "→";
  const label = up ? t("review.up") : down ? t("review.down") : t("review.flat");
  return (
    <span className="inline" style={{ gap: 6, color, fontWeight: 600 }}>
      <span style={{ fontSize: 15 }}>{arrow}</span>
      <span>{value > 0 ? `+${value}` : value} pts</span>
      <span className="small" style={{ fontWeight: 400 }}>· {label}</span>
    </span>
  );
}

/** Confidence as a 5-segment gauge with a plain label. */
function Confidence({ value }: { value?: number | null }) {
  const { t } = useI18n();
  if (!value) return <span className="small muted">{t("review.conf_none")}</span>;
  const color = value >= 4 ? "var(--green)" : value === 3 ? "var(--orange)" : "var(--red)";
  return (
    <span className="inline" style={{ gap: 8, alignItems: "center" }} title={t("review.conf_help")}>
      <span className="inline" style={{ gap: 3 }}>
        {[1, 2, 3, 4, 5].map((i) => (
          <span key={i} style={{ width: 14, height: 8, borderRadius: 2, background: i <= value ? color : "var(--line)" }} />
        ))}
      </span>
      <span className="small">{t(`progress.confidence.${value}`)} ({value}/5)</span>
    </span>
  );
}

function Metric({ label, children, help }: { label: string; children: ReactNode; help?: string }) {
  return (
    <div title={help} style={{ minWidth: 0 }}>
      <div className="small muted" style={{ marginBottom: 2 }}>{label}</div>
      <div>{children}</div>
    </div>
  );
}

// Clean line icons (Feather-style) instead of emoji.
const Svg = ({ children }: { children: ReactNode }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);
const IcoProgress = () => <Svg><line x1="6" y1="20" x2="6" y2="14" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="18" y1="20" x2="18" y2="10" /></Svg>;
const IcoTrend = () => <Svg><polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" /></Svg>;
const IcoTarget = () => <Svg><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" /></Svg>;
const IcoAlert = () => <Svg><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></Svg>;
const IcoActivity = () => <Svg><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></Svg>;
const IcoNote = () => <Svg><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></Svg>;
const IcoInfo = () => <Svg><circle cx="12" cy="12" r="9" /><line x1="12" y1="11" x2="12" y2="16" /><line x1="12" y1="8" x2="12.01" y2="8" /></Svg>;

function IconBadge({ children, color = "var(--accent)" }: { children: ReactNode; color?: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center",
                   width: 34, height: 34, borderRadius: 9, background: "var(--ice-soft)", color, flex: "0 0 auto" }}>
      {children}
    </span>
  );
}

function LegendChip({ rag, label }: { rag: "red" | "amber" | "green"; label: string }) {
  return (
    <span className="inline" style={{ gap: 6, alignItems: "center" }}>
      <Dot status={rag} /><span className="small strong">{label}</span>
    </span>
  );
}

/** Structured COPIL actions per squad: text + owner + due date + done/to-do. */
function ActionItems({ squadId, canEdit, onError }: { squadId: number; canEdit: boolean; onError: (m: string) => void }) {
  const { t, formatDate } = useI18n();
  const [items, setItems] = useState<ReviewAction[] | null>(null);
  const [add, setAdd] = useState({ text: "", owner: "", due_date: "" });

  async function load() {
    try { setItems(await api.get<ReviewAction[]>(`/api/squads/${squadId}/actions`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  useEffect(() => { load(); }, [squadId]);
  async function run(fn: () => Promise<any>) {
    try { await fn(); await load(); }
    catch (e) { onError(e instanceof ApiError ? (e.status === 403 ? t("review.actions_forbidden") : e.message) : "Erreur"); }
  }
  const create = () => { if (add.text.trim()) run(async () => { await api.post(`/api/squads/${squadId}/actions`, { text: add.text.trim(), owner: add.owner.trim() || null, due_date: add.due_date || null }); setAdd({ text: "", owner: "", due_date: "" }); }); };

  const overdue = (a: ReviewAction) => !a.done && a.due_date && new Date(a.due_date) < new Date();

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="small muted inline" style={{ gap: 6 }}><IcoNote /> {t("review.actions_title")}</div>
      {items && items.length === 0 && <div className="small muted">{t("review.actions_none")}</div>}
      {items?.map((a) => (
        <div key={a.id} className="inline" style={{ gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={a.done} disabled={!canEdit} onChange={(e) => run(() => api.put(`/api/actions/${a.id}`, { done: e.target.checked }))} />
          <span className="small" style={{ flex: 1, minWidth: 0, textDecoration: a.done ? "line-through" : "none", color: a.done ? "var(--grey)" : undefined }}>{a.text}</span>
          {a.owner && <span className="badge badge-grey">{a.owner}</span>}
          {a.due_date && <span className="small" style={{ color: overdue(a) ? "var(--red)" : "var(--grey)" }}>{formatDate(a.due_date)}</span>}
          {canEdit && <button className="btn-ghost btn-sm" onClick={() => run(() => api.del(`/api/actions/${a.id}`))}>✕</button>}
        </div>
      ))}
      {canEdit && (
        <div className="row" style={{ gap: 6, alignItems: "flex-end" }}>
          <input style={{ flex: 1, minWidth: 130 }} placeholder={t("review.actions_ph")} value={add.text}
                 onChange={(e) => setAdd({ ...add, text: e.target.value })} onKeyDown={(e) => e.key === "Enter" && create()} />
          <input style={{ width: 100 }} placeholder={t("review.action_owner")} value={add.owner} onChange={(e) => setAdd({ ...add, owner: e.target.value })} />
          <input style={{ width: 140 }} type="date" value={add.due_date} onChange={(e) => setAdd({ ...add, due_date: e.target.value })} />
          <button className="btn-secondary btn-sm" disabled={!add.text.trim()} onClick={create}>{t("review.actions_add")}</button>
        </div>
      )}
    </div>
  );
}

export default function ReviewPage() {
  const { t } = useI18n();
  const [days, setDays] = useState(7);
  const [rows, setRows] = useState<ProgressReviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [help, setHelp] = useState(false);
  const { effectiveRole } = useAuth();
  const canCapture = effectiveRole !== "member"; // who may log decisions/actions

  function load() {
    api.get<ProgressReviewRow[]>(`/api/progress/review?since_days=${days}`).then(setRows).catch((e) => setError(e.message));
  }
  useEffect(() => {
    setRows(null);
    load();
  }, [days]);

  const isPreset = PERIODS.includes(days);
  useSetPageChrome(
    {
      tabs: PERIODS.map((d) => ({ key: String(d), label: t(`review.period.${d}`) })),
      activeTab: isPreset ? String(days) : "",
      onTab: (k) => setDays(Number(k)),
      actions: (
        <div className="inline" style={{ gap: 10, alignItems: "center" }}>
          <label className="inline small muted" style={{ gap: 6, alignItems: "center" }}>
            {t("review.custom")}
            <input type="number" min={1} max={365} style={{ width: 72 }} value={days}
                   onChange={(e) => setDays(Math.max(1, Math.min(365, Number(e.target.value) || 1)))} />
            {t("review.days_unit")}
          </label>
          <ExportMenu sinceDays={days} />
        </div>
      ),
    },
    [days, t]
  );

  const byTribe = useMemo(() => {
    const m = new Map<string, ProgressReviewRow[]>();
    for (const r of rows ?? []) {
      const key = r.tribe_name || "—";
      (m.get(key) ?? m.set(key, []).get(key)!).push(r);
    }
    return [...m.entries()];
  }, [rows]);

  const summary = useMemo(() => {
    const list = rows ?? [];
    return {
      up: list.filter((r) => r.progress_delta > 0).length,
      flat: list.filter((r) => r.progress_delta === 0).length,
      down: list.filter((r) => r.progress_delta < 0).length,
      blocked: list.filter((r) => r.blocked_count > 0).length,
    };
  }, [rows]);

  if (error) return <ErrorBanner message={error} />;
  if (!rows) return <Spinner />;

  const attention = (rows ?? []).filter((r) => verdictOf(r) !== "ontrack")
    .sort((a, b) => (b.blocked_count - a.blocked_count) || (a.progress_delta - b.progress_delta));

  return (
    <div className="stack" style={{ gap: 18 }}>
      {/* Purpose */}
      <div className="card" style={{ borderLeft: "4px solid var(--accent)" }}>
        <div className="strong">{t("review.purpose_title")}</div>
        <div className="small muted" style={{ marginTop: 4 }}>{t("review.purpose_body")}</div>
      </div>

      {/* Visual legend strip */}
      <div className="card" style={{ padding: "10px 14px" }}>
        <div className="between" style={{ alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div className="inline" style={{ gap: 18, flexWrap: "wrap", alignItems: "center" }}>
            <LegendChip rag="green" label={t("review.verdict.ontrack")} />
            <LegendChip rag="amber" label={t("review.verdict.tension")} />
            <LegendChip rag="red" label={t("review.verdict.blocked")} />
            <span style={{ width: 1, height: 18, background: "var(--line)" }} />
            <span className="inline small" style={{ gap: 6, color: "var(--green)", fontWeight: 600 }}>▲ {t("review.up")}</span>
            <span className="inline small" style={{ gap: 6, color: "var(--red)", fontWeight: 600 }}>▼ {t("review.down")}</span>
          </div>
          <button className="btn-ghost btn-sm inline" style={{ gap: 6 }} onClick={() => setHelp(true)}><IcoInfo /> {t("review.how")}</button>
        </div>
      </div>

      {help && (
        <Modal title={t("review.how")} onClose={() => setHelp(false)} width={520}>
          <div className="stack" style={{ gap: 14 }}>
            {[
              [<IcoProgress />, "var(--accent)", t("review.m.progress"), t("review.h.progress")],
              [<IcoTrend />, "var(--green)", t("review.m.delta"), t("review.h.delta")],
              [<IcoTarget />, "var(--navy)", t("review.m.confidence"), t("review.h.confidence")],
              [<IcoAlert />, "var(--red)", t("review.m.jalons"), t("review.h.blocked")],
              [<IcoActivity />, "var(--accent)", t("review.m.changes"), t("review.h.changes")],
            ].map(([icon, color, label, desc]: any) => (
              <div key={label} className="inline" style={{ gap: 12, alignItems: "center" }}>
                <IconBadge color={color}>{icon}</IconBadge>
                <div><div className="strong small">{label}</div><div className="small muted">{desc}</div></div>
              </div>
            ))}
          </div>
        </Modal>
      )}

      {/* Summary band */}
      {rows.length > 0 && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
          <div className="kpi"><div className="v" style={{ color: "var(--green)" }}>{summary.up}</div><div className="l">{t("review.sum.up")}</div></div>
          <div className="kpi"><div className="v">{summary.flat}</div><div className="l">{t("review.sum.flat")}</div></div>
          <div className="kpi"><div className="v" style={{ color: summary.down ? "var(--red)" : undefined }}>{summary.down}</div><div className="l">{t("review.sum.down")}</div></div>
          <div className="kpi"><div className={`v ${summary.blocked ? "red" : ""}`}>{summary.blocked}</div><div className="l">{t("review.sum.blocked")}</div></div>
        </div>
      )}

      {/* Squads to unblock — the headline for COPIL prep */}
      {attention.length > 0 && (
        <div className="card stack" style={{ gap: 10, borderTop: "3px solid var(--red)" }}>
          <div className="strong inline" style={{ gap: 8 }}><IcoAlert /> {t("review.attention_title")} ({attention.length})</div>
          <div className="stack" style={{ gap: 6 }}>
            {attention.map((r) => {
              const v = verdictOf(r);
              const reasons = [
                r.blocked_count > 0 ? `${r.blocked_count} ${t("review.m.blocked")}` : null,
                r.at_risk_count > 0 ? `${r.at_risk_count} ${t("review.m.atrisk")}` : null,
                r.progress_delta < 0 ? `${r.progress_delta} pts` : null,
              ].filter(Boolean).join(" · ");
              return (
                <div key={r.squad_id} className="between" style={{ gap: 10, padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
                  <div className="inline" style={{ gap: 8 }}>
                    <Dot status={VERDICT_RAG[v]} />
                    <Link to={`/squads/${r.squad_id}`} className="strong">{r.squad_name}</Link>
                    {r.tribe_name && <span className="small muted">· {r.tribe_name}</span>}
                  </div>
                  <span className="small" style={{ color: VERDICT_RAG[v] === "red" ? "var(--red)" : "var(--orange)" }}>{reasons || t(`review.verdict.${v}`)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {rows.length === 0 && <div className="card muted">{t("review.no_squads")}</div>}

      {byTribe.map(([tribe, squads]) => (
        <div key={tribe} className="stack" style={{ gap: 10 }}>
          <h2 style={{ margin: 0 }}>{tribe}</h2>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(440px, 1fr))", gap: 14 }}>
            {squads.map((r) => {
              const v = verdictOf(r);
              return (
                <div key={r.squad_id} className="card stack" style={{ gap: 12, borderTop: `3px solid var(--${VERDICT_RAG[v] === "red" ? "red" : VERDICT_RAG[v] === "amber" ? "orange" : "green"})` }}>
                  <div className="between" style={{ alignItems: "flex-start" }}>
                    <Link to={`/squads/${r.squad_id}`} className="strong" style={{ fontSize: 16 }}>{r.squad_name}</Link>
                    <span className={`badge badge-${VERDICT_RAG[v] === "amber" ? "orange" : VERDICT_RAG[v]}`}>
                      <Dot status={VERDICT_RAG[v]} /> {t(`review.verdict.${v}`)}
                    </span>
                  </div>

                  <div className="row" style={{ gap: 16, alignItems: "flex-start" }}>
                    <Metric label={t("review.m.progress")} help={t("review.h.progress")}>
                      <div className="inline" style={{ gap: 8, alignItems: "center" }}>
                        <span className="strong" style={{ fontSize: 18 }}>{r.progress_pct}%</span>
                      </div>
                      <ProgressBar pct={r.progress_pct} />
                    </Metric>
                    <Metric label={t("review.m.delta")} help={t("review.h.delta")}>
                      <Delta value={r.progress_delta} />
                    </Metric>
                  </div>

                  <div className="row" style={{ gap: 16, alignItems: "flex-start" }}>
                    <Metric label={t("review.m.confidence")} help={t("review.h.confidence")}>
                      <Confidence value={r.confidence} />
                    </Metric>
                    <Metric label={t("review.m.jalons")} help={t("review.h.blocked")}>
                      <div className="inline small" style={{ gap: 12, flexWrap: "wrap" }}>
                        {r.blocked_count > 0 ? <span><Dot status="red" /> {r.blocked_count} {t("review.m.blocked")}</span> : null}
                        {r.at_risk_count > 0 ? <span><Dot status="amber" /> {r.at_risk_count} {t("review.m.atrisk")}</span> : null}
                        {r.blocked_count === 0 && r.at_risk_count === 0 ? <span className="muted">{t("review.none")}</span> : null}
                      </div>
                    </Metric>
                  </div>

                  {r.note && (
                    <div className="small" style={{ whiteSpace: "pre-wrap", background: "var(--ice-soft)", borderRadius: 8, padding: "8px 10px" }}>
                      <span className="muted inline" style={{ gap: 6 }}><IcoNote /> {t("review.note_label2")} : </span>{r.note}
                    </div>
                  )}

                  {/* Structured COPIL decisions & actions */}
                  <ActionItems squadId={r.squad_id} canEdit={canCapture} onError={setError} />

                  <div style={{ borderTop: "1px solid var(--line)", paddingTop: 8 }}>
                    <div className="small muted inline" style={{ marginBottom: 4, gap: 6 }}><IcoActivity /> {t("review.m.changes")} · <span title={t("review.h.points")}>{r.points_in_period} {t("review.points")}</span></div>
                    {r.changes.length > 0 ? <ChangeList changes={r.changes} max={5} /> : <div className="small muted">{t("review.no_change")}</div>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
