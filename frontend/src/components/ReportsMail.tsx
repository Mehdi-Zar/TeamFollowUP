// ReportsMail: Administration > Reports by email, the admin's alone. Three tabs:
//
//   * A tribe (the admin picks it): the tribe leader is the main recipient and
//     gets the tribe's document or one mail per squad; others are added in copy
//     of that same mail (one mail, never two for one person), by role in their
//     squad, by persona, by name or by address. Each kind of mail says which
//     documents it carries (weekly report, dashboard, roadmap, dependencies).
//   * Direction: the whole document, every tribe, at fixed addresses.
//   * At every change: the change notices.
//
// The server computes who receives which mail (app/mailplan.py), from the
// settings being edited: the list follows every tick, before saving.
import { ReactNode, useEffect, useState } from "react";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { Tribe } from "../types";
import { ChangeNotifyAdmin, RecipientList } from "../pages/admin/configuration";
import { ErrorBanner, Modal, Spinner } from "./ui";

export const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/** The documents a mail can carry (reportconfig.DOC_TYPES). */
const DOC_TYPES = ["weekly", "dashboard", "roadmap", "dependencies"] as const;

type TabKey = "tribe" | "direction" | "changes";
type Recipient = { email: string; name: string; line: string; role: "to" | "cc" };
type PlanMail = { key: string; kind: string; label: string; squad_id: number | null; docs: string[];
                  recipients: Recipient[]; missing: { name: string; line: string }[] };
type Copy = { type: "persona" | "user" | "email"; value: any; content: "tribe" | "squads"; squad_ids: number[] };
type Choices = { squads?: { id: number; name: string }[]; users?: { id: number; name: string; email: string }[];
                 personas?: { key: string; label: string }[]; tribe_leaders?: { id: number; name: string; email: string }[] };

/** The menu, by tabs. */
export function ReportsMailPanel({ initialTab = "tribe" }: { initialTab?: TabKey }) {
  const { t } = useI18n();
  const tabs: TabKey[] = ["tribe", "direction", "changes"];
  const [tab, setTab] = useState<TabKey>(initialTab);
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="mr-tabs" role="tablist">
        {tabs.map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k}
                  className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            {t(`mailrep.tab_${k}`)}
          </button>
        ))}
      </div>
      <div className="small muted">{t(`mailrep.intro_${tab}`)}</div>
      {tab === "tribe" && <ScheduleTab kind="tribe" />}
      {tab === "direction" && <ScheduleTab kind="direction" />}
      {tab === "changes" && <ChangeNotifyAdmin />}
    </div>
  );
}

// ---- A schedule (a tribe's, or the Direction's) ---------------------------------------

