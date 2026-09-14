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
import { MoodBadge } from "../components/TeamMood";
import SteercoConsolidation from "../components/SteercoConsolidation";
import { useSetPageChrome } from "../components/pageChrome";
import { ListControls, ListSearch, SortSpec, applyListView, useListView } from "../components/listView";
import { currentSteercoPeriod } from "../steerco";

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
  const [steercoPlatform, setSteercoPlatform] = useState<string>("");   // "" = all platforms
  const [data, setData] = useState<DashboardOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const view = useListView("dash", "risk");
  const [health, setHealth] = useState<Health>("all");
  const [freshFilter, setFreshFilter] = useState<"all" | "stale" | "fresh">("all");
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeFilter, setTribeFilter] = useState<string>("");

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
  const resetExtra = () => { setHealth("all"); setFreshFilter("all"); setTribeFilter(""); };

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
              <ExportMenu docs={["steerco", "report"]} steerco={{ period: steercoPeriod, platformId: steercoPlatform }} />
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
    [data?.year, showInitiatives, steercoTabOn, tab, steercoPeriod, steercoPlatform, t]
  );

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Spinner />;
  if (tab === "steerco" && steercoTabOn)
    return <SteercoConsolidation period={steercoPeriod} setPeriod={setSteercoPeriod} platformId={steercoPlatform} setPlatformId={setSteercoPlatform} />;

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
          <ListSearch view={view} id="dash-search" />
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
            <label>{t("dash.filter.fresh")}</label>
            <select value={freshFilter} onChange={(e) => setFreshFilter(e.target.value as any)}>
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
            <span className="strong">{t("dash.legend")} :</span>
            <span className="inline"><Dot status="red" decorative /> {roadmap("blocked")}</span>
            <span className="inline"><Dot status="amber" decorative /> {roadmap("at_risk")}</span>
            <span className="inline"><Dot status="green" decorative /> {roadmap("done")}</span>
          </div>
        } />

      {cards.length === 0 ? (
        <EmptyState message={t("dash.none")} />
      ) : view.dense ? (
        <CompactList cards={cards} showTribe={isAdmin} tribes={tribes} />
      ) : (
        <div className="squad-grid-2">
          {cards.map((c) => <Card key={c.squad_id} card={c} showTribe={isAdmin} />)}
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
function CompactList({ cards, showTribe, tribes }: {
  cards: SquadCard[]; showTribe: boolean; tribes: Tribe[];
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
                <Link className="strong" to={`/squads/${c.squad_id}`}>{c.name}</Link>
                <MoodBadge mood={c.mood as any} />
              </td>
              {showTribe && <td className="small muted">{c.tribe_name || tribeName(c.tribe_id)}</td>}
              <td className="small muted">{c.leader?.display_name || "-"}</td>
              <td><ProgressBar pct={c.annual_progress} /></td>
              <td className="small">
                <span className="inline" style={{ gap: 6 }}>
                  <Dot status={healthOf(c) === "blocked" ? "red" : healthOf(c) === "at_risk" ? "amber" : "green"} decorative />
                  {roadmap(healthOf(c))}
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
function Card({ card, showTribe }: { card: SquadCard; showTribe?: boolean }) {
  const navigate = useNavigate();
  const { t, roadmap } = useI18n();
  const h = healthOf(card);
  const sClass = h === "blocked" ? "s-red" : h === "at_risk" ? "s-orange" : "s-green";
  const statusDot = h === "blocked" ? "red" : h === "at_risk" ? "amber" : "green";
  // La carte se plie, comme l'equipe et l'historique sur la page d'une squad, et
  // par le meme geste: on clique l'en-tete, le chevron tourne. Elle s'ouvre par
  // defaut, a la difference de celles-la: un tableau de bord dont toutes les
  // cartes seraient fermees ne montrerait plus rien de ce qu'on vient y voir.
  //
  // Ce qui reste visible plie est ce qui se lit de loin: le point de statut, le
  // nom, le moral. Ce qui se plie est le detail, avancement et compte de jalons.
  const [open, setOpen] = useState(true);
  const toggle = () => setOpen((o) => !o);
  return (
    <div className={`squad-card ${sClass}`}>
      <div className="between collapsible-head" role="button" tabIndex={0} aria-expanded={open}
           style={{ alignItems: "flex-start", cursor: "pointer", gap: 10 }}
           onClick={toggle}
           onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } }}>
        <div className="inline" style={{ gap: 8, alignItems: "flex-start" }}>
          <span className="collapsible-caret"
                style={{ transition: "transform .15s", transform: open ? "rotate(90deg)" : "none",
                         color: "var(--accent)", lineHeight: 1.4 }}>▸</span>
          <Dot status={statusDot} />
          <div>
            {/* Le nom ouvre la squad. C'etait toute la carte auparavant, mais une
                carte qui se plie ne peut pas aussi naviguer d'un seul clic: il
                fallait choisir ou porter chacun des deux gestes. */}
            <button className="sc-open strong sc-name" style={{ color: "var(--navy)" }}
                    onClick={(e) => { e.stopPropagation(); navigate(`/squads/${card.squad_id}`); }}>
              {card.name}
            </button>
            <div className="muted small" style={{ marginTop: 2 }}>
              {card.leader?.display_name || t("card.no_leader")}, {card.members_count} {t("card.members")}
            </div>
          </div>
        </div>
        <span className="inline" style={{ gap: 6, alignItems: "center" }}>
          {/* Le moral, en tete de carte: c'est la seule donnee de cette grille
              qu'aucun calcul ne produit, et celle qui explique souvent les autres.
              Il reste visible carte pliee, pour la meme raison. */}
          <MoodBadge mood={card.mood} moodAt={card.mood_at} />
          {showTribe && card.tribe_name && <span className="badge badge-navy">{card.tribe_name}</span>}
        </span>
      </div>

      {open && (
        <>
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
        </>
      )}
    </div>
  );
}
