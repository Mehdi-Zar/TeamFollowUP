/**
 * RoadmapPage - the organisation-wide roadmap matrix (read-only).
 *
 * Renders every squad's milestones (jalons) as a grid: the four quarters of the
 * year in columns, squads grouped by tribe in rows, milestones inside the cells.
 * It is the on-screen twin of the roadmap export (HTML/PPTX). Admins get a tribe
 * filter; all users get a free-text squad search and the roadmap-domain exports.
 */
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { RoadmapCellItem, RoadmapMatrix, Tribe } from "../types";
import { Spinner, ErrorBanner, EmptyState } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";
import { ListControls, ListSearch, SortSpec, applyListView, useListView } from "../components/listView";
import ExportMenu from "../components/ExportMenu";

const QS = [1, 2, 3, 4];

/** Group milestones by theme, preserving first-seen order. A blank theme yields
 *  an empty key (rendered without a header). Mirrors the export grouping. */
function groupByTheme(items: RoadmapCellItem[]): [string, RoadmapCellItem[]][] {
  const order: string[] = [];
  const map = new Map<string, RoadmapCellItem[]>();
  for (const it of items) {
    const key = (it.theme ?? "").trim();
    if (!map.has(key)) { map.set(key, []); order.push(key); }
    map.get(key)!.push(it);
  }
  return order.map((k) => [k, map.get(k)!]);
}

/** Milestone line: title with the EA/GA stage coloured (gold / green), no status dot. */
function JalonLine({ it }: { it: RoadmapCellItem }) {
  return (
    <div className="rmv-j" title={it.dependency ?? undefined}>
      {it.title}
      {it.stage && (
        <> (<span className={it.stage === "EA" ? "rmv-ea" : "rmv-ga"}>{it.stage}</span>)</>
      )}
    </div>
  );
}

/** On-screen global roadmap: quarters in columns, squads (grouped by tribe) in
 *  rows, milestones in the cells - the in-app counterpart of the roadmap export. */
