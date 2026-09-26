/**
 * Administration > Configuration: modules, weekly report, leave, general settings.
 *
 * What the product DOES, as opposed to who is in it. ReportingAdmin is also
 * mounted outside this screen, by the reporting modal, which is why it is
 * exported rather than local.
 */
import { useEffect, useState } from "react";
import { api } from "../../api";
import { useI18n } from "../../i18n";
import { useReloadConfig } from "../../config";
import { useAuth } from "../../auth";
import { LeaveConfig, LeaveType, ModuleKey, Permissions, Squad, Tribe } from "../../types";
import { ErrorBanner } from "../../components/ui";

import { useErr, useLoadState } from "./shared";

export const MODULE_TREE: { key: ModuleKey; features: string[] }[] = [
  { key: "dashboard", features: [] },
  { key: "org", features: [] },
  { key: "reporting", features: [] },
  { key: "feed", features: ["reactions", "replies", "pin", "kinds"] },
  { key: "review", features: ["weekly_report"] },
  { key: "squad_content", features: ["roadmap", "kpis", "quarter_progress"] },  // objectives retired
  { key: "committees", features: [] },
  { key: "steerco", features: [] },
  { key: "notifications", features: ["inapp", "email"] },
  { key: "getting_started", features: [] },
  { key: "leaves", features: ["overlap_alert"] },
];


/** Admin > Modules: master on/off switches for each app module and its sub-features
 *  (from MODULE_TREE). Saving reloads the global config so the UI reflects the
 *  change immediately (nav, gated sections). Admin only. */
