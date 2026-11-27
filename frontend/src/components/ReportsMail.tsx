// ReportsMail: Administration > Reports by email.
//
// Two tabs:
//   * Scheduled reports: the diffusions, one card each (who, what, when, next
//     and last send), with Preview, Test, Send now and History on the card. A
//     diffusion opens in a window to edit it, its mail previewed live on the
//     right. The admin sees every one, the Direction's included; a tribe leader
//     (anyone holding the "report" tab) those of their own tribe.
//   * Change alerts: the change notices (admin only).
//
// The server computes who receives which mail (app/mailplan.py) from the
// settings being edited, so the list and the preview follow every click before
// saving. A real mail (test, send now) goes from what is saved.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, errorText } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { ChangeNotifyAdmin } from "../pages/admin/configuration";
import { ErrorBanner, Modal, Spinner, Toggle } from "./ui";
import { StepItem, StepLayout } from "./StepLayout";

export const WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/** The documents a mail can carry (reportconfig.DOC_TYPES). */
const DOC_TYPES = ["weekly", "dashboard", "roadmap", "dependencies"] as const;

type Recipient = { email: string; name: string; line: string; role: "to" | "cc" };
type PlanMail = { key: string; kind: "tribe" | "squad" | "all"; label: string; squad_id: number | null;
                  docs: string[]; recipients: Recipient[]; missing: { name: string; line: string }[] };
type Copy = { type: "persona" | "user" | "email"; value: any; content: "tribe" | "squads"; squad_ids: number[] };
type LastSend = { at: string; trigger: string; sent: number; attempted: number; failed: string[] };
type Diffusion = {
  id: number | null; name: string; tribe_id: number | null; enabled: boolean; weekdays: number[]; hour: number; minute?: number;
  since_days: number; only_when_changes: boolean; last_sent_day?: string; copies: Copy[];
  docs: Record<string, string[]>;
  body?: Record<string, string[]>;
  leader_tribe?: boolean; leader_squads?: boolean; squad_ids?: number[];
  copy_leader?: boolean; copy_co_leaders?: boolean; copy_contributors?: boolean;
  _tribe_name?: string | null; _next?: string | null; _last?: LastSend | null; _mails?: number;
  _to?: string[]; _cc?: string[]; _missing?: string[];
};
type Board = { diffusions: Diffusion[]; tribes: { id: number; name: string }[]; direction: boolean; smtp: boolean };
type Choices = { squads: { id: number; name: string }[]; users: { id: number; name: string; email: string | null }[];
                 personas: { key: string; label: string }[]; tribe_leaders: { id: number; name: string }[] };
type Send = { at: string; trigger: string; sent: number; attempted: number; recipients: number;
              failed: string[]; missing: string[]; error: string | null };

const ROLE_KEYS = ["copy_leader", "copy_co_leaders", "copy_contributors"] as const;

// The blocks of a mail's body (reportconfig.BODY_SECTIONS), in their order in the
// mail. One list for every mail of a diffusion: the server leaves the table of
// squads out of a squad's recap.
const BODY_BLOCKS = ["changes", "kpis", "squads", "key_messages", "late_otds", "kpi_watch", "milestones"];
// A diffusion saved before the choice existed (reportconfig.DEFAULT_BODY).
const DEFAULT_BODY: Record<string, string[]> = {
  tribe: ["changes", "kpis", "squads"], all: ["changes", "kpis", "squads"],
  squad: ["changes", "kpis", "key_messages", "late_otds", "kpi_watch", "milestones"],
};
/** What is sent to the server: the screen-only fields go. */
function strip(c: Diffusion): any {
  const out: any = {};
  for (const [k, v] of Object.entries(c)) if (!k.startsWith("_")) out[k] = v;
  return out;
}

/** A new diffusion of a scope, as the server would create it (reportconfig.defaults). */
function blank(tribeId: number | null): Diffusion {
  const base: Diffusion = { id: null, name: "", tribe_id: tribeId, enabled: true, weekdays: [0], hour: 8, minute: 0,
                            since_days: 7, only_when_changes: false, copies: [], docs: { all: ["weekly"] },
                            body: { all: [...BODY_BLOCKS] } };
  if (tribeId === null) return base;
  return { ...base, docs: { tribe: ["weekly"], squad: ["weekly"] },
           body: { tribe: [...BODY_BLOCKS], squad: [...BODY_BLOCKS] },
           leader_tribe: true, leader_squads: false,
           squad_ids: [], copy_leader: true, copy_co_leaders: false, copy_contributors: false };
}

