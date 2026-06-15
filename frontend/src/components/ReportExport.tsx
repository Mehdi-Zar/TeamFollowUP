import { useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useConfig } from "../config";
import { useAuth } from "../auth";

/** Export of the weekly report (combined dashboard + review) as HTML / PPTX,
 *  plus an on-demand email send. Placed in the Review page action bar. */
export default function ReportExport({ sinceDays = 7 }: { sinceDays?: number }) {
  const { t } = useI18n();
  const { smtp_enabled } = useConfig();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState(user?.email || "");
  const [msg, setMsg] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const qs = `since_days=${sinceDays}`;

  async function send() {
    if (!to.trim()) return;
    setSending(true);
    setMsg(null);
    try {
      await api.post("/api/reports/weekly/email", { to: to.trim(), since_days: sinceDays });
      setMsg(t("export.sent", { to: to.trim() }));
      setTimeout(() => { setOpen(false); setMsg(null); }, 1800);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Erreur");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="inline" style={{ gap: 8 }}>
      <a className="btn btn-secondary btn-sm" href={`/api/reports/weekly.html?${qs}`} target="_blank" rel="noreferrer">
        {t("report.html")}
      </a>
      <a className="btn btn-secondary btn-sm" href={`/api/reports/weekly.pptx?${qs}`}>
        {t("report.pptx")}
      </a>
      {smtp_enabled && (
        <div style={{ position: "relative", display: "inline-block" }}>
          <button className="btn btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}>
            {t("export.email")}
          </button>
          {open && (
            <div className="card" style={{ position: "absolute", right: 0, top: 38, zIndex: 50, width: 290, padding: 12 }}>
              <label>{t("export.to")}</label>
              <input value={to} onChange={(e) => setTo(e.target.value)} />
              <div className="small muted" style={{ marginTop: 6 }}>{t("report.email_hint")}</div>
              <div className="inline" style={{ justifyContent: "flex-end", gap: 8, marginTop: 10 }}>
                <button className="btn-secondary btn-sm" onClick={() => setOpen(false)}>{t("action.cancel")}</button>
                <button className="btn-sm" onClick={send} disabled={sending || !to.trim()}>{t("export.send")}</button>
              </div>
              {msg && <div className="small muted" style={{ marginTop: 8 }}>{msg}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
