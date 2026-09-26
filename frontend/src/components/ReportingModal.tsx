// ReportingModal: the "Subscribe to a report" popup opened from the dashboard.
// It adapts to the persona: admins get the org-wide reporting configuration
// (ReportingAdmin), everyone else manages their personal delivery schedule
// (which weekdays + hour to receive the weekly report by email).
import { useEffect, useState } from "react";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { useConfig, useModule } from "../config";
import { Modal, Spinner } from "./ui";
import { Link } from "react-router-dom";

// Shape of a user's report subscription. `weekdays` are 0=Mon..6=Sun; an empty
// list (or interval_days 0) means the subscription is off.

type Sub = { squad_id: number | null; interval_days: number; weekdays: number[]; hour: number };
const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/** "Subscribe to a report" popup, opened from the dashboard (and anywhere else).
 *  No dedicated tab: the general/org configuration lives in Administration, and
 *  this window adapts to the persona - admins get the full config, everyone else
 *  gets their personal subscription (which days + hour to receive the report). */
export function ReportingModal({ onClose, squadId }: { onClose: () => void; squadId?: number }) {
  const { t } = useI18n();
  const { adminTabs } = useAuth();
  const { smtp_enabled } = useConfig();
  // Everyone manages their own subscription here, the admin included; whoever
  // holds the "Weekly report" tab also gets the way to the organisation's sending.
  const canConfigure = adminTabs.includes("report");
  // The two blocks show the same subscription: a change in one reloads the other
  // (a remount through its key), else the list and the switch disagreed.
  const [schedKey, setSchedKey] = useState(0);
  const [subsKey, setSubsKey] = useState(0);

  return (
    <Modal width={620} title={t("reporting.title")} onClose={onClose}
      footer={<button className="btn btn-secondary" onClick={onClose}>{t("action.close")}</button>}>
      <div className="stack" style={{ gap: 16 }}>
        <MySchedule key={schedKey} smtpOn={smtp_enabled} initialSquadId={squadId ?? null}
                    onSaved={() => setSubsKey((k) => k + 1)} />
        <MySubscriptions key={subsKey} onChanged={() => setSchedKey((k) => k + 1)} />
        {canConfigure && (
          <div className="small" style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <Link to="/admin?section=report" onClick={onClose}>{t("reporting.configure_org")}</Link>
          </div>
        )}
      </div>
    </Modal>
  );
}

/** A ready-to-drop button that opens the reporting popup. Hidden when the weekly
 *  report module is off, or when the persona lacks the capability the
 *  subscription endpoints demand (the report carries dashboard/review content),
 *  so the button never opens a modal that the API would refuse. */
export function ReportingButton({ className = "btn-secondary btn-sm", squadId }: { className?: string; squadId?: number }) {
  const { t } = useI18n();
  const reportOn = useModule()("review", "weekly_report");
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  if (!reportOn || !can("dashboard")) return null;
  return (
    <>
      <button className={className} onClick={() => setOpen(true)}>{t("reporting.subscribe_btn")}</button>
      {open && <ReportingModal squadId={squadId} onClose={() => setOpen(false)} />}
    </>
  );
}

/** Everything the application emails this person, listed.
 *
 *  The schedule above only covers the dashboard report. A per-squad subscription
 *  could exist (set by an API key, or by an earlier version) and the person had no
 *  way to see it, let alone stop it: the endpoint that lists them was served and
 *  never called. Being emailed by a system is exactly the kind of thing one should
 *  be able to enumerate. */
