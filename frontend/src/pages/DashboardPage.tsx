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
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { useAuth } from "../auth";
import { DashboardOut, SquadCard, Tribe } from "../types";
import { Dot, FreshnessBadge, ProgressBar, Spinner, ErrorBanner, EmptyState } from "../components/ui";
import ExportMenu from "../components/ExportMenu";
import { ReportingButton } from "../components/ReportingModal";
import AbsencesWidget from "../components/AbsencesWidget";
import { MoodBadge } from "../components/TeamMood";
import SteercoConsolidation from "../components/SteercoConsolidation";
import { useSetPageChrome } from "../components/pageChrome";
import { ListControls, ListSearch, SortSpec, applyListView, useListView } from "../components/listView";
import { currentSteercoPeriod } from "../steerco";

type Health = "all" | "blocked" | "at_risk" | "on_track" | "empty";

/** Derive a squad's overall health from its milestone counts: any blocked
 *  milestone -> "blocked", else any at-risk -> "at_risk", else "on_track".
 *  Drives both the status dot/colour and the health filter. */
function healthOf(c: SquadCard): "blocked" | "at_risk" | "on_track" | "empty" {
  if (c.blocked_count > 0) return "blocked";
  if (c.at_risk_count > 0) return "at_risk";
  // Nothing planned this year is not "on track": it is said as such.
  if ((c.counts?.roadmap_total ?? 0) === 0) return "empty";
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
  const { effectiveRole, adminTabs, can, user } = useAuth();
  const isAdmin = effectiveRole === "admin";
  const navigate = useNavigate();
  // Dashboard + Initiatives are merged under one menu: everyone gets the Initiatives
  // tab (read-only list, editable by the tribe leader); the overview stays as-is.
  const showInitiatives = true;
  // The platforms' Steerco dashboards are the tribe's: the whole tribe reads them
  // when the module is on (the squads fill the data from Reporting). Whoever manages
  // the platforms gets a way to the one place where that is done.
  const steercoTabOn = moduleOn("steerco");
  const canManagePlatforms = adminTabs.includes("platforms");
  // The active sub-view is driven by ?tab= so the tab survives navigating to the
  // Initiatives page and back (the Initiatives tab bar links back to /?tab=steerco).
  const [params, setParams] = useSearchParams();
  // The Steerco tab only when its module is on: otherwise the overview (it used to
  // wait forever, loading neither).
  const tab: "overview" | "steerco" = params.get("tab") === "steerco" && steercoTabOn ? "steerco" : "overview";
  // Steerco view filters, lifted here so the chrome ExportMenu can target them.
  const [steercoPeriod, setSteercoPeriod] = useState<string>(currentSteercoPeriod());
  const [steercoPlatform, setSteercoPlatform] = useState<string>("");   // "" = all platforms
  const [data, setData] = useState<DashboardOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A link may name the year (?year=, from the initiatives tab): it wins.
  // Year and filters live in the address: back from a squad page, or a link sent
  // to someone, shows the same view.
  const year = Number(params.get("year")) || null;
  const health = (params.get("health") as Health) || "all";
  const freshFilter = (params.get("fresh") as "all" | "stale" | "fresh") || "all";
  const tribeFilter = params.get("tribe") || "";
  const setParam = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v === null || v === "" || v === "all") next.delete(k); else next.set(k, v);
    setParams(next, { replace: true });
  };
  const setYear = (y: number) => setParam("year", String(y));
  const setHealth = (h: Health) => setParam("health", h);
  const setFreshFilter = (f: string) => setParam("fresh", f);
  const setTribeFilter = (v: string) => setParam("tribe", v);
  const view = useListView("dash", "risk");
  const [tribes, setTribes] = useState<Tribe[]>([]);

  // No year in the address: the instance's default year (not written, the address stays clean).
  const shownYear = year ?? default_year;
  // Tribe list only needed to populate the admin-only tribe filter.
  useEffect(() => {
    if (isAdmin) api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {});
  }, [isAdmin]);

  // (Re)load the dashboard whenever the year or (admin) tribe filter changes.
  useEffect(() => {
    if (tab !== "overview" || !shownYear) return;  // the Steerco tab does not use it
    const p = new URLSearchParams();
    p.set("year", String(shownYear));
    if (isAdmin && tribeFilter) p.set("tribe_id", tribeFilter);
    // The latest request wins, and a new one clears the previous error.
    let alive = true;
    setError(null);
    api.get<DashboardOut>(`/api/dashboard?${p.toString()}`)
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setError(errorText(e)); });
    return () => { alive = false; };
  }, [shownYear, tribeFilter, isAdmin, tab]);

  // Le sens naturel de chaque critere: le risque et l'anciennete du pire au
  // meilleur, le nom et l'avancement du premier au dernier.
  const sorts: SortSpec<SquadCard>[] = useMemo(() => [
    { key: "risk", label: t("dash.sort.risk"),
      cmp: (a, b) => b.risk_rank - a.risk_rank || b.blocked_count - a.blocked_count || a.name.localeCompare(b.name) },
    { key: "progress", label: t("dash.sort.progress"),
      cmp: (a, b) => a.annual_progress - b.annual_progress || a.name.localeCompare(b.name) },
    { key: "name", label: t("dash.sort.name"), cmp: (a, b) => a.name.localeCompare(b.name) },
    { key: "fresh", label: t("dash.sort.fresh"),
      cmp: (a, b) => (b.freshness.age_days ?? 1e9) - (a.freshness.age_days ?? 1e9) || a.name.localeCompare(b.name) },
  ], [t]);

  // Vue cote navigateur: la recherche et le tri sont communs a tous les ecrans de
  // liste, les deux filtres de sante et de fraicheur sont propres a celui-ci.
  const cards = useMemo(() => {
    if (!data) return [];
    const kept = data.cards.filter((c) => {
      if (health !== "all" && healthOf(c) !== health) return false;
      if (freshFilter === "stale" && !c.freshness.is_stale) return false;
      if (freshFilter === "fresh" && c.freshness.is_stale) return false;
      return true;
    });
    return applyListView(kept, view, sorts, (c, q) => c.name.toLowerCase().includes(q));
  }, [data, health, freshFilter, view.sort, view.desc, view.query, sorts]);

  // Revenir a la vue par defaut d'un geste: quand on a empile quatre filtres, les
  // defaire un par un pour comprendre ce qu'on voit est une corvee.
  const extraTouched = health !== "all" || freshFilter !== "all" || tribeFilter !== "";
  const resetExtra = () => {
    const next = new URLSearchParams(params);
    ["health", "fresh", "tribe"].forEach((k) => next.delete(k));
    setParams(next, { replace: true });
  };

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
            // The year travels from tab to tab.
            const y = data?.year ?? shownYear;
            if (k === "initiatives") navigate(`/initiatives${y ? `?year=${y}` : ""}`);
            else if (k === "steerco") setParams({ tab: "steerco", ...(y ? { year: String(y) } : {}) });
            else setParams(y ? { year: String(y) } : {});
          },
          // Same toolbar model on every tab: subscribe button + export dropdown. On
          // Steerco the export dropdown carries the one-pager document instead.
          actions: tab === "steerco" ? (
            <>
              {canManagePlatforms && (
                <button className="btn-secondary btn-sm" onClick={() => navigate("/admin?section=platforms")}>
                  {t("steerco.manage_platforms")}
                </button>
              )}
              <ExportMenu docs={["steerco", "report"]} steerco={{ period: steercoPeriod, platformId: steercoPlatform }} />
            </>
          ) : (
            <>
              <div className="seg">
                {/* The chosen year and its two neighbours, as on every other screen. */}
                {[data.year - 1, data.year, data.year + 1].map((y) => (
                  <button key={y} className={y === data.year ? "active" : ""} aria-pressed={y === data.year} onClick={() => setYear(y)}>{y}</button>
                ))}
              </div>
              <ReportingButton />
              <ExportMenu year={data.year} docs={["dashboard", "report"]} />
            </>
          ),
        }
      : {},
    [data?.year, showInitiatives, steercoTabOn, tab, steercoPeriod, steercoPlatform, t]
  );

  if (tab === "steerco" && steercoTabOn)
    return <SteercoConsolidation period={steercoPeriod} setPeriod={setSteercoPeriod} platformId={steercoPlatform} setPlatformId={setSteercoPlatform} />;
  if (error && !data) return <ErrorBanner message={error} />;
  if (!data) return <Spinner />;

  const s = data.summary;
  // The band follows the filters: with a filter on, it counts what the list shows.
  const filtered = cards.length !== data.cards.length;
  const planned = cards.filter((c) => (c.counts?.roadmap_total ?? 0) > 0);
  const band = filtered ? {
    avg_progress: planned.length ? Math.round(planned.reduce((n, c) => n + c.annual_progress, 0) / planned.length) : 0,
    blocked_jalons: cards.reduce((n, c) => n + c.blocked_count, 0),
    at_risk_jalons: cards.reduce((n, c) => n + c.at_risk_count, 0),
    squads_stale: cards.filter((c) => c.freshness.is_stale).length,
    squads_total: cards.length,
  } : s;

  // Whoever reports for a squad (leader, co-leader, contributor) and is not
  // the tribe's manager: the way to their reporting, and whether it waits.
  const reporter = can("reporting") && !["admin", "tribe_leader"].includes(effectiveRole ?? "");
  const mineStale = cards.filter((c) => c.leader?.id === user?.id && c.freshness.is_stale).length;

  return (
    <div className="stack" style={{ gap: 20 }}>
      {reporter && (
        <div className="banner between" style={{ alignItems: "center", gap: 10 }}>
          <span className="small">{mineStale ? t("dash.my_reporting_stale", { n: mineStale }) : t("dash.my_reporting")}</span>
          <Link className="btn btn-sm" to="/saisie">{t("dash.open_reporting")}</Link>
        </div>
      )}
      {/* Concrete health band */}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
        <div className="kpi"><div className="v">{band.avg_progress}%</div><div className="l">{t("dash.avg")}</div></div>
        <div className="kpi"><div className={`v ${band.blocked_jalons ? "red" : ""}`}>{band.blocked_jalons}</div><div className="l">{t("dash.blocked")}</div></div>
        <div className="kpi"><div className={`v ${band.at_risk_jalons ? "orange" : ""}`}>{band.at_risk_jalons}</div><div className="l">{t("dash.atrisk")}</div></div>
        <div className="kpi"><div className={`v ${band.squads_stale ? "orange" : ""}`}>{band.squads_stale}</div><div className="l">{t("dash.kpi.stale")}</div></div>
        <div className="kpi"><div className="v">{band.squads_total}</div><div className="l">{t("dash.kpi.squads")}</div></div>
      </div>
      {error && <ErrorBanner message={error} />}
      {filtered && <div className="small muted" style={{ marginTop: -12 }}>{t("dash.band_filtered", { n: cards.length, total: data.cards.length })}</div>}

      <AbsencesWidget />

      <div className="card" style={{ padding: 14 }}>
        <div className="row" style={{ alignItems: "flex-end", gap: 12 }}>
          <ListSearch view={view} id="dash-search" />
          {isAdmin && (
            <div style={{ width: 200 }}>
              <label htmlFor="dash-tribe">{t("admin.tribe")}</label>
              <select id="dash-tribe" value={tribeFilter} onChange={(e) => setTribeFilter(e.target.value)}>
                <option value="">{t("dash.all_tribes")}</option>
                {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
              </select>
            </div>
          )}
          <div style={{ width: 170 }}>
            <label htmlFor="dash-health">{t("dash.filter.status")}</label>
            <select id="dash-health" value={health} onChange={(e) => setHealth(e.target.value as Health)}>
              <option value="all">{t("dash.filter.all_f")}</option>
              <option value="blocked">{roadmap("blocked")}</option>
              <option value="at_risk">{roadmap("at_risk")}</option>
              <option value="on_track">{roadmap("on_track")}</option>
              <option value="empty">{t("dash.no_milestone")}</option>
            </select>
          </div>
          <div style={{ width: 190 }}>
            <label htmlFor="dash-fresh">{t("dash.filter.fresh")}</label>
            <select id="dash-fresh" value={freshFilter} onChange={(e) => setFreshFilter(e.target.value)}>
              <option value="all">{t("dash.filter.all_f")}</option>
              <option value="stale">{t("dash.fresh.stale")}</option>
              <option value="fresh">{t("dash.fresh.fresh")}</option>
            </select>
          </div>
        </div>
      </div>

      {/* Legende a gauche, commandes d'affichage a droite: chercher et filtrer
          reduit ce qu'on voit, trier et changer de vue ne fait que le reordonner. */}
      <ListControls view={view} sorts={sorts} extraTouched={extraTouched} onResetExtra={resetExtra}
        left={
          <div className="inline small muted" style={{ gap: 16, flexWrap: "wrap" }}>
            <span className="strong">{t("dash.legend")}</span>
            <span className="inline"><Dot status="red" decorative /> {roadmap("blocked")}</span>
            <span className="inline"><Dot status="amber" decorative /> {roadmap("at_risk")}</span>
            <span className="inline"><Dot status="green" decorative /> {roadmap("on_track")}</span>
          </div>
        } />

      {cards.length === 0 ? (
        // Nothing at all, or everything filtered out: two different messages.
        data.cards.length === 0 ? <EmptyState message={t("dash.no_squad")} /> : (
          <div className="card stack" style={{ gap: 8, alignItems: "flex-start" }}>
            <div className="small muted">{t("dash.none")}</div>
            <button className="btn-secondary btn-sm" onClick={() => { resetExtra(); view.setQuery?.(""); }}>{t("common.reset_filters")}</button>
          </div>
        )
      ) : view.dense ? (
        <CompactList cards={cards} showTribe={isAdmin} tribes={tribes} year={data.year} />
      ) : (
        <div className="squad-grid-2">
          {cards.map((c) => <Card key={c.squad_id} card={c} showTribe={isAdmin} year={data.year} />)}
        </div>
      )}
    </div>
  );
}