export function ModulesAdmin() {
  const { t } = useI18n();
  const reloadConfig = useReloadConfig();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  const ls = useLoadState();
  const loadCfg = () => { api.get<any>("/api/admin/modules-config").then(setCfg).catch(ls.fail); };
  useEffect(loadCfg, []);
  if (!cfg) return ls.waiting(loadCfg);

  async function apply(next: any) {
    // Shown switched at once; put back if the server refuses.
    const before = cfg;
    setCfg(next);
    const ok = await wrap(async () => {
      const out = await api.put<any>("/api/admin/modules-config", next);
      setCfg(out);
      reloadConfig();
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
      return true;
    });
    if (!ok) setCfg(before);
  }
  const setModule = (key: string, enabled: boolean) => apply({ ...cfg, [key]: { ...cfg[key], enabled } });
  const setFeature = (key: string, feat: string, val: boolean) =>
    apply({ ...cfg, [key]: { ...cfg[key], [feat]: val } });

  const Switch = ({ checked, onChange, label, strong }: any) => (
    <label className="switch">
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track"><span className="knob" /></span>
      <span className={strong ? "strong" : "small"}>{label}</span>
    </label>
  );

  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      {error && <ErrorBanner message={error} />}
      <div className="banner">{t("modules.intro")}</div>
      <div className="stack" style={{ gap: 12 }}>
        {MODULE_TREE.map(({ key, features }) => {
          const mod = cfg[key] || {};
          const on = mod.enabled !== false;
          return (
            <div key={key} className="card stack" style={{ gap: 10, opacity: on ? 1 : 0.7 }}>
              <div className="between">
                <Switch checked={on} strong label={t(`mod.${key}`)} onChange={(v: boolean) => setModule(key, v)} />
                {!on && <span className="badge badge-red">{t("modules.off")}</span>}
              </div>
              {features.length > 0 && (
                <div className="small muted">{t(`mod.${key}.desc`)}</div>
              )}
              {features.length > 0 && on && (
                <div className="stack" style={{ gap: 8, paddingLeft: 14, borderLeft: "2px solid var(--line)" }}>
                  {features.map((f) => (
                    <Switch key={f} checked={mod[f] !== false} label={t(`mod.${key}.${f}`)}
                            onChange={(v: boolean) => setFeature(key, f, v)} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {saved && <div className="small" style={{ color: "var(--green)" }}>{t("admin.saved")}</div>}
    </div>
  );
}


/* ---------- Leave / absence administration ---------- */
/** Admin > Leaves: settings section (approval + overlap threshold) for everyone
 *  who can open it; the leave-type catalogue is admin-only. */
export function LeavesAdmin({ perms }: { perms: Permissions }) {
  const isAdmin = perms.role === "admin";
  return (
    <div className="stack" style={{ gap: 20, maxWidth: 760 }}>
      <LeaveSettingsAdmin isAdmin={isAdmin} />
      {isAdmin && <LeaveTypesAdmin />}
    </div>
  );
}


/** Leave settings (approval required, overlap alert threshold). For an admin the
 *  config is per-tribe (with a tribe picker); a tribe leader edits their own. */
export function LeaveSettingsAdmin({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useI18n();
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeId, setTribeId] = useState<number | "">("");
  const [cfg, setCfg] = useState<LeaveConfig | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  useEffect(() => {
    if (isAdmin) {
      api.get<Tribe[]>("/api/tribes").then((ts) => { setTribes(ts); if (ts[0]) setTribeId(ts[0].id); }).catch(() => {});
    } else {
      wrap(async () => setCfg(await api.get<LeaveConfig>("/api/leaves/config")));
    }
  }, [isAdmin]);
  useEffect(() => {
    if (isAdmin && tribeId !== "") api.get<LeaveConfig>(`/api/leaves/config?tribe_id=${tribeId}`).then(setCfg).catch(() => setCfg(null));
  }, [isAdmin, tribeId]);

  async function save() {
    if (!cfg) return;
    const qs = isAdmin && tribeId !== "" ? `?tribe_id=${tribeId}` : "";
    await wrap(async () => {
      const out = await api.put<LeaveConfig>(`/api/leaves/config${qs}`,
        { require_approval: cfg.require_approval, overlap_threshold: cfg.overlap_threshold });
      setCfg(out); setSaved(true); setTimeout(() => setSaved(false), 1500);
    });
  }

  return (
    <div className="card stack" style={{ gap: 14 }}>
      <h2 style={{ margin: 0 }}>{t("leaves.admin_settings")}</h2>
      {error && <ErrorBanner message={error} />}
      {isAdmin && (
        <div style={{ maxWidth: 300 }}>
          <label className="field-label">{t("leaves.tribe_pick")}</label>
          <select aria-label={t("leaves.tribe_pick")} value={tribeId} onChange={(e) => setTribeId(Number(e.target.value))}>
            {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
          </select>
        </div>
      )}
      {cfg && (
        <>
          <label className="switch">
            <input type="checkbox" checked={cfg.require_approval}
                   onChange={(e) => setCfg({ ...cfg, require_approval: e.target.checked })} />
            <span className="track"><span className="knob" /></span>
            <span className="strong">{t("leaves.require_approval")}</span>
          </label>
          <div style={{ maxWidth: 300 }}>
            <label className="field-label">{t("leaves.overlap_threshold")}</label>
            <input aria-label={t("leaves.overlap_threshold")} type="number" min={1} max={99} value={cfg.overlap_threshold}
                   onChange={(e) => setCfg({ ...cfg, overlap_threshold: Number(e.target.value) })} />
          </div>
          <div className="inline">
            <button onClick={save}>{t("action.save")}</button>
            {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
          </div>
        </>
      )}
    </div>
  );
}


/** Admin-only catalogue of leave types (label, colour, order, active, whether a
 *  detail note is required). Edits are per-row; delete is confirmed. */
export function LeaveTypesAdmin() {
  const { t } = useI18n();
  const [types, setTypes] = useState<LeaveType[]>([]);
  const { error, wrap } = useErr();
  const load = () => api.get<LeaveType[]>("/api/leaves/types?include_inactive=true").then(setTypes).catch(() => {});
  useEffect(() => { load(); }, []);

  const upd = (id: number, patch: Partial<LeaveType>) =>
    setTypes((ts) => ts.map((x) => (x.id === id ? { ...x, ...patch } : x)));

  async function addType() {
    await wrap(async () => {
      await api.post("/api/leaves/types", { label: t("leaves.add_type"), color: "#6B7280", display_order: types.length + 1 });
      load();
    });
  }
  async function saveType(tp: LeaveType) {
    await wrap(async () => {
      await api.put(`/api/leaves/types/${tp.id}`,
        { label: tp.label, color: tp.color, display_order: tp.display_order, is_active: tp.is_active, requires_detail: tp.requires_detail });
      load();
    });
  }
  async function delType(id: number) {
    if (!confirm(t("leaves.delete_confirm"))) return;
    await wrap(async () => { await api.del(`/api/leaves/types/${id}`); load(); });
  }

  return (
    <div className="card stack" style={{ gap: 12 }}>
      <div className="between">
        <h2 style={{ margin: 0 }}>{t("leaves.admin_types")}</h2>
        <button className="btn-secondary btn-sm" onClick={addType}>+ {t("leaves.add_type")}</button>
      </div>
      {error && <ErrorBanner message={error} />}
      <div className="stack" style={{ gap: 8 }}>
        {types.map((tp) => (
          <div key={tp.id} className="inline" style={{ gap: 8, opacity: tp.is_active ? 1 : 0.6 }}>
            <input type="color" value={tp.color} onChange={(e) => upd(tp.id, { color: e.target.value })}
                   style={{ width: 44, height: 38, padding: 2 }} aria-label={t("leaves.type_color")} />
            <input aria-label={t("a11y.leave_type_label")} value={tp.label} onChange={(e) => upd(tp.id, { label: e.target.value })} style={{ flex: 1 }} />
            <label className="inline small" style={{ gap: 6 }}>
              <input type="checkbox" checked={tp.is_active} onChange={(e) => upd(tp.id, { is_active: e.target.checked })} />
              {t("leaves.type_active")}
            </label>
            <label className="inline small" style={{ gap: 6 }} title={t("leaves.type_requires_detail_hint")}>
              <input type="checkbox" checked={tp.requires_detail} onChange={(e) => upd(tp.id, { requires_detail: e.target.checked })} />
              {t("leaves.type_requires_detail")}
            </label>
            <button className="btn-secondary btn-sm" onClick={() => saveType(tp)}>{t("action.save")}</button>
            <button className="btn-danger btn-sm" onClick={() => delType(tp.id)} aria-label={t("action.delete")}>✕</button>
          </div>
        ))}
      </div>
    </div>
  );
}


export const WEEKDAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];


export const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];


/** Admin > Report: the two ways a report is mailed, each in its own card with
 *  its own recipients. The scheduled report (days, hour, what is sent), and, for
 *  the admin, a mail at every change of a squad's reporting: what triggers it,
 *  for which squads, to whom (addresses, plus the squad's tribe leader or leaders
 *  added by a button), how often, then the whole setting in one sentence. */
export function ReportingAdmin() {
  const { t } = useI18n();
  // The admin runs the all-tribes schedule and the change mails; a tribe leader
  // runs their own tribe's schedule (the server pins it), and nothing else.
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [rep, setRep] = useState<any | null>(null);
  const [chg, setChg] = useState<any | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [saved, setSaved] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const { error, wrap } = useErr();

  useEffect(() => {
    api.get<any>("/api/admin/report-config").then(setRep).catch((e) => setLoadErr(e?.message || t("common.error")));
    if (isAdmin) api.get<any>("/api/admin/change-notify-config").then(setChg).catch((e) => setLoadErr(e?.message || t("common.error")));
    else setChg({});
    api.get<Squad[]>("/api/squads").then(setSquads).catch(() => {});
  }, [isAdmin]);
  // A refused load is said: the spinner used to turn forever.
  if (loadErr && (!rep || !chg)) return <ErrorBanner message={loadErr} />;
  if (!rep || !chg) return <div className="spinner">{t("common.loading")}</div>;

  const setR = (k: string, v: any) => setRep({ ...rep, [k]: v });
  const setC = (k: string, v: any) => setChg({ ...chg, [k]: v });
  const weekdays: number[] = rep.weekdays ?? [rep.weekday ?? 0];
  const toggleWeekday = (i: number) => setR("weekdays", weekdays.includes(i) ? weekdays.filter((x) => x !== i) : [...weekdays, i].sort());
  const events: string[] = (chg._all_events ?? ["progress", "roadmap", "budget", "key_message"]);
  const toggleEvent = (e: string) => setC("events", (chg.events ?? []).includes(e) ? chg.events.filter((x: string) => x !== e) : [...(chg.events ?? []), e]);
  const toggleSquad = (id: number) => setC("scope_squads", (chg.scope_squads ?? []).includes(id) ? chg.scope_squads.filter((x: number) => x !== id) : [...(chg.scope_squads ?? []), id]);
  const toggleRepSquad = (id: number) => setR("squad_ids", (rep.squad_ids ?? []).includes(id) ? rep.squad_ids.filter((x: number) => x !== id) : [...(rep.squad_ids ?? []), id]);
  const Chip = ({ on, onClick, children }: any) => (
    <label className={`rm-pick-chip${on ? " on" : ""}`} onClick={(e) => { e.preventDefault(); onClick(); }}>
      <input type="checkbox" checked={on} readOnly /><span className="rm-pick-name">{children}</span>
    </label>
  );

  async function save() {
    await wrap(async () => {
      const [r, c] = await Promise.all([
        api.put<any>("/api/admin/report-config", rep),
        isAdmin ? api.put<any>("/api/admin/change-notify-config", chg) : Promise.resolve({}),
      ]);
      setRep(r); setChg({ ...c, _all_events: chg._all_events });
      setSaved(true); setTimeout(() => setSaved(false), 2000);
    });
  }
  async function testWeekly() {
    setTestMsg(null);
    try { const r = await api.post<any>("/api/admin/report-config/test", {}); setTestMsg(r.ok ? t("report.test_ok", { to: r.to }) : t("report.test_fail") + (r.error ? ` (${r.error})` : "")); }
    catch (e: any) { setTestMsg(e.message); }
  }
  // Now, each squad's own document to its leaders (the chosen squads, else all).
  async function sendLeadersNow() {
    setTestMsg(null);
    try {
      const r = await api.post<any>("/api/admin/report-config/send-squad-leaders", { squad_ids: rep.squad_ids ?? [] });
      setTestMsg(t("reporting.send_leaders_done", { n: r.sent }) +
        (r.skipped?.length ? `, ${t("reporting.send_leaders_skipped", { names: r.skipped.join(", ") })}` : "") +
        (r.failed?.length ? `, ${t("reporting.send_leaders_failed", { names: r.failed.join(", ") })}` : ""));
    } catch (e: any) { setTestMsg(e.message); }
  }
  async function testChange() {
    setTestMsg(null);
    try { const r = await api.post<any>("/api/admin/change-notify-config/test", {}); setTestMsg(r.ok ? t("changenotify.test_ok", { to: r.to, squad: r.squad }) : t("changenotify.test_fail") + (r.error ? ` (${r.error})` : "")); }
    catch (e: any) { setTestMsg(e.message); }
  }

  // Each trigger has its own recipients: a weekly digest and a mail at every
  // change do not go to the same people, and one shared box hid that.
  const repList: string[] = (Array.isArray(rep.recipients) ? rep.recipients : String(rep.recipients ?? "").split("\n"))
    .map((x: string) => x.trim()).filter(Boolean);
  const chgList: string[] = (Array.isArray(chg.recipients) ? chg.recipients : String(chg.recipients ?? "").split("\n"))
    .map((x: string) => x.trim()).filter(Boolean);
  const Switch = ({ k, label }: { k: string; label: string }) => (
    <label className="switch">
      <input type="checkbox" checked={!!rep[k]} onChange={(e) => setR(k, e.target.checked)} />
      <span className="track"><span className="knob" /></span>
      <span className="strong">{label}</span>
    </label>
  );
  const sep = { borderTop: "1px solid var(--line)", paddingTop: 12 } as const;
  const chosenEvents: string[] = (chg.events ?? []).filter((e: string) => events.includes(e));
  const chosenSquads: number[] = chg.scope_squads ?? [];

  return (
    <div className="stack" style={{ maxWidth: 760, gap: 18 }}>
      {error && <ErrorBanner message={error} />}
      <h2 style={{ margin: 0 }}>{isAdmin ? t("reporting.admin_title") : t("reporting.tribe_scope")}</h2>

      {/* 1. The scheduled report */}
      <div className="card stack" style={{ gap: 12 }}>
        <label className="switch">
          <input type="checkbox" checked={!!rep.enabled} onChange={(e) => setR("enabled", e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="strong">{t("reporting.sched_enabled")}</span>
        </label>
        <div className="small muted" style={{ marginTop: -6 }}>{t("reporting.sched_hint")}</div>
        {rep.enabled && (
          <>
            <div>
              <label>{t("reporting.days")}</label>
              <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                {WEEKDAY_KEYS.map((k, i) => <Chip key={i} on={weekdays.includes(i)} onClick={() => toggleWeekday(i)}>{t(`reporting.day.${k}`)}</Chip>)}
              </div>
            </div>
            <div className="row" style={{ gap: 12 }}>
              <div style={{ width: 120 }}><label htmlFor="rep-hour">{t("report.hour")}</label>
                <input id="rep-hour" type="number" min={0} max={23} value={rep.hour ?? 8} onChange={(e) => setR("hour", Number(e.target.value))} /></div>
              <div style={{ width: 150 }}><label htmlFor="rep-since">{t("report.since_days")}</label>
                <input id="rep-since" type="number" min={1} max={120} value={rep.since_days ?? 7} onChange={(e) => setR("since_days", Number(e.target.value))} /></div>
            </div>
            <RecipientList label={t("changenotify.recipients")} list={repList}
                           onChange={(l) => setR("recipients", l)} t={t} />
            <div className="strong" style={sep}>{t("reporting.what")}</div>
            <Switch k="global_doc" label={t("reporting.global_doc")} />
            <Switch k="per_squad" label={t("reporting.per_squad")} />
            <Switch k="squad_leaders" label={t("reporting.squad_leaders")} />
            {(rep.per_squad || rep.squad_leaders) && (
              <div>
                <label>{t("reporting.squads")}</label>
                <div className="small muted" style={{ marginBottom: 4 }}>{t("reporting.squads_all_hint")}</div>
                <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                  {squads.map((s) => <Chip key={s.id} on={(rep.squad_ids ?? []).includes(s.id)} onClick={() => toggleRepSquad(s.id)}>{s.name}</Chip>)}
                </div>
              </div>
            )}
            {isAdmin && (
              <>
                <Switch k="tribe_leader_digest" label={t("reporting.tribe_digest")} />
                <div className="small muted" style={{ marginTop: -4 }}>{t("reporting.tribe_digest_hint")}</div>
              </>
            )}
            <Switch k="only_when_changes" label={t("reporting.only_when_changes")} />
            <div className="small muted" style={{ marginTop: -4 }}>{t("reporting.only_when_changes_hint")}</div>
            <label className="switch">
              <input type="checkbox" checked={rep.attach_pptx !== false} onChange={(e) => setR("attach_pptx", e.target.checked)} />
              <span className="track"><span className="knob" /></span>
              <span className="strong">{t("reporting.attach_pptx")}</span>
            </label>
            <div className="inline" style={{ flexWrap: "wrap" }}>
              <button className="btn-secondary btn-sm" onClick={testWeekly}>{t("reporting.test_sched")}</button>
              <button className="btn-secondary btn-sm" onClick={sendLeadersNow}>{t("reporting.send_leaders_now")}</button>
              {rep.last_sent_day && <span className="small muted">{t("reporting.last_sent_day", { date: rep.last_sent_day })}</span>}
            </div>
          </>
        )}
      </div>

      {/* 2. A mail at every change (admin: one setting for the whole application) */}
      {isAdmin && (
        <div className="card stack" style={{ gap: 12 }}>
          <label className="switch">
            <input type="checkbox" checked={!!chg.enabled} onChange={(e) => setC("enabled", e.target.checked)} />
            <span className="track"><span className="knob" /></span>
            <span className="strong">{t("changenotify.title")}</span>
          </label>
          <div className="small muted" style={{ marginTop: -6 }}>{t("changenotify.intro")}</div>
          {chg.enabled && (
            <>
              {/* What triggers it */}
              <div style={sep}>
                <div className="between" style={{ alignItems: "baseline" }}>
                  <label>{t("changenotify.q_what")}</label>
                  <span className="inline small" style={{ gap: 8 }}>
                    <button type="button" className="btn-ghost btn-sm" onClick={() => setC("events", [...events])}>{t("changenotify.all")}</button>
                    <button type="button" className="btn-ghost btn-sm" onClick={() => setC("events", [])}>{t("changenotify.none")}</button>
                  </span>
                </div>
                <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                  {events.map((e) => <Chip key={e} on={chosenEvents.includes(e)} onClick={() => toggleEvent(e)}>{t(`changenotify.event.${e}`)}</Chip>)}
                </div>
              </div>

              {/* Which squads */}
              <div>
                <div className="between" style={{ alignItems: "baseline" }}>
                  <label>{t("changenotify.q_which")}</label>
                  {chosenSquads.length > 0 && (
                    <button type="button" className="btn-ghost btn-sm" onClick={() => setC("scope_squads", [])}>{t("changenotify.all_squads")}</button>
                  )}
                </div>
                <div className="small muted" style={{ marginBottom: 4 }}>
                  {chosenSquads.length === 0 ? t("changenotify.scope_all_now") : t("changenotify.scope_some_now", { n: chosenSquads.length })}
                </div>
                <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                  {squads.map((s) => <Chip key={s.id} on={chosenSquads.includes(s.id)} onClick={() => toggleSquad(s.id)}>{s.name}</Chip>)}
                </div>
              </div>

              {/* Who receives it: the addresses typed, then the people found for
                  each squad (its tribe leader, its leaders), added by a button
                  and listed with the others. */}
              <RecipientList label={t("changenotify.q_who")} list={chgList}
                             onChange={(l) => setC("recipients", l)} t={t}
                             autos={[
                               { key: "tribe_leaders", on: !!chg.tribe_leaders, label: t("changenotify.auto_tribe_leader") },
                               { key: "squad_leaders", on: !!chg.squad_leaders, label: t("changenotify.auto_squad_leaders") },
                             ]}
                             onAuto={(k, v) => setC(k, v)} />

              {/* How often */}
              <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
                <div style={{ width: 200 }}>
                  <label htmlFor="chg-interval">{t("changenotify.q_often")}</label>
                  <input id="chg-interval" type="number" min={0} max={1440} value={chg.min_interval_minutes ?? 0}
                         onChange={(e) => setC("min_interval_minutes", Number(e.target.value))} />
                </div>
                <div className="small muted" style={{ paddingBottom: 8 }}>{t("changenotify.interval_hint")}</div>
              </div>
              <label className="inline small" style={{ gap: 6 }}>
                <input type="checkbox" checked={chg.current_year_only !== false} onChange={(e) => setC("current_year_only", e.target.checked)} />
                {t("changenotify.current_year_only")}
              </label>
              <label className="switch">
                <input type="checkbox" checked={chg.attach_pptx !== false} onChange={(e) => setC("attach_pptx", e.target.checked)} />
                <span className="track"><span className="knob" /></span>
                <span className="strong">{t("reporting.attach_pptx")}</span>
              </label>

              {/* The whole setting, said in one sentence. */}
              <div className="banner small" style={{ background: "var(--ice-soft)" }}>
                {changeSummary(t, chosenEvents, chosenSquads.map((id) => squads.find((s) => s.id === id)?.name ?? `#${id}`),
                               chgList, !!chg.tribe_leaders, !!chg.squad_leaders, chg.min_interval_minutes ?? 0)}
              </div>
              <div className="inline"><button className="btn-secondary btn-sm" onClick={testChange}>{t("reporting.test_change")}</button></div>
            </>
          )}
        </div>
      )}

      <div className="inline">
        <button onClick={save}>{t("action.save")}</button>
        {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
        {testMsg && <span className="small muted">{testMsg}</span>}
      </div>
    </div>
  );
}

/** The change mail's setting in one sentence: who gets what, when. */
function changeSummary(t: (k: string, v?: any) => string, events: string[], squadNames: string[],
                       emails: string[], tribeLeaders: boolean, squadLeaders: boolean, minutes: number): string {
  if (events.length === 0) return t("changenotify.sum_no_event");
  const who = [
    ...emails,
    ...(tribeLeaders ? [t("changenotify.sum_tribe_leader")] : []),
    ...(squadLeaders ? [t("changenotify.sum_squad_leaders")] : []),
  ];
  if (who.length === 0) return t("changenotify.sum_nobody");
  return t("changenotify.sum", {
    squads: squadNames.length ? squadNames.join(", ") : t("changenotify.sum_any_squad"),
    what: events.map((e) => t(`changenotify.event.${e}`).toLowerCase()).join(", "),
    who: who.join(", "),
    when: minutes > 0 ? t("changenotify.sum_throttled", { n: minutes }) : t("changenotify.sum_each"),
  });
}

/** A list of recipients as removable chips, an input to add an address, and
 *  (optional) automatic recipients added by a button and listed with the rest. */
function RecipientList({ label, list, onChange, autos = [], onAuto, t }: {
  label: string; list: string[]; onChange: (l: string[]) => void;
  autos?: { key: string; on: boolean; label: string }[]; onAuto?: (key: string, on: boolean) => void;
  t: (k: string, v?: any) => string;
}) {
  const [draft, setDraft] = useState("");
  const [bad, setBad] = useState(false);
  const add = () => {
    const parts = draft.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
    if (!parts.length) return;
    if (parts.some((p) => !p.includes("@"))) { setBad(true); return; }
    const seen = new Set(list.map((x) => x.toLowerCase()));
    onChange([...list, ...parts.filter((p) => !seen.has(p.toLowerCase()))]);
    setDraft(""); setBad(false);
  };
  const shown = autos.filter((a) => a.on);
  return (
    <div className="stack" style={{ gap: 6 }}>
      <label htmlFor={`rcpt-${label}`}>{label}</label>
      {list.length === 0 && shown.length === 0 && <div className="small muted">{t("changenotify.nobody_yet")}</div>}
      <div className="stack" style={{ gap: 4 }}>
        {list.map((addr) => (
          <div key={addr} className="between small" style={{ borderBottom: "1px solid var(--line)", paddingBottom: 3 }}>
            <span>{addr}</span>
            <button type="button" className="btn-ghost btn-sm" aria-label={`${t("action.delete")} ${addr}`}
                    onClick={() => onChange(list.filter((x) => x !== addr))}>✕</button>
          </div>
        ))}
        {shown.map((a) => (
          <div key={a.key} className="between small" style={{ borderBottom: "1px solid var(--line)", paddingBottom: 3 }}>
            <span>{a.label} <span className="badge badge-grey">{t("changenotify.auto")}</span></span>
            <button type="button" className="btn-ghost btn-sm" aria-label={`${t("action.delete")} ${a.label}`}
                    onClick={() => onAuto?.(a.key, false)}>✕</button>
          </div>
        ))}
      </div>
      <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
        <input id={`rcpt-${label}`} className="w-auto" style={{ minWidth: 240 }} value={draft} placeholder="nom@exemple.com"
               onChange={(e) => { setDraft(e.target.value); setBad(false); }}
               onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
               // Typed then left: kept, as the old text box did (it was lost on Save).
               onBlur={() => { if (draft.trim()) add(); }} />
        <button type="button" className="btn-secondary btn-sm" onClick={add} disabled={!draft.trim()}>{t("admin.add")}</button>
        {autos.filter((a) => !a.on).map((a) => (
          <button key={a.key} type="button" className="btn-secondary btn-sm" onClick={() => onAuto?.(a.key, true)}>
            + {a.label}
          </button>
        ))}
      </div>
      {bad && <div className="small" style={{ color: "var(--red)" }}>{t("changenotify.bad_address")}</div>}
    </div>
  );
}


/** Admin > Settings: global app settings - branding (name/subtitle), default
 *  language and year, staleness threshold, and feed scope/retention. Admin only. */
export function SettingsAdmin() {
  const { t } = useI18n();
  const reloadConfig = useReloadConfig();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  const ls = useLoadState();
  const loadCfg = () => { api.get<any>("/api/admin/settings").then(setCfg).catch(ls.fail); };
  useEffect(loadCfg, []);
  if (!cfg) return ls.waiting(loadCfg);
  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });

  async function save() {
    await wrap(async () => {
      const out = await api.put<any>("/api/admin/settings", cfg);
      setCfg(out);
      // The public config (app name, language rules) is read by every screen:
      // reload it so the change shows at once, not at the next page load.
      reloadConfig();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }

  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      {error && <ErrorBanner message={error} />}

      <div className="card">
        <h3>{t("set.section.brand")}</h3>
        <div className="row">
          <div className="col"><label>{t("set.app_name")}</label><input aria-label={t("set.app_name")} value={cfg.app_name ?? ""} onChange={(e) => set("app_name", e.target.value)} /></div>
          <div className="col"><label>{t("set.app_subtitle")}</label><input aria-label={t("set.app_subtitle")} value={cfg.app_subtitle ?? ""} onChange={(e) => set("app_subtitle", e.target.value)} /></div>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <div style={{ width: 200 }}>
            <label>{t("set.lang")}</label>
            <select aria-label={t("set.lang")} value={cfg.default_lang} onChange={(e) => set("default_lang", e.target.value)}>
              <option value="fr">Français</option>
              <option value="en">English</option>
            </select>
          </div>
          <label className="inline small" style={{ gap: 6, alignSelf: "flex-end" }}>
            <input type="checkbox" checked={cfg.lang_switch !== false} onChange={(e) => set("lang_switch", e.target.checked)} />
            {t("set.lang_switch")}
          </label>
          <div style={{ width: 160 }}>
            <label>{t("set.year")}</label>
            <input aria-label={t("set.year")} type="number" value={cfg.default_year ?? ""} onChange={(e) => set("default_year", Number(e.target.value))} />
          </div>
        </div>
      </div>

      <div className="card">
        <h3>{t("set.section.fresh")}</h3>
        <div className="small muted" style={{ marginBottom: 8 }}>{t("admin.threshold_hint")}</div>
        <div style={{ width: 160 }}>
          <label>{t("admin.days")}</label>
          <input aria-label={t("admin.days")} type="number" min={1} max={365} value={cfg.staleness_threshold_days ?? ""} onChange={(e) => set("staleness_threshold_days", Number(e.target.value))} />
        </div>
      </div>

      <div className="card">
        <h3>{t("set.section.feed")}</h3>
        <div className="row">
          <div style={{ width: 240 }}>
            <label>{t("set.feed_scope")}</label>
            <select aria-label={t("set.feed_scope")} value={cfg.feed_post_scope} onChange={(e) => set("feed_post_scope", e.target.value)}>
              <option value="leaders">{t("set.feed_scope.leaders")}</option>
              <option value="everyone">{t("set.feed_scope.everyone")}</option>
            </select>
          </div>
          <div style={{ width: 240 }}>
            <label>{t("set.feed_retention")}</label>
            <input aria-label={t("set.feed_retention")} type="number" min={0} value={cfg.feed_retention_days ?? 0} onChange={(e) => set("feed_retention_days", Number(e.target.value))} />
            <div className="small muted">{t("set.feed_retention_hint")}</div>
          </div>
        </div>
      </div>

      <div className="inline">
        <button onClick={save}>{t("action.save")}</button>
        {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
      </div>
    </div>
  );
}
