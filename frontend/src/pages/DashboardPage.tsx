import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { useAuth } from "../auth";
import { DashboardOut, SquadCard, Tribe } from "../types";
import { Dot, FreshnessBadge, ProgressBar, Spinner, ErrorBanner } from "../components/ui";
import EmailExport from "../components/EmailExport";
import ReportSubscribe from "../components/ReportSubscribe";
import { useSetPageChrome } from "../components/pageChrome";

type SortKey = "risk" | "progress" | "name" | "fresh";
type Health = "all" | "blocked" | "at_risk" | "on_track";

function healthOf(c: SquadCard): "blocked" | "at_risk" | "on_track" {
  if (c.blocked_count > 0) return "blocked";
  if (c.at_risk_count > 0) return "at_risk";
  return "on_track";
}

export default function DashboardPage() {
  const { t, roadmap } = useI18n();
  const { default_year } = useConfig();
  const csvOn = useModule()("exports_csv");
  const { effectiveRole } = useAuth();
  const isAdmin = effectiveRole === "admin";
  const [data, setData] = useState<DashboardOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [sort, setSort] = useState<SortKey>("risk");
  const [health, setHealth] = useState<Health>("all");
  const [freshFilter, setFreshFilter] = useState<"all" | "stale" | "fresh">("all");
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeFilter, setTribeFilter] = useState<string>("");

  useEffect(() => {
    if (year === null && default_year) setYear(default_year);
  }, [default_year]);
  useEffect(() => {
    if (isAdmin) api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {});
  }, [isAdmin]);

  useEffect(() => {
    const p = new URLSearchParams();
    if (year) p.set("year", String(year));
    if (isAdmin && tribeFilter) p.set("tribe_id", tribeFilter);
    api.get<DashboardOut>(`/api/dashboard?${p.toString()}`).then(setData).catch((e) => setError(e.message));
  }, [year, tribeFilter, isAdmin]);

  const cards = useMemo(() => {
    if (!data) return [];
    let r = data.cards.filter((c) => {
      if (health !== "all" && healthOf(c) !== health) return false;
      if (freshFilter === "stale" && !c.freshness.is_stale) return false;
      if (freshFilter === "fresh" && c.freshness.is_stale) return false;
      return true;
    });
    r = [...r];
    if (sort === "risk") r.sort((a, b) => b.risk_rank - a.risk_rank || b.blocked_count - a.blocked_count || a.name.localeCompare(b.name));
    else if (sort === "progress") r.sort((a, b) => a.annual_progress - b.annual_progress);
    else if (sort === "name") r.sort((a, b) => a.name.localeCompare(b.name));
    else if (sort === "fresh") r.sort((a, b) => (b.freshness.age_days ?? 1e9) - (a.freshness.age_days ?? 1e9));
    return r;
  }, [data, health, freshFilter, sort]);

  useSetPageChrome(
    data
      ? {
          tabs: [
            { key: "all", label: t("dash.filter.all_f") },
            { key: "blocked", label: roadmap("blocked") },
            { key: "at_risk", label: roadmap("at_risk") },
            { key: "on_track", label: roadmap("on_track") },
          ],
          activeTab: health,
          onTab: (k) => setHealth(k as Health),
          actions: (
            <>
              <div className="seg">
                {[data.current_year - 1, data.current_year, data.current_year + 1].map((y) => (
                  <button key={y} className={y === data.year ? "active" : ""} onClick={() => setYear(y)}>{y}</button>
                ))}
              </div>
              {csvOn && <a className="btn btn-secondary btn-sm" href={`/api/exports/dashboard.csv?year=${data.year}`}>{t("action.csv")}</a>}
              <Link className="btn btn-secondary btn-sm" to="/print/dashboard" target="_blank">{t("action.report")}</Link>
              <ReportSubscribe />
              {csvOn && <EmailExport endpoint="/api/exports/dashboard/email" year={data.year} />}
            </>
          ),
        }
      : {},
    [data?.year, health, csvOn]
  );

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Spinner />;

  const focusQ = data.year === data.current_year ? data.current_quarter : undefined;
  const s = data.summary;

  return (
    <div className="stack" style={{ gap: 20 }}>
      {/* Concrete health band */}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
        <div className="kpi"><div className="v">{s.avg_progress}%</div><div className="l">{t("dash.avg")}</div></div>
        <div className="kpi"><div className={`v ${s.blocked_jalons ? "red" : ""}`}>{s.blocked_jalons}</div><div className="l">{t("dash.blocked")}</div></div>
        <div className="kpi"><div className={`v ${s.at_risk_jalons ? "orange" : ""}`}>{s.at_risk_jalons}</div><div className="l">{t("dash.atrisk")}</div></div>
        <div className="kpi"><div className={`v ${s.squads_stale ? "orange" : ""}`}>{s.squads_stale}</div><div className="l">{t("dash.kpi.stale")}</div></div>
        <div className="kpi"><div className="v">{s.squads_total}</div><div className="l">{t("dash.kpi.squads")}</div></div>
      </div>

      <div className="card" style={{ padding: 14 }}>
        <div className="row" style={{ alignItems: "flex-end", gap: 12 }}>
          {isAdmin && (
            <div style={{ width: 200 }}>
              <label>{t("admin.tribe")}</label>
              <select value={tribeFilter} onChange={(e) => setTribeFilter(e.target.value)}>
                <option value="">{t("dash.all_tribes")}</option>
                {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
              </select>
            </div>
          )}
          <div style={{ width: 190 }}>
            <label>{t("dash.sort")}</label>
            <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              <option value="risk">{t("dash.sort.risk")}</option>
              <option value="progress">{t("dash.sort.progress")}</option>
              <option value="name">{t("dash.sort.name")}</option>
              <option value="fresh">{t("dash.sort.fresh")}</option>
            </select>
          </div>
          <div style={{ width: 190 }}>
            <label>{t("dash.filter.fresh")}</label>
            <select value={freshFilter} onChange={(e) => setFreshFilter(e.target.value as any)}>
              <option value="all">{t("dash.filter.all_f")}</option>
              <option value="stale">{t("dash.fresh.stale")}</option>
              <option value="fresh">{t("dash.fresh.fresh")}</option>
            </select>
          </div>
        </div>
      </div>

      <div className="inline small muted" style={{ gap: 16, flexWrap: "wrap" }}>
        <span className="strong">{t("dash.legend")} :</span>
        <span className="inline"><Dot status="red" /> {roadmap("blocked")}</span>
        <span className="inline"><Dot status="amber" /> {roadmap("at_risk")}</span>
        <span className="inline"><Dot status="green" /> {roadmap("done")}</span>
      </div>

      {cards.length === 0 ? (
        <div className="card muted">{t("dash.none")}</div>
      ) : (
        <div className="squad-grid-2">
          {cards.map((c) => <Card key={c.squad_id} card={c} focusQ={focusQ} showTribe={isAdmin} />)}
        </div>
      )}
    </div>
  );
}

