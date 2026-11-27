// Steerco > Reporting du mois: the monthly work, and only it. Pick the month, then
// three numbered steps, one under the other, in the order they are done:
//   1. fill in each platform's figures: the platforms are listed IN this step, each
//      with its "Fill in" button (the in-app assistant); an Excel file is the
//      alternative, offered under the list;
//   2. validate the figures (a validated month no longer moves);
//   3. send the deck by mail.
// The step to do now is highlighted. The settings are all in "Parametrage".
//
// A reader (the "steerco" capability) sees the platforms of the month, their state
// and their slide, without the steps.
import { useEffect, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { EmptyState, Spinner } from "../ui";
import MonthPicker from "../MonthPicker";
import SteercoWizard from "../SteercoWizard";
import SteercoBoard from "./SteercoBoard";
import { SteercoImportModal } from "./SteercoImport";
import { MonthState, monthLongLabel } from "../../steerco";

type Entry = MonthState & {
  platform_id: number; platform_name: string; tribe_id: number; tribe_name?: string | null;
  filled: boolean; can_run: boolean;
};

/** A platform's month state as one badge: validated, complete, in progress, empty. */
export function StateBadge({ s }: { s: MonthState }) {
  const { t } = useI18n();
  if (s.status === "validated") return <span className="badge badge-green">🔒 {t("steerco.state.validated")}</span>;
  if (s.fill === "complete") return <span className="badge badge-navy">{t("steerco.state.complete")}</span>;
  if (s.fill === "partial")
    return <span className="badge badge-orange">{t("steerco.state.partial", { n: s.filled_count, total: s.item_count })}</span>;
  return <span className="badge badge-grey">{t("steerco.state.empty")}</span>;
}

/** The saved slide of a platform's month, as it will be exported. */
function SlidePreview({ e, period }: { e: Entry; period: string }) {
  const { t, lang } = useI18n();
  const q = new URLSearchParams({ platform_id: String(e.platform_id), period, lang });
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="inline" style={{ gap: 8, justifyContent: "flex-end" }}>
        <a className="btn-secondary btn-sm" href={`/api/steerco/document.pptx?${q.toString()}`}>{t("steerco.render_pptx")}</a>
      </div>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <iframe src={`/api/steerco/onepager.html?${q.toString()}`} title={`${e.platform_name} (${period})`}
                style={{ width: "100%", height: 1180, border: 0, display: "block", background: "#F5F7FA" }} />
      </div>
    </div>
  );
}

type Props = {
  tribeId: number; canRun: boolean;
  period: string; setPeriod: (p: string) => void;
  /** The platform whose slide is open ("" none): the chrome export follows it. */
  platformId: string; setPlatformId: (s: string) => void;
  onSettings: () => void;
};

