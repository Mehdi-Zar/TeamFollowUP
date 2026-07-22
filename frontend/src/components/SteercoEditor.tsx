// Steerco 12-month backfill grid. The monthly input itself lives in SteercoWizard
// (guided popup); this grid is the "first report" companion that seeds the past
// months in one shot so the 12-month charts have data right away.
// Only raw values are entered here: the KPI variation vs M-1 and the SLA colours are
// computed from the numbers themselves when the one-pager is rendered.
import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { clampPct, last12Months, monthShort } from "../steerco";

/** 12-month history grid: one row per month, columns = KPI counts + SLA values +
 *  incidents. Loads existing snapshots, supports paste-from-Excel (TSV), and saves
 *  all months in one shot so the charts have 12 months of data. */
export function BackfillGrid({ squadId, period, services, kpiLabels }: { squadId: number; period: string; services: string[]; kpiLabels: string[] }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const months = last12Months(period);
  // grid[monthKey][colKey] = string value
  const cols = [
    ...kpiLabels.filter(Boolean).map((l) => ({ key: `kpi:${l}`, label: l })),
    ...services.map((s) => ({ key: `sla:${s}`, label: `SLA ${s}` })),
    { key: "incidents", label: t("steerco.f.incidents_count") },
  ];
  const [grid, setGrid] = useState<Record<string, Record<string, string>>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api.get<{ months: { period: string; data: any }[] }>(`/api/steerco/squad/${squadId}/history?period=${encodeURIComponent(period)}`)
      .then((r) => {
        const g: Record<string, Record<string, string>> = {};
        for (const m of r.months) {
          const row: Record<string, string> = {};
          for (const k of (m.data?.kpis ?? [])) row[`kpi:${k.label}`] = String(k.value ?? "");
          const svc = m.data?.sla?.services ?? [];
          (m.data?.sla?.cells ?? []).forEach((c: any, i: number) => { if (svc[i]) row[`sla:${svc[i]}`] = String(c.v ?? ""); });
          if (m.data?.incidents != null) row["incidents"] = String(m.data.incidents);
          g[m.period] = row;
        }
        setGrid(g);
      })
      .catch(() => {});
  }, [open, squadId, period]);

  // SLA columns hold percentages, so they are capped at 100.
  const clean = (ck: string, v: string) => (ck.startsWith("sla:") ? clampPct(v) : v);
  const set = (mk: string, ck: string, v: string) =>
    setGrid((g) => ({ ...g, [mk]: { ...(g[mk] ?? {}), [ck]: clean(ck, v) } }));

  // Paste TSV: rows map to months (top -> oldest), columns to `cols` in order.
  function onPaste(e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const rows = text.replace(/\r/g, "").split("\n").filter((r) => r.length);
    setGrid((g) => {
      const ng = { ...g };
      rows.forEach((r, ri) => {
        const mk = months[ri];
        if (!mk) return;
        const vals = r.split("\t");
        ng[mk] = { ...(ng[mk] ?? {}) };
        cols.forEach((c, ci) => { if (vals[ci] != null && vals[ci] !== "") ng[mk][c.key] = clean(c.key, vals[ci].trim()); });
      });
      return ng;
    });
    setMsg(t("steerco.f.pasted"));
  }

  async function save() {
    setBusy(true); setMsg(null);
    try {
      const payload: Record<string, any> = {};
      for (const mk of months) {
        const row = grid[mk];
        if (!row || Object.values(row).every((v) => !v)) continue;
        const snap: any = {};
        const kv = kpiLabels.filter(Boolean).map((l) => ({ label: l, value: row[`kpi:${l}`] ?? "" }));
        if (kv.some((k) => k.value)) snap.kpis = kv;
        // Only the value is stored: the SLA colour is computed from it at render time.
        const cells = services.map((s) => ({ v: row[`sla:${s}`] ?? "" }));
        if (cells.some((c) => c.v)) snap.sla = { services, cells };
        if (row["incidents"]) snap.incidents = row["incidents"];
        if (Object.keys(snap).length) payload[mk] = snap;
      }
      await api.put(`/api/steerco/squad/${squadId}/history`, { months: payload });
      setMsg(t("steerco.f.backfill_saved", { n: Object.keys(payload).length }));
    } catch (e: any) {
      setMsg(e?.message ?? "Erreur");
    } finally { setBusy(false); }
  }

  return (
    <div className="card stack" style={{ gap: 10, padding: 14, borderLeft: "3px solid var(--ice, #8DA9C4)" }}>
      <div className="between" style={{ alignItems: "center" }}>
        <span className="strong" style={{ color: "var(--navy)" }}>{t("steerco.f.backfill")}</span>
        <button type="button" className="btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}>{open ? "▾" : "▸"} {open ? t("action.close") : t("steerco.f.backfill_open")}</button>
      </div>
      <div className="small muted">{t("steerco.f.backfill_hint")}</div>
      {open && (
        <>
          <div style={{ overflowX: "auto" }} onPaste={onPaste}>
            <table className="table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th>{t("steerco.f.month")}</th>
                  {cols.map((c) => <th key={c.key} style={{ whiteSpace: "nowrap" }}>{c.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {months.map((mk) => (
                  <tr key={mk}>
                    <td className="strong small" style={{ whiteSpace: "nowrap" }}>{monthShort(mk)}</td>
                    {cols.map((c) => (
                      <td key={c.key} style={{ padding: 2 }}>
                        <input style={{ width: 64, padding: "2px 4px" }} value={grid[mk]?.[c.key] ?? ""}
                               onChange={(e) => set(mk, c.key, e.target.value)} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="small muted">{t("steerco.f.paste_hint")}</div>
          <div className="inline" style={{ justifyContent: "flex-end", gap: 10 }}>
            {msg && <span className="small" style={{ color: "var(--green)" }}>{msg}</span>}
            <button type="button" className="btn-sm" disabled={busy} onClick={save}>{t("steerco.f.backfill_save")}</button>
          </div>
        </>
      )}
    </div>
  );
}
