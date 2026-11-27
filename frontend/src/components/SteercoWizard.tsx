// SteercoWizard - a guided, step-by-step popup to produce ONE month's Steerco
// report for a PLATFORM. The Steerco leader moves through clear steps (month, KPIs,
// SLA & incidents, events, review), always seeing which month they are reporting and
// the previous months' values next to the editable current-month column, so the entry
// reads like filling the next column of a familiar table.
//
// Since 4.0 (ADR 0018) a Steerco leader fills the whole slide. Two leaders on the same
// month are kept apart by the month's version: a save made on a stale copy is refused
// (409) and the form offers to reload. A validated month is read-only until it is
// reopened, with a reason.
import { Fragment, useEffect, useMemo, useState } from "react";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { EmptyState, Modal, PickItem, Spinner } from "./ui";
import { StepLayout } from "./StepLayout";
import { BackfillGrid } from "./SteercoEditor";
import MonthPicker from "./MonthPicker";
import {
  SteercoData, SteercoKpi, SlaCell, SteercoEvent, PlatformTemplate, MonthState,
  EVENT_SEVS, SLA_ICON, TREND_ARROW, yearMonths, monthLongLabel,
  clampPct, dataFromTemplate, kpiChange, prevPeriod, slaStatus,
} from "../steerco";

type HistMap = Record<string, SteercoData>;
type LinkedSquad = { id: number; name: string };
type EntryPayload = MonthState & {
  data: SteercoData; template: PlatformTemplate; squads: LinkedSquad[];
  can_run: boolean; filled: boolean;
};
type HistoryPayload = {
  previous?: { period: string; data: SteercoData };
  months: { period: string; data: SteercoData; status?: string }[];
};

/** A key message a squad concerned wrote in its reporting (see /messages). */
type ReportMsg = { id: number; squad_id: number; squad_name: string; kind: "success" | "alert" | "risk";
  text: string; created_at: string; open: boolean };
const KIND_SEV: Record<ReportMsg["kind"], SteercoEvent["sev"]> = { success: "green", alert: "amber", risk: "red" };
const KIND_BADGE: Record<ReportMsg["kind"], string> = { success: "badge-green", alert: "badge-orange", risk: "badge-red" };

const EMPTY_TPL: PlatformTemplate = { kpis: [], sla: [] };

const same = (a?: string, b?: string) => (a || "").toLowerCase() === (b || "").toLowerCase();

/** Copy into `d` the previous month's figures where `d` has none (KPI and their
 *  sub-metrics, SLA, incidents). Events are the month's own: never copied. Returns
 *  the new data and how many fields were taken. */
export function takeOver(d: SteercoData, src: SteercoData): { data: SteercoData; n: number } {
  let n = 0;
  const kpis = (d.kpis ?? []).map((k) => {
    const p = (src.kpis ?? []).find((x) => same(x.label, k.label));
    if (!p) return k;
    let value = k.value;
    if (!(k.value || "").trim() && (p.value || "").trim()) { value = p.value; n++; }
    const sub = (k.sub ?? []).map((s) => {
      const ps = (p.sub ?? []).find((x) => same(x.label, s.label));
      if (ps && !(s.value || "").trim() && (ps.value || "").trim()) { n++; return { ...s, value: ps.value }; }
      return s;
    });
    return { ...k, value, ...(k.sub ? { sub } : {}) };
  });
  const cur = d.sla ?? { services: [], cells: [] };
  const ps = src.sla ?? { services: [], cells: [] };
  const cells = cur.services.map((svc, i) => {
    const c = cur.cells[i] ?? { v: "", s: null };
    const j = ps.services.findIndex((x) => same(x, svc));
    const pv = j >= 0 ? (ps.cells[j]?.v ?? "") : "";
    if ((c.v || "").trim() || !String(pv).trim()) return c;
    n++;
    return { ...c, v: pv };
  });
  let incidents = d.incidents;
  if (!String(d.incidents ?? "").trim() && String(src.incidents ?? "").trim()) { incidents = src.incidents; n++; }
  return { data: { ...d, kpis, sla: { services: cur.services, cells }, incidents }, n };
}

