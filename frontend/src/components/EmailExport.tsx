import { useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useConfig } from "../config";
import { useAuth } from "../auth";

export default function EmailExport({ endpoint, year }: { endpoint: string; year?: number }) {
  const { t } = useI18n();
  const { smtp_enabled } = useConfig();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState(user?.email || "");
  const [msg, setMsg] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  if (!smtp_enabled) return null;

  async function send() {
    if (!to.trim()) return;
    setSending(true);
    setMsg(null);
    try {
      await api.post(endpoint, { to: to.trim(), year });
      setMsg(t("export.sent", { to: to.trim() }));
      setTimeout(() => { setOpen(false); setMsg(null); }, 1800);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Erreur");
    } finally {
      setSending(false);
    }
  }

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <button className="btn btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}>
        {t("export.email")}
      </button>
      {open && (
        <div className="card" style={{ position: "absolute", right: 0, top: 38, zIndex: 50, width: 280, padding: 12 }}>
          <label>{t("export.to")}</label>
          <input value={to} onChange={(e) => setTo(e.target.value)} />
          <div className="inline" style={{ justifyContent: "flex-end", gap: 8, marginTop: 10 }}>
            <button className="btn-secondary btn-sm" onClick={() => setOpen(false)}>{t("action.cancel")}</button>
            <button className="btn-sm" onClick={send} disabled={sending || !to.trim()}>{t("export.send")}</button>
          </div>
          {msg && <div className="small muted" style={{ marginTop: 8 }}>{msg}</div>}
        </div>
      )}
    </div>
  );
}
