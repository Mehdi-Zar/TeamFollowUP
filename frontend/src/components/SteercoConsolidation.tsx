// SteercoConsolidation - the leadership Steerco view, shown as a tab inside the
// Dashboard. It previews the KPI one-pager (rendered server-side to look like
// kpi-onepager.html) for a chosen platform or for all platforms at once. Period +
// platform selection are lifted to DashboardPage so the standard chrome ExportMenu
// (top right, same model as every other page) targets the current selection.
//
// One platform is one slide, whatever the number of squads feeding it. The row also
// says who is still owing a figure, because chasing a late contributor is most of the
// work of running a monthly committee.
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Spinner, EmptyState } from "./ui";
import { ListControls, ListSearch, SortSpec, applyListView, useListView } from "./listView";
import { currentSteercoPeriod } from "../steerco";

type Entry = {
  platform_id: number; platform_name: string; filled: boolean; updated_at: string | null;
  contributors: { id: number; name: string }[]; missing: string[]; unassigned: number;
};

type Props = {
  period: string;
  setPeriod: (p: string) => void;
  platformId: string;      // "" = all platforms
  setPlatformId: (s: string) => void;
};

/** Steerco consolidation tab: pick a period + platform (or all) and preview the
 *  one-pager in-app. Export/subscribe live in the page chrome (ExportMenu). */
export default function SteercoConsolidation({ period, setPeriod, platformId, setPlatformId }: Props) {
  const { t, lang } = useI18n();
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!period) setPeriod(currentSteercoPeriod());
  }, [period, setPeriod]);

  useEffect(() => {
    setEntries(null); setErr(null);
    api.get<Entry[]>(`/api/steerco/entries?period=${encodeURIComponent(period)}`)
      .then((rows) => {
        setEntries(rows);
        if (platformId && !rows.some((e) => String(e.platform_id) === platformId)) setPlatformId("");
      })
      .catch((e) => { setErr(String(e?.message ?? e)); setEntries([]); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  const view = useListView("steerco", "name");
  const pq = encodeURIComponent(period);
  const filledCount = entries?.filter((e) => e.filled).length ?? 0;
  const late = (entries ?? []).filter((e) => e.missing.length);

  // Ce qui compte avant d'ouvrir: le nom pour retrouver, l'etat pour savoir ce
  // qui reste, la date pour savoir si c'est frais. Une plateforme non remplie
  // passe devant, c'est elle qui demande une action.
  const sorts: SortSpec<Entry>[] = useMemo(() => [
    { key: "name", label: t("steerco.sort_name"),
      cmp: (a, b) => a.platform_name.localeCompare(b.platform_name) },
    { key: "state", label: t("steerco.sort_state"),
      cmp: (a, b) => Number(a.filled) - Number(b.filled) || a.platform_name.localeCompare(b.platform_name) },
    { key: "updated", label: t("steerco.sort_updated"),
      cmp: (a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? "") },
  ], [t]);

  const rows = useMemo(
    () => applyListView(entries ?? [], view, sorts,
                        (e, q) => e.platform_name.toLowerCase().includes(q)
                               || e.contributors.some((c) => c.name.toLowerCase().includes(q))),
    [entries, view.query, view.sort, view.desc, sorts]);

  // Ouvrir une plateforme, c'est aussi la designer a l'export: ce qu'on regarde
  // et ce qu'on emporte doivent etre la meme chose.
  const toggle = (e: Entry) =>
    setPlatformId(String(e.platform_id) === platformId ? "" : String(e.platform_id));

  const onepager = (e: Entry) => (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <iframe key={e.platform_id}
              src={`/api/steerco/onepager.html?platform_id=${e.platform_id}&period=${pq}&lang=${lang}`}
              title={`${e.platform_name} (${period})`}
              style={{ width: "100%", height: 1180, border: 0, display: "block", background: "#F5F7FA" }} />
    </div>
  );

  /** L'etat d'une plateforme, en une ligne: rempli ou non, et qui retient. */
  const state = (e: Entry) => (
    <>
      <span className={`badge ${e.filled ? "badge-green" : "badge-grey"}`}>
        {e.filled ? t("steerco.state_filled") : t("steerco.not_filled")}
      </span>
      <span className="small muted">
        {e.contributors.map((c) => c.name).join(", ") || "-"}
      </span>
      {e.missing.length > 0 && (
        <span className="small" style={{ color: "var(--orange)" }}>
          {t("steerco.waiting_short", { who: e.missing.join(", ") })}
        </span>
      )}
    </>
  );

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card" style={{ padding: 14 }}>
        <div className="row" style={{ gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ width: 160 }}>
            <label htmlFor="steerco-period">{t("steerco.period")}</label>
            <input id="steerco-period" value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="2026-07" />
          </div>
          <ListSearch view={view} id="steerco-search" />
        </div>
        {entries && entries.length > 0 && (
          <div className="small muted" style={{ marginTop: 8 }}>
            {t("steerco.filled_count", { n: filledCount, total: entries.length })}
          </div>
        )}
        {/* Qui est en retard, nomme. Une slide alimentee par plusieurs squads n'est
            faite que quand son dernier contributeur l'a faite, et le compteur
            ci-dessus ne sait pas le dire. */}
        {late.length > 0 && (
          <div className="small" style={{ marginTop: 6 }}>
            {late.map((e) => (
              <div key={e.platform_id} className="muted">
                {t("steerco.waiting_on", { platform: e.platform_name, who: e.missing.join(", ") })}
              </div>
            ))}
          </div>
        )}
      </div>

      {err && <div className="small" style={{ color: "var(--red)" }}>{err}</div>}

      {entries === null ? <Spinner /> : entries.length === 0 ? (
        <EmptyState message={t("steerco.no_platforms")} />
      ) : (
        <>
          <ListControls view={view} sorts={sorts}
            left={<div className="small muted">{t("steerco.open_hint")}</div>} />

          {rows.length === 0 ? (
            <EmptyState message={t("list.no_match")} />
          ) : view.dense ? (
            /* En liste: la plateforme ouverte deploie son document juste dessous. */
            <div className="stack" style={{ gap: 10 }}>
              {rows.map((e) => (
                <div key={e.platform_id} className="stack" style={{ gap: 10 }}>
                  <button className="collapse-row" aria-expanded={String(e.platform_id) === platformId}
                          onClick={() => toggle(e)}>
                    <span className="collapse-caret" aria-hidden>
                      {String(e.platform_id) === platformId ? "\u25BE" : "\u25B8"}
                    </span>
                    <span className="strong">{e.platform_name}</span>
                    {state(e)}
                  </button>
                  {String(e.platform_id) === platformId && onepager(e)}
                </div>
              ))}
            </div>
          ) : (
            /* En cartes: la grille reste entiere, le document s'ouvre en dessous. */
            <>
              <div className="squad-grid-2">
                {rows.map((e) => (
                  <button key={e.platform_id}
                          className={`squad-card squad-card-lg${String(e.platform_id) === platformId ? " s-open" : ""}`}
                          aria-expanded={String(e.platform_id) === platformId}
                          onClick={() => toggle(e)}>
                    <div className="strong sc-name" style={{ color: "var(--navy)" }}>{e.platform_name}</div>
                    <div className="inline" style={{ gap: 8, marginTop: 8, flexWrap: "wrap" }}>{state(e)}</div>
                  </button>
                ))}
              </div>
              {rows.filter((e) => String(e.platform_id) === platformId).map(onepager)}
            </>
          )}
        </>
      )}
    </div>
  );
}
