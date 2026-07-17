// ReportingModal: the "Subscribe to a report" popup opened from the dashboard.
// It adapts to the persona — admins get the org-wide reporting configuration
// (ReportingAdmin), everyone else manages their personal delivery schedule
// (which weekdays + hour to receive the weekly report by email).
import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { useConfig, useModule } from "../config";
import { Modal, Spinner } from "./ui";
import { ReportingAdmin } from "../pages/AdminPage";

// Shape of a user's report subscription. `weekdays` are 0=Mon..6=Sun; an empty
// list (or interval_days 0) means the subscription is off.

type Sub = { squad_id: number | null; interval_days: number; weekdays: number[]; hour: number };
const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/** "Subscribe to a report" popup, opened from the dashboard (and anywhere else).
 *  No dedicated tab: the general/org configuration lives in Administration, and
 *  this window adapts to the persona - admins get the full config, everyone else
 *  gets their personal subscription (which days + hour to receive the report). */
export function ReportingModal({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const { effectiveRole } = useAuth();
  const { smtp_enabled } = useConfig();
  const isAdmin = effectiveRole === "admin";

  return (
    <Modal width={isAdmin ? 760 : 620} title={t("reporting.title")} onClose={onClose}
      footer={<button className="btn btn-secondary" onClick={onClose}>{t("action.close")}</button>}>
      {isAdmin ? (
        <div className="stack" style={{ gap: 12 }}>
          <div className="banner small">{t("reporting.admin_intro")}</div>
          <ReportingAdmin />
        </div>
      ) : (
        <MySchedule smtpOn={smtp_enabled} />
      )}
    </Modal>
  );
}

/** A ready-to-drop button that opens the reporting popup. Hidden when the weekly
 *  report module is off, or when the persona lacks the capability the
 *  subscription endpoints demand (the report carries dashboard/review content),
 *  so the button never opens a modal that the API would refuse. */
export function ReportingButton({ className = "btn-secondary btn-sm" }: { className?: string }) {
  const { t } = useI18n();
  const reportOn = useModule()("review", "weekly_report");
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  if (!reportOn || !can("dashboard")) return null;
  return (
    <>
      <button className={className} onClick={() => setOpen(true)}>{t("reporting.subscribe_btn")}</button>
      {open && <ReportingModal onClose={() => setOpen(false)} />}
    </>
  );
}

/** Personal subscription: pick the days + hour at which the report is emailed. */
function MySchedule({ smtpOn }: { smtpOn: boolean }) {
  const { t } = useI18n();
  const [sub, setSub] = useState<Sub | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api.get<Sub>("/api/reports/subscription").then(setSub).catch(() => setSub({ squad_id: null, interval_days: 0, weekdays: [], hour: 8 }));
  }, []);
  if (!sub) return <Spinner />;

  const on = (sub.weekdays?.length ?? 0) > 0 || sub.interval_days > 0;
  const weekdays = sub.weekdays ?? [];

  async function save(next: Partial<Sub>) {
    const merged = { ...sub, ...next } as Sub;
    setSub(merged);
    setMsg(null);
    try {
      const out = await api.put<Sub>("/api/reports/subscription", {
        squad_id: null, weekdays: merged.weekdays, hour: merged.hour,
      });
      setSub(out);
      setMsg((out.weekdays?.length ?? 0) > 0 ? t("reporting.saved") : t("sub.saved_off"));
    } catch { setMsg(t("changenotify.test_fail")); }
  }

  const toggleDay = (i: number) =>
    save({ weekdays: weekdays.includes(i) ? weekdays.filter((x) => x !== i) : [...weekdays, i].sort() });

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="small muted">{t("reporting.my_hint")}</div>
      {!smtpOn && <div className="banner small">{t("prefs.email_off")}</div>}

      <label className="switch">
        <input type="checkbox" checked={on} onChange={(e) => save(e.target.checked ? { weekdays: [0] } : { weekdays: [] })} />
        <span className="track"><span className="knob" /></span>
        <span className="strong">{t("reporting.send_me")}</span>
      </label>

      {on && (
        <div className="stack" style={{ gap: 16, paddingTop: 2 }}>
          <div>
            <label className="field-label">{t("reporting.days")}</label>
            <div className="day-pick">
              {WEEKDAY_KEYS.map((k, i) => (
                <button type="button" key={i} aria-pressed={weekdays.includes(i)}
                  className={`day-chip${weekdays.includes(i) ? " on" : ""}`}
                  onClick={() => toggleDay(i)}>{t(`reporting.day.${k}`)}</button>
              ))}
            </div>
          </div>
          <div style={{ maxWidth: 200 }}>
            <label className="field-label">{t("reporting.hour")}</label>
            <input type="number" min={0} max={23} value={sub.hour ?? 8} onChange={(e) => save({ hour: Number(e.target.value) })} />
          </div>
        </div>
      )}
      {msg && <div className="small strong" style={{ color: "var(--green)" }}>{msg}</div>}
    </div>
  );
}
