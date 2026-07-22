/**
 * DashboardPage - the leadership overview of every squad's health.
 *
 * Shows a KPI band (average progress, blocked/at-risk milestones, stale squads,
 * squad count), an absences widget, a filter/search/sort toolbar, and a grid of
 * one squad-health card each. Admins additionally get a tribe filter and see the
 * tribe badge on every card. The "Initiatives" tab lives under the same menu and
 * simply routes to /initiatives. Data comes from a single /api/dashboard call.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { useAuth } from "../auth";
import { DashboardOut, SquadCard, Tribe } from "../types";
import { Dot, FreshnessBadge, ProgressBar, Spinner, ErrorBanner, EmptyState } from "../components/ui";
import ExportMenu from "../components/ExportMenu";
import { ReportingButton } from "../components/ReportingModal";
import AbsencesWidget from "../components/AbsencesWidget";
import SteercoConsolidation from "../components/SteercoConsolidation";
import { useSetPageChrome } from "../components/pageChrome";
import { currentSteercoPeriod } from "../steerco";

type SortKey = "risk" | "progress" | "name" | "fresh";
type Health = "all" | "blocked" | "at_risk" | "on_track";

/** Derive a squad's overall health from its milestone counts: any blocked
 *  milestone -> "blocked", else any at-risk -> "at_risk", else "on_track".
 *  Drives both the status dot/colour and the health filter. */
function healthOf(c: SquadCard): "blocked" | "at_risk" | "on_track" {
  if (c.blocked_count > 0) return "blocked";
  if (c.at_risk_count > 0) return "at_risk";
  return "on_track";
}

/**
 * Dashboard overview page. Loads the squad-health cards for a given year (and,
 * for admins, an optional tribe), then filters/sorts them client-side.
 * Access: any authenticated user; only admins see the tribe filter + tribe badges.
 */
export default function DashboardPage() {
  const { t, roadmap } = useI18n();
  const { default_year } = useConfig();
  const moduleOn = useModule();
  const { effectiveRole } = useAuth();
  const isAdmin = effectiveRole === "admin";
  const navigate = useNavigate();
  // Dashboard + Initiatives are merged under one menu: everyone gets the Initiatives
  // tab (read-only list, editable by the tribe leader); the overview stays as-is.
  const showInitiatives = true;
  // Steerco consolidation is a leadership view: shown as an in-page tab to admins and
  // tribe leaders when the module is on (squad leaders fill the data from reporting).
  const steercoTabOn = moduleOn("steerco") && (isAdmin || effectiveRole === "tribe_leader");
  // The active sub-view is driven by ?tab= so the tab survives navigating to the
  // Initiatives page and back (the Initiatives tab bar links back to /?tab=steerco).
  const [params, setParams] = useSearchParams();
  const tab: "overview" | "steerco" = params.get("tab") === "steerco" ? "steerco" : "overview";
  // Steerco view filters, lifted here so the chrome ExportMenu can target them.
  const [steercoPeriod, setSteercoPeriod] = useState<string>(currentSteercoPeriod());
  const [steercoSquad, setSteercoSquad] = useState<string>("");   // "" = all squads
  const [data, setData] = useState<DashboardOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [sort, setSort] = useState<SortKey>("risk");
  const [health, setHealth] = useState<Health>("all");
  const [freshFilter, setFreshFilter] = useState<"all" | "stale" | "fresh">("all");
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeFilter, setTribeFilter] = useState<string>("");
  const [query, setQuery] = useState("");

  // Seed the selected year from the org default once it is known.
  useEffect(() => {
    if (year === null && default_year) setYear(default_year);
  }, [default_year]);
  // Tribe list only needed to populate the admin-only tribe filter.
  useEffect(() => {
    if (isAdmin) api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {});
  }, [isAdmin]);

  // (Re)load the dashboard whenever the year or (admin) tribe filter changes.
  useEffect(() => {
    const p = new URLSearchParams();
    if (year) p.set("year", String(year));
    if (isAdmin && tribeFilter) p.set("tribe_id", tribeFilter);
    api.get<DashboardOut>(`/api/dashboard?${p.toString()}`).then(setData).catch((e) => setError(e.message));
  }, [year, tribeFilter, isAdmin]);

  // Client-side view of the cards: apply search + health + freshness filters, then sort.
  const cards = useMemo(() => {
    if (!data) return [];
    const needle = query.trim().toLowerCase();
    let r = data.cards.filter((c) => {
      if (needle && !c.name.toLowerCase().includes(needle)) return false;
      if (health !== "all" && healthOf(c) !== health) return false;
      if (freshFilter === "stale" && !c.freshness.is_stale) return false;
      if (freshFilter === "fresh" && c.freshness.is_stale) return false;
      return true;
    });
    r = [...r];
    // "risk": most at-risk first (risk rank, then blocked count, then name as tie-breakers).
    if (sort === "risk") r.sort((a, b) => b.risk_rank - a.risk_rank || b.blocked_count - a.blocked_count || a.name.localeCompare(b.name));
    else if (sort === "progress") r.sort((a, b) => a.annual_progress - b.annual_progress);
    else if (sort === "name") r.sort((a, b) => a.name.localeCompare(b.name));
    else if (sort === "fresh") r.sort((a, b) => (b.freshness.age_days ?? 1e9) - (a.freshness.age_days ?? 1e9));
    return r;
  }, [data, health, freshFilter, sort, query]);

  useSetPageChrome(
    data
      ? {
          tabs: [
            { key: "overview", label: t("dash.tab_overview") },
            ...(steercoTabOn ? [{ key: "steerco", label: t("steerco.tab") }] : []),
            ...(showInitiatives ? [{ key: "initiatives", label: t("nav.initiatives") }] : []),
          ],
          activeTab: tab,
          onTab: (k) => {
            if (k === "initiatives") navigate("/initiatives");
            else if (k === "steerco") setParams({ tab: "steerco" });
            else setParams({});
          },
          // Same toolbar model on every tab: subscribe button + export dropdown. On
          // Steerco the export dropdown carries the one-pager document instead.
          actions: tab === "steerco" ? (
            <>
              <ReportingButton />
              <ExportMenu docs={["steerco", "report"]} steerco={{ period: steercoPeriod, squadId: steercoSquad }} />
            </>
          ) : (
            <>
              <div className="seg">
                {[data.current_year - 1, data.current_year, data.current_year + 1].map((y) => (
                  <button key={y} className={y === data.year ? "active" : ""} onClick={() => setYear(y)}>{y}</button>
                ))}
              </div>
              <ReportingButton />
              <ExportMenu year={data.year} docs={["dashboard", "report"]} />
            </>
          ),
        }
      : {},
    [data?.year, showInitiatives, steercoTabOn, tab, steercoPeriod, steercoSquad, t]
  );

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Spinner />;
  if (tab === "steerco" && steercoTabOn)
    return <SteercoConsolidation period={steercoPeriod} setPeriod={setSteercoPeriod} squadId={steercoSquad} setSquadId={setSteercoSquad} />;

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

      <AbsencesWidget />

      <div className="card" style={{ padding: 14 }}>
        <div className="row" style={{ alignItems: "flex-end", gap: 12 }}>
          <div style={{ width: 200 }}>
            <label htmlFor="dash-search">{t("roadmap.search")}</label>
            <input id="dash-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("roadmap.search")} />
          </div>
          {isAdmin && (
            <div style={{ width: 200 }}>
              <label>{t("admin.tribe")}</label>
              <select value={tribeFilter} onChange={(e) => setTribeFilter(e.target.value)}>
                <option value="">{t("dash.all_tribes")}</option>
                {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
              </select>
            </div>
          )}
          <div style={{ width: 170 }}>
            <label>{t("dash.filter.status")}</label>
            <select value={health} onChange={(e) => setHealth(e.target.value as Health)}>
              <option value="all">{t("dash.filter.all_f")}</option>
              <option value="blocked">{roadmap("blocked")}</option>
              <option value="at_risk">{roadmap("at_risk")}</option>
              <option value="on_track">{roadmap("on_track")}</option>
            </select>
          </div>
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
        <span className="inline"><Dot status="red" decorative /> {roadmap("blocked")}</span>
        <span className="inline"><Dot status="amber" decorative /> {roadmap("at_risk")}</span>
        <span className="inline"><Dot status="green" decorative /> {roadmap("done")}</span>
      </div>

      {cards.length === 0 ? (
        <EmptyState message={t("dash.none")} />
      ) : (
        <div className="squad-grid-2">
          {cards.map((c) => <Card key={c.squad_id} card={c} showTribe={isAdmin} />)}
        </div>
      )}
    </div>
  );
}