function MySubscriptions({ onChanged }: { onChanged?: () => void }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<Sub[] | null>(null);
  const [squads, setSquads] = useState<Record<number, string>>({});
  const [stopErr, setStopErr] = useState<string | null>(null);

  async function load() {
    try {
      const subs = await api.get<Sub[]>("/api/reports/subscriptions");
      setRows(subs);
      if (subs.some((s) => s.squad_id)) {
        const list = await api.get<{ id: number; name: string }[]>("/api/squads");
        setSquads(Object.fromEntries(list.map((s) => [s.id, s.name])));
      }
    } catch { setRows([]); }
  }
  useEffect(() => { load(); }, []);

  const active = (rows ?? []).filter((s) => (s.weekdays?.length ?? 0) > 0 || s.interval_days > 0);
  if (rows === null) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="strong">{t("reporting.my_subscriptions")}</div>
      {active.length === 0 ? (
        <div className="small muted">{t("reporting.no_subscription")}</div>
      ) : active.map((s, i) => (
        <div key={i} className="between small" style={{ borderBottom: "1px solid var(--line)", paddingBottom: 4 }}>
          <span>
            {s.squad_id ? (squads[s.squad_id] ?? `#${s.squad_id}`) : t("reporting.scope_dashboard")}
            {t("common.colon")}
            {(s.weekdays?.length ?? 0) > 0
              ? s.weekdays.map((d) => t(`reporting.day.${WEEKDAY_KEYS[d]}`)).join(", ")
              : t("reporting.every_n_days", { n: String(s.interval_days) })}
            {`, ${String(s.hour).padStart(2, "0")}h`}
          </span>
          <button className="btn-ghost btn-sm"
                  onClick={async () => {
                    setStopErr(null);
                    try {
                      await api.put("/api/reports/subscription",
                                    { squad_id: s.squad_id, weekdays: [], hour: s.hour });
                    } catch (e) {
                      // Said, not swallowed: the line staying in the list read as a
                      // click that did nothing.
                      setStopErr(e instanceof Error && e.message ? e.message : t("reporting.save_failed"));
                    }
                    load();
                    onChanged?.();
                  }}>
            {t("reporting.stop")}
          </button>
        </div>
      ))}
      {stopErr && <div className="small" style={{ color: "var(--red)" }}>{stopErr}</div>}
    </div>
  );
}

/** Personal subscription: pick the days + hour at which the report is emailed. */
function MySchedule({ smtpOn, onSaved, initialSquadId = null }: {
  smtpOn: boolean; onSaved?: () => void; initialSquadId?: number | null;
}) {
  const { t } = useI18n();
  const [sub, setSub] = useState<Sub | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  // What the mail covers: the whole dashboard, or one squad. A per-squad
  // subscription was listed below but nothing let anyone create one.
  const [scope, setScope] = useState<number | null>(initialSquadId);
  const [squads, setSquads] = useState<{ id: number; name: string }[]>([]);
  useEffect(() => { api.get<{ id: number; name: string }[]>("/api/squads").then(setSquads).catch(() => {}); }, []);

  // A failed load is said, with a retry: showing "off" instead would let one
  // click replace the real subscription.
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [loadTick, setLoadTick] = useState(0);
  useEffect(() => {
    setSub(null); setLoadErr(null);
    const q = scope == null ? "" : `?squad_id=${scope}`;
    api.get<Sub>(`/api/reports/subscription${q}`).then(setSub).catch((e) => setLoadErr(errorText(e)));
  }, [scope, loadTick]);
  if (loadErr) return (
    <div className="banner banner-red between" role="alert" style={{ alignItems: "center" }}>
      <span>{loadErr}</span>
      <button className="btn-secondary btn-sm" onClick={() => setLoadTick((n) => n + 1)}>{t("common.retry")}</button>
    </div>
  );
  if (!sub) return <Spinner />;

  const on = (sub.weekdays?.length ?? 0) > 0 || sub.interval_days > 0;
  const weekdays = sub.weekdays ?? [];

  async function save(next: Partial<Sub>) {
    const before = sub;
    const merged = { ...sub, ...next } as Sub;
    setSub(merged);
    setMsg(null); setFailed(false);
    try {
      const out = await api.put<Sub>("/api/reports/subscription", {
        squad_id: scope, weekdays: merged.weekdays, hour: merged.hour,
      });
      setSub(out);
      setMsg((out.weekdays?.length ?? 0) > 0 ? t("reporting.saved") : t("sub.saved_off"));
      onSaved?.();
    } catch (e) {
      // Back to what the server still holds, and said in red: the switch used to
      // stay on, with a green "sending failed, check the configuration".
      setSub(before);
      setFailed(true);
      setMsg(e instanceof Error && e.message ? e.message : t("reporting.save_failed"));
    }
  }

  const toggleDay = (i: number) =>
    save({ weekdays: weekdays.includes(i) ? weekdays.filter((x) => x !== i) : [...weekdays, i].sort() });

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="small muted">{t("reporting.my_hint")}</div>
      {!smtpOn && <div className="banner small">{t("prefs.email_off")}</div>}
      <div style={{ maxWidth: 320 }}>
        <label className="field-label" htmlFor="sub-scope">{t("reporting.scope")}</label>
        <select id="sub-scope" value={scope ?? ""} onChange={(e) => setScope(e.target.value ? Number(e.target.value) : null)}>
          <option value="">{t("reporting.scope_dashboard")}</option>
          {squads.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>

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
      {msg && <div className="small strong" style={{ color: failed ? "var(--red)" : "var(--green)" }}>{msg}</div>}
    </div>
  );
}
