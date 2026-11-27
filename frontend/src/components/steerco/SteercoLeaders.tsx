// Steerco > Parametres, sections "Qui mene le Steerco" and "Les mails".
//
// The tribe leader is a Steerco leader by default; the administrator and the tribe
// leader designate others (any role, a squad leader for instance). A Steerco leader
// cannot designate anyone, and only the administrator may withdraw a tribe leader's
// default designation. The monthly reminder and the pack's recipients are set here
// too: they are the Steerco leaders' business.
import { useEffect, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { ErrorBanner, Spinner } from "../ui";

type Leader = { user_id: number; display_name: string; email: string; role: string; by_default: boolean; active: boolean };
type LeadersOut = { tribe_id: number; leaders: Leader[]; can_designate: boolean; can_exclude_default: boolean };
type Person = { id: number; name: string; email: string | null; tribe_id: number | null };
type MailCfg = { reminder_enabled: boolean; reminder_day: number; recipients: string[]; last_reminder: string | null };

export function LeadersSection({ tribeId, onChanged }: { tribeId: number; onChanged?: () => void }) {
  const { t, role } = useI18n();
  const [data, setData] = useState<LeadersOut | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [pick, setPick] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const update = (d: LeadersOut) => { setData(d); onChanged?.(); };

  useEffect(() => {
    setData(null); setErr(null);
    api.get<LeadersOut>(`/api/steerco/leaders?tribe_id=${tribeId}`).then(setData).catch((e) => setErr(errorText(e)));
    api.get<Person[]>("/api/tribes/people").then((ps) => setPeople(ps.filter((p) => p.tribe_id === tribeId))).catch(() => {});
  }, [tribeId]);

  async function add() {
    if (!pick) return;
    setBusy(true); setErr(null);
    try {
      update(await api.post<LeadersOut>("/api/steerco/leaders", { tribe_id: tribeId, user_id: Number(pick) }));
      setPick("");
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }
  async function remove(l: Leader) {
    const msg = l.by_default ? t("steerco.leaders.exclude_confirm", { name: l.display_name })
      : t("steerco.leaders.remove_confirm", { name: l.display_name });
    if (!window.confirm(msg)) return;
    setBusy(true); setErr(null);
    try { update(await api.del<LeadersOut>(`/api/steerco/leaders/${l.user_id}?tribe_id=${tribeId}`)); }
    catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }
  // Giving a tribe leader their default designation back is the same call as adding.
  async function restore(l: Leader) {
    setBusy(true); setErr(null);
    try { update(await api.post<LeadersOut>("/api/steerco/leaders", { tribe_id: tribeId, user_id: l.user_id })); }
    catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  const taken = new Set((data?.leaders ?? []).filter((l) => l.active).map((l) => l.user_id));
  const candidates = people.filter((p) => !taken.has(p.id));

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="stack" style={{ gap: 12 }}>
        <div className="small muted">{t("steerco.leaders.hint")}</div>
        {err && <ErrorBanner message={err} />}
        {data === null ? (!err && <Spinner />) : (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("steerco.leaders.name")}</th>
                  <th>{t("steerco.leaders.role")}</th>
                  <th>{t("steerco.leaders.how")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.leaders.length === 0 && (
                  <tr><td colSpan={4} className="small muted">{t("steerco.leaders.none")}</td></tr>
                )}
                {data.leaders.map((l) => (
                  <tr key={l.user_id} style={l.active ? undefined : { opacity: 0.6 }}>
                    <td className="strong">{l.display_name}</td>
                    <td className="small">{role(l.role as any)}</td>
                    <td>
                      {l.by_default
                        ? <span className={`badge ${l.active ? "badge-navy" : "badge-grey"}`}>
                            {l.active ? t("steerco.leaders.by_default") : t("steerco.leaders.excluded")}
                          </span>
                        : <span className="badge badge-green">{t("steerco.leaders.designated")}</span>}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {l.by_default ? (
                        data.can_exclude_default && (l.active
                          ? <button className="btn-ghost btn-sm" disabled={busy} onClick={() => remove(l)}>{t("steerco.leaders.exclude")}</button>
                          : <button className="btn-secondary btn-sm" disabled={busy} onClick={() => restore(l)}>{t("steerco.leaders.restore")}</button>)
                      ) : (
                        data.can_designate && <button className="btn-ghost btn-sm" disabled={busy} onClick={() => remove(l)}>{t("action.remove")}</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.can_designate ? (
              <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                <select aria-label={t("steerco.leaders.pick")} value={pick} onChange={(e) => setPick(e.target.value)} style={{ minWidth: 240 }}>
                  <option value="">{t("steerco.leaders.pick")}</option>
                  {candidates.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <button className="btn-sm" disabled={!pick || busy} onClick={add}>{t("steerco.leaders.add")}</button>
              </div>
            ) : (
              <div className="small muted">{t("steerco.leaders.only_tl")}</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** The monthly reminder (day, on or off) and the recipients of the pack. */
export function MailSettings({ tribeId, onSaved }: { tribeId: number; onSaved?: () => void }) {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<MailCfg | null>(null);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setCfg(null); setErr(null); setMsg(null);
    api.get<MailCfg>(`/api/steerco/mail?tribe_id=${tribeId}`)
      .then((c) => { setCfg(c); setText((c.recipients ?? []).join("\n")); })
      .catch((e) => setErr(errorText(e)));
  }, [tribeId]);

  async function save() {
    if (!cfg) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      const recipients = text.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
      const c = await api.put<MailCfg>(`/api/steerco/mail?tribe_id=${tribeId}`, {
        reminder_enabled: cfg.reminder_enabled, reminder_day: cfg.reminder_day, recipients,
      });
      setCfg(c); setText(c.recipients.join("\n")); setMsg(t("admin.saved"));
      onSaved?.();
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="small muted">{t("steerco.mail.hint")}</div>
      {err && <ErrorBanner message={err} />}
      {cfg === null ? (!err && <Spinner />) : (
        <>
          <div className="inline" style={{ gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <label className="switch" style={{ fontWeight: 400, fontSize: 13 }}>
              <input type="checkbox" checked={cfg.reminder_enabled}
                     onChange={(e) => setCfg({ ...cfg, reminder_enabled: e.target.checked })} />
              <span className="track"><span className="knob" /></span>
              <span>{t("steerco.mail.reminder")}</span>
            </label>
            <label className="inline small" style={{ gap: 6 }}>
              {t("steerco.mail.day")}
              <input type="number" min={1} max={28} value={cfg.reminder_day} style={{ width: 70 }}
                     disabled={!cfg.reminder_enabled}
                     onChange={(e) => setCfg({ ...cfg, reminder_day: Math.min(28, Math.max(1, Number(e.target.value) || 1)) })} />
            </label>
          </div>
          <div className="small muted">{t("steerco.mail.reminder_hint", { day: cfg.reminder_day })}</div>
          <div>
            <label htmlFor="sc-recipients">{t("steerco.mail.recipients")}</label>
            <textarea id="sc-recipients" rows={4} value={text} onChange={(e) => setText(e.target.value)}
                      placeholder="comite@example.com" />
            <div className="small muted">{t("steerco.mail.recipients_hint")}</div>
          </div>
          <div className="inline" style={{ gap: 10 }}>
            <button className="btn-sm" disabled={busy} onClick={save}>{t("action.save")}</button>
            {msg && <span className="small" style={{ color: "var(--green)" }}>{msg}</span>}
          </div>
        </>
      )}
    </div>
  );
}
