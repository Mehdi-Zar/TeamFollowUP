// SteercoWizard - a guided, step-by-step popup to produce ONE month's Steerco
// report for a PLATFORM. The contributor moves through clear steps (month, KPIs,
// SLA & incidents, events, review), always seeing which month they are reporting and
// the previous months' values next to the editable current-month column, so the entry
// reads like filling the next column of a familiar table.
//
// A platform can be fed by several squads, and the platform's template assigns every
// KPI card and every SLA column to one of them. The form shows the WHOLE slide and
// only enables the items the signed-in user owns: the rest stays visible, greyed, and
// labelled with the squad that owes it. That is what lets two squad leaders fill one
// slide without either of them overwriting the other, and it tells each of them what
// the slide is still missing.
import { Fragment, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { Modal, Spinner } from "./ui";
import { BackfillGrid } from "./SteercoEditor";
import {
  SteercoData, SteercoKpi, SlaCell, SteercoEvent, PlatformTemplate, EditableItems,
  EVENT_SEVS, SLA_ICON, TREND_ARROW, yearMonths, monthLongLabel,
  clampPct, dataFromTemplate, kpiChange, prevPeriod, slaStatus,
} from "../steerco";

type HistMap = Record<string, SteercoData>;
type Contributor = { id: number; name: string };
type EntryPayload = {
  data: SteercoData; template: PlatformTemplate; editable: EditableItems;
  editable_squad_ids: number[]; contributors: Contributor[]; filled: boolean;
};

const EMPTY_TPL: PlatformTemplate = { kpis: [], sla: [], incidents: { owner_squad_id: null } };

export default function SteercoWizard({ platformId, platformName, initialPeriod, readonly, onClose, onSaved }: {
  platformId: number; platformName: string; initialPeriod: string; readonly?: boolean;
  onClose: () => void; onSaved?: () => void;
}) {
  const { t, lang } = useI18n();
  const ro = !!readonly;
  const [period, setPeriod] = useState(initialPeriod);
  const [data, setData] = useState<SteercoData>(dataFromTemplate(EMPTY_TPL));
  const [tpl, setTpl] = useState<PlatformTemplate>(EMPTY_TPL);
  const [editable, setEditable] = useState<EditableItems>({ kpis: [], sla: [], incidents: false, events: false });
  const [mySquads, setMySquads] = useState<number[]>([]);
  const [contributors, setContributors] = useState<Contributor[]>([]);
  const [hist, setHist] = useState<HistMap>({});
  const [existed, setExisted] = useState(false);      // a report already exists for this month
  const [loaded, setLoaded] = useState(false);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewErr, setPreviewErr] = useState<string | null>(null);

  // Load the picked month's snapshot + the 12-month history (for the context columns).
  useEffect(() => {
    let alive = true;
    setLoaded(false); setErr(null);
    Promise.all([
      api.get<EntryPayload>(`/api/steerco/platform/${platformId}?period=${encodeURIComponent(period)}`),
      api.get<{ months: { period: string; data: SteercoData }[] }>(`/api/steerco/platform/${platformId}/history?period=${encodeURIComponent(period)}`),
    ]).then(([cur, h]) => {
      if (!alive) return;
      setTpl(cur.template ?? EMPTY_TPL);
      setEditable(cur.editable);
      setMySquads(cur.editable_squad_ids ?? []);
      setContributors(cur.contributors ?? []);
      setExisted(!!cur.filled);
      setData(cur.data && (cur.data.kpis?.length || cur.data.sla?.services?.length)
        ? cur.data : dataFromTemplate(cur.template ?? EMPTY_TPL));
      const map: HistMap = {};
      for (const m of h.months) map[m.period] = m.data || {};
      setHist(map);
    }).catch((e) => { if (alive) setErr(e instanceof ApiError ? e.message : String(e)); })
      .finally(() => { if (alive) setLoaded(true); });
    return () => { alive = false; };
  }, [platformId, period]);

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

  // Who owes an item, as a name to show next to the fields somebody else fills.
  const ownerName = (id: number | null | undefined) =>
    contributors.find((c) => c.id === id)?.name ?? t("steerco.owner_none");
  const canKpi = (i: number) => !ro && editable.kpis.includes(i);
  const canSla = (i: number) => !ro && editable.sla.includes(i);
  const canInc = !ro && editable.incidents;
  const mine = (e: SteercoEvent) => mySquads.some((id) => String(id) === String(e.squad_id));

  // Live one-pager preview of the (still unsaved) snapshot, built when the user
  // reaches the review step. Nothing is persisted until they submit.
  useEffect(() => {
    if (step !== 4 || !loaded) return;
    let alive = true;
    setPreviewHtml(null); setPreviewErr(null); setPreviewBusy(true);
    api.post<string>(`/api/steerco/platform/${platformId}/preview.html?period=${encodeURIComponent(period)}&lang=${lang}`, data)
      .then((html) => { if (alive) setPreviewHtml(typeof html === "string" ? html : String(html)); })
      .catch((e) => { if (alive) setPreviewErr(e instanceof ApiError ? e.message : String(e)); })
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

  // Submit = save this month's snapshot, then close the wizard. The server keeps only
  // the items we own out of this payload, so sending the whole form is safe.
  async function save() {
    setBusy(true); setErr(null);
    try {
      await api.put(`/api/steerco/platform/${platformId}?period=${encodeURIComponent(period)}`, withComputed(data));
      onSaved?.();
      onClose();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  // ---- data mutators ----
  const kpis = data.kpis ?? [];
  const setKpis = (k: SteercoKpi[]) => setData({ ...data, kpis: k });
  const updKpi = (i: number, patch: Partial<SteercoKpi>) => setKpis(kpis.map((k, j) => (j === i ? { ...k, ...patch } : k)));
  const updKpiSub = (i: number, si: number, v: string) =>
    setKpis(kpis.map((k, j) => (j === i ? { ...k, sub: (k.sub ?? []).map((s, sj) => (sj === si ? { ...s, value: v } : s)) } : k)));

  const sla = data.sla ?? { services: [], cells: [] };
  const blank: SlaCell = { v: "", s: null };
  const updCell = (i: number, patch: Partial<SlaCell>) =>
    setData({ ...data, sla: { services: sla.services, cells: sla.services.map((_, j) => (j === i ? { ...(sla.cells[j] ?? blank), ...patch } : (sla.cells[j] ?? blank))) } });

  const evList = (which: "last_events" | "next_events") => data[which] ?? [];
  const setEv = (which: "last_events" | "next_events", list: SteercoEvent[]) => setData({ ...data, [which]: list });

  // ---- history lookups (read-only context) ----
  const kpiHist = (label: string, m: string) =>
    (hist[m]?.kpis ?? []).find((k) => (k.label || "").toLowerCase() === label.toLowerCase())?.value ?? "";
  const slaHist = (svc: string, m: string) => {
    const d = hist[m]; if (!d?.sla) return "";
    const idx = d.sla.services.findIndex((s) => (s || "").toLowerCase() === svc.toLowerCase());
    return idx >= 0 ? (d.sla.cells[idx]?.v ?? "") : "";
  };

  // ---- computed indicators (shown read-only, never typed in) ----
  const prev = prevPeriod(period);
  const changeOf = (k: SteercoKpi) => kpiChange(k.value, kpiHist(k.label, prev));
  const withComputed = (d: SteercoData): SteercoData => ({
    ...d,
    kpis: (d.kpis ?? []).map((k) => ({ ...k, ...changeOf(k) })),
    ...(d.sla ? { sla: { ...d.sla, cells: (d.sla.cells ?? []).map((c) => ({ ...c, s: slaStatus(c.v) })) } } : {}),
  });

  const monthName = monthLongLabel(period, lang);
  const ownedCount = editable.kpis.length + editable.sla.length + (editable.incidents ? 1 : 0);

  return (
    <Modal
      width={980}
      title={t("steerco.wiz.title")}
      onClose={onClose}
      footer={
        <div className="between" style={{ width: "100%", alignItems: "center" }}>
          <div className="inline" style={{ gap: 10 }}>
            {err && <span className="small" style={{ color: "var(--red)" }}>{err}</span>}
          </div>
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-secondary btn-sm" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>‹ {t("common.prev")}</button>
            {step < last
              ? <button className="btn-sm" onClick={() => setStep((s) => Math.min(last, s + 1))}>{t("common.next")} ›</button>
              : (ro
                  ? <button className="btn-sm" onClick={onClose}>{t("action.close")}</button>
                  : <button className="btn-sm" disabled={busy} onClick={save}>{busy ? "…" : t("steerco.wiz.submit")}</button>)}
          </div>
        </div>
      }
    >
      {/* Stepper */}
      <div className="wiz-steps">
        {steps.map((s, i) => (
          <div key={s.key} className={`wiz-step ${i === step ? "active" : i < step ? "done" : ""}`}
               onClick={() => i < step && setStep(i)}>
            <span className="wiz-dot">{i < step ? "✓" : i + 1}</span>
            <span>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Persistent context: which platform + which month this report is for */}
      <div className="wiz-ctx">
        <span>{t("steerco.wiz.ctx_prefix")}</span>
        <span className="wiz-month">{platformName}, {monthName}</span>
        <span className="wiz-badge">{existed ? t("steerco.wiz.status_draft") : t("steerco.wiz.status_new")}</span>
      </div>

      {/* What this contributor owns on a slide fed by several squads. */}
      {!ro && contributors.length > 1 && (
        <div className="small muted" style={{ marginBottom: 10 }}>
          {t("steerco.wiz.shared_hint", { n: ownedCount, who: contributors.map((c) => c.name).join(", ") })}
        </div>
      )}

      {!loaded ? <Spinner /> : (
        <>
          {/* ---- Step: month ---- */}
          {step === 0 && (
            <div className="stack" style={{ gap: 12 }}>
              <div>
                <div className="wiz-h">{t("steerco.wiz.month_label")}</div>
                <div className="wiz-help">{t("steerco.wiz.month_help")}</div>
                <input type="month" value={period} disabled={ro} style={{ width: 200 }}
                       onChange={(e) => e.target.value && setPeriod(e.target.value)} />
              </div>
              <div className="wiz-help" style={{ marginBottom: 0 }}>{t("steerco.wiz.month_next_hint")}</div>
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
                    <col />
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="sc-name">{t("steerco.wiz.col_kpi")}</th>
                      {months.map((m) => <MonthTh key={m} m={m} />)}
                      <th>{t("steerco.f.delta")}</th>
                      <th>{t("steerco.owner")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kpis.map((k, i) => {
                      const ch = changeOf(k);
                      const owned = canKpi(i);
                      return (
                      <Fragment key={i}>
                        <tr>
                          <td className="sc-name">{k.label}</td>
                          {months.map((m) => (m === period
                            ? <td key={m} className="sc-cur"><input value={k.value} disabled={!owned}
                                     title={owned ? "" : t("steerco.owned_by", { who: ownerName(tpl.kpis[i]?.owner_squad_id) })}
                                     onChange={(e) => updKpi(i, { value: e.target.value })} /></td>
                            : <td key={m} className="sc-past">{kpiHist(k.label, m) || "-"}</td>))}
                          <td className={`sc-chg ${ch.trend}`} title={t("steerco.f.delta_auto")}>
                            {ch.delta ? `${TREND_ARROW[ch.trend]} ${ch.delta}` : "-"}
                          </td>
                          <td className="small muted">{ownerName(tpl.kpis[i]?.owner_squad_id)}</td>
                        </tr>
                        {(k.sub ?? []).map((s, si) => (
                          <tr key={`${i}-${si}`} className="sc-sub">
                            <td className="sc-name">{s.label}</td>
                            {months.map((m) => (m === period
                              ? <td key={m} className="sc-cur"><input value={s.value} disabled={!owned} onChange={(e) => updKpiSub(i, si, e.target.value)} /></td>
                              : <td key={m}></td>))}
                            <td colSpan={2}></td>
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
                      <col />
                    </colgroup>
                    <thead>
                      <tr>
                        <th className="sc-name">{t("steerco.wiz.col_service")}</th>
                        {months.map((m) => <MonthTh key={m} m={m} />)}
                        <th>{t("steerco.f.status")}</th>
                        <th>{t("steerco.owner")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sla.services.map((svc, i) => {
                        const cell = sla.cells[i] ?? blank;
                        const st = slaStatus(cell.v);
                        const owned = canSla(i);
                        return (
                          <tr key={i}>
                            <td className="sc-name">{svc}</td>
                            {months.map((m) => (m === period
                              ? <td key={m} className="sc-cur"><input value={cell.v} disabled={!owned} placeholder="99,4%"
                                       title={owned ? "" : t("steerco.owned_by", { who: ownerName(tpl.sla[i]?.owner_squad_id) })}
                                       onChange={(e) => updCell(i, { v: clampPct(e.target.value) })} /></td>
                              : <td key={m} className="sc-past">{slaHist(svc, m) || "-"}</td>))}
                            <td className={`sc-rag ${st ?? "none"}`} title={t("steerco.f.status_auto")}>
                              {st ? `${SLA_ICON[st]} ${t(`steerco.rag.${st}`)}` : "-"}
                            </td>
                            <td className="small muted">{ownerName(tpl.sla[i]?.owner_squad_id)}</td>
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
                      <col />
                    </colgroup>
                    <thead>
                      <tr>
                        <th className="sc-name"></th>
                        {months.map((m) => <MonthTh key={m} m={m} />)}
                        <th>{t("steerco.owner")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td className="sc-name">{t("steerco.f.incidents_count")}</td>
                        {months.map((m) => (m === period
                          ? <td key={m} className="sc-cur"><input type="number" value={data.incidents ?? ""} disabled={!canInc} placeholder="13"
                                   title={canInc ? "" : t("steerco.owned_by", { who: ownerName(tpl.incidents?.owner_squad_id) })}
                                   onChange={(e) => setData({ ...data, incidents: e.target.value })} /></td>
                          : <td key={m} className="sc-past">{hist[m]?.incidents ?? "-"}</td>))}
                        <td className="small muted">{ownerName(tpl.incidents?.owner_squad_id)}</td>
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
              {contributors.length > 1 && <div className="small muted">{t("steerco.events_shared")}</div>}
              {(["last_events", "next_events"] as const).map((which) => {
                const list = evList(which);
                return (
                  <div key={which} className="stack" style={{ gap: 8 }}>
                    <div className="between" style={{ alignItems: "center" }}>
                      <span className="wiz-h" style={{ marginBottom: 0 }}>{t(`steerco.f.${which}`)}</span>
                      {!ro && editable.events && <button type="button" className="btn-secondary btn-sm"
                        onClick={() => setEv(which, [...list, { date: "", text: "", sev: which === "last_events" ? "amber" : "ice", squad_id: mySquads[0] }])}>{t("steerco.f.add_event")}</button>}
                    </div>
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
                            // Somebody else's line: visible (it is the same timeline)
                            // but not editable, so nobody can rewrite a colleague's.
                            const own = !ro && (mine(ev) || ev.squad_id == null);
                            return (
                              <tr key={i}>
                                <td><input value={ev.date} disabled={!own} placeholder="14/07" onChange={(e) => upd({ date: e.target.value })} /></td>
                                <td><input value={ev.tag ?? ""} disabled={!own} placeholder="Incident" onChange={(e) => upd({ tag: e.target.value })} /></td>
                                <td><input value={ev.text} disabled={!own} placeholder={t("steerco.f.text")} onChange={(e) => upd({ text: e.target.value })} /></td>
                                <td>
                                  <select value={ev.sev ?? "ice"} disabled={!own} onChange={(e) => upd({ sev: e.target.value as any })}>
                                    {EVENT_SEVS.map((s) => <option key={s} value={s}>{t(`steerco.sev.${s}`)}</option>)}
                                  </select>
                                </td>
                                {!ro && <td>{own && <button type="button" className="icon-del" title={t("action.delete")} aria-label={t("action.delete")} onClick={() => setEv(which, list.filter((_, j) => j !== i))}>✕</button>}</td>}
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

          {/* ---- Step: review & submit ---- */}
          {step === 4 && (
            <div className="stack" style={{ gap: 16 }}>
              <div>
                <div className="wiz-h">{t("steerco.wiz.review_title", { month: monthName })}</div>
                <div className="wiz-help">{t("steerco.wiz.review_hint")}</div>
              </div>
              <div className="wiz-recap">
                <div className="rc"><div className="rc-n">{kpis.filter((k) => (k.value || "").trim()).length}/{kpis.length}</div><div className="rc-l">{t("steerco.f.kpis")}</div></div>
                <div className="rc"><div className="rc-n">{(sla.cells || []).filter((c) => (c.v || "").trim()).length}/{sla.services.length}</div><div className="rc-l">{t("steerco.f.sla")}</div></div>
                <div className="rc"><div className="rc-n">{(data.incidents || "").trim() || "-"}</div><div className="rc-l">{t("steerco.f.incidents")}</div></div>
                <div className="rc"><div className="rc-n">{evList("last_events").length + evList("next_events").length}</div><div className="rc-l">{t("steerco.wiz.step_events")}</div></div>
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

              {!ro && (
                <details>
                  <summary className="small" style={{ cursor: "pointer", color: "var(--accent)" }}>{t("steerco.wiz.first_time")}</summary>
                  <div style={{ marginTop: 10 }}>
                    <BackfillGrid platformId={platformId} period={period} template={tpl} editable={editable} />
                  </div>
                </details>
              )}

              {!ro && <div className="small muted">{t("steerco.wiz.submit_hint")}</div>}
            </div>
          )}
        </>
      )}
    </Modal>
  );
}

/** Standalone one-pager preview for a platform's already-saved month (opened from the
 *  reporting launcher, next to "edit the report"). Uses the same contributor-safe
 *  preview endpoint, feeding it the saved snapshot. */
export function SteercoPreviewModal({ platformId, platformName, period, onClose }: {
  platformId: number; platformName: string; period: string; onClose: () => void;
}) {
  const { t, lang } = useI18n();
  const [html, setHtml] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setHtml(null); setErr(null);
    api.get<{ data: SteercoData }>(`/api/steerco/platform/${platformId}?period=${encodeURIComponent(period)}`)
      .then((r) => api.post<string>(`/api/steerco/platform/${platformId}/preview.html?period=${encodeURIComponent(period)}&lang=${lang}`, r.data || {}))
      .then((h) => { if (alive) setHtml(typeof h === "string" ? h : String(h)); })
      .catch((e) => { if (alive) setErr(e instanceof ApiError ? e.message : String(e)); });
    return () => { alive = false; };
  }, [platformId, period, lang]);

  return (
    <Modal width={980} title={`${t("steerco.wiz.preview_title")} : ${platformName}, ${monthLongLabel(period, lang)}`} onClose={onClose}
           footer={<button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}>
      {err ? <div className="banner banner-red">{err}</div>
        : html === null ? <Spinner label={t("steerco.wiz.preview_loading")} />
        : <iframe title={t("steerco.wiz.preview_title")} srcDoc={html}
                  style={{ width: "100%", height: 560, border: "1px solid var(--line)", borderRadius: 12, background: "#fff" }} />}
    </Modal>
  );
}
