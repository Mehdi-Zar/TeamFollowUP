import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useConfig } from "../config";
import { Preferences } from "../types";
import { Spinner } from "../components/ui";

export default function PreferencesPage() {
  const { t } = useI18n();
  const { smtp_enabled } = useConfig();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get<Preferences>("/api/me/preferences").then(setPrefs);
  }, []);
  if (!prefs) return <Spinner />;

  async function update(patch: Partial<Preferences>) {
    const next = { ...prefs, ...patch } as Preferences;
    setPrefs(next);
    await api.put("/api/me/preferences", patch);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  }

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
        <Toggle checked={prefs.notify_tweets} label={t("prefs.tweets")} onChange={(v: boolean) => update({ notify_tweets: v })} />
        <Toggle checked={prefs.notify_replies} label={t("prefs.replies")} onChange={(v: boolean) => update({ notify_replies: v })} />
        <div style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
          <Toggle checked={prefs.email_notifications} disabled={!smtp_enabled} label={t("prefs.email")} onChange={(v: boolean) => update({ email_notifications: v })} />
          {!smtp_enabled && <div className="small muted" style={{ marginTop: 6 }}>{t("prefs.email_off")}</div>}
        </div>
        <div style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
          <Toggle checked={prefs.subscribe_weekly_report} disabled={!smtp_enabled} label={t("prefs.weekly_report")} onChange={(v: boolean) => update({ subscribe_weekly_report: v })} />
          <div className="small muted" style={{ marginTop: 6 }}>{!smtp_enabled ? t("prefs.email_off") : t("prefs.weekly_report_hint")}</div>
        </div>
        {saved && <div className="small" style={{ color: "var(--green)" }}>{t("prefs.saved")}</div>}
      </div>
    </div>
  );
}