export default function SteercoWizard({ platformId, platformName, initialPeriod, readonly, onClose, onSaved }: {
  platformId: number; platformName: string; initialPeriod: string; readonly?: boolean;
  onClose: () => void; onSaved?: () => void;
}) {
  const { t, lang } = useI18n();
  const [period, setPeriod] = useState(initialPeriod);
  const [data, setData] = useState<SteercoData>(dataFromTemplate(EMPTY_TPL));
  const [tpl, setTpl] = useState<PlatformTemplate>(EMPTY_TPL);
  const [squads, setSquads] = useState<LinkedSquad[]>([]);
  const [canRun, setCanRun] = useState(false);
  const [state, setState] = useState<MonthState | null>(null);
  const [hist, setHist] = useState<HistMap>({});
  // The month before the reported one (December of the year before for a January).
  const [previous, setPrevious] = useState<SteercoData>({});
  const [existed, setExisted] = useState(false);      // a report already exists for this month
  const [loaded, setLoaded] = useState(false);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [reopening, setReopening] = useState(false);
  const [reason, setReason] = useState("");
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewErr, setPreviewErr] = useState<string | null>(null);

  // Load the picked month's snapshot + the 12-month history (for the context columns).
  useEffect(() => {
    let alive = true;
    setLoaded(false); setErr(null); setConflict(false); setNote(null);
    Promise.all([
      api.get<EntryPayload>(`/api/steerco/platform/${platformId}?period=${encodeURIComponent(period)}`),
      api.get<HistoryPayload>(`/api/steerco/platform/${platformId}/history?period=${encodeURIComponent(period)}`),
    ]).then(([cur, h]) => {
      if (!alive) return;
      setTpl(cur.template ?? EMPTY_TPL);
      setSquads(cur.squads ?? []);
      setCanRun(!!cur.can_run);
      setState(cur);
      setExisted(!!cur.filled);
      setPrevious(h.previous?.data ?? {});
      setData(cur.data && (cur.data.kpis?.length || cur.data.sla?.services?.length)
        ? cur.data : dataFromTemplate(cur.template ?? EMPTY_TPL));
      const map: HistMap = {};
      for (const m of h.months) map[m.period] = m.data || {};
      setHist(map);
    }).catch((e) => { if (alive) setErr(errorText(e)); })
      .finally(() => { if (alive) setLoaded(true); });
    return () => { alive = false; };
  }, [platformId, period, reloadTick]);

  const validated = state?.status === "validated";
  // Read-only: asked by the caller, a reader, or a validated month.
  const ro = !!readonly || !canRun || validated;

  // The report year's 12 months, January to December: exactly what /history returns
  // and what the one-pager charts plot. The reported month is highlighted and
  // editable; the other months are read-only context.
  const months = useMemo(() => yearMonths(period), [period]);
  const mAbbr = (m: string) => {
    const [y, mm] = m.split("-").map(Number);
    const s = new Date(y, mm - 1, 1).toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { month: "short" });
    return s.replace(".", "");
  };
  const MonthTh = ({ m }: { m: string }) => (
    <th className={m === period ? "sc-cur" : "sc-past"}>{mAbbr(m)}</th>
  );

  // Live one-pager preview of the (still unsaved) snapshot, built when the user
  // reaches the review step. Nothing is persisted until they save.
  useEffect(() => {
    if (step !== 4 || !loaded) return;
    let alive = true;
    setPreviewHtml(null); setPreviewErr(null); setPreviewBusy(true);
    const req = canRun
      ? api.post<string>(`/api/steerco/platform/${platformId}/preview.html?period=${encodeURIComponent(period)}&lang=${lang}`, data)
      : api.get<string>(`/api/steerco/onepager.html?platform_id=${platformId}&period=${encodeURIComponent(period)}&lang=${lang}`);
    req.then((html) => { if (alive) setPreviewHtml(typeof html === "string" ? html : String(html)); })
      .catch((e) => { if (alive) setPreviewErr(errorText(e)); })
      .finally(() => { if (alive) setPreviewBusy(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, period, loaded]);

  const steps = [
    { key: "month", label: t("steerco.wiz.step_month") },
    { key: "kpis", label: t("steerco.f.kpis") },
    { key: "sla", label: t("steerco.wiz.step_sla") },
    { key: "events", label: t("steerco.wiz.step_events") },
    { key: "review", label: t("steerco.wiz.step_review") },
  ];
  const last = steps.length - 1;

  // ---- data mutators ----
  const kpis = data.kpis ?? [];
  // Every mutator starts from the latest data (functional update), not from the
  // copy captured at render: two edits in a row kept only the last one.
  const setKpis = (fn: (k: SteercoKpi[]) => SteercoKpi[]) => setData((d) => ({ ...d, kpis: fn(d.kpis ?? []) }));
  const updKpi = (i: number, patch: Partial<SteercoKpi>) => setKpis((ks) => ks.map((k, j) => (j === i ? { ...k, ...patch } : k)));
  const updKpiSub = (i: number, si: number, v: string) =>
    setKpis((ks) => ks.map((k, j) => (j === i ? { ...k, sub: (k.sub ?? []).map((s, sj) => (sj === si ? { ...s, value: v } : s)) } : k)));

  const sla = data.sla ?? { services: [], cells: [] };
  const blank: SlaCell = { v: "", s: null };
  const updCell = (i: number, patch: Partial<SlaCell>) => setData((d) => {
    const cur = d.sla ?? { services: [], cells: [] };
    return { ...d, sla: { services: cur.services,
      cells: cur.services.map((_, j) => (j === i ? { ...(cur.cells[j] ?? blank), ...patch } : (cur.cells[j] ?? blank))) } };
  });

  const evList = (which: "last_events" | "next_events") => data[which] ?? [];
  // Which list the reporting-message picker is open for, if any.
  const [pickFor, setPickFor] = useState<"last_events" | "next_events" | null>(null);
  const setEv = (which: "last_events" | "next_events", list: SteercoEvent[]) => setData((d) => ({ ...d, [which]: list }));

  // ---- history lookups (read-only context) ----
  const kpiHist = (label: string, m: string) =>
    (hist[m]?.kpis ?? []).find((k) => same(k.label, label))?.value ?? "";
  const slaHist = (svc: string, m: string) => {
    const d = hist[m]; if (!d?.sla) return "";
    const idx = d.sla.services.findIndex((s) => same(s, svc));
    return idx >= 0 ? (d.sla.cells[idx]?.v ?? "") : "";
  };

  // ---- computed indicators (shown read-only, never typed in) ----
  const prev = prevPeriod(period);
  // M-1 is in the year's history, except for a January (its December is `previous`).
  const prevKpi = (label: string) => (hist[prev] ? kpiHist(label, prev)
    : (previous.kpis ?? []).find((k) => same(k.label, label))?.value ?? "");
  const changeOf = (k: SteercoKpi) => kpiChange(k.value, prevKpi(k.label));
  const withComputed = (d: SteercoData): SteercoData => ({
    ...d,
    kpis: (d.kpis ?? []).map((k) => ({ ...k, ...changeOf(k) })),
    ...(d.sla ? { sla: { ...d.sla, cells: (d.sla.cells ?? []).map((c) => ({ ...c, s: slaStatus(c.v) })) } } : {}),
  });

  // Save this month's snapshot (with the version it was loaded at), then validate it
  // when asked, then close. A 409 on save means another Steerco leader saved in
  // between: nothing is overwritten, the form offers to reload.
  async function save(andValidate: boolean) {
    setBusy(true); setErr(null); setConflict(false);
    const q = `period=${encodeURIComponent(period)}`;
    try {
      await api.put(`/api/steerco/platform/${platformId}?${q}`, { data: withComputed(data), version: state?.version ?? 0 });
    } catch (e: any) {
      setErr(errorText(e)); setConflict(e?.status === 409); setBusy(false);
      return;
    }
    if (andValidate) {
      try { await api.post(`/api/steerco/platform/${platformId}/validate?${q}`, {}); }
      catch (e) {
        // Saved but not validated: say so and stay, the figures are not lost.
        setErr(errorText(e)); setBusy(false); onSaved?.(); setReloadTick((n) => n + 1);
        return;
      }
    }
    onSaved?.();
    onClose();
  }

  // Reopen a validated month: back to draft, the reason goes to the audit log and
  // the exported document then says "revised on".
  async function reopen() {
    setBusy(true); setErr(null);
    try {
      await api.post(`/api/steerco/platform/${platformId}/reopen?period=${encodeURIComponent(period)}`, { reason });
      setReopening(false); setReason("");
      onSaved?.();
      setReloadTick((n) => n + 1);
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  const hasPrevious = (previous.kpis ?? []).some((k) => (k.value || "").trim())
    || (previous.sla?.cells ?? []).some((c) => String(c.v || "").trim())
    || !!String(previous.incidents ?? "").trim();
  function takePrevious() {
    const { data: next, n } = takeOver(data, previous);
    setData(next);
    setNote(n ? t("steerco.wiz.prev_taken", { n }) : t("steerco.wiz.prev_nothing"));
  }

  const monthName = monthLongLabel(period, lang);
  const statusLabel = validated ? t("steerco.state.validated")
    : existed ? t("steerco.wiz.status_draft") : t("steerco.wiz.status_new");
  const fmtDate = (iso?: string | null) =>
    iso ? new Date(iso).toLocaleDateString(lang === "fr" ? "fr-FR" : "en-GB") : "-";

  // What each step already holds, under its name in the side menu.
  const kpiFilled = kpis.filter((k) => (k.value || "").trim()).length;
  const slaFilled = (sla.cells || []).filter((c) => (c.v || "").trim()).length;
  const evCount = evList("last_events").length + evList("next_events").length;
  const meta: Record<string, { text: string; done: boolean }> = {
    month: { text: monthName, done: true },
    kpis: { text: `${kpiFilled}/${kpis.length}`, done: kpis.length > 0 && kpiFilled === kpis.length },
    sla: { text: `${slaFilled}/${sla.services.length}`, done: sla.services.length > 0 && slaFilled === sla.services.length },
    events: { text: t("steerco.wiz.meta_events", { n: evCount }), done: evCount > 0 },
    review: { text: statusLabel, done: validated },
  };

  return (
    <Modal
      width={1360}
      title={t("steerco.wiz.title")}
      onClose={onClose}
      footer={
        <div className="between" style={{ width: "100%", alignItems: "center" }}>
          <div className="inline" style={{ gap: 10 }}>
            {err && <span className="small" role="alert" style={{ color: "var(--red)" }}>{err}</span>}
            {conflict && (
              <button type="button" className="btn-secondary btn-sm" onClick={() => setReloadTick((n) => n + 1)}>
                {t("steerco.wiz.reload")}
              </button>
            )}
          </div>
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-secondary btn-sm" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>‹ {t("common.prev")}</button>
            {step < last
              ? <button className="btn-sm" onClick={() => setStep((s) => Math.min(last, s + 1))}>{t("common.next")} ›</button>
              : (ro
                  ? <button className="btn-sm" onClick={onClose}>{t("action.close")}</button>
                  : <>
                      <button className="btn-secondary btn-sm" disabled={busy} onClick={() => save(false)}>
                        {busy ? t("common.saving") : t("steerco.wiz.save_draft")}
                      </button>
                      <button className="btn-sm" disabled={busy} onClick={() => save(true)}>{t("steerco.wiz.save_validate")}</button>
                    </>)}
          </div>
        </div>
      }
    >
      <StepLayout ariaLabel={t("steerco.wiz.title")} at={step} onGo={setStep}
                  desc={t(`steerco.wiz.stepd.${steps[step].key}`)}
                  steps={steps.map((x) => ({ key: x.key, title: x.label, meta: meta[x.key]?.text, done: meta[x.key]?.done }))}
                  aside={
                    // Persistent context: which platform + which month this report is for.
                    <div className="wiz-ctx" style={{ margin: 0 }}>
                      <span className="wiz-month">{platformName}, {monthName}</span>
                      <span className="wiz-badge">{validated ? "🔒 " : ""}{statusLabel}</span>
                    </div>
                  }>

      {/* A validated month: read-only, and the one way back is a reopening with a reason. */}
      {loaded && validated && (
        <div className="banner stack" style={{ gap: 8 }}>
          <div className="small">
            🔒 {t("steerco.wiz.validated_banner", { who: state?.validated_by ?? "-", date: fmtDate(state?.validated_at) })}
          </div>
          {canRun && !readonly && (reopening ? (
            <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
              <input autoFocus aria-label={t("steerco.wiz.reopen_reason")} placeholder={t("steerco.wiz.reopen_reason")}
                     value={reason} onChange={(e) => setReason(e.target.value)} style={{ flex: 1, minWidth: 240 }} />
              <button className="btn-sm" disabled={busy || reason.trim().length < 3} onClick={reopen}>{t("steerco.wiz.reopen")}</button>
              <button className="btn-ghost btn-sm" onClick={() => { setReopening(false); setReason(""); }}>{t("action.cancel")}</button>
            </div>
          ) : (
            <div><button className="btn-secondary btn-sm" onClick={() => setReopening(true)}>{t("steerco.wiz.reopen")}</button></div>
          ))}
        </div>
      )}
      {loaded && !validated && state?.revised_at && (
        <div className="small muted">{t("steerco.wiz.reopened_hint")}</div>
      )}
      {note && <div className="small" role="status" style={{ color: "var(--green)" }}>{note}</div>}

      {!loaded ? <Spinner /> : (
        <>
          {/* ---- Step: month ---- */}
          {step === 0 && (
            <div className="stack" style={{ gap: 12 }}>
              <div>
                <div className="wiz-h">{t("steerco.wiz.month_label")}</div>
                <div className="wiz-help">{t("steerco.wiz.month_help")}</div>
                <MonthPicker value={period} width={200} onChange={setPeriod} />
              </div>
              <div className="wiz-help" style={{ marginBottom: 0 }}>{t("steerco.wiz.month_next_hint")}</div>
              {!ro && (
                <div className="stack" style={{ gap: 4 }}>
                  <div>
                    <button type="button" className="btn-secondary btn-sm" disabled={!hasPrevious} onClick={takePrevious}>
                      {t("steerco.wiz.take_prev")}
                    </button>
                  </div>
                  <div className="small muted">{hasPrevious ? t("steerco.wiz.take_prev_hint") : t("steerco.wiz.prev_none")}</div>
                </div>
              )}
            </div>
          )}

          {/* ---- Step: KPIs (history table + editable current column) ---- */}
          {step === 1 && (
            <div className="stack" style={{ gap: 12 }}>
              <div className="wiz-help">{t("steerco.wiz.history_hint")} {t("steerco.f.delta_auto")}</div>
              {kpis.length === 0 && <div className="small muted">{t("steerco.wiz.no_items")}</div>}
              <div className="sc-hist">
                <table>
                  <colgroup>
                    <col className="c-name" />
                    {months.map((m) => <col key={m} className={m === period ? "c-cur" : "c-m"} />)}
                    <col className="c-delta" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="sc-name">{t("steerco.wiz.col_kpi")}</th>
                      {months.map((m) => <MonthTh key={m} m={m} />)}
                      <th>{t("steerco.f.delta")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kpis.map((k, i) => {
                      const ch = changeOf(k);
                      return (
                      <Fragment key={i}>
                        <tr>
                          <td className="sc-name">{k.label}</td>
                          {months.map((m) => (m === period
                            ? <td key={m} className="sc-cur"><input value={k.value} disabled={ro}
                                     onChange={(e) => updKpi(i, { value: e.target.value })} /></td>
                            : <td key={m} className="sc-past">{kpiHist(k.label, m) || "-"}</td>))}
                          <td className={`sc-chg ${ch.trend}`} title={t("steerco.f.delta_auto")}>
                            {ch.delta ? `${TREND_ARROW[ch.trend]} ${ch.delta}` : "-"}
                          </td>
                        </tr>
                        {(k.sub ?? []).map((s, si) => (
                          <tr key={`${i}-${si}`} className="sc-sub">
                            <td className="sc-name">{s.label}</td>
                            {months.map((m) => (m === period
                              ? <td key={m} className="sc-cur"><input value={s.value} disabled={ro} onChange={(e) => updKpiSub(i, si, e.target.value)} /></td>
                              : <td key={m}></td>))}
                            <td></td>
                          </tr>
                        ))}
                      </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="small muted">{t("steerco.template_note")}</div>
            </div>
          )}

          {/* ---- Step: SLA & incidents ---- */}
          {step === 2 && (
            <div className="stack" style={{ gap: 14 }}>
              <div>
                <div className="wiz-h">{t("steerco.f.sla")}</div>
                <div className="wiz-help">{t("steerco.wiz.history_hint")} {t("steerco.f.status_auto")}</div>
                <div className="sc-hist">
                  <table>
                    <colgroup>
                      <col className="c-name" />
                      {months.map((m) => <col key={m} className={m === period ? "c-cur" : "c-m"} />)}
                      <col className="c-status" />
                    </colgroup>
                    <thead>
                      <tr>
                        <th className="sc-name">{t("steerco.wiz.col_service")}</th>
                        {months.map((m) => <MonthTh key={m} m={m} />)}
                        <th>{t("steerco.f.status")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sla.services.map((svc, i) => {
                        const cell = sla.cells[i] ?? blank;
                        const st = slaStatus(cell.v);
                        return (
                          <tr key={i}>
                            <td className="sc-name">{svc}</td>
                            {months.map((m) => (m === period
                              ? <td key={m} className="sc-cur"><input value={cell.v} disabled={ro} placeholder="99,4%"
                                       onChange={(e) => updCell(i, { v: clampPct(e.target.value) })} /></td>
                              : <td key={m} className="sc-past">{slaHist(svc, m) || "-"}</td>))}
                            <td className={`sc-rag ${st ?? "none"}`} title={t("steerco.f.status_auto")}>
                              {st ? `${SLA_ICON[st]} ${t(`steerco.rag.${st}`)}` : "-"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <div className="wiz-h">{t("steerco.f.incidents")}</div>
                <div className="wiz-help">{t("steerco.f.incidents_hint")}</div>
                <div className="sc-hist">
                  <table>
                    <colgroup>
                      <col className="c-name" />
                      {months.map((m) => <col key={m} className={m === period ? "c-cur" : "c-m"} />)}
                    </colgroup>
                    <thead>
                      <tr>
                        <th className="sc-name"></th>
                        {months.map((m) => <MonthTh key={m} m={m} />)}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td className="sc-name">{t("steerco.f.incidents_count")}</td>
                        {months.map((m) => (m === period
                          ? <td key={m} className="sc-cur"><input type="number" value={data.incidents ?? ""} disabled={ro} placeholder="13"
                                   onChange={(e) => setData((d) => ({ ...d, incidents: e.target.value }))} /></td>
                          : <td key={m} className="sc-past">{hist[m]?.incidents ?? "-"}</td>))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ---- Step: events ---- */}
          {step === 3 && (
            <div className="stack" style={{ gap: 16 }}>
              <div className="wiz-help" style={{ marginBottom: 0 }}>{t("steerco.wiz.events_hint")}</div>
              {(["last_events", "next_events"] as const).map((which) => {
                const list = evList(which);
                return (
                  <div key={which} className="stack" style={{ gap: 8 }}>
                    <div className="between" style={{ alignItems: "center" }}>
                      <span className="wiz-h" style={{ marginBottom: 0 }}>{t(`steerco.f.${which}`)}</span>
                      {!ro && (
                        <div className="inline" style={{ gap: 6 }}>
                          {/* Key messages of the squads concerned, when the platform has some. */}
                          {squads.length > 0 && (
                            <button type="button" className="btn-secondary btn-sm" aria-expanded={pickFor === which}
                              onClick={() => setPickFor(pickFor === which ? null : which)}>{t("steerco.msg.take")}</button>
                          )}
                          <button type="button" className="btn-secondary btn-sm"
                            onClick={() => setEv(which, [...list, { date: "", text: "", sev: which === "last_events" ? "amber" : "ice" }])}>{t("steerco.f.add_event")}</button>
                        </div>
                      )}
                    </div>
                    {pickFor === which && (
                      <MessagePicker platformId={platformId} period={period} taken={list.map((e) => e.text)}
                        onCancel={() => setPickFor(null)}
                        onAdd={(msgs) => {
                          setEv(which, [...list, ...msgs.map((m): SteercoEvent => ({
                            date: new Date(m.created_at).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }),
                            tag: t(`km.kind.${m.kind}`), text: m.text, sev: KIND_SEV[m.kind],
                          }))]);
                          setPickFor(null);
                        }} />
                    )}
                    <div className="sc-ev">
                      <table>
                        <colgroup>
                          <col className="c-date" />
                          <col className="c-type" />
                          <col />
                          <col className="c-sev" />
                          {!ro && <col className="c-evdel" />}
                        </colgroup>
                        <thead>
                          <tr>
                            <th>{t("steerco.f.date")}</th>
                            <th>{t("steerco.f.tag")}</th>
                            <th>{t("steerco.f.text")}</th>
                            <th>{t("steerco.f.sev")}</th>
                            {!ro && <th></th>}
                          </tr>
                        </thead>
                        <tbody>
                          {list.length === 0 && (
                            <tr><td className="sc-ev-empty" colSpan={ro ? 4 : 5}>{t("steerco.f.none")}</td></tr>
                          )}
                          {list.map((ev, i) => {
                            const upd = (patch: Partial<SteercoEvent>) => setEv(which, list.map((x, j) => (j === i ? { ...x, ...patch } : x)));
                            return (
                              <tr key={i}>
                                <td><input value={ev.date} disabled={ro} placeholder="14/07" onChange={(e) => upd({ date: e.target.value })} /></td>
                                <td><input value={ev.tag ?? ""} disabled={ro} placeholder="Incident" onChange={(e) => upd({ tag: e.target.value })} /></td>
                                <td><input value={ev.text} disabled={ro} placeholder={t("steerco.f.text")} onChange={(e) => upd({ text: e.target.value })} /></td>
                                <td>
                                  <select value={ev.sev ?? "ice"} disabled={ro} onChange={(e) => upd({ sev: e.target.value as any })}>
                                    {EVENT_SEVS.map((s) => <option key={s} value={s}>{t(`steerco.sev.${s}`)}</option>)}
                                  </select>
                                </td>
                                {!ro && <td><button type="button" className="icon-del" title={t("action.delete")} aria-label={t("action.delete")} onClick={() => setEv(which, list.filter((_, j) => j !== i))}>✕</button></td>}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* ---- Step: review & save ---- */}
          {step === 4 && (
            <div className="stack" style={{ gap: 16 }}>
              <div>
                <div className="wiz-h">{t("steerco.wiz.review_title", { month: monthName })}</div>
                <div className="wiz-help">{t("steerco.wiz.review_hint")}</div>
              </div>
              <div className="wiz-recap">
                <div className="rc"><div className="rc-n">{kpiFilled}/{kpis.length}</div><div className="rc-l">{t("steerco.f.kpis")}</div></div>
                <div className="rc"><div className="rc-n">{slaFilled}/{sla.services.length}</div><div className="rc-l">{t("steerco.f.sla")}</div></div>
                <div className="rc"><div className="rc-n">{String(data.incidents ?? "").trim() || "-"}</div><div className="rc-l">{t("steerco.f.incidents")}</div></div>
                <div className="rc"><div className="rc-n">{evCount}</div><div className="rc-l">{t("steerco.wiz.step_events")}</div></div>
              </div>

              {/* Live preview of the one-pager this report will produce */}
              <div>
                <div className="wiz-h">{t("steerco.wiz.preview_title")}</div>
                <div className="wiz-help">{t("steerco.wiz.preview_hint")}</div>
                {previewBusy ? <Spinner label={t("steerco.wiz.preview_loading")} />
                  : previewErr ? <div className="banner banner-red">{previewErr}</div>
                  : <iframe title={t("steerco.wiz.preview_title")} srcDoc={previewHtml ?? ""}
                            style={{ width: "100%", height: 460, border: "1px solid var(--line)", borderRadius: 12, background: "#fff" }} />}
              </div>

              {canRun && !readonly && (
                <details>
                  <summary className="small" style={{ cursor: "pointer", color: "var(--accent)" }}>{t("steerco.wiz.first_time")}</summary>
                  <div style={{ marginTop: 10 }}>
                    <BackfillGrid platformId={platformId} period={period} template={tpl}
                                  onSaved={() => { onSaved?.(); setReloadTick((n) => n + 1); }} />
                  </div>
                </details>
              )}

              {!ro && <div className="small muted">{t("steerco.wiz.submit_hint")}</div>}
            </div>
          )}
        </>
      )}
      </StepLayout>
    </Modal>
  );
}

/** Standalone one-pager preview for a platform's saved month, read-only: the
 *  saved snapshot rendered as the committee will see it. */
export function SteercoPreviewModal({ platformId, platformName, period, onClose }: {
  platformId: number; platformName: string; period: string; onClose: () => void;
}) {
  const { t, lang } = useI18n();
  const [html, setHtml] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setHtml(null); setErr(null);
    api.get<string>(`/api/steerco/onepager.html?platform_id=${platformId}&period=${encodeURIComponent(period)}&lang=${lang}`)
      .then((h) => { if (alive) setHtml(typeof h === "string" ? h : String(h)); })
      .catch((e) => { if (alive) setErr(errorText(e)); });
    return () => { alive = false; };
  }, [platformId, period, lang]);

  return (
    <Modal width={980} title={`${t("steerco.wiz.preview_title")}${t("common.colon")}${platformName}, ${monthLongLabel(period, lang)}`} onClose={onClose}
           footer={<button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}>
      {err ? <div className="banner banner-red">{err}</div>
        : html === null ? <Spinner label={t("steerco.wiz.preview_loading")} />
        : <iframe title={t("steerco.wiz.preview_title")} srcDoc={html}
                  style={{ width: "100%", height: 560, border: "1px solid var(--line)", borderRadius: 12, background: "#fff" }} />}
    </Modal>
  );
}

/** The key messages written in the reportings of the platform's squads concerned,
 *  to take over as events: filter by kind, tick, add. A message already on the list
 *  is shown but cannot be taken twice. */
function MessagePicker({ platformId, period, taken, onAdd, onCancel }: {
  platformId: number; period: string; taken: string[];
  onAdd: (msgs: ReportMsg[]) => void; onCancel: () => void;
}) {
  const { t, lang } = useI18n();
  const [msgs, setMsgs] = useState<ReportMsg[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [kind, setKind] = useState<ReportMsg["kind"] | "">("");
  const [picked, setPicked] = useState<number[]>([]);

  useEffect(() => {
    api.get<ReportMsg[]>(`/api/steerco/platform/${platformId}/messages?period=${encodeURIComponent(period)}`)
      .then(setMsgs).catch((e) => { setErr(errorText(e)); setMsgs([]); });
  }, [platformId, period]);

  const norm = (s: string) => s.split(/\s+/).join(" ").trim().toLowerCase();
  const takenSet = new Set(taken.map(norm));
  const all = msgs ?? [];
  const shown = all.filter((m) => !kind || m.kind === kind);
  const count = (k: ReportMsg["kind"]) => all.filter((m) => m.kind === k).length;
  const toggle = (id: number) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const when = (iso: string) =>
    new Date(iso).toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { day: "numeric", month: "short" });

  return (
    <div className="card stack" style={{ gap: 10, padding: 12, background: "var(--ice-soft)" }}>
      <div className="between" style={{ alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <div className="small muted">{t("steerco.msg.hint")}</div>
        <div className="seg" role="group" aria-label={t("steerco.msg.filter")}>
          <button type="button" className={kind === "" ? "active" : ""} onClick={() => setKind("")}>
            {t("steerco.msg.all")} ({all.length})
          </button>
          {(["success", "alert", "risk"] as const).map((k) => (
            <button key={k} type="button" className={kind === k ? "active" : ""} onClick={() => setKind(k)}>
              {t(`km.kind.${k}`)} ({count(k)})
            </button>
          ))}
        </div>
      </div>
      {err && <div className="small" style={{ color: "var(--red)" }}>{err}</div>}
      {msgs === null ? <Spinner /> : shown.length === 0 ? (
        <EmptyState message={t("steerco.msg.none")} />
      ) : (
        <div className="stack" style={{ gap: 6, maxHeight: 320, overflowY: "auto" }}>
          {shown.map((m) => {
            const already = takenSet.has(norm(m.text));
            return (
              <PickItem key={m.id} selected={picked.includes(m.id)} disabled={already}
                onToggle={() => toggle(m.id)} title={m.text}
                meta={`${m.squad_name}, ${when(m.created_at)}${m.open ? ` (${t("steerco.msg.open")})` : ""}`}
                tag={already ? <span className="badge badge-grey">{t("steerco.msg.taken")}</span>
                  : <span className={`badge ${KIND_BADGE[m.kind]}`}>{t(`km.kind.${m.kind}`)}</span>} />
            );
          })}
        </div>
      )}
      <div className="inline" style={{ gap: 8, justifyContent: "flex-end" }}>
        <button type="button" className="btn-ghost btn-sm" onClick={onCancel}>{t("action.cancel")}</button>
        <button type="button" className="btn-sm" disabled={!picked.length}
          onClick={() => onAdd(all.filter((m) => picked.includes(m.id)))}>
          {t("steerco.msg.add", { n: picked.length })}
        </button>
      </div>
    </div>
  );
}
