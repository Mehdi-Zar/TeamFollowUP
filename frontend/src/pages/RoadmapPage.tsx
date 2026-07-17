import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { RoadmapCellItem, RoadmapMatrix, Tribe } from "../types";
import { Spinner, ErrorBanner, EmptyState } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";
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
  const [q, setQ] = useState("");

  useEffect(() => {
    setData(null);
    setError(null);
    api.get<RoadmapMatrix>(`/api/roadmap/matrix${tribeId ? `?tribe_id=${tribeId}` : ""}`)
      .then(setData).catch((e) => setError(e.message));
  }, [tribeId]);
  useEffect(() => {
    if (isAdmin) api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {});
  }, [isAdmin]);

  useSetPageChrome({
    actions: (
      <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
        {isAdmin && (
          <select className="w-auto" value={tribeId} onChange={(e) => setTribeId(e.target.value)} aria-label={t("roadmap.all_tribes")}>
            <option value="">{t("roadmap.all_tribes")}</option>
            {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
          </select>
        )}
        <input className="w-auto" style={{ width: 190 }} placeholder={t("roadmap.search")}
               aria-label={t("roadmap.search")} value={q} onChange={(e) => setQ(e.target.value)} />
        {/* Roadmap tab: only roadmap-domain exports. The weekly report (a dashboard
            artifact) and its subscription belong on the Dashboard, not here. */}
        <ExportMenu docs={["roadmap", "dependencies"]} />
      </div>
    ),
  }, [isAdmin, tribes, tribeId, q, t]);

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Spinner />;

  const needle = q.trim().toLowerCase();
  const blocks = data.tribes
    .map((tb) => ({ ...tb, squads: tb.squads.filter((s) => !needle || s.name.toLowerCase().includes(needle)) }))
    .filter((tb) => tb.squads.length > 0);
  const total = blocks.reduce((n, tb) => n + tb.squads.length, 0);

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="small muted">{t("roadmap.subtitle", { year: data.year })}</div>
      <div className="inline small muted" style={{ gap: 16, flexWrap: "wrap" }}>
        <span className="strong">{t("dash.legend")} :</span>
        <span className="inline"><b className="rmv-ea">EA</b> {t("jalon.stage_ea")}</span>
        <span className="inline"><b className="rmv-ga">GA</b> {t("jalon.stage_ga")}</span>
      </div>

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
