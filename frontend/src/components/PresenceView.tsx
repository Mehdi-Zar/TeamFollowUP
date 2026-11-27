// PresenceView - who is on site and who works remotely (ADR 0021).
// A view of its own in the leaves menu: remote work is not an absence. On top, the
// recap (each working day: how many on site, remote, absent, and who; then each
// squad over the period); below, the grid of the team, one row per person, where
// a click on a day switches it between on site and remote. The usual week of a
// person (their usual remote days) is set from their row. Who may change what is
// decided by the backend (`can_edit` per person).
import { useEffect, useMemo, useState } from "react";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { leaveTypeLabel } from "../leaves";
import { Chip, ErrorBanner, Modal, Spinner } from "./ui";

type Status = "onsite" | "remote" | "leave" | "off";
type Away = { label: string; detail: string | null; color: string; half: boolean; pending: boolean };
type Person = {
  user_id: number; name: string; squad_ids: number[]; can_edit: boolean; weekdays: number[];
  days: Record<string, Status>; changes: Record<string, "remote" | "onsite">; leaves: Record<string, Away>;
};
type Data = { days: string[]; squads: { id: number; name: string }[]; people: Person[] };
type Mode = "week" | "month";

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseISO = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const monday = (d: Date) => addDays(new Date(d.getFullYear(), d.getMonth(), d.getDate()), -((d.getDay() + 6) % 7));
const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri"];
const isWorkday = (s: string) => { const w = parseISO(s).getDay(); return w >= 1 && w <= 5; };

type Counts = { onsite: number; remote: number; leave: number };
const zero = (): Counts => ({ onsite: 0, remote: 0, leave: 0 });