/**
 * One squad-health card in the dashboard grid. Shows identity (name, leader,
 * member count), annual progress bar, and a one-line health readout with a
 * freshness badge. Colour/dot reflect health (blocked/at-risk/on-track).
 * Clicking navigates to that squad's detail page. `showTribe` adds the tribe
 * badge (admin cross-tribe view only).
 */
function Card({ card, showTribe }: { card: SquadCard; showTribe?: boolean }) {
  const navigate = useNavigate();
  const { t, roadmap } = useI18n();
  const h = healthOf(card);
  const sClass = h === "blocked" ? "s-red" : h === "at_risk" ? "s-orange" : "s-green";
  const statusDot = h === "blocked" ? "red" : h === "at_risk" ? "amber" : "green";
  // Simplified card: identity + annual progress + a one-line health readout.
  // The full quarter-by-quarter breakdown lives on the squad detail page.
  return (
    <button className={`squad-card ${sClass}`} onClick={() => navigate(`/squads/${card.squad_id}`)}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div className="inline" style={{ gap: 8, alignItems: "flex-start" }}>
          <Dot status={statusDot} />
          <div>
            <div className="strong sc-name" style={{ color: "var(--navy)" }}>{card.name}</div>
            <div className="muted small" style={{ marginTop: 2 }}>
              {card.leader?.display_name || t("card.no_leader")}, {card.members_count} {t("card.members")}
            </div>
          </div>
        </div>
        {showTribe && card.tribe_name && <span className="badge badge-navy">{card.tribe_name}</span>}
      </div>

      {/* Annual progress */}
      <div style={{ marginTop: 12 }}>
        <div className="between" style={{ marginBottom: 4 }}>
          <span className="small strong" style={{ color: "var(--navy)" }}>{t("dash.annual")}</span>
          <span className="small muted">{card.annual_progress}%</span>
        </div>
        <ProgressBar pct={card.annual_progress} />
      </div>

      {/* One-line health readout */}
      <div className="between" style={{ marginTop: 12, gap: 8, flexWrap: "wrap" }}>
        <span className="inline" style={{ gap: 8 }}>
          {card.blocked_count > 0 && <span className="badge badge-red">{card.blocked_count} {t("card.blocked")}</span>}
          {card.at_risk_count > 0 && <span className="badge badge-orange">{card.at_risk_count} {t("card.atrisk")}</span>}
          {card.blocked_count === 0 && card.at_risk_count === 0 && (
            <span className="small muted">{roadmap("on_track")}</span>
          )}
        </span>
        <FreshnessBadge freshness={card.freshness} />
      </div>
    </button>
  );
}
