import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";

/** Self-service: subscribe to receive the report by email every N days.
 *  Surfaced on the dashboard so it isn't buried in the admin. */
const INTERVALS = [7, 14, 30];

type Sub = { interval_days: number; last_sent_at: string | null };

export default function ReportSubscribe({ squadId }: { squadId?: number }) {
  const { t } = useI18n();
  const { smtp_enabled } = useConfig();
  const weeklyOn = useModule()("review", "weekly_report");
  const [open, setOpen] = useState(false);
  const [sub, setSub] = useState<Sub | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const qs = squadId ? `?squad_id=${squadId}` : "";

  useEffect(() => {
    if (weeklyOn) api.get<Sub>(`/api/reports/subscription${qs}`).then(setSub).catch(() => {});
  }, [weeklyOn, squadId]);

  // Visible as soon as the report module is on; emails only start once SMTP is
  // configured (we surface that inside the popover so the option stays discoverable).
  if (!weeklyOn) return null;

  async function choose(days: number) {
    setMsg(null);
    try {
      const out = await api.put<Sub>("/api/reports/subscription", { interval_days: days, squad_id: squadId ?? null });
      setSub(out);
      setMsg(days ? t("sub.saved_on", { n: days }) : t("sub.saved_off"));
      setTimeout(() => { setMsg(null); if (!days) setOpen(false); }, 1600);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Erreur");
    }
  }

  const current = sub?.interval_days ?? 0;

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <button className="btn btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}>
        {current > 0 ? t("sub.subscribed", { n: current }) : t("sub.subscribe")}
      </button>
      {open && (
        <div className="card" style={{ position: "absolute", right: 0, top: 38, zIndex: 50, width: 290, padding: 12 }}>
          <div className="small muted" style={{ marginBottom: 8 }}>{t("sub.intro")}</div>
          {!smtp_enabled && (
            <div className="small" style={{ marginBottom: 8, color: "var(--orange)" }}>{t("sub.no_smtp")}</div>
          )}
          <div className="stack" style={{ gap: 6 }}>
            {INTERVALS.map((d) => (
              <button
                key={d}
                className={current === d ? "btn-sm" : "btn-secondary btn-sm"}
                onClick={() => choose(d)}
              >
                {t(`sub.every.${d}`)}{current === d ? " ✓" : ""}
              </button>
            ))}
            {current > 0 && (
              <button className="btn-ghost btn-sm" onClick={() => choose(0)} style={{ marginTop: 4 }}>
                {t("sub.unsubscribe")}
              </button>
            )}
          </div>
          {msg && <div className="small muted" style={{ marginTop: 8 }}>{msg}</div>}
        </div>
      )}
    </div>
  );
}
