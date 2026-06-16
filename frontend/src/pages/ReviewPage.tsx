import { ReactNode, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { ProgressReviewRow } from "../types";
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

function LegendChip({ rag, label }: { rag: "red" | "amber" | "green"; label: string }) {
  return (
    <span className="inline" style={{ gap: 6, alignItems: "center" }}>
      <Dot status={rag} /><span className="small strong">{label}</span>
    </span>
  );
}

export default function ReviewPage() {
  const { t } = useI18n();
  const [days, setDays] = useState(7);
  const [rows, setRows] = useState<ProgressReviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [help, setHelp] = useState(false);

  useEffect(() => {
    setRows(null);
    api.get<ProgressReviewRow[]>(`/api/progress/review?since_days=${days}`).then(setRows).catch((e) => setError(e.message));
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

  return (
    <div className="stack" style={{ gap: 18 }}>
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
          <button className="btn-ghost btn-sm" onClick={() => setHelp(true)}>ⓘ {t("review.how")}</button>
        </div>
      </div>

      {help && (
        <Modal title={t("review.how")} onClose={() => setHelp(false)} width={520}>
          <div className="stack" style={{ gap: 12 }}>
            {[
              ["📊", t("review.m.progress"), t("review.h.progress")],
              ["📈", t("review.m.delta"), t("review.h.delta")],
              ["🎯", t("review.m.confidence"), t("review.h.confidence")],
              ["🔴", t("review.m.jalons"), t("review.h.blocked")],
              ["🔄", t("review.m.changes"), t("review.h.changes")],
            ].map(([icon, label, desc]) => (
              <div key={label} className="inline" style={{ gap: 12, alignItems: "flex-start" }}>
                <span style={{ fontSize: 22, lineHeight: 1, width: 28, textAlign: "center" }}>{icon}</span>
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
                      <span className="muted">💬 {t("review.latest_note")} : </span>{r.note}
                    </div>
                  )}

                  <div>
                    <div className="small muted" style={{ marginBottom: 4 }}>🔄 {t("review.m.changes")} · <span title={t("review.h.points")}>{r.points_in_period} {t("review.points")}</span></div>
                    {r.changes.length > 0 ? <ChangeList changes={r.changes} max={6} /> : <div className="small muted">{t("review.no_change")}</div>}
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
