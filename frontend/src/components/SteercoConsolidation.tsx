// SteercoConsolidation - the leadership Steerco view, shown as a tab inside the
// Dashboard. It previews the KPI one-pager (rendered server-side to look like
// kpi-onepager.html) for a chosen platform or for all platforms at once. Period +
// platform selection are lifted to DashboardPage so the standard chrome ExportMenu
// (top right, same model as every other page) targets the current selection.
//
// One platform is one slide, whatever the number of squads feeding it. The row also
// says who is still owing a figure, because chasing a late contributor is most of the
// work of running a monthly committee.
import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Spinner, EmptyState } from "./ui";
import { currentSteercoPeriod } from "../steerco";

type Entry = {
  platform_id: number; platform_name: string; filled: boolean; updated_at: string | null;
  contributors: { id: number; name: string }[]; missing: string[]; unassigned: number;
};

type Props = {
  period: string;
  setPeriod: (p: string) => void;
  platformId: string;      // "" = all platforms
  setPlatformId: (s: string) => void;
};

/** Steerco consolidation tab: pick a period + platform (or all) and preview the
 *  one-pager in-app. Export/subscribe live in the page chrome (ExportMenu). */
export default function SteercoConsolidation({ period, setPeriod, platformId, setPlatformId }: Props) {
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
        if (platformId && !rows.some((e) => String(e.platform_id) === platformId)) setPlatformId("");
      })
      .catch((e) => { setErr(String(e?.message ?? e)); setEntries([]); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  const pq = encodeURIComponent(period);
  const htmlUrl = platformId
    ? `/api/steerco/onepager.html?platform_id=${platformId}&period=${pq}&lang=${lang}`
    : `/api/steerco/document.html?period=${pq}&lang=${lang}`;
  const filledCount = entries?.filter((e) => e.filled).length ?? 0;
  const selected = entries?.find((e) => String(e.platform_id) === platformId);
  const title = platformId ? `${selected?.platform_name ?? ""} (${period})` : `Steerco ${period}`;
  const late = (entries ?? []).filter((e) => e.missing.length);

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card" style={{ padding: 14 }}>
        <div className="row" style={{ gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ width: 160 }}>
            <label htmlFor="steerco-period">{t("steerco.period")}</label>
            <input id="steerco-period" value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="2026-07" />
          </div>
          <div style={{ minWidth: 200 }}>
            <label htmlFor="steerco-platform">{t("steerco.platform")}</label>
            <select id="steerco-platform" value={platformId} onChange={(e) => setPlatformId(e.target.value)}>
              <option value="">{t("steerco.all_platforms")}</option>
              {(entries ?? []).map((e) => (
                <option key={e.platform_id} value={e.platform_id}>{e.platform_name}{e.filled ? "" : ` (${t("steerco.not_filled")})`}</option>
              ))}
            </select>
          </div>
        </div>
        {entries && entries.length > 0 && (
          <div className="small muted" style={{ marginTop: 8 }}>
            {t("steerco.filled_count", { n: filledCount, total: entries.length })}
          </div>
        )}
        {/* Who is late, named. A slide fed by several squads is only as done as its
            last contributor, and the counter above cannot say that. */}
        {late.length > 0 && (
          <div className="small" style={{ marginTop: 6 }}>
            {late.map((e) => (
              <div key={e.platform_id} className="muted">
                {t("steerco.waiting_on", { platform: e.platform_name, who: e.missing.join(", ") })}
              </div>
            ))}
          </div>
        )}
      </div>

      {err && <div className="small" style={{ color: "var(--red)" }}>{err}</div>}

      {entries === null ? <Spinner /> : entries.length === 0 ? (
        <EmptyState message={t("steerco.no_platforms")} />
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <iframe key={htmlUrl} src={htmlUrl} title={title}
                  style={{ width: "100%", height: 1180, border: 0, display: "block", background: "#F5F7FA" }} />
        </div>
      )}
    </div>
  );
}