function Card({ card, focusQ, showTribe }: { card: SquadCard; focusQ?: number; showTribe?: boolean }) {
  const navigate = useNavigate();
  const { t, roadmap } = useI18n();
  const h = healthOf(card);
  const sClass = h === "blocked" ? "s-red" : h === "at_risk" ? "s-orange" : "s-green";
  return (
    <button className={`squad-card squad-card-lg ${sClass}`} onClick={() => navigate(`/squads/${card.squad_id}`)}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div>
          <div className="strong sc-name" style={{ color: "var(--navy)" }}>{card.name}</div>
          <div className="muted small" style={{ marginTop: 2 }}>
            {card.leader?.display_name || t("card.no_leader")} · {card.members_count} {t("card.members")}
          </div>
        </div>
        {showTribe && card.tribe_name && <span className="badge badge-navy">{card.tribe_name}</span>}
      </div>

      {/* Annual progress */}
      <div style={{ marginTop: 14 }}>
        <div className="between" style={{ marginBottom: 4 }}>
          <span className="small strong" style={{ color: "var(--navy)" }}>{t("dash.annual")}</span>
          <span className="small muted">{card.annual_progress}%</span>
        </div>
        <ProgressBar pct={card.annual_progress} />
      </div>

      {/* 4 quarters in columns */}
      <div className="quarters" style={{ marginTop: 14 }}>
        {[1, 2, 3, 4].map((q) => {
          const bd = card.quarter_breakdowns[String(q)] || { total: 0, blocked: 0, at_risk: 0, done: 0, on_track: 0 };
          const pct = card.quarter_progress[String(q)] ?? 0;
          return (
            <div key={q} className={`q ${focusQ === q ? "current" : ""}`}>
              <div className="qlabel">Q{q}{focusQ === q ? " ·" : ""}</div>
              <div className="qbar"><div style={{ width: `${pct}%` }} /></div>
              <div className="qpct">{pct}%</div>
              <div className="small" style={{ marginTop: 4, lineHeight: 1.5 }}>
                {bd.blocked > 0 && <div style={{ color: "var(--red)" }}>● {bd.blocked} {roadmap("blocked")}</div>}
                {bd.at_risk > 0 && <div style={{ color: "var(--orange)" }}>● {bd.at_risk} {roadmap("at_risk")}</div>}
                <div className="muted">{bd.done}/{bd.total} {t("card.done")}</div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="between" style={{ marginTop: 16, gap: 12, flexWrap: "wrap" }}>
        <span className="inline rag-counts" title="Objectives">
          <span style={{ color: "var(--red)" }}><Dot status="red" /> {card.counts.objectives_red}</span>
          <span style={{ color: "var(--orange)" }}><Dot status="amber" /> {card.counts.objectives_amber}</span>
          <span style={{ color: "var(--green)" }}><Dot status="green" /> {card.counts.objectives_green}</span>
        </span>
        <FreshnessBadge freshness={card.freshness} />
      </div>
    </button>
  );
}
