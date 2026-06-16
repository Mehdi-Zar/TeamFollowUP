import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { useAuth } from "../auth";

/** One tidy "Export / Share" dropdown that groups every export & email action
 *  (CSV, HTML/PPTX report, printable view, send by mail, auto-subscribe) so the
 *  action bar stays clean. Items appear only when their module/SMTP allows it. */
type Props = {
  year?: number;
  squadId?: number;
  sinceDays?: number;
  csvHref?: string;
  csvEmailEndpoint?: string;
};

type Sub = { interval_days: number };
type View = "menu" | "emailReport" | "emailCsv" | "subscribe";
const INTERVALS = [7, 14, 30];

export default function ExportMenu({ year, squadId, sinceDays = 7, csvHref, csvEmailEndpoint }: Props) {
  const { t, lang } = useI18n();
  const { smtp_enabled } = useConfig();
  const m = useModule();
  const { user } = useAuth();
  const reportOn = m("review", "weekly_report");
  const csvOn = m("exports_csv");

  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("menu");
  const [to, setTo] = useState(user?.email || "");
  const [sub, setSub] = useState<Sub | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const rqs = `since_days=${sinceDays}${squadId ? `&squad_id=${squadId}` : ""}&lang=${lang}`;

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) { setOpen(false); setView("menu"); }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    if (open && view === "subscribe" && reportOn) {
      api.get<Sub>(`/api/reports/subscription${squadId ? `?squad_id=${squadId}` : ""}`).then(setSub).catch(() => {});
    }
  }, [open, view, squadId, reportOn]);

  const hasDownloads = (csvHref && csvOn) || reportOn;
  const hasEmail = smtp_enabled && (reportOn || (csvEmailEndpoint && csvOn));
  if (!hasDownloads && !hasEmail) return null;

  async function sendReport() {
    if (!to.trim()) return;
    setBusy(true); setMsg(null);
    try {
      await api.post("/api/reports/weekly/email", { to: to.trim(), since_days: sinceDays, squad_id: squadId ?? null, lang });
      setMsg(t("export.sent", { to: to.trim() }));
    } catch (e) { setMsg(e instanceof ApiError ? e.message : "Erreur"); } finally { setBusy(false); }
  }
  async function sendCsv() {
    if (!to.trim() || !csvEmailEndpoint) return;
    setBusy(true); setMsg(null);
    try {
      await api.post(csvEmailEndpoint, { to: to.trim(), year });
      setMsg(t("export.sent", { to: to.trim() }));
    } catch (e) { setMsg(e instanceof ApiError ? e.message : "Erreur"); } finally { setBusy(false); }
  }
  async function subscribe(days: number) {
    setMsg(null);
    try {
      const out = await api.put<Sub>("/api/reports/subscription", { interval_days: days, squad_id: squadId ?? null });
      setSub(out);
      setMsg(days ? t("sub.saved_on", { n: days }) : t("sub.saved_off"));
    } catch (e) { setMsg(e instanceof ApiError ? e.message : "Erreur"); }
  }

  const Item = ({ children, onClick, href, download }: any) =>
    href ? (
      <a className="menu-item" href={href} target={download ? undefined : "_blank"} rel="noreferrer" onClick={() => setOpen(false)}>{children}</a>
    ) : (
      <button className="menu-item" onClick={onClick}>{children}</button>
    );

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button className="btn btn-secondary btn-sm" onClick={() => { setOpen((o) => !o); setView("menu"); setMsg(null); }}>
        {t("export.menu")} ▾
      </button>
      {open && (
        <div className="card menu-pop" style={{ position: "absolute", right: 0, top: 38, zIndex: 60, width: 268, padding: 8 }}>
          {view === "menu" && (
            <>
              {hasDownloads && <div className="menu-label">{t("export.group_download")}</div>}
              {csvHref && csvOn && <Item href={csvHref} download>{t("export.csv_data")}</Item>}
              {reportOn && <Item href={`/api/reports/weekly.html?${rqs}`}>{t("export.report_html")}</Item>}
              {reportOn && <Item href={`/api/reports/weekly.pptx?${rqs}`} download>{t("export.report_pptx")}</Item>}

              {hasEmail && <div className="menu-label" style={{ marginTop: 6 }}>{t("export.group_email")}</div>}
              {smtp_enabled && reportOn && <Item onClick={() => { setView("emailReport"); setMsg(null); }}>{t("export.send_report")} …</Item>}
              {smtp_enabled && csvEmailEndpoint && csvOn && <Item onClick={() => { setView("emailCsv"); setMsg(null); }}>{t("export.send_csv")} …</Item>}
              {reportOn && smtp_enabled && <Item onClick={() => { setView("subscribe"); setMsg(null); }}>{t("export.auto") } …</Item>}
            </>
          )}

          {(view === "emailReport" || view === "emailCsv") && (
            <div className="stack" style={{ gap: 8, padding: 6 }}>
              <button className="btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => setView("menu")}>← {t("action.cancel")}</button>
              <label className="small">{t("export.to")}</label>
              <input value={to} onChange={(e) => setTo(e.target.value)} />
              <button className="btn-sm" disabled={busy || !to.trim()} onClick={view === "emailReport" ? sendReport : sendCsv}>{t("export.send")}</button>
            </div>
          )}

          {view === "subscribe" && (
            <div className="stack" style={{ gap: 6, padding: 6 }}>
              <button className="btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => setView("menu")}>← {t("action.cancel")}</button>
              <div className="small muted">{t("sub.intro")}</div>
              {INTERVALS.map((d) => (
                <button key={d} className={sub?.interval_days === d ? "btn-sm" : "btn-secondary btn-sm"} onClick={() => subscribe(d)}>
                  {t(`sub.every.${d}`)}{sub?.interval_days === d ? " ✓" : ""}
                </button>
              ))}
              {(sub?.interval_days ?? 0) > 0 && <button className="btn-ghost btn-sm" onClick={() => subscribe(0)}>{t("sub.unsubscribe")}</button>}
            </div>
          )}

          {msg && <div className="small muted" style={{ padding: "6px 8px 2px" }}>{msg}</div>}
        </div>
      )}
    </div>
  );
}