export default function PresenceView() {
  const { t, lang } = useI18n();
  const locale = lang === "en" ? "en-GB" : "fr-FR";
  const [mode, setMode] = useState<Mode>("week");
  const [cursor, setCursor] = useState(() => monday(new Date()));
  const [squadId, setSquadId] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [week, setWeek] = useState<Person | null>(null);
  const [bump, setBump] = useState(0);

  // The period: Monday to Sunday, or the whole month of the cursor.
  const [from, to] = useMemo(() => {
    if (mode === "week") return [cursor, addDays(cursor, 6)];
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    return [first, new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0)];
  }, [mode, cursor.getTime()]);

  useEffect(() => {
    setErr(null);
    const p = new URLSearchParams({ from: iso(from), to: iso(to) });
    if (squadId) p.set("squad_id", squadId);
    api.get<Data>(`/api/presence?${p.toString()}`).then(setData).catch((e) => { setErr(errorText(e)); setData(null); });
  }, [from.getTime(), to.getTime(), squadId, bump]);

  function move(step: number) {
    setPicked(null);
    if (mode === "week") setCursor(addDays(cursor, 7 * step));
    else setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + step, 1));
  }
  function setModeKeep(m: Mode) {
    setMode(m); setPicked(null);
    setCursor(m === "week" ? monday(new Date()) : new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  }

  const people = (data?.people ?? []).filter((p) => !q || p.name.toLowerCase().includes(q.toLowerCase()));
  const workdays = (data?.days ?? []).filter(isWorkday);
  const today = iso(new Date());

  // Each working day: how many on site, remote, absent.
  const perDay = useMemo(() => {
    const m: Record<string, Counts> = {};
    for (const d of workdays) m[d] = zero();
    for (const p of people) for (const d of workdays) {
      const s = p.days[d];
      if (s === "onsite" || s === "remote" || s === "leave") m[d][s] += 1;
    }
    return m;
  }, [data, q]);
  const total = workdays.reduce((acc, d) => {
    acc.onsite += perDay[d].onsite; acc.remote += perDay[d].remote; acc.leave += perDay[d].leave; return acc;
  }, zero());

  // Each squad over the period, in person-days; people without a squad apart.
  const perSquad = useMemo(() => {
    const rows = (data?.squads ?? []).map((s) => ({ id: s.id, name: s.name, people: 0, ...zero() }));
    const none = { id: 0, name: t("presence.no_squad"), people: 0, ...zero() };
    for (const p of people) {
      const targets = p.squad_ids.length ? rows.filter((r) => p.squad_ids.includes(r.id)) : [none];
      for (const r of targets) {
        r.people += 1;
        for (const d of workdays) {
          const s = p.days[d];
          if (s === "onsite" || s === "remote" || s === "leave") r[s] += 1;
        }
      }
    }
    return [...rows, none].filter((r) => r.people > 0);
  }, [data, q, lang]);

  async function flip(p: Person, d: string) {
    const s = p.days[d];
    if (!p.can_edit || (s !== "onsite" && s !== "remote")) return;
    const next = s === "onsite" ? "remote" : "onsite";
    // Shown at once, then confirmed by the server's answer.
    setData((cur) => cur && ({ ...cur, people: cur.people.map((x) => x.user_id !== p.user_id ? x
      : { ...x, days: { ...x.days, [d]: next } }) }));
    try { await api.put(`/api/presence/day/${p.user_id}`, { day: d, location: next }); }
    catch (e) { setErr(errorText(e)); }
    setBump((b) => b + 1);
  }

  const fmtDay = (d: string, long = false) => parseISO(d).toLocaleDateString(locale, long
    ? { weekday: "long", day: "numeric", month: "long" } : { weekday: "short", day: "numeric" });
  const periodLabel = mode === "week"
    ? t("presence.week_of", { d: from.toLocaleDateString(locale, { day: "numeric", month: "long" }) })
    : from.toLocaleDateString(locale, { month: "long", year: "numeric" });
  const pct = (c: Counts) => { const n = c.onsite + c.remote; return n ? Math.round((100 * c.onsite) / n) : 0; };
  const usualText = (p: Person) => p.weekdays.length
    ? p.weekdays.map((w) => t(`reporting.day.${WEEKDAY_KEYS[w]}`)).join(", ") : t("presence.usual_none");

  const pickedDay = picked && perDay[picked] ? picked : null;
  const names = (d: string, s: Status) => people.filter((p) => p.days[d] === s).map((p) => p.name);

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card stack" style={{ gap: 12 }}>
        <div className="between" style={{ alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div className="inline" style={{ gap: 6 }}>
            <button className="btn-secondary btn-sm" aria-label={t("common.prev")} onClick={() => move(-1)}>‹</button>
            <button className="btn-secondary btn-sm" onClick={() => setModeKeep(mode)}>{t(mode === "week" ? "presence.this_week" : "presence.this_month")}</button>
            <button className="btn-secondary btn-sm" aria-label={t("common.next")} onClick={() => move(1)}>›</button>
            <strong style={{ marginLeft: 8, textTransform: mode === "month" ? "capitalize" : undefined }}>{periodLabel}</strong>
          </div>
          <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
            <div className="seg" role="tablist">
              {(["week", "month"] as Mode[]).map((m) => (
                <button key={m} className={mode === m ? "seg-on" : ""} onClick={() => setModeKeep(m)}>{t(`presence.mode.${m}`)}</button>
              ))}
            </div>
            <select aria-label={t("presence.squad")} value={squadId} onChange={(e) => setSquadId(e.target.value)} style={{ width: 200 }}>
              <option value="">{t("presence.all_squads")}</option>
              {(data?.squads ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <input aria-label={t("leaves.search")} placeholder={t("leaves.search")} value={q}
                   onChange={(e) => setQ(e.target.value)} style={{ width: 180 }} />
          </div>
        </div>
        <div className="small muted">{t("presence.intro")}</div>
      </div>

      {err && <ErrorBanner message={err} />}
      {!data ? (!err && <Spinner />) : (
        <>
          {/* The recap: the whole period, then each day, then each squad. */}
          <div className="card stack" style={{ gap: 14 }}>
            <div className="between" style={{ alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
              <h2 style={{ margin: 0 }}>{t("presence.recap")}</h2>
              <span className="small muted">{t("presence.recap_hint", { n: people.length })}</span>
            </div>
            <div className="pr-kpis">
              <Kpi cls="pr-onsite" label={t("presence.onsite")} value={total.onsite} />
              <Kpi cls="pr-remote" label={t("presence.remote")} value={total.remote} />
              <Kpi cls="pr-leave" label={t("presence.absent")} value={total.leave} />
              <Kpi cls="" label={t("presence.share_onsite")} value={`${pct(total)} %`} />
            </div>
            <div className="small muted">{t("presence.person_days")}</div>

            <div className={`pr-days${mode === "month" ? " pr-days-month" : ""}`}>
              {workdays.map((d) => {
                const c = perDay[d]; const n = c.onsite + c.remote + c.leave || 1;
                return (
                  <button key={d} type="button" className={`pr-day${d === today ? " today" : ""}${pickedDay === d ? " on" : ""}`}
                          onClick={() => setPicked(pickedDay === d ? null : d)} aria-pressed={pickedDay === d}>
                    <span className="pr-day-name">{fmtDay(d)}</span>
                    <span className="pr-bar" aria-hidden>
                      <span className="pr-onsite" style={{ width: `${(100 * c.onsite) / n}%` }} />
                      <span className="pr-remote" style={{ width: `${(100 * c.remote) / n}%` }} />
                      <span className="pr-leave" style={{ width: `${(100 * c.leave) / n}%` }} />
                    </span>
                    {mode === "week" ? (
                      <span className="pr-day-nums small">
                        <span>{t("presence.n_onsite", { n: c.onsite })}</span>
                        <span>{t("presence.n_remote", { n: c.remote })}</span>
                        {c.leave > 0 && <span>{t("presence.n_absent", { n: c.leave })}</span>}
                      </span>
                    ) : <span className="pr-day-nums small">{c.onsite}/{c.remote}/{c.leave}</span>}
                  </button>
                );
              })}
            </div>
            {mode === "month" && <div className="small muted">{t("presence.month_nums")}</div>}
            {pickedDay ? (
              <div className="pr-who">
                <div className="strong" style={{ textTransform: "capitalize" }}>{fmtDay(pickedDay, true)}</div>
                {(["onsite", "remote", "leave"] as Status[]).map((s) => (
                  <div key={s} className="pr-who-row">
                    <span className={`pr-tag pr-${s}`}>{t(s === "leave" ? "presence.absent" : `presence.${s}`)}</span>
                    <span className="small">{names(pickedDay, s).join(", ") || "-"}</span>
                  </div>
                ))}
              </div>
            ) : <div className="small muted">{t("presence.pick_day")}</div>}

            {perSquad.length > 0 && (
              <table>
                <thead><tr>
                  <th>{t("presence.squad")}</th><th>{t("presence.people")}</th>
                  <th>{t("presence.onsite")}</th><th>{t("presence.remote")}</th><th>{t("presence.absent")}</th>
                  <th>{t("presence.share_onsite")}</th>
                </tr></thead>
                <tbody>
                  {perSquad.map((r) => (
                    <tr key={r.id}>
                      <td><strong>{r.name}</strong></td><td>{r.people}</td>
                      <td>{r.onsite}</td><td>{r.remote}</td><td>{r.leave}</td>
                      <td><span className="pr-share"><span className="pr-bar" aria-hidden>
                        <span className="pr-onsite" style={{ width: `${pct(r)}%` }} />
                        <span className="pr-remote" style={{ width: `${100 - pct(r)}%` }} />
                      </span>{pct(r)} %</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* The grid: one row per person, one column per working day. */}
          <div className="card stack" style={{ gap: 10 }}>
            <div className="between" style={{ alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
              <h2 style={{ margin: 0 }}>{t("presence.team")}</h2>
              <span className="inline small" style={{ gap: 12, flexWrap: "wrap" }}>
                <span className="pr-tag pr-onsite">{t("presence.onsite")}</span>
                <span className="pr-tag pr-remote">{t("presence.remote")}</span>
                <span className="pr-tag pr-leave">{t("presence.absent")}</span>
                <span className="muted">{t("presence.changed_hint")}</span>
              </span>
            </div>
            <div className="small muted">{t("presence.click_hint")}</div>
            {people.length === 0 ? <div className="small muted">{t("presence.none")}</div> : (
              <div style={{ overflowX: "auto" }}>
                <table className={`pr-grid${mode === "month" ? " pr-grid-month" : ""}`}>
                  <thead><tr>
                    <th>{t("leaves.person")}</th>
                    {workdays.map((d) => <th key={d} className={d === today ? "today" : ""}>
                      {mode === "week" ? fmtDay(d) : parseISO(d).getDate()}</th>)}
                    <th title={t("presence.remote_days")}>{t("presence.remote_short")}</th>
                  </tr></thead>
                  <tbody>
                    {people.map((p) => (
                      <tr key={p.user_id}>
                        <td className="pr-person">
                          <strong>{p.name}</strong>
                          <div className="small muted">
                            {t("presence.usual_is", { d: usualText(p) })}
                            {p.can_edit && <button type="button" className="btn-link small" style={{ marginLeft: 8 }} onClick={() => setWeek(p)}>{t("action.edit")}</button>}
                          </div>
                        </td>
                        {workdays.map((d) => {
                          const s = p.days[d]; const lv = p.leaves[d];
                          const text = s === "leave" && lv ? leaveTypeLabel(lv.label, lang) + (lv.half ? " ½" : "")
                            : t(`presence.${s}`);
                          const can = p.can_edit && (s === "onsite" || s === "remote");
                          return (
                            <td key={d} className={d === today ? "today" : ""}>
                              <button type="button" disabled={!can}
                                className={`pr-cell pr-${s}${p.changes[d] ? " changed" : ""}`}
                                style={s === "leave" && lv ? { borderColor: lv.color, color: lv.color } : undefined}
                                title={`${p.name}, ${fmtDay(d, true)} : ${text}${can ? ". " + t("presence.click_one") : ""}`}
                                onClick={() => flip(p, d)}>
                                {mode === "week" ? text : ""}
                              </button>
                            </td>
                          );
                        })}
                        <td className="small strong">{workdays.filter((d) => p.days[d] === "remote").length}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {week && <WeekModal person={week} onClose={() => setWeek(null)}
                          onSaved={() => { setWeek(null); setBump((b) => b + 1); }} />}
    </div>
  );
}

function Kpi({ cls, label, value }: { cls: string; label: string; value: number | string }) {
  return (
    <div className="pr-kpi">
      <span className={`pr-kpi-dot ${cls}`} aria-hidden />
      <span className="pr-kpi-v">{value}</span>
      <span className="small muted">{label}</span>
    </div>
  );
}

/** The usual week of one person: the weekdays they usually work remotely. */
function WeekModal({ person, onClose, onSaved }: { person: Person; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [days, setDays] = useState<number[]>(person.weekdays);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const toggle = (w: number) => setDays((c) => (c.includes(w) ? c.filter((x) => x !== w) : [...c, w].sort()));
  async function save() {
    setBusy(true); setErr(null);
    try { await api.put(`/api/presence/week/${person.user_id}`, { weekdays: days }); onSaved(); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }
  return (
    <Modal title={t("presence.week_title", { name: person.name })} onClose={onClose} width={480}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
        <button className="btn" disabled={busy} onClick={save}>{busy ? t("common.saving") : t("action.save")}</button>
      </>}>
      <div className="stack" style={{ gap: 12 }}>
        <div className="small muted">{t("presence.week_hint")}</div>
        <div className="chips">
          {WEEKDAY_KEYS.map((k, w) => (
            <Chip key={k} on={days.includes(w)} onToggle={() => toggle(w)}>{t(`reporting.day.${k}`)}</Chip>
          ))}
        </div>
        <div className="small">{days.length
          ? t("presence.week_sum", { n: days.length, m: 5 - days.length })
          : t("presence.usual_none")}</div>
        {err && <div className="banner banner-red small">{err}</div>}
      </div>
    </Modal>
  );
}