/**
 * La vue compacte: une ligne par squad, les memes informations que la carte.
 *
 * Une grille de cartes se lit bien a dix squads et se parcourt mal a quarante,
 * ou la question devient « ou est la mienne » plutot que « comment vont-elles ».
 * Les colonnes sont celles sur lesquelles on trie, pour qu'un tri se voie.
 */
function CompactList({ cards, showTribe, tribes, year }: {
  cards: SquadCard[]; showTribe: boolean; tribes: Tribe[]; year: number;
}) {
  const { t, roadmap } = useI18n();
  const tribeName = (id: number | null | undefined) =>
    tribes.find((x) => x.id === id)?.name ?? "-";
  return (
    <div className="card" style={{ padding: 0, overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>{t("admin.squad")}</th>
            {showTribe && <th>{t("admin.tribe")}</th>}
            <th>{t("squad.responsible")}</th>
            <th style={{ width: 160 }}>{t("dash.annual")}</th>
            <th>{t("dash.filter.status")}</th>
            <th>{t("dash.filter.fresh")}</th>
          </tr>
        </thead>
        <tbody>
          {cards.map((c) => (
            <tr key={c.squad_id}>
              <td>
                <Link className="strong" to={`/squads/${c.squad_id}?year=${year}`}>{c.name}</Link>
                <MoodBadge mood={c.mood as any} />
              </td>
              {showTribe && <td className="small muted">{c.tribe_name || tribeName(c.tribe_id)}</td>}
              <td className="small muted">{c.leader?.display_name || "-"}</td>
              <td><ProgressBar pct={c.annual_progress} /></td>
              <td className="small">
                <span className="inline" style={{ gap: 6 }}>
                  {healthOf(c) === "empty" ? <span className="dot dot-grey" aria-hidden /> : <Dot status={healthOf(c) === "blocked" ? "red" : healthOf(c) === "at_risk" ? "amber" : "green"} decorative />}
                  {healthOf(c) === "empty" ? t("dash.no_milestone") : roadmap(healthOf(c) as any)}
                </span>
              </td>
              <td><FreshnessBadge freshness={c.freshness} /></td>
            </tr>
          ))}
        </tbody>
      </table>
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
function Card({ card, showTribe, year }: { card: SquadCard; showTribe?: boolean; year: number }) {
  const navigate = useNavigate();
  const { t, roadmap } = useI18n();
  const h = healthOf(card);
  // Nothing planned: a neutral card, not a green one.
  const sClass = h === "blocked" ? "s-red" : h === "at_risk" ? "s-orange" : h === "empty" ? "s-grey" : "s-green";
  const statusDot = h === "blocked" ? "red" : h === "at_risk" ? "amber" : "green";
  // Simplified card: identity + annual progress + a one-line health readout.
  // The full quarter-by-quarter breakdown lives on the squad detail page.
  return (
    <button className={`squad-card ${sClass}`} onClick={() => navigate(`/squads/${card.squad_id}?year=${year}`)}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div className="inline" style={{ gap: 8, alignItems: "flex-start" }}>
          {h === "empty" ? <span className="dot dot-grey" aria-hidden /> : <Dot status={statusDot} />}
          <div>
            <div className="strong sc-name" style={{ color: "var(--navy)" }}>{card.name}</div>
            <div className="muted small" style={{ marginTop: 2 }}>
              {card.leader?.display_name || t("card.no_leader")}, {t("card.members_n", { n: card.members_count })}
            </div>
          </div>
        </div>
        <span className="inline" style={{ gap: 6, alignItems: "center" }}>
          {/* Le moral, en tete de carte: c'est la seule donnee de cette grille
              qu'aucun calcul ne produit, et celle qui explique souvent les autres. */}
          <MoodBadge mood={card.mood} moodAt={card.mood_at} />
          {showTribe && card.tribe_name && <span className="badge badge-navy">{card.tribe_name}</span>}
        </span>
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
          {card.blocked_count > 0 && <span className="badge badge-red">{t("card.blocked_n", { n: card.blocked_count })}</span>}
          {card.at_risk_count > 0 && <span className="badge badge-orange">{t("card.atrisk_n", { n: card.at_risk_count })}</span>}
          {card.blocked_count === 0 && card.at_risk_count === 0 && (
            <span className="small muted">{roadmap("on_track")}</span>
          )}
        </span>
        <FreshnessBadge freshness={card.freshness} />
      </div>
    </button>
  );
}