function ScheduleTab({ kind }: { kind: "tribe" | "direction" }) {
  const { t } = useI18n();
  const [tribes, setTribes] = useState<Tribe[] | null>(null);
  const [tribeId, setTribeId] = useState<number | null>(null);
  const [cfg, setCfg] = useState<any | null>(null);
  const [saved, setSaved] = useState<any | null>(null);
  const [plan, setPlan] = useState<PlanMail[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // The tribe whose schedule is shown.
  useEffect(() => {
    if (kind !== "tribe") return;
    api.get<Tribe[]>("/api/tribes").then((l) => { setTribes(l); setTribeId((cur) => cur ?? l[0]?.id ?? null); })
      .catch(() => setTribes([]));
  }, [kind]);
  const q = kind === "direction" ? "" : (tribeId != null ? `?tribe_id=${tribeId}` : null);
  const qs = (extra = "") => (q ? `${q}${extra ? `&${extra}` : ""}` : (extra ? `?${extra}` : ""));

  useEffect(() => {
    if (q === null) return;
    setCfg(null); setPlan(null); setErr(null); setMsg(null);
    api.get<any>(`/api/admin/report-config${qs()}`).then((c) => { setCfg(c); setSaved(c); })
      .catch((e) => setErr(errorText(e)));
  }, [q]);
  // Who receives what, for the settings as they are on screen: recomputed by the
  // server at each change (a short pause groups the clicks), nothing saved.
  const draftKey = cfg ? JSON.stringify(strip(cfg)) : "";
  useEffect(() => {
    if (q === null || !cfg) return;
    const h = setTimeout(() => {
      api.post<{ mails: PlanMail[] }>(`/api/admin/report-config/plan${qs()}`, { cfg: strip(cfg) })
        .then((r) => setPlan(r.mails)).catch(() => setPlan([]));
    }, 250);
    return () => clearTimeout(h);
  }, [q, draftKey]);

  if (err && !cfg) return <ErrorBanner message={err} />;
  // No tribe yet: nothing to set up here (the spinner used to turn forever).
  if (kind === "tribe" && tribes !== null && tribes.length === 0) {
    return <div className="small muted">{t("mailrep.no_tribe")}</div>;
  }
  if (!cfg) return <Spinner />;
  const choices: Choices = cfg._choices ?? {};
  const dirty = JSON.stringify(strip(cfg)) !== JSON.stringify(strip(saved));
  const set = (k: string, v: any) => setCfg((p: any) => ({ ...p, [k]: v }));

  async function save() {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const out = await api.put<any>(`/api/admin/report-config${qs()}`, strip(cfg));
      setCfg(out); setSaved(out); setMsg(t("admin.saved"));
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  const lineActions = (line: string) => (
    <LineActions line={line} plan={plan} qs={qs} dirty={dirty} draft={strip(cfg)} />
  );

  return (
    <div className="stack" style={{ gap: 16 }}>
      {kind === "tribe" && (
        <div style={{ maxWidth: 320 }}>
          <label htmlFor="mr-tribe">{t("mailrep.tribe_pick")}</label>
          <select id="mr-tribe" value={tribeId ?? ""} onChange={(e) => setTribeId(Number(e.target.value))}>
            {(tribes ?? []).map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
          </select>
        </div>
      )}
      {err && <ErrorBanner message={err} />}

      {/* When */}
      <section className="card stack mr-card">
        <div className="mr-card-head">
          <label className="switch">
            <input type="checkbox" checked={!!cfg.enabled} onChange={(e) => set("enabled", e.target.checked)} />
            <span className="track"><span className="knob" /></span>
            <span className="strong">{t(kind === "tribe" ? "mailrep.enabled_tribe" : "mailrep.enabled_direction")}</span>
          </label>
        </div>
        <div className="mr-when">
          <div>
            <label>{t("reporting.days")}</label>
            <div className="day-pick">
              {WEEKDAY_KEYS.map((k, i) => {
                const on = (cfg.weekdays ?? []).includes(i);
                return (
                  <button type="button" key={k} aria-pressed={on} className={`day-chip${on ? " on" : ""}`}
                          onClick={() => set("weekdays", on ? cfg.weekdays.filter((x: number) => x !== i) : [...cfg.weekdays, i].sort())}>
                    {t(`reporting.day.${k}`)}
                  </button>
                );
              })}
            </div>
          </div>
          <div style={{ width: 160 }}>
            <label htmlFor="mr-hour">{t("reporting.hour")}</label>
            <input id="mr-hour" type="number" min={0} max={23} value={cfg.hour ?? 8} onChange={(e) => set("hour", Number(e.target.value))} />
          </div>
        </div>
        <label className="mr-check">
          <input type="checkbox" checked={!!cfg.only_when_changes} onChange={(e) => set("only_when_changes", e.target.checked)} />
          <span><span className="strong">{t("mailrep.only_changes")}</span><br />
            <span className="small muted">{t("mailrep.only_changes_hint")}</span></span>
        </label>
      </section>

      {/* What each kind of mail carries */}
      <section className="card stack mr-card">
        <div className="strong mr-title">{t("mailrep.content_title")}</div>
        <div className="small muted">{t("mailrep.content_hint")}</div>
        {(kind === "direction" ? ["all"] : ["tribe", "squad"]).map((mk) => {
          const on: string[] = cfg.docs?.[mk] ?? [];
          return (
            <div key={mk} className="mr-doc-row">
              <div className="mr-doc-kind">
                <div className="strong">{t(`mailrep.kind_${mk}`)}</div>
                <div className="small muted">{t(`mailrep.kind_${mk}_hint`)}</div>
              </div>
              <div className="mr-chips">
                {DOC_TYPES.map((d) => (
                  <label key={d} className={`mr-chip${on.includes(d) ? " on" : ""}`}>
                    <input type="checkbox" checked={on.includes(d)}
                           onChange={() => set("docs", { ...cfg.docs, [mk]: on.includes(d) ? on.filter((x) => x !== d) : [...on, d] })} />
                    {t(`mailrep.doc_${d}`)}
                  </label>
                ))}
              </div>
              {on.length === 0 && <div className="small muted">{t("mailrep.no_doc")}</div>}
            </div>
          );
        })}
      </section>

      {/* Who receives what */}
      <section className="card stack mr-card">
        <div className="strong mr-title">{t("mailrep.who_what")}</div>
        {kind === "direction" ? (
          <div className="mr-line">
            <div className="mr-line-head">
              <div><div className="strong">{t("mailrep.direction_line")}</div>
                <div className="small muted">{t("mailrep.direction_hint")}</div></div>
              {lineActions("direction")}
            </div>
            <RecipientList label={t("mailrep.addresses")} list={cfg.recipients ?? []}
                           onChange={(l) => set("recipients", l)} t={t} />
          </div>
        ) : (
          <TribeLines cfg={cfg} set={set} choices={choices} lineActions={lineActions} />
        )}
        <div className="banner small mr-summary">{summarize(t, kind, cfg, choices)}</div>
      </section>

      <div className="inline mr-save">
        <button onClick={save} disabled={busy || !dirty}>{busy ? t("common.saving") : t("action.save")}</button>
        {dirty && <span className="small muted">{t("mailrep.unsaved")}</span>}
        {msg && !dirty && <span className="small" style={{ color: "var(--green)" }}>{msg}</span>}
      </div>

      {/* The plan, as on screen */}
      <section className="card stack mr-card">
        <div className="between" style={{ alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <div className="strong mr-title">{t("mailrep.plan_title")}</div>
          <SendNow qs={qs} line={null} disabled={dirty || !plan?.length} label={t("mailrep.send_all_now")} />
        </div>
        <div className="small muted">
          {t(cfg.enabled ? "mailrep.plan_hint" : "mailrep.plan_hint_off")}
          {dirty ? ` ${t("mailrep.plan_unsaved")}` : ""}
        </div>
        <PlanTable plan={plan} />
      </section>
    </div>
  );
}

/** What is saved: the screen-only fields go, the scheduler's bookkeeping too. */
function strip(c: any): any {
  if (!c) return c;
  const out: any = {};
  for (const [k, v] of Object.entries(c)) if (!k.startsWith("_") && k !== "last_sent_day" && k !== "v") out[k] = v;
  return out;
}

function TribeLines({ cfg, set, choices, lineActions }: {
  cfg: any; set: (k: string, v: any) => void; choices: Choices; lineActions: (line: string) => ReactNode;
}) {
  const { t, role: roleLabel } = useI18n();
  // A built-in persona reads by its role's name, a custom one by its own label.
  const personaName = (p: { key: string; label: string }) =>
    ["admin", "tribe_leader", "squad_leader", "member"].includes(p.key) ? roleLabel(p.key as any) : p.label;
  const leaders = choices.tribe_leaders ?? [];
  const squads = choices.squads ?? [];
  const copies: Copy[] = cfg.copies ?? [];
  const setCopy = (i: number, patch: Partial<Copy>) => set("copies", copies.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const addCopy = (c: Copy) => {
    if (copies.some((x) => x.type === c.type && String(x.value).toLowerCase() === String(c.value).toLowerCase())) return;
    set("copies", [...copies, c]);
  };
  const [email, setEmail] = useState("");
  const toggle = (list: number[], id: number) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const copyName = (c: Copy) =>
    c.type === "persona" ? personaName(choices.personas?.find((p) => p.key === c.value) ?? { key: c.value, label: c.value })
      : c.type === "user" ? (choices.users?.find((u) => u.id === Number(c.value))?.name ?? `#${c.value}`)
        : c.value;

  return (
    <>
      {/* 1. The tribe leader */}
      <div className="mr-line">
        <div className="mr-line-head">
          <div>
            <div className="strong">{t("mailrep.leader_line")}</div>
            <div className="small muted">
              {leaders.length ? leaders.map((l) => l.name).join(", ") : t("mailrep.no_leader")}
            </div>
          </div>
          {lineActions("leader")}
        </div>
        <div className="mr-radio">
          {(["tribe", "per_squad"] as const).map((m) => (
            <label key={m} className={`mr-option${cfg.leader_mode === m ? " on" : ""}`}>
              <input type="radio" name="mr-mode" checked={cfg.leader_mode === m} onChange={() => set("leader_mode", m)} />
              <span><span className="strong">{t(`mailrep.mode_${m}`)}</span><br />
                <span className="small muted">{t(`mailrep.mode_${m}_hint`)}</span></span>
            </label>
          ))}
        </div>
      </div>

      {/* 2. In copy of their own squad's mail */}
      <div className="mr-line">
        <div className="mr-line-head">
          <div>
            <div className="strong">{t("mailrep.roles_line")}</div>
            <div className="small muted">{t("mailrep.roles_hint")}</div>
          </div>
          {lineActions("roles")}
        </div>
        <div className="mr-chips">
          {(["copy_leader", "copy_co_leaders", "copy_contributors"] as const).map((k) => (
            <label key={k} className={`mr-chip${cfg[k] ? " on" : ""}`}>
              <input type="checkbox" checked={!!cfg[k]} onChange={(e) => set(k, e.target.checked)} />
              {t(`mailrep.${k}`)}
            </label>
          ))}
        </div>
      </div>

      {/* 3. Other copies */}
      <div className="mr-line">
        <div>
          <div className="strong">{t("mailrep.copies_line")}</div>
          <div className="small muted">{t("mailrep.copies_hint")}</div>
        </div>
        {copies.length === 0 && <div className="small muted">{t("mailrep.no_copy")}</div>}
        {copies.map((c, i) => (
          <div key={`${c.type}:${c.value}`} className="mr-copy">
            <div className="mr-line-head">
              <div>
                <span className="badge badge-grey">{t(`mailrep.copy_type_${c.type}`)}</span>{" "}
                <span className="strong">{copyName(c)}</span>
              </div>
              <div className="inline" style={{ gap: 6 }}>
                {lineActions(`copy:${i}`)}
                <button type="button" className="btn-ghost btn-sm" aria-label={t("action.delete")}
                        onClick={() => set("copies", copies.filter((_, j) => j !== i))}>✕</button>
              </div>
            </div>
            <div className="mr-copy-what">
              <label htmlFor={`mr-copy-${i}`} className="small muted">{t("mailrep.copy_gets")}</label>
              <select id={`mr-copy-${i}`} className="w-auto" value={c.content}
                      onChange={(e) => setCopy(i, { content: e.target.value as Copy["content"], squad_ids: [] })}>
                <option value="tribe">{t("mailrep.content_tribe")}</option>
                <option value="squads">{t("mailrep.content_squads")}</option>
              </select>
            </div>
            {c.content === "squads" && (
              <div className="mr-chips">
                <span className="small muted">{c.squad_ids.length ? "" : t("mailrep.all_squads")}</span>
                {squads.map((s) => (
                  <label key={s.id} className={`mr-chip${c.squad_ids.includes(s.id) ? " on" : ""}`}>
                    <input type="checkbox" checked={c.squad_ids.includes(s.id)}
                           onChange={() => setCopy(i, { squad_ids: toggle(c.squad_ids, s.id) })} />
                    {s.name}
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
        <div className="mr-add">
          <select className="w-auto" aria-label={t("mailrep.add_persona")} value=""
                  onChange={(e) => e.target.value && addCopy({ type: "persona", value: e.target.value, content: "tribe", squad_ids: [] })}>
            <option value="">+ {t("mailrep.add_persona")}</option>
            {(choices.personas ?? []).map((p) => <option key={p.key} value={p.key}>{personaName(p)}</option>)}
          </select>
          <select className="w-auto" aria-label={t("mailrep.add_user")} value=""
                  onChange={(e) => e.target.value && addCopy({ type: "user", value: Number(e.target.value), content: "tribe", squad_ids: [] })}>
            <option value="">+ {t("mailrep.add_user")}</option>
            {(choices.users ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          <span className="inline" style={{ gap: 6 }}>
            <input className="w-auto" style={{ minWidth: 200 }} value={email} placeholder={t("mailrep.add_email_ph")}
                   aria-label={t("mailrep.add_email")}
                   onChange={(e) => setEmail(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter" && email.includes("@")) { e.preventDefault(); addCopy({ type: "email", value: email.trim(), content: "tribe", squad_ids: [] }); setEmail(""); } }} />
            <button type="button" className="btn-secondary btn-sm" disabled={!email.includes("@")}
                    onClick={() => { addCopy({ type: "email", value: email.trim(), content: "tribe", squad_ids: [] }); setEmail(""); }}>
              {t("mailrep.add_email")}
            </button>
          </span>
        </div>
      </div>

      {/* Which squads the squad mails cover */}
      <div className="mr-line">
        <div>
          <div className="strong">{t("mailrep.squads_line")}</div>
          <div className="small muted">{t("mailrep.squads_hint")}</div>
        </div>
        <div className="mr-chips">
          {squads.map((s) => {
            const on = (cfg.squad_ids ?? []).includes(s.id);
            return (
              <label key={s.id} className={`mr-chip${on ? " on" : ""}`}>
                <input type="checkbox" checked={on} onChange={() => set("squad_ids", toggle(cfg.squad_ids ?? [], s.id))} />
                {s.name}
              </label>
            );
          })}
        </div>
      </div>
    </>
  );
}

/** The whole setting in one sentence. */
function summarize(t: (k: string, v?: any) => string, kind: string, cfg: any, choices: Choices): string {
  if (!cfg.enabled) return t("mailrep.sum_off");
  const days = (cfg.weekdays ?? []).map((d: number) => t(`reporting.day.${WEEKDAY_KEYS[d]}`)).join(", ");
  const when = t("mailrep.sum_when", { days, h: String(cfg.hour ?? 8).padStart(2, "0") });
  if (kind === "direction") {
    return (cfg.recipients ?? []).length
      ? `${when} ${t("mailrep.sum_direction", { who: cfg.recipients.join(", ") })}`
      : t("mailrep.sum_nobody");
  }
  const parts = [t(cfg.leader_mode === "per_squad" ? "mailrep.sum_leader_squads" : "mailrep.sum_leader_tribe")];
  const roles = (["copy_leader", "copy_co_leaders", "copy_contributors"] as const).filter((k) => cfg[k])
    .map((k) => t(`mailrep.${k}`).toLowerCase());
  if (roles.length) parts.push(t("mailrep.sum_roles", { who: roles.join(", ") }));
  const copies: Copy[] = cfg.copies ?? [];
  if (copies.length) parts.push(t("mailrep.sum_copies", { n: copies.length }));
  if ((cfg.squad_ids ?? []).length) {
    parts.push(t("mailrep.sum_squads", { names: cfg.squad_ids.map((id: number) => choices.squads?.find((s) => s.id === id)?.name ?? `#${id}`).join(", ") }));
  }
  return `${when} ${parts.join(" ")}`;
}

/** Preview, recipients, test and send now, for one line of the settings. */
function LineActions({ line, plan, qs, dirty, draft }: {
  line: string; plan: PlanMail[] | null; qs: (extra?: string) => string; dirty: boolean; draft: any;
}) {
  const { t } = useI18n();
  const [preview, setPreview] = useState<any | null>(null);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const mine = (plan ?? []).map((m) => ({ ...m, recipients: m.recipients.filter((r) => r.line === line),
                                           missing: m.missing.filter((x) => x.line === line) }))
    .filter((m) => m.recipients.length || m.missing.length);
  const people = new Set(mine.flatMap((m) => m.recipients.map((r) => r.email.toLowerCase())));
  // The preview follows the screen; a real mail (test, send now) waits for Save.
  const empty = mine.length === 0;
  const off = dirty || empty;
  const why = empty ? t("mailrep.line_empty") : dirty ? t("mailrep.save_first") : undefined;

  async function showPreview() {
    setNote(null);
    try { setPreview(await api.post<any>(`/api/admin/report-config/preview${qs()}`, { line, cfg: draft })); }
    catch (e) { setNote(errorText(e)); }
  }
  async function test() {
    setNote(null);
    try {
      const r = await api.post<any>(`/api/admin/report-config/test${qs()}`, { line });
      setNote(r.ok ? t("mailrep.test_ok", { to: r.to, label: r.label }) : t("report.test_fail") + (r.error ? ` (${r.error})` : ""));
    } catch (e) { setNote(errorText(e)); }
  }

  return (
    <div className="mr-actions">
      <button type="button" className="btn-ghost btn-sm" onClick={() => setOpen((o) => !o)}>
        {t("mailrep.n_recipients", { n: people.size })}{open ? " ▴" : " ▾"}
      </button>
      <button type="button" className="btn-ghost btn-sm" onClick={showPreview} disabled={empty} title={empty ? why : undefined}>{t("mailrep.preview")}</button>
      <button type="button" className="btn-ghost btn-sm" onClick={test} disabled={off} title={why}>{t("mailrep.test_me")}</button>
      <SendNow qs={qs} line={line} disabled={off} label={t("mailrep.send_now")} onDone={setNote} />
      {note && <div className="small muted mr-note">{note}</div>}
      {open && (
        <div className="mr-who small">
          {mine.length === 0 ? <span className="muted">{t("mailrep.line_empty")}</span> : mine.map((m) => (
            <div key={m.key}>
              <span className="strong">{m.label}</span>{t("common.colon")}
              {m.recipients.map((r) => r.name).join(", ")}
              {m.missing.length > 0 && <span style={{ color: "var(--orange)" }}> ({t("mailrep.no_address", { names: m.missing.map((x) => x.name).join(", ") })})</span>}
            </div>
          ))}
        </div>
      )}
      {preview && (
        <Modal width={760} title={preview.subject} onClose={() => setPreview(null)}
               footer={<button className="btn-sm" onClick={() => setPreview(null)}>{t("action.close")}</button>}>
          <div className="stack" style={{ gap: 8 }}>
            <div className="small"><span className="muted">{t("mailrep.to")}</span> {preview.to.join(", ") || "-"}</div>
            {preview.cc.length > 0 && <div className="small"><span className="muted">{t("mailrep.cc")}</span> {preview.cc.join(", ")}</div>}
            <div className="small"><span className="muted">{t("mailrep.attached")}</span>{" "}
              {preview.docs?.length ? preview.docs.map((d: string) => `${t(`mailrep.doc_${d}`)} (PPTX)`).join(", ") : t("mailrep.no_doc")}</div>
            <iframe title={preview.subject} srcDoc={preview.html} sandbox="" className="mr-preview" />
          </div>
        </Modal>
      )}
    </div>
  );
}

/** "Send now", with a second click to confirm (it mails real people). */
function SendNow({ qs, line, disabled, label, onDone }: {
  qs: (extra?: string) => string; line: string | null; disabled: boolean; label: string; onDone?: (msg: string) => void;
}) {
  const { t } = useI18n();
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const say = (m: string) => (onDone ? onDone(m) : setMsg(m));
  async function go() {
    setConfirm(false);
    try {
      const r = await api.post<any>(`/api/admin/report-config/send-now${qs()}`, line ? { line } : {});
      say(t("mailrep.sent_n", { n: r.sent }) + (r.failed?.length ? `, ${t("reporting.send_leaders_failed", { names: r.failed.join(", ") })}` : "")
          + (r.missing?.length ? `, ${t("mailrep.no_address", { names: r.missing.join(", ") })}` : ""));
    } catch (e) { say(errorText(e)); }
  }
  return confirm ? (
    <span className="inline" style={{ gap: 4 }}>
      <button type="button" className="btn-sm" onClick={go}>{t("mailrep.confirm_send")}</button>
      <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirm(false)}>{t("action.cancel")}</button>
    </span>
  ) : (
    <>
      <button type="button" className={line ? "btn-ghost btn-sm" : "btn-secondary btn-sm"} disabled={disabled}
              onClick={() => setConfirm(true)}>{label}</button>
      {msg && <span className="small muted">{msg}</span>}
    </>
  );
}

/** Every mail of the schedule: the document, To and copy. */
function PlanTable({ plan }: { plan: PlanMail[] | null }) {
  const { t } = useI18n();
  if (plan === null) return <Spinner />;
  if (plan.length === 0) return <div className="small muted">{t("mailrep.plan_empty")}</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="mr-plan">
        <thead><tr><th>{t("mailrep.h_doc")}</th><th>{t("mailrep.h_attached")}</th><th>{t("mailrep.h_to")}</th><th>{t("mailrep.h_cc")}</th></tr></thead>
        <tbody>
          {plan.map((m) => (
            <tr key={m.key}>
              <td><span className="strong">{m.label}</span><div className="small muted">{t(`mailrep.kind_${m.kind}`)}</div></td>
              <td className="small">{m.docs?.length ? m.docs.map((d) => t(`mailrep.doc_${d}`)).join(", ") : <span className="muted">{t("mailrep.no_doc_short")}</span>}</td>
              <td className="small">{m.recipients.filter((r) => r.role === "to").map((r) => r.name).join(", ") || "-"}</td>
              <td className="small">
                {m.recipients.filter((r) => r.role === "cc").map((r) => r.name).join(", ") || "-"}
                {m.missing.length > 0 && <div style={{ color: "var(--orange)" }}>{t("mailrep.no_address", { names: m.missing.map((x) => x.name).join(", ") })}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