export default function SteercoMonth({ tribeId, canRun, period, setPeriod, platformId, setPlatformId, onSettings }: Props) {
  const { t, lang } = useI18n();
  const [view, setView] = useState<"month" | "year">("month");
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [recipients, setRecipients] = useState<string[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<Entry | null>(null);
  const [importing, setImporting] = useState(false);
  const [tick, setTick] = useState(0);
  const reload = () => setTick((n) => n + 1);

  useEffect(() => {
    setEntries(null); setErr(null);
    api.get<Entry[]>(`/api/steerco/entries?period=${encodeURIComponent(period)}&tribe_id=${tribeId}`)
      .then((rows) => {
        setEntries(rows);
        if (platformId && !rows.some((e) => String(e.platform_id) === platformId)) setPlatformId("");
      })
      .catch((e) => { setErr(errorText(e)); setEntries([]); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, tribeId, tick]);

  useEffect(() => {
    if (!canRun) { setRecipients(null); return; }
    api.get<{ recipients: string[] }>(`/api/steerco/mail?tribe_id=${tribeId}`)
      .then((c) => setRecipients(c.recipients ?? [])).catch(() => setRecipients(null));
  }, [canRun, tribeId, tick]);

  const all = entries ?? [];
  const total = all.length;
  const ready = all.filter((e) => e.status === "validated" || e.fill === "complete").length;
  const validated = all.filter((e) => e.status === "validated").length;
  const toValidate = all.filter((e) => e.status !== "validated" && e.fill !== "empty");
  const allValidated = total > 0 && validated === total;
  // The step to do now: the first one not finished.
  const current = !total ? 0 : ready < total ? 1 : !allValidated ? 2 : 3;
  const month = monthLongLabel(period, lang);

  async function validateAll() {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await api.post<{ validated: string[]; empty: string[] }>(
        `/api/steerco/validate?period=${encodeURIComponent(period)}&tribe_id=${tribeId}`, {});
      setMsg(t("steerco.validated_n", { n: r.validated.length })
        + (r.empty.length ? ` ${t("steerco.validate_empty", { list: r.empty.join(", ") })}` : ""));
      reload();
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  async function sendDeck() {
    if (!window.confirm(t("steerco.send_confirm", { n: recipients?.length ?? 0, month }))) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await api.post<{ sent: string[]; failed: string[] }>(
        `/api/steerco/send?period=${encodeURIComponent(period)}&tribe_id=${tribeId}&lang=${lang}`, {});
      setMsg(t("steerco.sent", { n: r.sent.length })
        + (r.failed.length ? ` ${t("steerco.send_failed", { list: r.failed.join(", ") })}` : ""));
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  const stepClass = (i: number) => `card sc-step${current === i ? " now" : current > i ? " done" : ""}`;
  const togglePreview = (e: Entry) =>
    setPlatformId(String(e.platform_id) === platformId ? "" : String(e.platform_id));

  const Head = ({ i, title, state }: { i: number; title: string; state: string }) => (
    <div className="sc-step-head">
      <span className="sc-step-n">{current > i ? "✓" : i}</span>
      <span style={{ flex: 1 }}>{title}</span>
      <span className="small muted" style={{ fontWeight: 400 }}>{state}</span>
    </div>
  );

  // The platforms of the month. For a Steerco leader it is the content of step 1.
  const list = (
    <div className="sc-list">
      {all.map((e) => {
        const isOpen = String(e.platform_id) === platformId;
        const action = e.status === "validated" ? t("steerco.row.read")
          : e.fill === "empty" ? t("steerco.row.enter") : t("steerco.row.continue");
        const primary = e.status !== "validated" && e.fill !== "complete";
        return (
          <div key={e.platform_id} className="stack" style={{ gap: 10 }}>
            <div className="sc-row">
              <div className="stack" style={{ gap: 2, flex: 1, minWidth: 180 }}>
                <span className="strong">{e.platform_name}</span>
                <span className="small muted">
                  {e.status === "validated" && e.validated_by ? t("steerco.validated_by", { who: e.validated_by })
                    : e.updated_by ? t("steerco.updated_by", { who: e.updated_by }) : t("steerco.nothing_yet")}
                </span>
              </div>
              <StateBadge s={e} />
              <div className="inline" style={{ gap: 6 }}>
                {e.can_run && (
                  <button className={primary ? "btn-sm" : "btn-secondary btn-sm"} onClick={() => setOpen(e)}>
                    {primary ? "✎ " : ""}{action}
                  </button>
                )}
                <button className="btn-ghost btn-sm" aria-expanded={isOpen} onClick={() => togglePreview(e)}>
                  {isOpen ? t("steerco.row.hide") : t("steerco.row.preview")}
                </button>
              </div>
            </div>
            {isOpen && <SlidePreview e={e} period={period} />}
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card" style={{ padding: 14 }}>
        <div className="row" style={{ gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          {view === "month" && (
            <div style={{ width: 190 }}>
              <label htmlFor="steerco-period">{t("steerco.month_of")}</label>
              <MonthPicker id="steerco-period" value={period} onChange={setPeriod} />
            </div>
          )}
          {view === "month" && <div className="small muted" style={{ flex: 1, minWidth: 220 }}>{t("steerco.month_hint")}</div>}
          {canRun && (
            <div className="seg" role="group" aria-label={t("steerco.view")} style={{ marginLeft: "auto" }}>
              <button type="button" className={view === "month" ? "active" : ""} onClick={() => setView("month")}>{t("steerco.view_month")}</button>
              <button type="button" className={view === "year" ? "active" : ""} onClick={() => setView("year")}>{t("steerco.view_year")}</button>
            </div>
          )}
        </div>
        {view === "year" && <div className="small muted" style={{ marginTop: 8 }}>{t("steerco.board.hint")}</div>}
      </div>

      {msg && <div className="small" role="status" style={{ color: "var(--green)" }}>{msg}</div>}
      {err && <div className="small" role="alert" style={{ color: "var(--red)" }}>{err}</div>}

      {view === "year" ? <SteercoBoard tribeId={tribeId} /> : entries === null ? <Spinner /> : total === 0 ? (
        canRun ? (
          <div className="card stack" style={{ gap: 8, alignItems: "flex-start" }}>
            <div className="strong">{t("steerco.first.title")}</div>
            <div className="small muted">{t("steerco.first.hint")}</div>
            <button className="btn-sm" onClick={onSettings}>{t("steerco.first.go")}</button>
          </div>
        ) : <EmptyState message={t("steerco.no_platforms")} />
      ) : !canRun ? (
        <div className="card stack" style={{ gap: 10 }}>{list}</div>
      ) : (
        <>
          <section className={stepClass(1)}>
            <Head i={1} title={t("steerco.step.enter")} state={t("steerco.step.enter_state", { n: ready, total })} />
            <div className="small muted">{t("steerco.step.enter_hint")}</div>
            {list}
            <div className="sc-alt">
              <span className="small muted">{t("steerco.step.excel_hint")}</span>
              <button className="btn-ghost btn-sm" onClick={() => setImporting(true)}>{t("steerco.board.import")}</button>
            </div>
          </section>

          <section className={stepClass(2)}>
            <Head i={2} title={t("steerco.step.validate")} state={t("steerco.validated_count", { n: validated, total })} />
            <div className="small muted">{t("steerco.step.validate_hint")}</div>
            <div>
              <button className={current === 2 ? "btn-sm" : "btn-secondary btn-sm"} disabled={busy || toValidate.length === 0} onClick={validateAll}>
                {t("steerco.validate_all", { n: toValidate.length })}
              </button>
            </div>
          </section>

          <section className={stepClass(3)}>
            <Head i={3} title={t("steerco.step.send")}
                  state={recipients === null ? "" : t("steerco.step.send_state", { n: recipients.length })} />
            <div className="small muted">
              {!allValidated ? t("steerco.send_needs_validated")
                : recipients && !recipients.length ? t("steerco.send_needs_recipients")
                : t("steerco.step.send_hint", { month })}
            </div>
            <div className="inline" style={{ gap: 6 }}>
              <button className={current === 3 ? "btn-sm" : "btn-secondary btn-sm"} disabled={busy || !allValidated || !recipients?.length} onClick={sendDeck}>
                {t("steerco.send_pack")}
              </button>
              {recipients && !recipients.length && (
                <button className="btn-ghost btn-sm" onClick={onSettings}>{t("steerco.step.set_recipients")}</button>
              )}
            </div>
          </section>
        </>
      )}

      {open && (
        <SteercoWizard platformId={open.platform_id} platformName={open.platform_name} initialPeriod={period}
                       onClose={() => setOpen(null)} onSaved={reload} />
      )}
      {importing && (
        <SteercoImportModal tribeId={tribeId} onClose={() => setImporting(false)} onDone={reload} />
      )}
    </div>
  );
}
