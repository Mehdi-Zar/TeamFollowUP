// Le bloc unique de la page d'une squad: la frise de l'annee, les engagements OTD
// poses dessus, puis les initiatives avec les jalons qui les servent.
//
// Avant, ces trois choses etaient trois cartes empilees: les initiatives, les OTD,
// puis une roadmap decoupee en quatre colonnes. Trois lectures pour une seule
// question, "ou en est l'annee", et aucune des trois ne disait a quoi servait un
// jalon ni quand tombait un engagement. Les rassembler sur un axe commun repond a
// la question d'un seul regard: le temps est le meme pour tout le monde.
//
// La donnee ne change pas, seul son agencement change. Le chainage existait deja:
// une initiative porte des objectifs, un objectif porte des jalons.
import { useMemo, useState } from "react";
import { useI18n } from "../i18n";
import { Initiative, OtdReport, RoadmapItem, SquadDetail } from "../types";
import { Dot } from "./ui";

const MONTHS = 12;
const QUARTERS = [1, 2, 3, 4] as const;

/** Rang du mois (0..11) d'une date ISO, ou null si elle manque ou sort de l'annee. */
function monthIndex(iso: string | null | undefined, year: number): number | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime()) || d.getFullYear() !== year) return null;
  return d.getMonth();
}

/** Le statut d'un jalon, ramene aux trois couleurs de l'application. */
function ragOf(status: string): "green" | "amber" | "red" {
  if (status === "blocked") return "red";
  if (status === "at_risk") return "amber";
  return "green";
}

type Props = {
  squad: SquadDetail;
  initiatives: Initiative[];
  otds: OtdReport[];
  onOpenJalon: (item: RoadmapItem) => void;
};

