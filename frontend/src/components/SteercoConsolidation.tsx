// SteercoConsolidation - the leadership Steerco view, shown as a tab inside the
// Dashboard. It previews the KPI one-pager (rendered server-side to look like
// kpi-onepager.html) for a chosen squad or for all squads at once. Period + squad
// selection are lifted to DashboardPage so the standard chrome ExportMenu (top
// right, same model as every other page) targets the current selection. Squad
// leaders fill the underlying data from the reporting screen (SteercoEditor).
import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Spinner, EmptyState } from "./ui";
import { currentSteercoPeriod } from "../steerco";

type Entry = { squad_id: number; squad_name: string; filled: boolean; updated_at: string | null };

type Props = {
  period: string;
  setPeriod: (p: string) => void;
  squadId: string;      // "" = all squads
  setSquadId: (s: string) => void;
};

/** Steerco consolidation tab: pick a period + squad (or all) and preview the
 *  one-pager in-app. Export/subscribe live in the page chrome (ExportMenu). */
export default function SteercoConsolidation({ period, setPeriod, squadId, setSquadId }: Props) {
  const { t, lang } = useI18n();
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!period) setPeriod(currentSteercoPeriod());
  }, [period, setPeriod]);

  useEffect(() => {
    setEntries(null); setErr(null);
    api.get<Entry[]>(`/api/steerco/entries?period=${encodeURIComponent(period)}`)
      .then((rows) => {
        setEntries(rows);
        if (squadId && !rows.some((e) => String(e.squad_id) === squadId)) setSquadId("");
      })
      .catch((e) => { setErr(String(e?.message ?? e)); setEntries([]); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  const pq = encodeURIComponent(period);
  const htmlUrl = squadId
    ? `/api/steerco/onepager.html?squad_id=${squadId}&period=${pq}&lang=${lang}`
    : `/api/steerco/document.html?period=${pq}&lang=${lang}`;
  const filledCount = entries?.filter((e) => e.filled).length ?? 0;
  const title = squadId
    ? `${entries?.find((e) => String(e.squad_id) === squadId)?.squad_name ?? ""} (${period})`
    : `Steerco ${period}`;

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card" style={{ padding: 14 }}>
        <div className="row" style={{ gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ width: 160 }}>
            <label htmlFor="steerco-period">{t("steerco.period")}</label>
            <input id="steerco-period" value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="2026-07" />
          </div>
          <div style={{ minWidth: 200 }}>
            <label htmlFor="steerco-squad">{t("steerco.squad")}</label>
            <select id="steerco-squad" value={squadId} onChange={(e) => setSquadId(e.target.value)}>
              <option value="">{t("steerco.all_squads")}</option>
              {(entries ?? []).map((e) => (
                <option key={e.squad_id} value={e.squad_id}>{e.squad_name}{e.filled ? "" : ` (${t("steerco.not_filled")})`}</option>
              ))}
            </select>
          </div>
        </div>
        {entries && entries.length > 0 && (
          <div className="small muted" style={{ marginTop: 8 }}>
            {t("steerco.filled_count", { n: filledCount, total: entries.length })}
          </div>
        )}
      </div>

      {err && <div className="small" style={{ color: "var(--red)" }}>{err}</div>}

      {entries === null ? <Spinner /> : entries.length === 0 ? (
        <EmptyState message={t("steerco.no_squads")} />
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <iframe key={htmlUrl} src={htmlUrl} title={title}
                  style={{ width: "100%", height: 1180, border: 0, display: "block", background: "#F5F7FA" }} />
        </div>
      )}
    </div>
  );
}