function useFmt() {
  const { lang, t } = useI18n();
  const locale = lang === "fr" ? "fr-FR" : "en-GB";
  const date = (iso: string, withYear = false) => new Date(iso).toLocaleDateString(locale, {
    timeZone: "Europe/Paris", weekday: "long", day: "numeric", month: "long", ...(withYear ? { year: "numeric" } : {}),
  });
  const time = (iso: string) => new Date(iso).toLocaleTimeString(locale, { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit" });
  const short = (iso: string) => new Date(iso).toLocaleString(locale, {
    timeZone: "Europe/Paris", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const days = (wd: number[]) => {
    if (wd.length === 7) return t("mailrep.every_day");
    if (wd.length === 5 && [0, 1, 2, 3, 4].every((d) => wd.includes(d))) return t("mailrep.weekdays");
    const names = wd.map((d) => t(`mailrep.dayname.${WEEKDAY_KEYS[d]}`));
    return names.length > 1 ? `${names.slice(0, -1).join(", ")} ${t("mailrep.and")} ${names[names.length - 1]}` : names[0];
  };
  const hour = (h: number, m = 0) => (lang === "fr"
    ? `${h} h${m ? ` ${String(m).padStart(2, "0")}` : ""}`
    : `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`);
  return { date, time, short, days, hour };
}

/** A list of names, the first few and "and N others". */
function names(t: (k: string, v?: any) => string, list: string[], max = 3): string {
  if (list.length <= max) return list.join(", ");
  return `${list.slice(0, max).join(", ")} ${t("mailrep.and_others", { n: list.length - max })}`;
}

// ---- The menu ----------------------------------------------------------------------

export function ReportsMailPanel() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState<"diffusions" | "alerts">("diffusions");
  return (
    <div className="stack" style={{ gap: 16 }}>
      {isAdmin && (
        <div className="mr-tabs" role="tablist">
          {(["diffusions", "alerts"] as const).map((k) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k}
                    className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
              {t(`mailrep.tab_${k}`)}
            </button>
          ))}
        </div>
      )}
      {tab === "diffusions" && <DiffusionBoard />}
      {tab === "alerts" && isAdmin && (
        <>
          <div className="small muted">{t("mailrep.intro_alerts")}</div>
          <ChangeNotifyAdmin />
        </>
      )}
    </div>
  );
}

// ---- The cards ---------------------------------------------------------------------

function DiffusionBoard() {
  const { t } = useI18n();
  const [board, setBoard] = useState<Board | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<Diffusion | null>(null);

  const load = () => api.get<Board>("/api/admin/diffusions").then(setBoard).catch((e) => setErr(errorText(e)));
  useEffect(() => { load(); }, []);

  if (err && !board) return <ErrorBanner message={err} />;
  if (!board) return <Spinner />;
  // The tribes first (the usual case), "every tribe" last.
  const scopes = [...board.tribes.map((x) => ({ id: x.id as number | null, name: x.name })),
                  ...(board.direction ? [{ id: null as number | null, name: t("mailrep.direction") }] : [])];
  // "New mailing" opens the editor at once, on the first tribe: its first step picks the tribe.
  const create = () => scopes.length && setEditing(blank(scopes[0].id));
  const sorted = [...board.diffusions].sort((a, b) =>
    (a.tribe_id === null ? "" : a._tribe_name ?? "").localeCompare(b.tribe_id === null ? "" : b._tribe_name ?? "")
    || (a.id ?? 0) - (b.id ?? 0));

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="mr-board-head">
        <div className="small muted">{t("mailrep.intro_diffusions")}</div>
        <button type="button" onClick={create} disabled={scopes.length === 0}>
          + {t("mailrep.new")}
        </button>
      </div>
      {!board.smtp && <div className="banner banner-amber small">{t("mailrep.no_smtp")}</div>}
      {err && <ErrorBanner message={err} />}
      {scopes.length === 0 && <div className="small muted">{t("mailrep.no_tribe")}</div>}
      {sorted.length === 0 && scopes.length > 0 ? (
        <div className="card mr-empty">
          <div className="strong">{t("mailrep.empty_title")}</div>
          <div className="small muted">{t("mailrep.empty_hint")}</div>
          <div><button type="button" onClick={create}>+ {t("mailrep.new")}</button></div>
        </div>
      ) : (
        <div className="mr-cards">
          {sorted.map((d) => (
            <DiffusionCard key={d.id} d={d} smtp={board.smtp} onEdit={() => setEditing(d)} onChanged={load} />
          ))}
        </div>
      )}
      {editing && (
        <DiffusionEditor initial={editing} scopes={scopes}
                         onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

function defaultName(t: (k: string) => string, d: Diffusion) {
  return d.name || t("mailrep.default_name");
}

function DiffusionCard({ d, smtp, onEdit, onChanged }: {
  d: Diffusion; smtp: boolean; onEdit: () => void; onChanged: () => void;
}) {
  const { t } = useI18n();
  const f = useFmt();
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [preview, setPreview] = useState(false);
  const [hist, setHist] = useState(false);
  const [confirm, setConfirm] = useState<"send" | "delete" | null>(null);
  const docs = Array.from(new Set(Object.values(d.docs ?? {}).flat()));
  const empty = (d._mails ?? 0) === 0;

  async function toggle() {
    setBusy(true);
    try { await api.put(`/api/admin/diffusions/${d.id}`, { enabled: !d.enabled }); onChanged(); }
    catch (e) { setNote({ ok: false, text: errorText(e) }); }
    finally { setBusy(false); }
  }
  async function test() {
    setNote(null); setBusy(true);
    try {
      const r = await api.post<any>(`/api/admin/diffusions/${d.id}/test`, {});
      setNote(r.ok ? { ok: true, text: t("mailrep.test_ok", { to: r.to, label: r.label }) }
                   : { ok: false, text: t("report.test_fail") + (r.error ? ` (${r.error})` : "") });
      onChanged();
    } catch (e) { setNote({ ok: false, text: errorText(e) }); }
    finally { setBusy(false); }
  }
  async function sendNow() {
    setConfirm(null); setNote(null); setBusy(true); setSending(true);
    try {
      const r = await api.post<any>(`/api/admin/diffusions/${d.id}/send-now`, {});
      const parts = [t("mailrep.sent_n", { n: r.sent })];
      if (r.failed?.length) parts.push(t("mailrep.refused", { names: r.failed.join(", ") }));
      if (r.missing?.length) parts.push(t("mailrep.no_address", { names: r.missing.join(", ") }));
      setNote({ ok: !r.failed?.length, text: parts.join(", ") });
      onChanged();
    } catch (e) { setNote({ ok: false, text: errorText(e) }); }
    finally { setBusy(false); setSending(false); }
  }
  async function remove() {
    setConfirm(null);
    try { await api.del(`/api/admin/diffusions/${d.id}`); onChanged(); }
    catch (e) { setNote({ ok: false, text: errorText(e) }); }
  }

  const last = d._last;
  const lastOk = last && last.sent > 0 && !last.failed.length;
  return (
    <article className={`card mr-dcard${d.enabled ? "" : " off"}`}>
      <header className="mr-dcard-head">
        <div style={{ minWidth: 0 }}>
          <div className="mr-dcard-title">{defaultName(t, d)}</div>
          <span className={`badge ${d.tribe_id === null ? "badge-navy" : "badge-grey"}`}>
            {d.tribe_id === null ? t("mailrep.direction") : d._tribe_name}
          </span>
        </div>
        <label className="switch" title={t(d.enabled ? "mailrep.pause" : "mailrep.resume")}>
          <input type="checkbox" checked={d.enabled} disabled={busy} onChange={toggle} />
          <span className="track"><span className="knob" /></span>
          <span className="small">{t(d.enabled ? "mailrep.active" : "mailrep.paused")}</span>
        </label>
      </header>

      <dl className="mr-facts">
        <dt>{t("mailrep.when")}</dt>
        <dd>{f.days(d.weekdays)}, {f.hour(d.hour, d.minute)}{d.only_when_changes ? ` (${t("mailrep.if_new")})` : ""}</dd>
        <dt>{t("mailrep.what")}</dt>
        <dd>{docs.length ? docs.map((x) => t(`mailrep.doc_${x}`)).join(", ") : t("mailrep.summary_only")}</dd>
        <dt>{t("mailrep.to")}</dt>
        <dd>{d._to?.length ? names(t, d._to) : <span className="muted">{t("mailrep.nobody")}</span>}</dd>
        {(d._cc?.length ?? 0) > 0 && (<><dt>{t("mailrep.cc")}</dt><dd>{names(t, d._cc!)}</dd></>)}
        {(d._mails ?? 0) > 1 && (<><dt>{t("mailrep.mails")}</dt><dd>{t("mailrep.n_mails", { n: d._mails! })}</dd></>)}
      </dl>
      {(d._missing?.length ?? 0) > 0 && (
        <div className="small mr-warn">{t("mailrep.no_address", { names: d._missing!.join(", ") })}</div>
      )}

      <div className="mr-status small">
        <div>
          {d._next ? (<><span className="muted">{t("mailrep.next")}</span>{" "}
                        <span className="strong">{f.date(d._next)}, {f.time(d._next)}</span></>)
                   : <span className="muted">{t(d.enabled ? "mailrep.never" : "mailrep.paused_long")}</span>}
        </div>
        <button type="button" className="mr-link" onClick={() => setHist(true)}>
          <span className={`dot ${!last ? "dot-grey" : lastOk ? "dot-green" : "dot-red"}`} aria-hidden />{" "}
          {last ? t("mailrep.last", { when: f.short(last.at), what: t(`mailrep.trigger_${last.trigger}`) })
                : t("mailrep.never_sent")}
        </button>
      </div>

      {note && <div className={`small mr-note ${note.ok ? "ok" : "ko"}`} role="status">{note.text}</div>}

      <footer className="mr-dcard-actions">
        <button type="button" className="btn-sm" onClick={onEdit}>{t("action.edit")}</button>
        <button type="button" className="btn-ghost btn-sm" onClick={() => setPreview(true)} disabled={empty}>
          {t("mailrep.preview")}
        </button>
        <button type="button" className="btn-ghost btn-sm" onClick={test} disabled={busy || empty || !smtp}
                title={!smtp ? t("mailrep.no_smtp") : undefined}>{t("mailrep.test_me")}</button>
        {confirm === "send" ? (
          <span className="inline" style={{ gap: 4 }}>
            <button type="button" className="btn-sm" onClick={sendNow}>{t("mailrep.confirm_send")}</button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirm(null)}>{t("action.cancel")}</button>
          </span>
        ) : (
          <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirm("send")}
                  disabled={busy || empty || !smtp}>{t(sending ? "mailrep.sending" : "mailrep.send_now")}</button>
        )}
        <span className="mr-spacer" />
        {confirm === "delete" ? (
          <span className="inline" style={{ gap: 4 }}>
            <button type="button" className="btn-danger btn-sm" onClick={remove}>{t("mailrep.confirm_delete")}</button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirm(null)}>{t("action.cancel")}</button>
          </span>
        ) : (
          <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirm("delete")}>{t("action.delete")}</button>
        )}
      </footer>

      {preview && (
        <Modal width={860} title={t("mailrep.preview_of", { name: defaultName(t, d) })} onClose={() => setPreview(false)}
               footer={<button className="btn-sm" onClick={() => setPreview(false)}>{t("action.close")}</button>}>
          <LivePreview cfg={d} />
        </Modal>
      )}
      {hist && <HistoryModal d={d} onClose={() => setHist(false)} />}
    </article>
  );
}