export default function RoadmapTimeline({ squad, initiatives, otds, onOpenJalon }: Props) {
  const { t, roadmap, formatDate } = useI18n();
  const year = squad.year;
  const [openInit, setOpenInit] = useState<number | "none" | null>(null);

  const monthLabels = useMemo(() => Array.from({ length: MONTHS }, (_, i) =>
    new Date(year, i, 1).toLocaleDateString(undefined, { month: "short" }).replace(".", "")), [year]);

  // Les jalons, regroupes par initiative. Le chemin passe par l'objectif: un
  // jalon repond a un objectif de squad, qui sert une initiative de tribu. Ceux
  // qui ne repondent a rien ont leur propre ligne, plutot que d'etre caches.
  const byInitiative = useMemo(() => {
    const objToInit = new Map<number, number>();
    for (const o of squad.objectives ?? []) {
      if (o.initiative_id) objToInit.set(o.id, o.initiative_id);
    }
    const groups = new Map<number | "none", RoadmapItem[]>();
    for (const item of squad.roadmap_items ?? []) {
      const key = (item.objective_id && objToInit.get(item.objective_id)) || "none";
      const list = groups.get(key) ?? [];
      list.push(item);
      groups.set(key, list);
    }
    return groups;
  }, [squad.objectives, squad.roadmap_items]);

  // Une initiative n'est montree que si elle concerne cette squad ou porte des
  // jalons: la frise d'une squad n'a pas a lister le portefeuille de la tribu.
  const rows = useMemo(() => {
    const out: { key: number | "none"; title: string; deadline?: string | null; items: RoadmapItem[] }[] = [];
    for (const init of initiatives) {
      const items = byInitiative.get(init.id) ?? [];
      if (!items.length && init.squad_id !== squad.id) continue;
      out.push({ key: init.id, title: init.title, deadline: init.deadline, items });
    }
    const orphans = byInitiative.get("none") ?? [];
    if (orphans.length) out.push({ key: "none", title: t("timeline.no_initiative"), items: orphans });
    return out;
  }, [initiatives, byInitiative, squad.id, t]);

  const quarterCell = (q: number) => squad.quarter_progress?.[String(q)];

  return (
    <div className="card tl">
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div>
          <h2 style={{ margin: 0 }}>{t("timeline.title", { year })}</h2>
          <div className="small muted">{t("timeline.hint")}</div>
        </div>
        <div className="inline small muted" style={{ gap: 10 }}>
          <span className="inline" style={{ gap: 4 }}><Dot status="green" decorative /> {roadmap("on_track")}</span>
          <span className="inline" style={{ gap: 4 }}><Dot status="amber" decorative /> {roadmap("at_risk")}</span>
          <span className="inline" style={{ gap: 4 }}><Dot status="red" decorative /> {roadmap("blocked")}</span>
        </div>
      </div>

      <div className="tl-scroll">
        <div className="tl-grid">
          {/* ---- Trimestres, avec l'avancement calcule de chacun ---- */}
          <div className="tl-row tl-quarters">
            <div className="tl-label" />
            {QUARTERS.map((q) => {
              const cell = quarterCell(q);
              const focus = squad.freshness && q === (squad as any).focus_quarter;
              return (
                <div key={q} className={`tl-q${focus ? " focus" : ""}`} style={{ gridColumn: `span 3` }}>
                  <div className="between">
                    <span className="strong">Q{q}</span>
                    <span className="small muted">{cell?.progress_pct ?? 0} %</span>
                  </div>
                  <div className="tl-bar"><span style={{ width: `${cell?.progress_pct ?? 0}%` }} /></div>
                  {cell?.comment && <div className="tl-qc small muted" title={cell.comment}>{cell.comment}</div>}
                </div>
              );
            })}
          </div>

          {/* ---- Mois ---- */}
          <div className="tl-row tl-months">
            <div className="tl-label" />
            {monthLabels.map((m, i) => <div key={i} className="tl-m small muted">{m}</div>)}
          </div>

          {/* ---- Les engagements OTD, poses sur l'axe a leur date ---- */}
          <div className="tl-row tl-otds">
            <div className="tl-label small strong">{t("timeline.otd")}</div>
            {Array.from({ length: MONTHS }, (_, i) => {
              const here = otds.filter((o) => monthIndex(o.committed_date, year) === i);
              return (
                <div key={i} className="tl-cell">
                  {here.map((o) => (
                    <div key={o.id} className={`tl-otd st-${o.status}`} title={`${o.title} : ${formatDate(o.committed_date ?? "")}`}>
                      <span className="tl-otd-dot" />
                      <span className="tl-otd-text">{o.title}</span>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
          {otds.length === 0 && (
            <div className="tl-row"><div className="tl-label" />
              <div className="small muted" style={{ gridColumn: "span 12", padding: "2px 0 8px" }}>
                {t("timeline.no_otd")}
              </div>
            </div>
          )}

          {/* ---- Une ligne par initiative, avec ses jalons au trimestre ---- */}
          {rows.map((row) => (
            <div key={row.key} className="tl-row tl-init">
              <div className="tl-label">
                <button className="tl-init-name" onClick={() => setOpenInit(openInit === row.key ? null : row.key)}
                        title={t("timeline.toggle")}>
                  {row.title}
                </button>
                <div className="small muted">
                  {t("timeline.jalon_count", { n: String(row.items.length) })}
                  {row.deadline ? `, ${formatDate(row.deadline)}` : ""}
                </div>
              </div>
              {QUARTERS.map((q) => {
                const items = row.items.filter((r) => r.quarter === q);
                return (
                  <div key={q} className="tl-cell" style={{ gridColumn: "span 3" }}>
                    {items.map((r) => (
                      <button key={r.id} className={`tl-jalon rag-${ragOf(r.status)}`}
                              onClick={() => onOpenJalon(r)}
                              title={`${r.title} - ${roadmap(r.status)}`}>
                        <Dot status={ragOf(r.status)} decorative />
                        <span className="tl-jalon-text">{r.title}</span>
                        <span className="tl-stage">{r.release_stage}</span>
                      </button>
                    ))}
                  </div>
                );
              })}
            </div>
          ))}

          {rows.length === 0 && (
            <div className="tl-row"><div className="tl-label" />
              <div className="small muted" style={{ gridColumn: "span 12", padding: "6px 0" }}>
                {t("timeline.empty")}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
