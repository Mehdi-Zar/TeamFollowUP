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
import { LeaveConfig, LeaveType, ModuleKey, Permissions, Squad, Tribe } from "../../types";
import { ErrorBanner } from "../../components/ui";

import { useErr } from "./shared";

export const MODULE_TREE: { key: ModuleKey; features: string[] }[] = [
  { key: "dashboard", features: [] },
  { key: "org", features: [] },
  { key: "reporting", features: [] },
  { key: "feed", features: ["reactions", "replies", "pin", "kinds"] },
  { key: "review", features: ["weekly_report"] },
  { key: "squad_content", features: ["objectives", "roadmap", "kpis"] },
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

  useEffect(() => { api.get<any>("/api/admin/modules-config").then(setCfg); }, []);
  if (!cfg) return <div className="spinner">{t("common.loading")}</div>;

  async function apply(next: any) {
    setCfg(next);
    await wrap(async () => {
      const out = await api.put<any>("/api/admin/modules-config", next);
      setCfg(out);
      reloadConfig();
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    });
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


/** Single, unified reporting menu: automatic report + change notifications,
 *  one full (advanced) view - no simple/advanced toggle. Shown in the Admin
 *  "Reporting" tab and inside the reporting popup for admins. */
export function ReportingAdmin() {
  const { t } = useI18n();
  const [rep, setRep] = useState<any | null>(null);
  const [chg, setChg] = useState<any | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [saved, setSaved] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const { error, wrap } = useErr();

  useEffect(() => {
    api.get<any>("/api/admin/report-config").then(setRep).catch(() => {});
    api.get<any>("/api/admin/change-notify-config").then(setChg).catch(() => {});
    api.get<Squad[]>("/api/squads").then(setSquads).catch(() => {});
  }, []);
  if (!rep || !chg) return <div className="spinner">{t("common.loading")}</div>;

  const setR = (k: string, v: any) => setRep({ ...rep, [k]: v });
  const setC = (k: string, v: any) => setChg({ ...chg, [k]: v });
  const repRecipients = Array.isArray(rep.recipients) ? rep.recipients.join("\n") : (rep.recipients ?? "");
  const chgRecipients = Array.isArray(chg.recipients) ? chg.recipients.join("\n") : (chg.recipients ?? "");
  const weekdays: number[] = rep.weekdays ?? [rep.weekday ?? 0];
  const toggleWeekday = (i: number) => setR("weekdays", weekdays.includes(i) ? weekdays.filter((x) => x !== i) : [...weekdays, i].sort());
  const events: string[] = chg._all_events ?? ["progress", "roadmap", "objectives", "budget", "key_message"];
  const toggleEvent = (e: string) => setC("events", (chg.events ?? []).includes(e) ? chg.events.filter((x: string) => x !== e) : [...(chg.events ?? []), e]);
  const toggleSquad = (id: number) => setC("scope_squads", (chg.scope_squads ?? []).includes(id) ? chg.scope_squads.filter((x: number) => x !== id) : [...(chg.scope_squads ?? []), id]);
  const Chip = ({ on, onClick, children }: any) => (
    <label className={`rm-pick-chip${on ? " on" : ""}`} onClick={(e) => { e.preventDefault(); onClick(); }}>
      <input type="checkbox" checked={on} readOnly /><span className="rm-pick-name">{children}</span>
    </label>
  );

  async function save() {
    await wrap(async () => {
      const [r, c] = await Promise.all([
        api.put<any>("/api/admin/report-config", rep),
        api.put<any>("/api/admin/change-notify-config", chg),
      ]);
      setRep(r); setChg({ ...c, _all_events: chg._all_events });
      setSaved(true); setTimeout(() => setSaved(false), 2000);
    });
  }
  async function testWeekly() {
    setTestMsg(null);
    try { const r = await api.post<any>("/api/admin/report-config/test", {}); setTestMsg(r.ok ? t("report.test_ok", { to: r.to }) : t("report.test_fail")); }
    catch (e: any) { setTestMsg(e.message); }
  }
  async function testChange() {
    setTestMsg(null);
    try { const r = await api.post<any>("/api/admin/change-notify-config/test", {}); setTestMsg(r.ok ? t("changenotify.test_ok", { to: r.to, squad: r.squad }) : t("changenotify.test_fail")); }
    catch (e: any) { setTestMsg(e.message); }
  }

  // One shared recipients list and one shared "attach PPTX", written to both
  // delivery triggers - that's the whole point of merging the two menus.
  const recipients = Array.isArray(rep.recipients) ? rep.recipients.join("\n") : (rep.recipients ?? "");
  const setRecipients = (text: string) => {
    const list = text.split("\n");
    setRep({ ...rep, recipients: list });
    setChg({ ...chg, recipients: list });
  };
  const setAttach = (v: boolean) => { setRep({ ...rep, attach_pptx: v }); setChg({ ...chg, attach_pptx: v }); };
  const sep = { borderTop: "1px solid var(--line)", paddingTop: 12 } as const;

  return (
    <div className="stack" style={{ maxWidth: 700 }}>
      {error && <ErrorBanner message={error} />}
      <div className="between" style={{ alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>{t("reporting.title")}</h2>
      </div>

      <div className="card stack" style={{ gap: 14 }}>
        <div className="small muted">{t("reporting.merged_hint")}</div>

        {/* Shared recipients */}
        <div>
          <label>{t("changenotify.recipients")}</label>
          <textarea aria-label={t("changenotify.recipients")} rows={2} value={recipients} placeholder="dir@exemple.com&#10;copil@exemple.com"
                    onChange={(e) => setRecipients(e.target.value)} />
          <div className="small muted">{t("reporting.recipients_hint")}</div>
        </div>

        <div className="strong" style={{ marginTop: 2 }}>{t("reporting.when")}</div>

        {/* Trigger 1 - scheduled */}
        <div className="stack" style={{ gap: 10, ...sep }}>
          <label className="switch">
            <input type="checkbox" checked={!!rep.enabled} onChange={(e) => setR("enabled", e.target.checked)} />
            <span className="track"><span className="knob" /></span>
            <span className="strong">{t("reporting.sched_enabled")}</span>
          </label>
          {rep.enabled && (
            <>
              <div>
                <label>{t("reporting.days")}</label>
                <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                  {WEEKDAY_KEYS.map((k, i) => <Chip key={i} on={weekdays.includes(i)} onClick={() => toggleWeekday(i)}>{t(`reporting.day.${k}`)}</Chip>)}
                </div>
              </div>
              <div className="row" style={{ gap: 12 }}>
                <div style={{ width: 120 }}><label>{t("report.hour")}</label>
                  <input aria-label={t("report.hour")} type="number" min={0} max={23} value={rep.hour ?? 8} onChange={(e) => setR("hour", Number(e.target.value))} /></div>
                <div style={{ width: 150 }}><label>{t("report.since_days")}</label>
                  <input aria-label={t("report.since_days")} type="number" min={1} max={120} value={rep.since_days ?? 7} onChange={(e) => setR("since_days", Number(e.target.value))} /></div>
              </div>
              <label className="switch">
                <input type="checkbox" checked={!!rep.tribe_leader_digest} onChange={(e) => setR("tribe_leader_digest", e.target.checked)} />
                <span className="track"><span className="knob" /></span>
                <span className="strong">{t("reporting.tribe_digest")}</span>
              </label>
              <div className="small muted" style={{ marginTop: -4 }}>{t("reporting.tribe_digest_hint")}</div>
              <label className="switch">
                <input type="checkbox" checked={!!rep.only_when_changes} onChange={(e) => setR("only_when_changes", e.target.checked)} />
                <span className="track"><span className="knob" /></span>
                <span className="strong">{t("reporting.only_when_changes")}</span>
              </label>
              <div className="small muted" style={{ marginTop: -4 }}>{t("reporting.only_when_changes_hint")}</div>
              <div className="inline">
                <button className="btn-secondary btn-sm" onClick={testWeekly}>{t("reporting.test_sched")}</button>
                {rep.last_sent_day && <span className="small muted">{t("reporting.last_sent_day", { date: rep.last_sent_day })}</span>}
              </div>
            </>
          )}
        </div>

        {/* Trigger 2 - on change */}
        <div className="stack" style={{ gap: 10, ...sep }}>
          <label className="switch">
            <input type="checkbox" checked={!!chg.enabled} onChange={(e) => setC("enabled", e.target.checked)} />
            <span className="track"><span className="knob" /></span>
            <span className="strong">{t("reporting.change_enabled")}</span>
          </label>
          {chg.enabled && (
            <>
              <div>
                <label>{t("changenotify.events")}</label>
                <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                  {events.map((e) => <Chip key={e} on={(chg.events ?? []).includes(e)} onClick={() => toggleEvent(e)}>{t(`changenotify.event.${e}`)}</Chip>)}
                </div>
              </div>
              <div className="row" style={{ gap: 12 }}>
                <div style={{ width: 180 }}><label>{t("changenotify.interval")}</label>
                  <input aria-label={t("changenotify.interval")} type="number" min={0} max={1440} value={chg.min_interval_minutes ?? 0} onChange={(e) => setC("min_interval_minutes", Number(e.target.value))} /></div>
                <label className="inline small" style={{ gap: 6, alignSelf: "flex-end" }}>
                  <input type="checkbox" checked={chg.current_year_only !== false} onChange={(e) => setC("current_year_only", e.target.checked)} />{t("changenotify.current_year_only")}</label>
              </div>
              <div>
                <label>{t("changenotify.scope")}</label>
                <div className="small muted" style={{ marginBottom: 4 }}>{t("changenotify.scope_all_hint")}</div>
                <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
                  {squads.map((s) => <Chip key={s.id} on={(chg.scope_squads ?? []).includes(s.id)} onClick={() => toggleSquad(s.id)}>{s.name}</Chip>)}
                </div>
              </div>
              <div className="inline"><button className="btn-secondary btn-sm" onClick={testChange}>{t("reporting.test_change")}</button></div>
            </>
          )}
        </div>

        {/* Shared option */}
        {(rep.enabled || chg.enabled) && (
          <div style={sep}>
            <label className="switch">
              <input type="checkbox" checked={rep.attach_pptx !== false} onChange={(e) => setAttach(e.target.checked)} />
              <span className="track"><span className="knob" /></span>
              <span className="strong">{t("reporting.attach_pptx")}</span>
            </label>
          </div>
        )}
      </div>

      <div className="inline">
        <button onClick={save}>{t("action.save")}</button>
        {saved && <span style={{ color: "var(--green)" }}>{t("admin.saved")}</span>}
        {testMsg && <span className="small muted">{testMsg}</span>}
      </div>
    </div>
  );
}


/** Admin > Settings: global app settings - branding (name/subtitle), default
 *  language and year, staleness threshold, and feed scope/retention. Admin only. */
export function SettingsAdmin() {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, wrap } = useErr();

  useEffect(() => {
    api.get<any>("/api/admin/settings").then(setCfg);
  }, []);
  if (!cfg) return <div className="spinner">{t("common.loading")}</div>;
  const set = (k: string, v: any) => setCfg({ ...cfg, [k]: v });

  async function save() {
    await wrap(async () => {
      const out = await api.put<any>("/api/admin/settings", cfg);
      setCfg(out);
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
