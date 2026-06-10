import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { SquadDetail } from "../types";

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

export function ReportFooter() {
  return (
    <div className="small muted" style={{ borderTop: "1px solid var(--line)", paddingTop: 8, marginTop: 20 }}>
      {new Date().toLocaleString()}
    </div>
  );
}

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

export default function PrintSquadPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const year = params.get("year");
  const { t, rag, roadmap, trend, freshness } = useI18n();
  const [squad, setSquad] = useState<SquadDetail | null>(null);

  useEffect(() => {
    api.get<SquadDetail>(`/api/squads/${id}${year ? `?year=${year}` : ""}`).then(setSquad);
  }, [id, year]);

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
          <tr><td className="muted">{t("squad.responsible")}</td><td>{squad.leader?.display_name || "—"}</td></tr>
          <tr><td className="muted">{t("dash.filter.fresh")}</td><td>{freshness(squad.freshness)}{squad.freshness.is_stale ? ` (${t("fresh.stale_suffix")})` : ""}</td></tr>
        </tbody>
      </table>

      {[1, 2, 3, 4].map((q) => {
        const cell = squad.quarter_progress[String(q)];
        const items = squad.roadmap_items.filter((r) => r.quarter === q);
        return (
          <div key={q} style={{ marginBottom: 12, breakInside: "avoid" }}>
            <h3 style={{ borderBottom: "1px solid var(--line)", paddingBottom: 4 }}>
              Q{q} — {cell?.progress_pct ?? 0}%
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

      {squad.kpis_enabled && (
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