export default function RoadmapPage() {
  const { t } = useI18n();
  const { effectiveRole } = useAuth();
  const isAdmin = effectiveRole === "admin";
  const [data, setData] = useState<RoadmapMatrix | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeId, setTribeId] = useState<string>("");
  const view = useListView("roadmap", "tribe");
  // Les squads retenues. Vide = toutes: c'est l'etat de depart, et l'ecran le dit
  // plutot que de laisser croire qu'aucune n'est choisie.
  const [picked, setPicked] = useState<Set<number>>(new Set());

  // Load (or reload) the matrix; scoped to a tribe when the admin filter is set.
  useEffect(() => {
    setData(null);
    setError(null);
    api.get<RoadmapMatrix>(`/api/roadmap/matrix${tribeId ? `?tribe_id=${tribeId}` : ""}`)
      .then(setData).catch((e) => setError(e.message));
  }, [tribeId]);
  // Tribe list only needed to populate the admin-only tribe filter.
  useEffect(() => {
    if (isAdmin) api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {});
  }, [isAdmin]);

  // Par tribu d'abord, qui est l'ordre de lecture de la matrice; puis par nom, et
  // par avancement quand on cherche qui decroche.
  const sorts: SortSpec<{ squad_id: number; name: string; annual_pct: number }>[] = useMemo(() => {
    const tribeOf = new Map<number, string>();
    for (const tb of data?.tribes ?? []) for (const s of tb.squads) tribeOf.set(s.squad_id, tb.tribe_name);
    return [
      { key: "tribe", label: t("roadmap.sort_tribe"),
        cmp: (a, b) => (tribeOf.get(a.squad_id) ?? "").localeCompare(tribeOf.get(b.squad_id) ?? "")
                       || a.name.localeCompare(b.name) },
      { key: "name", label: t("roadmap.sort_name"), cmp: (a, b) => a.name.localeCompare(b.name) },
      { key: "progress", label: t("roadmap.sort_progress"),
        cmp: (a, b) => a.annual_pct - b.annual_pct || a.name.localeCompare(b.name) },
    ];
  }, [data, t]);

  useSetPageChrome({
    actions: (
      <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
        {isAdmin && (
          <select className="w-auto" value={tribeId} onChange={(e) => setTribeId(e.target.value)} aria-label={t("roadmap.all_tribes")}>
            <option value="">{t("roadmap.all_tribes")}</option>
            {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
          </select>
        )}
        {/* Roadmap tab: only roadmap-domain exports. The weekly report (a dashboard
            artifact) and its subscription belong on the Dashboard, not here. */}
        <ExportMenu docs={["roadmap", "dependencies"]} />
      </div>
    ),
  }, [isAdmin, tribes, tribeId, t]);

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Spinner />;

  const all = data.tribes.flatMap((tb) => tb.squads);
  // Recherche, tri et choix de squads: on garde ce qui passe, puis on laisse
  // tomber les tribus videes, qui n'ont plus rien a montrer.
  const kept = applyListView(
    picked.size ? all.filter((s) => picked.has(s.squad_id)) : all,
    view, sorts, (s, q) => s.name.toLowerCase().includes(q));
  const keptIds = new Set(kept.map((s) => s.squad_id));
  const order = new Map(kept.map((s, i) => [s.squad_id, i]));
  const blocks = data.tribes
    .map((tb) => ({
      ...tb,
      squads: tb.squads.filter((s) => keptIds.has(s.squad_id))
                       .sort((a, b) => order.get(a.squad_id)! - order.get(b.squad_id)!),
    }))
    .filter((tb) => tb.squads.length > 0);
  const total = kept.length;

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="small muted">{t("roadmap.subtitle", { year: data.year })}</div>

      <div className="card" style={{ padding: 14 }}>
        <div className="row" style={{ gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <ListSearch view={view} id="roadmap-search" />
        </div>
      </div>

      <ListControls view={view} sorts={sorts} views={false}
        extraTouched={picked.size > 0} onResetExtra={() => setPicked(new Set())}
        left={
          <div className="inline small muted" style={{ gap: 16, flexWrap: "wrap" }}>
            <span className="strong">{t("dash.legend")} :</span>
            <span className="inline"><b className="rmv-ea">EA</b> {t("jalon.stage_ea")}</span>
            <span className="inline"><b className="rmv-ga">GA</b> {t("jalon.stage_ga")}</span>
          </div>
        }
        right={<SquadPicker all={all} picked={picked} onChange={setPicked} t={t} />} />

      {total === 0 ? (
        <EmptyState message={t("roadmap.empty")} />
      ) : (
        <div className="card" style={{ padding: 8, overflowX: "auto" }}>
          <table className="rmv">
            <thead>
              <tr>
                <th className="rmv-corner" />
                {QS.map((qn) => <th key={qn} className="rmv-q">Q{qn} {data.year}</th>)}
              </tr>
            </thead>
            <tbody>
              {blocks.map((tb) => (
                <Fragment key={tb.tribe_id ?? tb.tribe_name}>
                  <tr><td className="rmv-tribe" colSpan={5}>{tb.tribe_name}</td></tr>
                  {tb.squads.map((s) => (
                    <tr key={s.squad_id}>
                      <th className="rmv-row">
                        <Link to={`/squads/${s.squad_id}`}>{s.name}</Link>
                        <div className="rmv-pct">{s.annual_pct}%</div>
                      </th>
                      {QS.map((qn) => {
                        const items = s.quarters.find((qd) => qd.q === qn)?.items ?? [];
                        return (
                          <td key={qn} className="rmv-cell">
                            {items.length === 0 ? <span className="muted small">-</span> : groupByTheme(items).map(([theme, group], gi) => (
                              <div key={gi} className="rmv-group">
                                {theme && <div className="rmv-theme">{theme}</div>}
                                {group.map((it, i) => <JalonLine key={i} it={it} />)}
                              </div>
                            ))}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


/**
 * Choisir les squads affichees dans la matrice.
 *
 * Rien de coche veut dire « toutes », et le bouton le dit: laisser croire qu'aucune
 * n'est choisie alors que la matrice est pleine serait faux. Le panneau se ferme
 * en cliquant a cote, comme les autres menus de l'application.
 */
function SquadPicker({ all, picked, onChange, t }: {
  all: { squad_id: number; name: string }[];
  picked: Set<number>;
  onChange: (s: Set<number>) => void;
  t: (k: string, v?: any) => string;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const toggle = (id: number) => {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id); else next.add(id);
    onChange(next);
  };

  return (
    <div ref={box} style={{ position: "relative", display: "inline-block" }}>
      <button className="btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}>
        {picked.size ? t("roadmap.squads_n", { n: picked.size }) : t("roadmap.squads_all")} ▾
      </button>
      {open && (
        <div className="card menu-pop" style={{ position: "absolute", right: 0, top: 38, zIndex: 60, minWidth: 240 }}>
          <div className="between" style={{ marginBottom: 8 }}>
            <span className="small muted">{t("roadmap.squads_pick")}</span>
            {picked.size > 0 && (
              <button className="btn-ghost btn-sm" onClick={() => onChange(new Set())}>
                {t("roadmap.squads_all")}
              </button>
            )}
          </div>
          <div className="stack" style={{ gap: 2, maxHeight: 320, overflowY: "auto" }}>
            {all.map((s) => (
              <label key={s.squad_id} className="inline small" style={{ gap: 6, cursor: "pointer" }}>
                <input type="checkbox" checked={picked.has(s.squad_id)} onChange={() => toggle(s.squad_id)} />
                {s.name}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
