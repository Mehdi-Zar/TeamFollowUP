// Steerco > Le mois, "year" view: one row per platform, one cell per month of the
// year, each cell saying where the month stands (empty, N/M in progress, complete,
// validated). A click opens the five-step wizard on that month.
import { useEffect, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { EmptyState, ErrorBanner, Spinner } from "../ui";
import SteercoWizard from "../SteercoWizard";
import { MonthState, currentSteercoPeriod, monthShort } from "../../steerco";

type Cell = MonthState & { period: string };
type Row = {
  platform_id: number; platform_name: string; tribe_id: number; tribe_name?: string | null;
  steerco_enabled: boolean; months: Cell[];
};

function cellClass(c: Cell): string {
  if (c.status === "validated") return "sc-cell validated";
  return `sc-cell ${c.fill}`;
}

export default function SteercoBoard({ tribeId }: { tribeId: number | null }) {
  const { t } = useI18n();
  const now = currentSteercoPeriod();
  const [year, setYear] = useState(Number(now.slice(0, 4)));
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<{ id: number; name: string; period: string } | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setRows(null); setErr(null);
    const q = tribeId ? `&tribe_id=${tribeId}` : "";
    api.get<{ platforms: Row[] }>(`/api/steerco/board?year=${year}${q}`)
      .then((r) => setRows(r.platforms))
      .catch((e) => { setErr(errorText(e)); setRows([]); });
  }, [year, tribeId, tick]);

  const label = (c: Cell) => {
    if (c.status === "validated") return "🔒";
    if (c.fill === "complete") return "✓";
    if (c.fill === "partial") return `${c.filled_count}/${c.item_count}`;
    return "";
  };
  const title = (r: Row, c: Cell) => {
    const st = c.status === "validated" ? t("steerco.state.validated")
      : c.fill === "complete" ? t("steerco.state.complete")
      : c.fill === "partial" ? t("steerco.state.partial", { n: c.filled_count, total: c.item_count })
      : t("steerco.state.empty");
    return `${r.platform_name}, ${monthShort(c.period)} : ${st}`;
  };

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="inline" style={{ gap: 6 }}>
        <button className="btn-ghost btn-sm" aria-label={t("common.prev")} onClick={() => setYear((y) => y - 1)}>‹</button>
        <span className="strong">{year}</span>
        <button className="btn-ghost btn-sm" aria-label={t("common.next")} onClick={() => setYear((y) => y + 1)}>›</button>
      </div>

      {err && <ErrorBanner message={err} />}

      {rows === null ? <Spinner /> : rows.length === 0 ? (
        <EmptyState message={t("steerco.board.empty")} />
      ) : (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="table sc-board">
            <thead>
              <tr>
                <th>{t("platforms.name")}</th>
                {rows[0].months.map((c) => (
                  <th key={c.period} className={c.period === now ? "sc-now" : ""}>{monthShort(c.period)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.platform_id}>
                  <td>
                    <div className="strong">{r.platform_name}</div>
                    {!tribeId && r.tribe_name && <div className="small muted">{r.tribe_name}</div>}
                    {!r.steerco_enabled && <span className="badge badge-grey">{t("platforms.off")}</span>}
                  </td>
                  {r.months.map((c) => (
                    <td key={c.period} className={c.period === now ? "sc-now" : ""}>
                      <button type="button" className={cellClass(c)} title={title(r, c)} aria-label={title(r, c)}
                              onClick={() => setOpen({ id: r.platform_id, name: r.platform_name, period: c.period })}>
                        {label(c)}
                      </button>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="inline small muted" style={{ gap: 14, flexWrap: "wrap" }}>
        <span><span className="sc-cell empty sc-legend" /> {t("steerco.state.empty")}</span>
        <span><span className="sc-cell partial sc-legend">2/5</span> {t("steerco.board.legend_partial")}</span>
        <span><span className="sc-cell complete sc-legend">✓</span> {t("steerco.state.complete")}</span>
        <span><span className="sc-cell validated sc-legend">🔒</span> {t("steerco.state.validated")}</span>
      </div>

      {open && (
        <SteercoWizard platformId={open.id} platformName={open.name} initialPeriod={open.period}
                       onClose={() => setOpen(null)} onSaved={() => setTick((n) => n + 1)} />
      )}
    </div>
  );
}
