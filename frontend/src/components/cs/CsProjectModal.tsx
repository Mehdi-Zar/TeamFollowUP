// One Customer Success project, brought up to date step by step (docs/37, section 3).
//
// Only for a project that exists: it is created in its own short window
// (CreateModal in CsProjects). The same guided window as a squad's set-up: the
// steps on the left, each with what it already holds, and Previous / Next at the
// bottom. Few fields, laid flat (no box inside the window). The card is saved
// when the user changes step or closes the window. The history and the points
// to do (one step, Suivi) save each line at once.
import { ReactNode, useCallback, useEffect, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import {
  BILLINGS, CsSettings, HEALTHS, ITEM_KINDS, Item, ItemKind, JOURNAL_KINDS, JournalEntry, JournalKind,
  DiscountKind, Project, RECAP_BY_DEFAULT, fmtAmount, fmtDate, netAmount, todayIso,
} from "../../cs";
import { ErrorBanner, Modal, Spinner } from "../ui";
import { StepLayout } from "../StepLayout";

type StepKey = "project" | "follow" | "billing" | "track";

export default function CsProjectModal({ projectId, settings, onClose, onChanged }: {
  projectId: number; settings: CsSettings; onClose: () => void; onChanged: () => void;
}) {
  const { t, lang } = useI18n();
  const id = projectId;
  const [p, setP] = useState<Project | null>(null);
  const [f, setF] = useState<Project | null>(null);
  const [dirty, setDirty] = useState(false);
  const [at, setAt] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);

  const take = (next: Project) => { setP(next); setF(next); setDirty(false); };
  const load = useCallback((pid: number) => {
    api.get<Project>(`/api/cs/projects/${pid}`).then(take).catch((e) => setErr(errorText(e)));
  }, []);
  useEffect(() => { load(projectId); }, [projectId, load]);

  if (!p || !f) {
    return <Modal width={1100} title={t("cs.title")} onClose={onClose}>{err ? <ErrorBanner message={err} /> : <Spinner />}</Modal>;
  }

  const ro = !p.can_edit;
  const set = <K extends keyof Project>(k: K, v: Project[K]) => { setF((x) => (x ? { ...x, [k]: v } : x)); setDirty(true); };

  /** Saves the card if it changed. False when it could not (the error is shown). */
  async function flush(): Promise<boolean> {
    if (ro || !f) return true;
    if (!dirty) return true;
    if (!f.title.trim()) { setErr(t("cs.wiz.need_title")); setAt(0); return false; }
    setBusy(true); setErr(null);
    try {
      const body = {
        title: f.title, notes: f.notes, client: f.client, requesters: f.requesters,
        stage: f.stage, health: f.health, planned_delivery: f.planned_delivery, actual_delivery: f.actual_delivery,
        build_amount: f.build_amount, billing: f.billing, cost_code: f.cost_code,
        discount_value: f.discount_value, discount_kind: f.discount_kind,
        links: f.links.filter((l) => l.url.trim()),
      };
      await api.put<Project>(`/api/cs/projects/${id}`, body);
      load(id);
      setDirty(false); onChanged();
      return true;
    } catch (e) { setErr(errorText(e)); return false; }
    finally { setBusy(false); }
  }

  const steps: StepKey[] = ["project", "follow", "billing", "track"];
  const last = steps.length - 1;
  const current = steps[Math.min(at, last)];
  async function go(i: number) {
    if (i === at) return;
    if (await flush()) setAt(i);
  }
  async function close() {
    if (await flush()) onClose();
  }
  async function del() {
    try { await api.del(`/api/cs/projects/${id}`); onChanged(); onClose(); }
    catch (e) { setErr(errorText(e)); setConfirmDel(false); }
  }

  const stageLabel = settings.stages.find((s) => s.key === f.stage)?.label ?? f.stage;
  const openItems = (p.items ?? []).filter((i) => !i.done).length;
  const todo = t("cs.meta.todo");
  const meta: Record<StepKey, { text: string; done: boolean }> = {
    project: { text: f.client || todo, done: !!(f.title && f.client && f.requesters) },
    follow: { text: f.health ? `${stageLabel}, ${t(`cs.hv.${f.health}`)}` : stageLabel, done: !!f.health },
    billing: { text: f.build_amount !== null ? `${fmtAmount(netAmount(f.build_amount, f.discount_value, f.discount_kind), lang)}, ${t(`cs.bill.${f.billing}`).toLowerCase()}` : todo,
               done: f.build_amount !== null && !!f.cost_code },
    track: { text: `${t("cs.meta.items", { n: openItems })}, ${t("cs.meta.journal", { n: p.journal?.length ?? 0 })}`,
             done: (p.journal?.length ?? 0) + (p.items?.length ?? 0) > 0 },
  };

  const txt = (k: keyof Project, label: string, opts: { wide?: boolean; list?: string; autoFocus?: boolean } = {}) => (
    <Field label={label} wide={opts.wide}>
      <input value={(f[k] as string | null) ?? ""} disabled={ro} list={opts.list} maxLength={k === "requesters" ? 500 : 255}
             autoFocus={opts.autoFocus} onChange={(e) => set(k, e.target.value as never)} />
    </Field>
  );
  const day = (k: keyof Project, label: string) => (
    <Field label={label}>
      <input type="date" value={(f[k] as string | null) ?? ""} disabled={ro} onChange={(e) => set(k, (e.target.value || null) as never)} />
    </Field>
  );

  const reload = () => { load(id); onChanged(); };

  return (
    <Modal
      width={1100}
      onClose={close}
      title={
        <span className="sq-title">
          <span>{f.title || p.title}</span>
          {p.client && <span className="sq-title-sub">{p.client}</span>}
        </span>
      }
      footer={
        <div className="between" style={{ width: "100%", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {confirmDel ? (
            <div className="inline" style={{ gap: 6 }}>
              <span className="small">{t("cs.delete_confirm", { title: p.title })}</span>
              <button className="btn-danger btn-sm" onClick={del}>{t("action.delete")}</button>
              <button className="btn-secondary btn-sm" onClick={() => setConfirmDel(false)}>{t("action.cancel")}</button>
            </div>
          ) : (
            <span className="inline" style={{ gap: 12 }}>
              {p.can_run && (
                <button className="btn-ghost btn-sm sq-danger" onClick={() => setConfirmDel(true)}>{t("cs.delete")}</button>
              )}
              <span className="small muted">{ro ? t("cs.read_only") : busy ? t("common.saving") : t("cs.wiz.autosave")}</span>
            </span>
          )}
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-secondary btn-sm" disabled={at === 0 || busy} onClick={() => go(at - 1)}>‹ {t("common.prev")}</button>
            {at < last
              ? <button className="btn-sm" disabled={busy} onClick={() => go(at + 1)}>{t("common.next")} ›</button>
              : <button className="btn-sm" disabled={busy} onClick={close}>{t("cs.wiz.finish")}</button>}
          </div>
        </div>
      }
    >
      <StepLayout ariaLabel={t("cs.title")} at={Math.min(at, last)} onGo={go} desc={t(`cs.stepd.${current}`)}
                  steps={steps.map((k) => ({ key: k, title: t(`cs.step.${k}`), meta: meta[k].text, done: meta[k].done }))}>
        {err && <ErrorBanner message={err} />}

        {current === "project" && (
          <div className="cs-form">
            {txt("title", t("cs.f.title"), { wide: true })}
            <Field label={t("cs.f.notes")} wide>
              <textarea rows={4} disabled={ro} value={f.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
            </Field>
            {txt("client", t("cs.f.client"))}
            {txt("requesters", t("cs.f.requesters"))}
            <Field label={t("cs.g.links")} wide hint={t("cs.links_hint")}>
              <Links ro={ro} rows={f.links} onChange={(rows) => set("links", rows)} />
            </Field>
          </div>
        )}

        {current === "follow" && (
          <div className="cs-form">
            <Field label={t("cs.f.stage")}>
              <select value={f.stage} disabled={ro} onChange={(e) => set("stage", e.target.value)}>
                {settings.stages.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </Field>
            <Field label={t("cs.f.health")}>
              <select value={f.health ?? ""} disabled={ro} onChange={(e) => set("health", (e.target.value || null) as Project["health"])}>
                <option value="">{t("cs.health.none")}</option>
                {HEALTHS.map((h) => <option key={h} value={h}>{t(`cs.hv.${h}`)}</option>)}
              </select>
            </Field>
            {day("planned_delivery", t("cs.f.planned"))}
            {day("actual_delivery", t("cs.f.actual"))}
          </div>
        )}

        {current === "billing" && (
          <div className="cs-form">
            <Field label={t("cs.f.amount")}>
              <input type="number" min={0} step="0.01" value={f.build_amount ?? ""} disabled={ro}
                     onChange={(e) => set("build_amount", e.target.value === "" ? null : Number(e.target.value))} />
            </Field>
            <DiscountInput price={f.build_amount} value={f.discount_value} kind={f.discount_kind} disabled={ro}
                           onChange={(v, k) => { set("discount_value", v); set("discount_kind", k); }} />
            {txt("cost_code", t("cs.f.cost_code"))}
            <Field label={t("cs.f.billing")}>
              <select value={f.billing} disabled={ro} onChange={(e) => set("billing", e.target.value as Project["billing"])}>
                {BILLINGS.map((b) => <option key={b} value={b}>{t(`cs.bill.${b}`)}</option>)}
              </select>
            </Field>
          </div>
        )}

        {current === "track" && <TrackPart p={p} onChanged={reload} />}
      </StepLayout>
    </Modal>
  );
}

/** The discount on the price: a figure, in percent or in euros, and the net price
 *  it leaves. Shared by the creation window and the Facturation step. */
export function DiscountInput({ price, value, kind, disabled, onChange }: {
  price: number | null; value: number | null; kind: DiscountKind; disabled?: boolean;
  onChange: (value: number | null, kind: DiscountKind) => void;
}) {
  const { t, lang } = useI18n();
  const net = netAmount(price, value, kind);
  return (
    <div className="cs-field">
      <span className="cs-label">{t("cs.f.discount")}</span>
      <div className="cs-discount">
        <input type="number" min={0} max={kind === "pct" ? 100 : undefined} step="0.01" value={value ?? ""} disabled={disabled}
               aria-label={t("cs.f.discount")}
               onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value), kind)} />
        <select value={kind} disabled={disabled} aria-label={t("cs.f.discount_kind")}
                onChange={(e) => onChange(value, e.target.value as DiscountKind)}>
          <option value="pct">%</option>
          <option value="amount">€</option>
        </select>
      </div>
      {price !== null && !!value && <span className="small muted">{t("cs.f.net", { v: fmtAmount(net, lang) })}</span>}
    </div>
  );
}

function Field({ label, children, wide, hint }: { label: string; children: ReactNode; wide?: boolean; hint?: string }) {
  return (
    <label className={`cs-field${wide ? " cs-wide" : ""}`}>
      <span className="cs-label">{label}</span>
      {hint && <span className="small muted">{hint}</span>}
      {children}
    </label>
  );
}

/** The project's links: a name and an address per line. */
function Links({ rows, onChange, ro }: { rows: Project["links"]; onChange: (rows: Project["links"]) => void; ro: boolean }) {
  const { t } = useI18n();
  return (
    <span className="stack" style={{ gap: 6 }}>
      {rows.map((r, i) => (
        <span key={i} className="cs-line">
          <input placeholder={t("cs.link_label")} aria-label={t("cs.link_label")} value={r.label} disabled={ro}
                 onChange={(e) => onChange(rows.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
          <input placeholder="https://" aria-label="URL" value={r.url} disabled={ro}
                 onChange={(e) => onChange(rows.map((x, j) => j === i ? { ...x, url: e.target.value } : x))} />
          {!ro && <button type="button" className="btn-ghost btn-sm" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
            {t("action.remove")}</button>}
        </span>
      ))}
      {!ro && <span><button type="button" className="btn-ghost btn-sm" onClick={() => onChange([...rows, { label: "", url: "" }])}>
        + {t("cs.link_add")}</button></span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// The follow-up: two tables, one question each. "À faire" holds what is left to
// do (ticked once settled), "Historique" what happened (newest first). Each has
// its own new line at the top, filled where it will be read, and every line is
// changed in place (Modifier), never in another window.
// ---------------------------------------------------------------------------

// A history entry "Blocage" would read like the point of the same name: what
// blocks is noted as a point to do, so it is not offered for a new entry.
const PAST_KINDS = JOURNAL_KINDS.filter((k) => k !== "blocker");
const KIND_COLOR: Record<ItemKind, string | undefined> = { blocker: "var(--red)", risk: "var(--orange)", action: undefined };

function TrackPart({ p, onChanged }: { p: Project; onChanged: () => void }) {
  const { t } = useI18n();
  const open = (p.items ?? []).filter((i) => !i.done).length;
  return (
    <div className="stack" style={{ gap: 24 }}>
      <section className="stack" style={{ gap: 8 }}>
        <div className="cs-sec-head">
          <span className="strong">{t("cs.track.todo")}</span>
          <span className="small muted">{t("cs.t.open_n", { n: open })}</span>
        </div>
        <TodoTable p={p} onChanged={onChanged} />
      </section>
      <section className="stack" style={{ gap: 8 }}>
        <div className="cs-sec-head">
          <span className="strong">{t("cs.track.history")}</span>
          <span className="small muted">{t("cs.meta.journal", { n: (p.journal ?? []).length })}</span>
        </div>
        <HistoryTable p={p} onChanged={onChanged} />
      </section>
    </div>
  );
}

/** Calls the API, reports a failure in the table, refreshes on success. */
function useRun(onChanged: () => void) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function run(fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true); setErr(null);
    try { await fn(); onChanged(); return true; } catch (e) { setErr(errorText(e)); return false; }
    finally { setBusy(false); }
  }
  return { err, busy, run };
}

// ----- À faire ---------------------------------------------------------------

type ItemDraft = { kind: ItemKind; label: string; owner: string; due: string };
const blankItem = (kind: ItemKind = "action"): ItemDraft => ({ kind, label: "", owner: "", due: "" });

function TodoTable({ p, onChanged }: { p: Project; onChanged: () => void }) {
  const { t, lang } = useI18n();
  const { err, busy, run } = useRun(onChanged);
  const [draft, setDraft] = useState<ItemDraft>(blankItem());
  const [editing, setEditing] = useState<{ id: number; d: ItemDraft } | null>(null);
  const [showDone, setShowDone] = useState(false);
  const all = p.items ?? [];
  const rows = all.filter((i) => showDone || !i.done);
  const doneCount = all.filter((i) => i.done).length;
  const today = todayIso();
  const body = (d: ItemDraft) => ({ kind: d.kind, label: d.label, owner: d.owner || null, due: d.due || null });

  const add = () => run(() => api.post(`/api/cs/projects/${p.id}/items`, body(draft))).then((ok) => ok && setDraft(blankItem(draft.kind)));
  const save = () => editing && run(() => api.put(`/api/cs/items/${editing.id}`, body(editing.d))).then((ok) => ok && setEditing(null));
  const remove = (i: Item) => window.confirm(t("cs.i.delete_confirm")) && run(() => api.del(`/api/cs/items/${i.id}`));
  const enter = (fn: () => void, ok: boolean) => (e: React.KeyboardEvent) => { if (e.key === "Enter" && ok) fn(); };

  const inputs = (d: ItemDraft, set: (d: ItemDraft) => void, onEnter: (e: React.KeyboardEvent) => void, focus = false) => (
    <>
      <td><select aria-label={t("cs.add.kind")} value={d.kind} onChange={(e) => set({ ...d, kind: e.target.value as ItemKind })}>
        {ITEM_KINDS.map((k) => <option key={k} value={k}>{t(`cs.ik.${k}`)}</option>)}
      </select></td>
      <td><input aria-label={t("cs.t.what")} placeholder={t("cs.add.text_todo")} maxLength={500} value={d.label} autoFocus={focus}
                 onChange={(e) => set({ ...d, label: e.target.value })} onKeyDown={onEnter} /></td>
      <td><input aria-label={t("cs.t.owner")} placeholder={t("cs.t.owner")} maxLength={255} value={d.owner}
                 onChange={(e) => set({ ...d, owner: e.target.value })} onKeyDown={onEnter} /></td>
      <td><input type="date" aria-label={t("cs.add.date_due")} value={d.due} onChange={(e) => set({ ...d, due: e.target.value })} /></td>
    </>
  );

  return (
    <div className="stack" style={{ gap: 8 }}>
      {err && <ErrorBanner message={err} />}
      <table className="table cs-ttable">
        <colgroup><col style={{ width: 40 }} /><col style={{ width: 112 }} /><col /><col style={{ width: 110 }} /><col style={{ width: 156 }} /><col style={{ width: 128 }} /></colgroup>
        <thead><tr>
          <th aria-label={t("cs.i.done")} /><th>{t("cs.add.kind")}</th><th>{t("cs.t.what")}</th><th>{t("cs.t.owner")}</th><th>{t("cs.add.date_due")}</th><th />
        </tr></thead>
        <tbody>
          {p.can_edit && !editing && (
            <tr className="cs-newrow">
              <td />
              {inputs(draft, setDraft, enter(add, !!draft.label.trim()))}
              <td className="cs-tact"><button className="btn-sm" disabled={busy || !draft.label.trim()} onClick={add}>{t("action.add")}</button></td>
            </tr>
          )}
          {rows.length === 0 && <tr><td /><td colSpan={5} className="small muted">{t("cs.i.none")}</td></tr>}
          {rows.map((i) => editing?.id === i.id ? (
            <tr key={i.id} className="cs-newrow">
              <td />
              {inputs(editing.d, (d) => setEditing({ id: i.id, d }), enter(save, !!editing.d.label.trim()), true)}
              <td className="cs-tact">
                <button className="btn-ghost btn-sm" onClick={() => setEditing(null)}>{t("action.cancel")}</button>
                <button className="btn-sm" disabled={busy || !editing.d.label.trim()} onClick={save}>{t("action.save")}</button>
              </td>
            </tr>
          ) : (
            <tr key={i.id} className={i.done ? "cs-done" : undefined}>
              <td><input type="checkbox" checked={i.done} disabled={!p.can_edit || busy} aria-label={t("cs.i.done")}
                         onChange={(e) => run(() => api.put(`/api/cs/items/${i.id}`, { done: e.target.checked }))} /></td>
              <td style={{ color: i.done ? undefined : KIND_COLOR[i.kind] }}>{t(`cs.ik.${i.kind}`)}</td>
              <td className="cs-wrap">{i.label}</td>
              <td className="cs-cut" title={i.owner ?? undefined}>{i.owner || <span className="muted">-</span>}</td>
              <td style={!i.done && i.due && i.due < today ? { color: "var(--red)" } : undefined}>
                {i.due ? fmtDate(i.due, lang) : <span className="muted">-</span>}
                {!i.done && i.due && i.due < today && <span className="small">{`, ${t("cs.i.late")}`}</span>}
              </td>
              <td className="cs-tact">{p.can_edit && !editing && (
                <>
                  <button className="btn-ghost btn-sm" onClick={() => setEditing({ id: i.id, d: { kind: i.kind, label: i.label, owner: i.owner ?? "", due: i.due ?? "" } })}>{t("action.edit")}</button>
                  <button className="btn-ghost btn-sm" onClick={() => remove(i)}>{t("action.delete")}</button>
                </>
              )}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {doneCount > 0 && (
        <div><button className="btn-ghost btn-sm" onClick={() => setShowDone(!showDone)}>
          {showDone ? t("cs.i.hide_done") : t("cs.i.show_done_n", { n: doneCount })}</button></div>
      )}
    </div>
  );
}

// ----- Historique ------------------------------------------------------------

type EntryDraft = { date: string; kind: JournalKind; text: string; in_recap: boolean };
const blankEntry = (kind: JournalKind = "note"): EntryDraft => ({ date: todayIso(), kind, text: "", in_recap: RECAP_BY_DEFAULT.includes(kind) });

function HistoryTable({ p, onChanged }: { p: Project; onChanged: () => void }) {
  const { t, lang } = useI18n();
  const { err, busy, run } = useRun(onChanged);
  const [draft, setDraft] = useState<EntryDraft>(blankEntry());
  const [recapTouched, setRecapTouched] = useState(false);
  const [editing, setEditing] = useState<{ id: number; d: EntryDraft } | null>(null);
  const rows = p.journal ?? [];

  const add = () => run(() => api.post(`/api/cs/projects/${p.id}/journal`, { ...draft, date: draft.date || todayIso() }))
    .then((ok) => { if (ok) { setDraft(blankEntry(draft.kind)); setRecapTouched(false); } });
  const save = () => editing && run(() => api.put(`/api/cs/journal/${editing.id}`, editing.d)).then((ok) => ok && setEditing(null));
  const remove = (e: JournalEntry) => window.confirm(t("cs.j.delete_confirm")) && run(() => api.del(`/api/cs/journal/${e.id}`));
  const enter = (fn: () => void, ok: boolean) => (e: React.KeyboardEvent) => { if (e.key === "Enter" && ok) fn(); };

  const inputs = (d: EntryDraft, set: (d: EntryDraft) => void, onEnter: (e: React.KeyboardEvent) => void,
                  kinds: JournalKind[], focus = false) => (
    <>
      <td><input type="date" aria-label={t("cs.j.date")} value={d.date} onChange={(e) => set({ ...d, date: e.target.value })} /></td>
      <td><select aria-label={t("cs.j.kind")} value={d.kind} onChange={(e) => set({ ...d, kind: e.target.value as JournalKind })}>
        {kinds.map((k) => <option key={k} value={k}>{t(`cs.jk.${k}`)}</option>)}
      </select></td>
      <td><input aria-label={t("cs.j.text")} placeholder={t("cs.add.text_past")} value={d.text} autoFocus={focus}
                 onChange={(e) => set({ ...d, text: e.target.value })} onKeyDown={onEnter} /></td>
      <td className="cs-tcenter"><input type="checkbox" aria-label={t("cs.j.in_recap")} title={t("cs.j.in_recap")} checked={d.in_recap}
                                         onChange={(e) => set({ ...d, in_recap: e.target.checked })} /></td>
    </>
  );
  // A new entry's kind sets whether it goes in the recap, until the box is ticked by hand.
  const setNew = (d: EntryDraft) => {
    if (d.in_recap !== draft.in_recap) setRecapTouched(true);
    else if (d.kind !== draft.kind && !recapTouched) d = { ...d, in_recap: RECAP_BY_DEFAULT.includes(d.kind) };
    setDraft(d);
  };

  return (
    <div className="stack" style={{ gap: 8 }}>
      {err && <ErrorBanner message={err} />}
      <table className="table cs-ttable">
        <colgroup><col style={{ width: 150 }} /><col style={{ width: 130 }} /><col /><col style={{ width: 64 }} /><col style={{ width: 128 }} /></colgroup>
        <thead><tr>
          <th>{t("cs.j.date")}</th><th>{t("cs.j.kind")}</th><th>{t("cs.j.text")}</th>
          <th className="cs-tcenter" title={t("cs.j.in_recap")}>{t("cs.t.recap")}</th><th />
        </tr></thead>
        <tbody>
          {p.can_edit && !editing && (
            <tr className="cs-newrow">
              {inputs(draft, setNew, enter(add, !!draft.text.trim()), PAST_KINDS)}
              <td className="cs-tact"><button className="btn-sm" disabled={busy || !draft.text.trim()} onClick={add}>{t("action.add")}</button></td>
            </tr>
          )}
          {rows.length === 0 && <tr><td colSpan={5} className="small muted">{t("cs.j.none")}</td></tr>}
          {rows.map((e) => editing?.id === e.id ? (
            <tr key={e.id} className="cs-newrow">
              {inputs(editing.d, (d) => setEditing({ id: e.id, d }), enter(save, !!editing.d.text.trim()), JOURNAL_KINDS, true)}
              <td className="cs-tact">
                <button className="btn-ghost btn-sm" onClick={() => setEditing(null)}>{t("action.cancel")}</button>
                <button className="btn-sm" disabled={busy || !editing.d.text.trim()} onClick={save}>{t("action.save")}</button>
              </td>
            </tr>
          ) : (
            <tr key={e.id}>
              <td>{fmtDate(e.date, lang)}{e.new && <div className="small" style={{ color: "var(--green)" }}>{t("cs.j.new")}</div>}</td>
              <td>{t(`cs.jk.${e.kind}`)}</td>
              <td className="cs-wrap">
                {e.text}
                {e.people && <div className="small muted">{e.people}</div>}
                {e.links.map((l, i) => <div key={i}><a className="small" href={l.url} target="_blank" rel="noreferrer noopener">{l.label || l.url}</a></div>)}
              </td>
              <td className="cs-tcenter">
                <input type="checkbox" checked={e.in_recap} disabled={!p.can_edit || busy}
                       aria-label={e.in_recap ? t("cs.j.remove_recap") : t("cs.j.put_recap")} title={e.in_recap ? t("cs.j.remove_recap") : t("cs.j.put_recap")}
                       onChange={(x) => run(() => api.put(`/api/cs/journal/${e.id}`, { in_recap: x.target.checked }))} />
              </td>
              <td className="cs-tact">{p.can_edit && !editing && (
                <>
                  <button className="btn-ghost btn-sm" onClick={() => setEditing({ id: e.id, d: { date: e.date, kind: e.kind, text: e.text, in_recap: e.in_recap } })}>{t("action.edit")}</button>
                  <button className="btn-ghost btn-sm" onClick={() => remove(e)}>{t("action.delete")}</button>
                </>
              )}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