function HistoryModal({ d, onClose }: { d: Diffusion; onClose: () => void }) {
  const { t } = useI18n();
  const f = useFmt();
  const [sends, setSends] = useState<Send[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.get<{ sends: Send[] }>(`/api/admin/diffusions/${d.id}/history`).then((r) => setSends(r.sends))
      .catch((e) => setErr(errorText(e)));
  }, [d.id]);
  return (
    <Modal width={760} title={t("mailrep.history_of", { name: defaultName(t, d) })} onClose={onClose}
           footer={<button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}>
      {err ? <ErrorBanner message={err} /> : sends === null ? <Spinner /> : sends.length === 0 ? (
        <div className="small muted">{t("mailrep.history_empty")}</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="mr-hist">
            <thead><tr><th>{t("mailrep.h_when")}</th><th>{t("mailrep.h_how")}</th><th>{t("mailrep.h_result")}</th></tr></thead>
            <tbody>
              {sends.map((s, i) => {
                const ok = s.sent > 0 && !s.failed.length;
                const nothing = s.attempted === 0;
                return (
                  <tr key={i}>
                    <td className="small">{f.short(s.at)}</td>
                    <td className="small">{t(`mailrep.trigger_${s.trigger}`)}</td>
                    <td className="small">
                      <span className={`dot ${nothing ? "dot-grey" : ok ? "dot-green" : "dot-red"}`} aria-hidden />{" "}
                      {nothing ? t("mailrep.nothing_new")
                        : t("mailrep.result", { sent: s.sent, attempted: s.attempted, people: s.recipients })}
                      {s.failed.length > 0 && <div style={{ color: "var(--red)" }}>{t("mailrep.refused", { names: s.failed.join(", ") })}</div>}
                      {s.error && <div className="muted">{s.error}</div>}
                      {s.missing.length > 0 && <div style={{ color: "var(--orange)" }}>{t("mailrep.no_address", { names: s.missing.join(", ") })}</div>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}

// ---- The editor --------------------------------------------------------------------

function DiffusionEditor({ initial, scopes, onClose, onSaved }: {
  initial: Diffusion; scopes: { id: number | null; name: string }[]; onClose: () => void; onSaved: () => void;
}) {
  const { t, lang } = useI18n();
  const f = useFmt();
  const [cfg, setCfg] = useState<Diffusion>(initial);
  const [choices, setChoices] = useState<Choices | null>(null);
  const [plan, setPlan] = useState<PlanMail[] | null>(null);
  const [pick, setPick] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [at, setAtRaw] = useState(0);
  // A new mailing ticks a step once it has been passed; a saved one is complete.
  const [reached, setReached] = useState(initial.id === null ? 0 : 4);
  const setAt = (i: number) => { setAtRaw(i); setReached((r) => Math.max(r, i)); };
  const seen = (i: number) => initial.id !== null || i < reached;
  const direction = cfg.tribe_id === null;
  const set = <K extends keyof Diffusion>(k: K, v: Diffusion[K]) => setCfg((p) => ({ ...p, [k]: v }));
  const draftKey = JSON.stringify(strip(cfg));
  const dirty = draftKey !== JSON.stringify(strip(initial)) || initial.id === null;
  const scopeName = scopes.find((x) => x.id === cfg.tribe_id)?.name ?? "";
  // A new mailing changes tribe freely: the recipients start again from that
  // tribe's defaults, the name and the calendar stay.
  const pickScope = (raw: string) => {
    const tid = raw === "all" ? null : Number(raw);
    setChoices(null);
    setCfg((p) => ({ ...blank(tid), name: p.name, enabled: p.enabled, weekdays: p.weekdays, hour: p.hour, minute: p.minute,
                     only_when_changes: p.only_when_changes }));
  };

  useEffect(() => {
    const q = cfg.tribe_id === null ? "" : `?tribe_id=${cfg.tribe_id}`;
    api.get<Choices>(`/api/admin/diffusions/choices${q}`).then(setChoices).catch((e) => setErr(errorText(e)));
  }, [cfg.tribe_id]);
  // Who receives what, for the settings as they are on screen (a short pause groups the clicks).
  useEffect(() => {
    const h = setTimeout(() => {
      api.post<{ mails: PlanMail[] }>("/api/admin/diffusions/plan", { cfg: strip(cfg) })
        .then((r) => setPlan(r.mails)).catch(() => setPlan([]));
    }, 250);
    return () => clearTimeout(h);
  }, [draftKey]);
  useEffect(() => {
    if (plan && !plan.some((m) => m.key === pick)) setPick(plan[0]?.key ?? null);
  }, [plan]);

  async function save() {
    setBusy(true); setErr(null);
    try {
      if (cfg.id === null) await api.post("/api/admin/diffusions", strip(cfg));
      else await api.put(`/api/admin/diffusions/${cfg.id}`, strip(cfg));
      onSaved();
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  const docsKinds = direction ? ["all"] : ["tribe", "squad"];
  // What each step holds, shown under it in the menu: the whole set-up at a glance.
  const people = new Set((plan ?? []).flatMap((m) => m.recipients.map((r) => r.email.toLowerCase()))).size;
  const docCount = new Set(Object.values(cfg.docs ?? {}).flat()).size;
  const steps: StepItem[] = [
    { key: "scope", title: t("mailrep.step_scope"), meta: scopeName, done: seen(0) },
    { key: "when", title: t("mailrep.step_when"), done: seen(1) && cfg.weekdays.length > 0,
      meta: cfg.enabled ? `${f.days(cfg.weekdays)}, ${f.hour(cfg.hour, cfg.minute)}` : t("mailrep.paused") },
    { key: "who", title: t("mailrep.step_who"), done: seen(2) && people > 0,
      meta: plan ? t("mailrep.n_people_mails", { p: people, n: plan.length }) : undefined },
    { key: "body", title: t("mailrep.step_body"), done: seen(3),
      meta: t("mailrep.n_blocks", { n: shownBody(cfg, docsKinds).length }) },
    { key: "what", title: t("mailrep.step_what"), done: seen(4),
      meta: docCount ? t("mailrep.n_docs", { n: docCount }) : t("mailrep.summary_short") },
  ];
  const last = at === steps.length - 1;
  const saveBtn = (primary: boolean) => (
    <button type="button" className={primary ? "" : "btn-ghost"} onClick={save} disabled={busy}>
      {busy ? t("common.saving") : t(cfg.id === null ? "mailrep.create" : "action.save")}
    </button>
  );
  const footer = (
    <div className="mr-edit-foot">
      <button type="button" className="btn-ghost" onClick={onClose}>{t("action.cancel")}</button>
      <span className="mr-edit-sum small muted">{t("mailrep.step_n", { n: at + 1, total: steps.length })}</span>
      {at > 0 && <button type="button" className="btn-ghost" onClick={() => setAt(at - 1)}>{t("mailrep.prev")}</button>}
      {!last && cfg.id !== null && saveBtn(false)}
      {last ? saveBtn(true) : <button type="button" onClick={() => setAt(at + 1)}>{t("mailrep.next_step")}</button>}
    </div>
  );

  return (
    <Modal width={1440} dirty={dirty} onClose={onClose} footer={footer}
           title={cfg.id === null ? t("mailrep.new") : `${defaultName(t, initial)} : ${scopeName}`}>
      {err && <ErrorBanner message={err} />}
      <div className="mr-edit">
        <StepLayout steps={steps} at={at} onGo={setAt} ariaLabel={t("mailrep.steps")}
                    desc={t(`mailrep.desc_${steps[at].key}`)}
                    aside={steps[at].key === "when" ? (
                      <label className="switch">
                        <input type="checkbox" checked={cfg.enabled} onChange={(e) => set("enabled", e.target.checked)} />
                        <span className="track"><span className="knob" /></span>
                        <span className="small">{t(cfg.enabled ? "mailrep.active" : "mailrep.paused")}</span>
                      </label>) : undefined}>
          {at === 0 && (<div className="mr-step-body">
            {cfg.id === null ? (
              <>
                <label htmlFor="mr-scope">{t("mailrep.scope_label")}</label>
                <select id="mr-scope" value={cfg.tribe_id === null ? "all" : String(cfg.tribe_id)}
                        onChange={(e) => pickScope(e.target.value)}>
                  {scopes.map((x) => (
                    <option key={String(x.id)} value={x.id === null ? "all" : String(x.id)}>
                      {x.id === null ? t("mailrep.scope_all_option") : x.name}
                    </option>
                  ))}
                </select>
              </>
            ) : (
              <div><span className="badge badge-navy">{scopeName}</span></div>
            )}
            <label htmlFor="mr-name">{t("mailrep.name")}</label>
            <input id="mr-name" value={cfg.name} maxLength={80} placeholder={t("mailrep.default_name")}
                   onChange={(e) => set("name", e.target.value)} />
          </div>)}

          {at === 1 && (<div className="mr-step-body">
            <div className="mr-when">
              <div className="day-pick" role="group" aria-label={t("reporting.days")}>
                {WEEKDAY_KEYS.map((k, i) => {
                  const on = cfg.weekdays.includes(i);
                  return (
                    <button type="button" key={k} aria-pressed={on} className={`day-chip${on ? " on" : ""}`}
                            onClick={() => set("weekdays", on ? cfg.weekdays.filter((x) => x !== i) : [...cfg.weekdays, i].sort())}>
                      {t(`reporting.day.${k}`)}
                    </button>
                  );
                })}
              </div>
              <div className="mr-hour">
                <span className="strong small">{t("mailrep.at")}</span>
                <Stepper value={cfg.hour} max={23} step={1} label={t("mailrep.hours")}
                         onChange={(v) => set("hour", v)} />
                <span className="mr-time-sep" aria-hidden>{lang === "fr" ? "h" : ":"}</span>
                <Stepper value={cfg.minute ?? 0} max={55} step={5} label={t("mailrep.minutes")}
                         onChange={(v) => set("minute", v)} />
                <span className="small muted">{t("mailrep.paris")}</span>
              </div>
            </div>
            <Toggle checked={cfg.only_when_changes} onChange={(v) => set("only_when_changes", v)}>
              <span><span className="strong">{t("mailrep.only_changes")}</span><br />
                <span className="small muted" style={{ fontWeight: 400 }}>{t("mailrep.only_changes_hint")}</span></span>
            </Toggle>
          </div>)}

          {at === 2 && (<div className="mr-step-body">
            {!choices ? <Spinner /> : direction ? (
              <Others cfg={cfg} set={set} choices={choices} direction />
            ) : (
              <TribeRecipients cfg={cfg} set={set} choices={choices} />
            )}
          </div>)}

          {at === 3 && (<div className="mr-step-body">
            <BodyPicker blocks={shownBody(cfg, docsKinds)}
                        onChange={(b) => set("body", Object.fromEntries(docsKinds.map((k) => [k, b])))} />
          </div>)}

          {at === 4 && (<div className="mr-step-body">
            {docsKinds.map((mk) => {
              const on: string[] = cfg.docs?.[mk] ?? [];
              const used = plan === null || mk === "all" || plan.some((m) => m.kind === mk);
              return (
                <div key={mk} className={`mr-doc-row${used ? "" : " unused"}`}>
                  <div className="strong small">{t(`mailrep.kind_${mk}`)}
                    {!used && <span className="muted"> ({t("mailrep.kind_unused")})</span>}</div>
                  <div className="mr-chips">
                    {DOC_TYPES.map((d) => (
                      <button type="button" key={d} aria-pressed={on.includes(d)} className={`mr-chip${on.includes(d) ? " on" : ""}`}
                              onClick={() => set("docs", { ...cfg.docs, [mk]: on.includes(d) ? on.filter((x) => x !== d) : [...on, d] })}>
                        {t(`mailrep.doc_${d}`)}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>)}
        </StepLayout>

        <aside className="mr-edit-side">
          <div className="mr-side-title">{t("mailrep.who_what")}</div>
          {plan === null ? <Spinner /> : plan.length === 0 ? (
            <div className="small muted mr-side-empty">{t("mailrep.plan_empty")}</div>
          ) : (
            <div className="mr-mails" role="listbox" aria-label={t("mailrep.who_what")}>
              {plan.map((m) => {
                const to = m.recipients.filter((r) => r.role === "to").map((r) => r.name);
                const cc = m.recipients.filter((r) => r.role === "cc").map((r) => r.name);
                return (
                  <button type="button" key={m.key} role="option" aria-selected={pick === m.key}
                          className={`mr-mail${pick === m.key ? " on" : ""}`} onClick={() => setPick(m.key)}>
                    <span className="mr-mail-head">
                      <span className="strong">{m.label}</span>
                      <span className="small muted">{t(`mailrep.kind_${m.kind}`)}</span>
                    </span>
                    <span className="small"><span className="muted">{t("mailrep.to")} </span>{names(t, to, 2) || "-"}</span>
                    {cc.length > 0 && <span className="small"><span className="muted">{t("mailrep.cc")} </span>{names(t, cc, 2)}</span>}
                    {m.missing.length > 0 && <span className="small mr-warn">{t("mailrep.no_address", { names: m.missing.map((x) => x.name).join(", ") })}</span>}
                  </button>
                );
              })}
            </div>
          )}
          {plan && plan.length > 0 && <LivePreview cfg={cfg} mailKey={pick} />}
        </aside>
      </div>
    </Modal>
  );
}

function bodyOf(cfg: Diffusion, kind: string): string[] {
  return cfg.body?.[kind] ?? DEFAULT_BODY[kind];
}

/** The one list the screen shows: every block ticked for one kind of mail or another. */
function shownBody(cfg: Diffusion, kinds: string[]): string[] {
  const on = new Set(kinds.flatMap((k) => bodyOf(cfg, k)));
  return BODY_BLOCKS.filter((b) => on.has(b));
}

/** The blocks of the mail, ticked by hand, in the order the mail shows them. */
function BodyPicker({ blocks, onChange }: { blocks: string[]; onChange: (b: string[]) => void }) {
  const { t } = useI18n();
  const toggle = (b: string) => onChange(BODY_BLOCKS.filter((x) => (x === b ? !blocks.includes(b) : blocks.includes(x))));
  return (
    <div className="mr-blocks">
      {BODY_BLOCKS.map((b, i) => (
        <label key={b} className={`mr-option${blocks.includes(b) ? " on" : ""}`}>
          <input type="checkbox" checked={blocks.includes(b)} onChange={() => toggle(b)} />
          <span className="mr-block-n" aria-hidden>{i + 1}</span>
          <span><span className="strong">{t(`mailrep.block_${b}`)}</span><br />
            <span className="small muted">{t(`mailrep.block_${b}_hint`)}</span></span>
        </label>
      ))}
      {blocks.length === 0 && <div className="small muted">{t("mailrep.body_empty")}</div>}
    </div>
  );
}


/** A number changed with - and + (wraps around: 23 + 1 gives 0). */
function Stepper({ value, max, step, label, onChange }: {
  value: number; max: number; step: number; label: string; onChange: (v: number) => void;
}) {
  const { t } = useI18n();
  const size = max + step;
  const go = (d: number) => onChange((value + d * step + size) % size);
  return (
    <span className="mr-stepper" role="group" aria-label={label}>
      <button type="button" className="mr-step-btn" onClick={() => go(-1)} aria-label={`${label} ${t("mailrep.less")}`}>-</button>
      <span className="mr-step-val" aria-live="polite">{String(value).padStart(2, "0")}</span>
      <button type="button" className="mr-step-btn" onClick={() => go(1)} aria-label={`${label} ${t("mailrep.more")}`}>+</button>
    </span>
  );
}

type Setter = <K extends keyof Diffusion>(k: K, v: Diffusion[K]) => void;

function TribeRecipients({ cfg, set, choices }: { cfg: Diffusion; set: Setter; choices: Choices }) {
  const { t } = useI18n();
  const leaders = choices.tribe_leaders;
  const onTribe = !!cfg.leader_tribe && !cfg.leader_squads;
  const squadIds = cfg.squad_ids ?? [];
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="mr-group">
        <div className="mr-group-head">
          <span className="strong">{t("mailrep.leader_line")}</span>
          <span className="small muted">{leaders.length ? leaders.map((l) => l.name).join(", ") : t("mailrep.no_leader")}</span>
        </div>
        <div className="mr-options">
          {(["leader_tribe", "leader_squads"] as const).map((k) => (
            <label key={k} className={`mr-option${cfg[k] ? " on" : ""}`}>
              <input type="checkbox" checked={!!cfg[k]} onChange={(e) => set(k, e.target.checked)} />
              <span><span className="strong">{t(`mailrep.${k}`)}</span><br />
                <span className="small muted">{t(`mailrep.${k}_hint`)}</span></span>
            </label>
          ))}
        </div>
      </div>

      <div className="mr-group">
        <div className="mr-group-head">
          <span className="strong">{t("mailrep.roles_line")}</span>
          <span className="small muted">{t(onTribe ? "mailrep.roles_on_tribe" : "mailrep.roles_on_squad")}</span>
        </div>
        <div className="mr-chips">
          {ROLE_KEYS.map((k) => (
            <button type="button" key={k} aria-pressed={!!cfg[k]} className={`mr-chip${cfg[k] ? " on" : ""}`}
                    onClick={() => set(k, !cfg[k])}>
              {t(`mailrep.${k}`)}
            </button>
          ))}
        </div>
      </div>

      <Others cfg={cfg} set={set} choices={choices} />

      <details className="mr-more" open={squadIds.length > 0}>
        <summary>{t("mailrep.squads_line")} <span className="small muted">
          ({squadIds.length ? t("mailrep.n_squads", { n: squadIds.length }) : t("mailrep.all_squads")})</span></summary>
        <div className="small muted">{t("mailrep.squads_hint")}</div>
        <div className="mr-chips">
          {choices.squads.map((s) => {
            const on = squadIds.includes(s.id);
            return (
              <button type="button" key={s.id} aria-pressed={on} className={`mr-chip${on ? " on" : ""}`}
                      onClick={() => set("squad_ids", on ? squadIds.filter((x) => x !== s.id) : [...squadIds, s.id])}>
                {s.name}
              </button>
            );
          })}
        </div>
      </details>
    </div>
  );
}

/** The other recipients: people, personas and addresses, each with what it receives. */
function Others({ cfg, set, choices, direction = false }: { cfg: Diffusion; set: Setter; choices: Choices; direction?: boolean }) {
  const { t, role: roleLabel } = useI18n();
  const copies = cfg.copies;
  const personaName = (key: string) => {
    if (["admin", "tribe_leader", "squad_leader", "member"].includes(key)) return roleLabel(key as any);
    return choices.personas.find((p) => p.key === key)?.label ?? key;
  };
  const copyName = (c: Copy) =>
    c.type === "persona" ? personaName(String(c.value))
      : c.type === "user" ? (choices.users.find((u) => u.id === Number(c.value))?.name ?? `#${c.value}`)
        : (choices.users.find((u) => (u.email ?? "").toLowerCase() === String(c.value).toLowerCase())?.name || String(c.value));
  const setCopy = (i: number, patch: Partial<Copy>) => set("copies", copies.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const add = (c: Copy) => {
    if (copies.some((x) => x.type === c.type && String(x.value).toLowerCase() === String(c.value).toLowerCase())) return;
    set("copies", [...copies, c]);
  };
  return (
    <div className="mr-group">
      <div className="mr-group-head">
        <span className="strong">{t(direction ? "mailrep.direction_people" : "mailrep.copies_line")}</span>
        <span className="small muted">{t(direction ? "mailrep.direction_hint" : "mailrep.copies_hint")}</span>
      </div>
      {copies.length > 0 && (
        <ul className="mr-people">
          {copies.map((c, i) => (
            <li key={`${c.type}:${c.value}`} className="mr-person">
              <div className="mr-person-head">
                <span className="badge badge-grey">{t(`mailrep.copy_type_${c.type}`)}</span>
                <span className="strong mr-person-name">{copyName(c)}</span>
                {!direction && (
                  <select className="w-auto mr-person-what" aria-label={t("mailrep.copy_gets")} value={c.content}
                          onChange={(e) => setCopy(i, { content: e.target.value as Copy["content"], squad_ids: [] })}>
                    <option value="tribe">{t("mailrep.content_tribe")}</option>
                    <option value="squads">{t("mailrep.content_squads")}</option>
                  </select>
                )}
                <button type="button" className="btn-ghost btn-sm" aria-label={t("action.delete")}
                        onClick={() => set("copies", copies.filter((_, j) => j !== i))}>✕</button>
              </div>
              {!direction && c.content === "squads" && (
                <div className="mr-chips mr-person-squads">
                  <span className="small muted">{c.squad_ids.length ? "" : t("mailrep.all_squads")}</span>
                  {choices.squads.map((s) => {
                    const on = c.squad_ids.includes(s.id);
                    return (
                      <button type="button" key={s.id} aria-pressed={on} className={`mr-chip sm${on ? " on" : ""}`}
                              onClick={() => setCopy(i, { squad_ids: on ? c.squad_ids.filter((x) => x !== s.id) : [...c.squad_ids, s.id] })}>
                        {s.name}
                      </button>
                    );
                  })}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <AddRecipient choices={choices} personaName={personaName} onAdd={add} />
    </div>
  );
}

/** One field: type a name, a persona or an address, pick it in the list. */
function AddRecipient({ choices, personaName, onAdd }: {
  choices: Choices; personaName: (k: string) => string; onAdd: (c: Copy) => void;
}) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const options = useMemo(() => {
    const s = norm(q.trim());
    const out: { label: string; meta: string; copy: Copy }[] = [];
    if (s.includes("@") && /^[^\s@]+@[^\s@]+$/.test(q.trim())) {
      out.push({ label: q.trim(), meta: t("mailrep.copy_type_email"), copy: { type: "email", value: q.trim(), content: "tribe", squad_ids: [] } });
    }
    for (const p of choices.personas) {
      const name = personaName(p.key);
      if (!s || norm(name).includes(s)) out.push({ label: name, meta: t("mailrep.copy_type_persona"),
                                                  copy: { type: "persona", value: p.key, content: "tribe", squad_ids: [] } });
    }
    for (const u of choices.users) {
      if (!s || norm(u.name).includes(s) || norm(u.email ?? "").includes(s)) {
        out.push({ label: u.name, meta: u.email ?? "", copy: { type: "user", value: u.id, content: "tribe", squad_ids: [] } });
      }
    }
    return out.slice(0, 12);
  }, [q, choices]);
  useEffect(() => setHi(0), [q]);
  useEffect(() => {
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);
  const choose = (i: number) => { const o = options[i]; if (!o) return; onAdd(o.copy); setQ(""); setOpen(false); };
  return (
    <div className="mr-add" ref={box}>
      <input value={q} placeholder={t("mailrep.add_ph")} aria-label={t("mailrep.add")} role="combobox"
             aria-expanded={open} aria-autocomplete="list"
             onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
             onKeyDown={(e) => {
               if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setHi((h) => Math.min(h + 1, options.length - 1)); }
               else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
               else if (e.key === "Enter") { e.preventDefault(); choose(hi); }
               else if (e.key === "Escape") { e.stopPropagation(); setOpen(false); }
             }} />
      {open && options.length > 0 && (
        <ul className="mr-suggest" role="listbox">
          {options.map((o, i) => (
            <li key={`${o.copy.type}:${o.copy.value}`} role="option" aria-selected={i === hi}
                className={i === hi ? "on" : ""} onMouseDown={(e) => { e.preventDefault(); choose(i); }}
                onMouseEnter={() => setHi(i)}>
              <span>{o.label}</span><span className="small muted">{o.meta}</span>
            </li>
          ))}
        </ul>
      )}
      {open && q.trim() && options.length === 0 && (
        <div className="mr-suggest small muted" style={{ padding: "8px 10px" }}>{t("mailrep.add_none")}</div>
      )}
    </div>
  );
}

/** One mail of the settings, as it will be received (follows the settings on screen). */
function LivePreview({ cfg, mailKey }: { cfg: Diffusion; mailKey?: string | null }) {
  const { t } = useI18n();
  const [mail, setMail] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const key = JSON.stringify(strip(cfg)) + (mailKey ?? "");
  useEffect(() => {
    setLoading(true);
    const h = setTimeout(() => {
      api.post<any>("/api/admin/diffusions/preview", { cfg: strip(cfg), key: mailKey ?? null })
        .then((m) => { setMail(m); setErr(null); }).catch((e) => { setMail(null); setErr(errorText(e)); })
        .finally(() => setLoading(false));
    }, 500);
    return () => clearTimeout(h);
  }, [key]);
  if (err) return <div className="small muted">{err}</div>;
  if (!mail) return <Spinner />;
  return (
    <div className={`mr-preview-wrap${loading ? " loading" : ""}`}>
      <div className="mr-envelope small">
        <div className="strong mr-subject">{mail.subject}</div>
        <div><span className="muted">{t("mailrep.to")}</span> {mail.to.join(", ") || "-"}</div>
        {mail.cc.length > 0 && <div><span className="muted">{t("mailrep.cc")}</span> {mail.cc.join(", ")}</div>}
        <div><span className="muted">{t("mailrep.attached")}</span>{" "}
          {mail.docs?.length ? mail.docs.map((d: string) => `${t(`mailrep.doc_${d}`)} (PPTX)`).join(", ") : t("mailrep.summary_only")}</div>
      </div>
      <iframe title={mail.subject} srcDoc={mail.html} sandbox="" className="mr-preview" />
    </div>
  );
}
