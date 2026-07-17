// PrintSquadPage - print/PDF-oriented view of a single squad's report.
// It is a bare, unchromed layout (no app nav) meant to be opened in its own
// window and immediately sent to the browser's print dialog. It also exports the
// shared ReportHeader / ReportFooter used by the other print pages.
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { SquadDetail } from "../types";
import { useModule } from "../config";

/**
 * Shared report banner (product label + title) with a "PDF" button that triggers
 * the print dialog. The button carries `no-print` so it is excluded from output.
 * Exported for reuse by the other print pages.
 */
export function ReportHeader({ title }: { title: string }) {
  return (
    <div style={{ borderBottom: "2px solid var(--navy)", paddingBottom: 8, marginBottom: 16 }}>
      <div className="small muted" style={{ textTransform: "uppercase", letterSpacing: ".04em" }}>
        Tribe Cockpit
      </div>
      <h1 style={{ margin: "2px 0 0" }}>{title}</h1>
      <div className="no-print" style={{ marginTop: 10 }}>
        <button className="btn-secondary" onClick={() => window.print()}>
          PDF
        </button>
      </div>
    </div>
  );
}

/** Shared report footer showing the generation timestamp. Exported for reuse. */
export function ReportFooter() {
  return (
    <div className="small muted" style={{ borderTop: "1px solid var(--line)", paddingTop: 8, marginTop: 20 }}>
      {new Date().toLocaleString()}
    </div>
  );
}

/**
 * One report row: a left label, an optional right-aligned value (e.g. status),
 * and an optional muted sub-label. Used for roadmap items, objectives and KPIs.
 */
function Line({ left, right, sub }: { left: string; right?: string; sub?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--line)", padding: "5px 0" }}>
      <div>
        {left}
        {sub ? <span className="small muted" style={{ marginLeft: 8 }}>{sub}</span> : null}
      </div>
      {right ? <span className="muted">{right}</span> : null}
    </div>
  );
}

/**
 * Printable one-squad report: annual/quarterly progress, roadmap items grouped by
 * quarter, objectives, and (when the KPI module + squad opt-in are on) KPIs.
 *
 * Business logic:
 * - Squad id comes from the route (`:id`); an optional `?year=` narrows the report
 *   to a given reporting year.
 * - Once the squad data has loaded, a short timeout auto-opens the print dialog so
 *   the page behaves like a "generate PDF" action.
 * - The KPI block is doubly gated: the `squad_content.kpis` module must be enabled
 *   AND the squad must have KPIs enabled.
 *
 * Access: users who can view the squad (route/endpoint enforce it).
 */
export default function PrintSquadPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const year = params.get("year");
  const { t, rag, roadmap, trend, freshness } = useI18n();
  const kpisOn = useModule()("squad_content", "kpis");
  const [squad, setSquad] = useState<SquadDetail | null>(null);

  // Fetch the squad detail whenever the id or year changes.
  useEffect(() => {
    api.get<SquadDetail>(`/api/squads/${id}${year ? `?year=${year}` : ""}`).then(setSquad);
  }, [id, year]);

  // Auto-trigger printing once data is in; the delay lets the DOM paint first.
  useEffect(() => {
    if (squad) setTimeout(() => window.print(), 400);
  }, [squad]);

  if (!squad) return <div className="spinner">{t("common.loading")}</div>;

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: 32 }}>
      <ReportHeader title={`${squad.name} (${squad.year})`} />
      <table style={{ marginBottom: 16 }}>
        <tbody>
          <tr><td className="muted" style={{ width: 200 }}>{t("dash.annual")}</td><td className="strong">{squad.annual_progress}%</td></tr>
          <tr><td className="muted">{t("squad.responsible")}</td><td>{squad.leader?.display_name || "-"}</td></tr>
          <tr><td className="muted">{t("dash.filter.fresh")}</td><td>{freshness(squad.freshness)}{squad.freshness.is_stale ? ` (${t("fresh.stale_suffix")})` : ""}</td></tr>
        </tbody>
      </table>

      {/* One section per quarter: its progress % plus that quarter's roadmap items */}
      {[1, 2, 3, 4].map((q) => {
        const cell = squad.quarter_progress[String(q)];
        const items = squad.roadmap_items.filter((r) => r.quarter === q);
        return (
          <div key={q} style={{ marginBottom: 12, breakInside: "avoid" }}>
            <h3 style={{ borderBottom: "1px solid var(--line)", paddingBottom: 4 }}>
              Q{q} - {cell?.progress_pct ?? 0}%
            </h3>
            {items.length === 0 ? (
              <div className="small muted">{t("squad.no_jalon")}</div>
            ) : (
              items.map((r) => <Line key={r.id} left={r.title} right={roadmap(r.status)} />)
            )}
          </div>
        );
      })}

      <div style={{ marginBottom: 12, breakInside: "avoid" }}>
        <h3 style={{ borderBottom: "1px solid var(--line)", paddingBottom: 4 }}>{t("squad.objectives", { year: squad.year })}</h3>
        {squad.objectives.length === 0 ? <div className="small muted">{t("squad.no_obj")}</div> : squad.objectives.map((o) => <Line key={o.id} left={o.title} right={rag(o.rag_status)} />)}
      </div>

      {kpisOn && squad.kpis_enabled && (
        <div style={{ marginBottom: 12, breakInside: "avoid" }}>
          <h3 style={{ borderBottom: "1px solid var(--line)", paddingBottom: 4 }}>{t("squad.kpis")}</h3>
          {squad.kpis.length === 0 ? <div className="small muted">{t("squad.no_kpi")}</div> : squad.kpis.map((k) => (
            <Line key={k.id} left={k.name} right={trend(k.trend_status)} sub={k.current_value != null ? `${k.current_value}${k.target_value != null ? ` / ${k.target_value}` : ""}${k.unit ? ` ${k.unit}` : ""}` : ""} />
          ))}
        </div>
      )}

      <ReportFooter />
    </div>
  );
}
