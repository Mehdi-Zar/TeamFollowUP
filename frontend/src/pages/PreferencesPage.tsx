// PreferencesPage - the current user's personal notification settings.
// Each toggle maps to a field on the user's Preferences and is persisted
// immediately (optimistic update + PUT). Email-related toggles only appear when
// the relevant module is enabled, and are disabled when SMTP is not configured
// server-side (you can't receive email the platform can't send).
import { useEffect, useState } from "react";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { Preferences } from "../types";
import { Spinner } from "../components/ui";
import { ReportingButton } from "../components/ReportingModal";

/**
 * "My preferences" page. Renders a small set of notification switches bound to
 * the authenticated user's Preferences record.
 *
 * Business logic:
 * - Loads `/api/me/preferences` on mount; shows a spinner until it resolves.
 * - `update()` applies the change optimistically to local state, PUTs the patch,
 *   then flashes a transient "saved" confirmation for ~1.8s.
 * - Email notifications / weekly report rows are gated by their module flags
 *   (`notifications.email`, `review.weekly_report`) AND require SMTP to be
 *   enabled - otherwise the switch is shown disabled with an explanatory hint.
 *
 * Access: any authenticated user (self-scoped, no special capability).
 */
export default function PreferencesPage() {
  const { t } = useI18n();
  const { smtp_enabled } = useConfig();
  const moduleOn = useModule();
  const emailNotifOn = moduleOn("notifications", "email");
  const weeklyReportOn = moduleOn("review", "weekly_report");
  // The feed's notifications only mean something while the feed is on.
  const feedOn = moduleOn("feed");
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<Preferences>("/api/me/preferences").then(setPrefs).catch((e) => setErr(errorText(e)));
  }, []);
  if (!prefs && err) return <div className="error-text">{err}</div>;
  if (!prefs) return <Spinner />;

  // Optimistically merge the patch into local state, persist it, then briefly
  // show the "saved" indicator. A refusal puts the switch back and says why.
  async function update(patch: Partial<Preferences>) {
    const before = prefs;
    setPrefs({ ...prefs, ...patch } as Preferences);
    setErr(null);
    try {
      await api.put("/api/me/preferences", patch);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      setPrefs(before);
      setErr(e instanceof Error && e.message ? e.message : t("common.error"));
    }
  }
  const mailing = emailNotifOn || weeklyReportOn;

  /** Small controlled switch used for every preference row (label + toggle). */
  const Toggle = ({ checked, onChange, label, disabled }: any) => (
    <label className="switch" style={{ opacity: disabled ? 0.5 : 1 }}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="track"><span className="knob" /></span>
      <span>{label}</span>
    </label>
  );

  return (
    <div className="stack" style={{ gap: 16, maxWidth: 560 }}>
      <div className="card stack" style={{ gap: 14 }}>
        <h3 style={{ margin: 0 }}>{t("prefs.notifs")}</h3>
        {/* Said once, above everything it concerns. */}
        {mailing && !smtp_enabled && <div className="banner small">{t("prefs.email_off")}</div>}
        {feedOn && <>
          <Toggle checked={prefs.notify_tweets} label={t("prefs.tweets")} onChange={(v: boolean) => update({ notify_tweets: v })} />
          <Toggle checked={prefs.notify_replies} label={t("prefs.replies")} onChange={(v: boolean) => update({ notify_replies: v })} />
        </>}
        {!feedOn && !mailing && <div className="small muted">{t("prefs.nothing")}</div>}
        {emailNotifOn && feedOn && (
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
            <Toggle checked={prefs.email_notifications} disabled={!smtp_enabled} label={t("prefs.email")} onChange={(v: boolean) => update({ email_notifications: v })} />
          </div>
        )}
        {weeklyReportOn && (
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
            {/* One place to choose what is mailed and when: the subscription window.
                A switch here set "every 7 days" and overwrote the days chosen there. */}
            <div className="between" style={{ alignItems: "center", gap: 10 }}>
              <span>{t("prefs.weekly_report")}</span>
              <ReportingButton />
            </div>
            {smtp_enabled && <div className="small muted" style={{ marginTop: 6 }}>{t("prefs.weekly_report_hint")}</div>}
          </div>
        )}
        {saved && <div className="small" style={{ color: "var(--green)" }}>{t("prefs.saved")}</div>}
        {err && <div className="small" style={{ color: "var(--red)" }}>{err}</div>}
      </div>
    </div>
  );
}
