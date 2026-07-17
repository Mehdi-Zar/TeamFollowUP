// PrintDashboardPage - print/PDF-oriented view of the whole-org dashboard.
// Unchromed layout meant to be opened in its own window and auto-printed. Shows
// the summary KPIs and a per-squad table (annual + quarterly progress, late
// jalons, freshness). Reuses the shared ReportHeader/ReportFooter from the squad
// print page for a consistent report look.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { DashboardOut } from "../types";
import { ReportFooter, ReportHeader } from "./PrintSquadPage";

/**
 * Printable organization dashboard for a given reporting year.
 *
 * Business logic:
 * - Optional `?year=` selects the reporting year; omitted means the API default.
 * - Fetches `/api/dashboard`, then auto-opens the print dialog once data is in
 *   (short delay so the DOM can paint first).
 * - Renders four summary stats and one table row per squad.
 *
 * Access: users who can view the dashboard (route/endpoint enforce it).
 */
export default function PrintDashboardPage() {
  const [params] = useSearchParams();
  const year = params.get("year");
  const { t, roadmap, freshness } = useI18n();
  const [data, setData] = useState<DashboardOut | null>(null);

  // Load the dashboard payload for the selected (or default) year.
  useEffect(() => {
    api.get<DashboardOut>(`/api/dashboard${year ? `?year=${year}` : ""}`).then(setData);
  }, [year]);

  // Auto-print once data is ready; the delay lets the DOM paint first.
  useEffect(() => {
    if (data) setTimeout(() => window.print(), 400);
  }, [data]);

  if (!data) return <div className="spinner">{t("common.loading")}</div>;
  const s = data.summary;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: 32 }}>
      <ReportHeader title={`${t("dash.title")} - ${data.year}`} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 16, textAlign: "center" }}>
        <Stat label={t("dash.kpi.squads")} value={s.squads_total} />
        <Stat label={t("dash.blocked")} value={s.blocked_jalons} />
        <Stat label={t("dash.atrisk")} value={s.at_risk_jalons} />
        <Stat label={t("dash.kpi.stale")} value={s.squads_stale} />
      </div>

      <table>
        <thead>
          <tr>
            <th>{t("admin.squad")}</th>
            <th>{t("dash.annual")}</th>
            <th>Q1</th>
            <th>Q2</th>
            <th>Q3</th>
            <th>Q4</th>
            <th>{t("card.late")}</th>
            <th>{t("dash.filter.fresh")}</th>
          </tr>
        </thead>
        <tbody>
          {data.cards.map((c) => (
            <tr key={c.squad_id}>
              <td className="strong">{c.name}</td>
              <td>{c.annual_progress}%</td>
              <td>{c.quarter_progress["1"] ?? 0}%</td>
              <td>{c.quarter_progress["2"] ?? 0}%</td>
              <td>{c.quarter_progress["3"] ?? 0}%</td>
              <td>{c.quarter_progress["4"] ?? 0}%</td>
              <td>{c.blocked_count}</td>
              <td className="muted">{freshness(c.freshness)}{c.freshness.is_stale ? ` (${t("fresh.stale_suffix")})` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <ReportFooter />
    </div>
  );
}

/** Single summary KPI tile (large number + caption) used in the header grid. */
function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 10, padding: "10px 6px" }}>
      <div className="strong" style={{ fontSize: 24, color: "var(--navy)" }}>{value}</div>
      <div className="small muted">{label}</div>
    </div>
  );
}
