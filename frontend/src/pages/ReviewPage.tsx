import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { ProgressReviewRow } from "../types";
import { Dot, Spinner, ErrorBanner } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";
import { ChangeList, ConfidenceBadge, DeltaBadge } from "../components/progress";
import ReportExport from "../components/ReportExport";

const PERIODS = [7, 14, 30];

export default function ReviewPage() {
  const { t } = useI18n();
  const [days, setDays] = useState(7);
  const [rows, setRows] = useState<ProgressReviewRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows(null);
    api.get<ProgressReviewRow[]>(`/api/progress/review?since_days=${days}`).then(setRows).catch((e) => setError(e.message));
  }, [days]);

  useSetPageChrome(
    {
      tabs: PERIODS.map((d) => ({ key: String(d), label: t(`review.period.${d}`) })),
      activeTab: String(days),
      onTab: (k) => setDays(Number(k)),
      actions: <ReportExport sinceDays={days} />,
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

  if (error) return <ErrorBanner message={error} />;
  if (!rows) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="small muted">{t("review.intro")}</div>
      {rows.length === 0 && <div className="card muted">{t("review.no_squads")}</div>}

      {byTribe.map(([tribe, squads]) => (
        <div key={tribe} className="stack" style={{ gap: 10 }}>
          <h2 style={{ margin: 0 }}>{tribe}</h2>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))" }}>
            {squads.map((r) => (
              <div key={r.squad_id} className="card stack" style={{ gap: 8 }}>
                <div className="between" style={{ alignItems: "flex-start" }}>
                  <Link to={`/squads/${r.squad_id}`} className="strong" style={{ fontSize: 16 }}>{r.squad_name}</Link>
                  <div className="inline" style={{ gap: 8 }}>
                    <span className="strong">{r.progress_pct}%</span>
                    <DeltaBadge value={r.progress_delta} />
                  </div>
                </div>

                <div className="inline small muted" style={{ gap: 14, flexWrap: "wrap" }}>
                  {r.blocked_count > 0 && <span><Dot status="red" /> {r.blocked_count} {t("card.blocked")}</span>}
                  {r.at_risk_count > 0 && <span><Dot status="amber" /> {r.at_risk_count} {t("card.atrisk")}</span>}
                  {r.confidence ? <ConfidenceBadge value={r.confidence} /> : null}
                  <span>{r.points_in_period} {t("review.points")}</span>
                </div>

                {r.note && (
                  <div className="small" style={{ whiteSpace: "pre-wrap", borderLeft: "3px solid var(--accent)", paddingLeft: 10 }}>
                    <span className="muted">{t("review.latest_note")} : </span>{r.note}
                  </div>
                )}

                {r.changes.length > 0 ? (
                  <ChangeList changes={r.changes} max={6} />
                ) : (
                  <div className="small muted">{t("review.no_change")}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
