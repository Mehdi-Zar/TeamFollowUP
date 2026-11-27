// One Customer Success project, in a window of the app (docs/37, section 3).
//
// Four parts: the card (saved with one button, so a half-typed card is never
// half-saved), the journal and the points to follow (each line saved at once),
// and, for a CS leader, who contributes and the delete button.
import { ReactNode, useCallback, useEffect, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import {
  CsSettings, HEALTHS, ITEM_KINDS, Item, ItemKind, JOURNAL_KINDS, JournalEntry, JournalKind, Link,
  Project, RECAP_BY_DEFAULT, fmtDate, todayIso,
} from "../../cs";
import { Chip, ErrorBanner, Modal, Spinner, Toggle } from "../ui";

type Part = "card" | "journal" | "items" | "access";

export default function CsProjectModal({ projectId, settings, onClose, onChanged }: {
  projectId: number; settings: CsSettings; onClose: () => void; onChanged: () => void;
}) {
  const { t } = useI18n();
  const [p, setP] = useState<Project | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [part, setPart] = useState<Part>("card");
  const [dirty, setDirty] = useState(false);

  const load = useCallback(() => {
    api.get<Project>(`/api/cs/projects/${projectId}`).then(setP).catch((e) => setErr(errorText(e)));
  }, [projectId]);
  useEffect(() => { load(); }, [load]);
  const changed = (next?: Project) => { if (next) setP(next); else load(); onChanged(); };

  const parts: { key: Part; label: string }[] = [
    { key: "card", label: t("cs.part.card") },
    { key: "journal", label: t("cs.part.journal", { n: p?.journal?.length ?? 0 }) },
    { key: "items", label: t("cs.part.items", { n: (p?.items ?? []).filter((i) => !i.done).length }) },
    ...(p?.can_run ? [{ key: "access" as Part, label: t("cs.part.access") }] : []),
  ];

  return (
    <Modal width={980} dirty={dirty} onClose={onClose}
           title={p ? (p.client ? `${p.client} : ${p.title}` : p.title) : t("cs.title")}>
      {err && <ErrorBanner message={err} />}
      {!p ? (!err && <Spinner />) : (
        <div className="stack" style={{ gap: 16 }}>
          <div className="inline" role="tablist" style={{ gap: 6, flexWrap: "wrap" }}>
            {parts.map((x) => (
              <button key={x.key} role="tab" aria-selected={part === x.key}
                      className={`btn-sm ${part === x.key ? "" : "btn-secondary"}`}
                      onClick={() => { if (!dirty || window.confirm(t("cs.leave_unsaved"))) { setDirty(false); setPart(x.key); } }}>
                {x.label}
              </button>
            ))}
          </div>
          {!p.can_edit && <div className="banner small">{t("cs.read_only")}</div>}
          {part === "card" && <CardForm p={p} settings={settings} setDirty={setDirty} onSaved={changed} />}
          {part === "journal" && <JournalPart p={p} onChanged={() => changed()} />}
          {part === "items" && <ItemsPart p={p} onChanged={() => changed()} />}
          {part === "access" && <AccessPart p={p} onSaved={changed} onDeleted={() => { onChanged(); onClose(); }} />}
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// The card
// ---------------------------------------------------------------------------

function Field({ label, children, wide }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className="stack" style={{ gap: 4, gridColumn: wide ? "1 / -1" : undefined }}>
      <span className="small strong">{label}</span>{children}
    </label>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="stack" style={{ gap: 12, border: "1px solid var(--line)", borderRadius: "var(--radius)", padding: 16, margin: 0 }}>
      <legend className="strong" style={{ padding: "0 6px" }}>{title}</legend>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>{children}</div>
    </fieldset>
  );
}

function CardForm({ p, settings, setDirty, onSaved }: {
  p: Project; settings: CsSettings; setDirty: (v: boolean) => void; onSaved: (p: Project) => void;
}) {
  const { t } = useI18n();
  const [f, setF] = useState<Project>(p);
  const [tags, setTags] = useState((p.tags ?? []).join(", "));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  const ro = !p.can_edit;
  useEffect(() => { setF(p); setTags((p.tags ?? []).join(", ")); }, [p]);

  const set = <K extends keyof Project>(k: K, v: Project[K]) => { setF((x) => ({ ...x, [k]: v })); setDirty(true); setOk(false); };
  const txt = (k: keyof Project, label: string, opts: { wide?: boolean; list?: string; max?: number } = {}) => (
    <Field label={label} wide={opts.wide}>
      <input value={(f[k] as string | null) ?? ""} disabled={ro} list={opts.list} maxLength={opts.max ?? 255}
             onChange={(e) => set(k, e.target.value as never)} />
    </Field>
  );
  const day = (k: keyof Project, label: string) => (
    <Field label={label}>
      <input type="date" value={(f[k] as string | null) ?? ""} disabled={ro} onChange={(e) => set(k, (e.target.value || null) as never)} />
    </Field>
  );

  async function save() {
    setBusy(true); setErr(null);
    try {
      const body = {
        title: f.title, client: f.client, requesters: f.requesters, contacts: f.contacts,
        tags: tags.split(",").map((x) => x.trim()).filter(Boolean),
        stage: f.stage, health: f.health, offer: f.offer, delivery_mode: f.delivery_mode,
        gcp_project: f.gcp_project, planned_delivery: f.planned_delivery, actual_delivery: f.actual_delivery,
        build_amount: f.build_amount, quote_signed: f.quote_signed, cost_code: f.cost_code,
        consumption_billing: f.consumption_billing, consumption_cap: f.consumption_cap,
        users_count: f.users_count, models: f.models, data_classification: f.data_classification,
        max_duration: f.max_duration, access_end: f.access_end, milestones: f.milestones,
        links: f.links.filter((l) => l.url.trim()), notes: f.notes,
      };
      const next = await api.put<Project>(`/api/cs/projects/${p.id}`, body);
      setDirty(false); setOk(true); onSaved(next);
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  const ms = (key: string, which: "planned" | "actual", v: string) => {
    const cur = f.milestones[key] ?? { planned: null, actual: null };
    set("milestones", { ...f.milestones, [key]: { ...cur, [which]: v || null } });
  };

  return (
    <div className="stack" style={{ gap: 16 }}>
      {err && <ErrorBanner message={err} />}
      <Group title={t("cs.g.identity")}>
        {txt("title", t("cs.f.title"))}
        {txt("client", t("cs.f.client"))}
        {txt("requesters", t("cs.f.requesters"), { max: 500 })}
        <Field label={t("cs.f.tags")}>
          <input value={tags} disabled={ro} placeholder={t("cs.f.tags_hint")}
                 onChange={(e) => { setTags(e.target.value); setDirty(true); }} />
        </Field>
        <Field label={t("cs.f.contacts")} wide>
          <ListEditor ro={ro} rows={f.contacts} empty={{ name: "", role: "" }}
                      onChange={(rows) => set("contacts", rows)} addLabel={t("cs.f.contact_add")}
                      cols={[{ key: "name", ph: t("cs.f.contact_name") }, { key: "role", ph: t("cs.f.contact_role") }]} />
        </Field>
      </Group>

      <Group title={t("cs.g.follow")}>
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
      </Group>

      <Group title={t("cs.g.delivery")}>
        {txt("offer", t("cs.f.offer"), { list: "cs-offers" })}
        <datalist id="cs-offers">{settings.offers.map((o) => <option key={o} value={o} />)}</datalist>
        {txt("delivery_mode", t("cs.f.mode"), { list: "cs-modes", max: 120 })}
        <datalist id="cs-modes"><option value={t("cs.mode.for_you")} /><option value={t("cs.mode.with_you")} /></datalist>
        {txt("gcp_project", t("cs.f.gcp"))}
        {day("planned_delivery", t("cs.f.planned"))}
        {day("actual_delivery", t("cs.f.actual"))}
      </Group>

      <Group title={t("cs.g.money")}>
        <Field label={t("cs.f.build")}>
          <input type="number" min={0} step="0.01" value={f.build_amount ?? ""} disabled={ro}
                 onChange={(e) => set("build_amount", e.target.value === "" ? null : Number(e.target.value))} />
        </Field>
        <div className="stack" style={{ gap: 4, justifyContent: "flex-end" }}>
          <Toggle checked={f.quote_signed} disabled={ro} onChange={(v) => set("quote_signed", v)}>{t("cs.f.quote_signed")}</Toggle>
        </div>
        {txt("cost_code", t("cs.f.cost_code"))}
        <Field label={t("cs.f.billing")}>
          <select value={f.consumption_billing ?? ""} disabled={ro}
                  onChange={(e) => set("consumption_billing", (e.target.value || null) as Project["consumption_billing"])}>
            <option value="">{t("cs.billing.none")}</option>
            <option value="uncapped">{t("cs.billing.uncapped")}</option>
            <option value="capped">{t("cs.billing.capped")}</option>
          </select>
        </Field>
        {f.consumption_billing === "capped" && txt("consumption_cap", t("cs.f.cap"))}
      </Group>

      <Group title={t("cs.g.scope")}>
        <Field label={t("cs.f.users")}>
          <input type="number" min={0} value={f.users_count ?? ""} disabled={ro}
                 onChange={(e) => set("users_count", e.target.value === "" ? null : Number(e.target.value))} />
        </Field>
        {txt("models", t("cs.f.models"), { max: 500 })}
        {txt("data_classification", t("cs.f.classification"), { max: 40 })}
        {txt("max_duration", t("cs.f.duration"), { max: 120 })}
        {day("access_end", t("cs.f.access_end"))}
      </Group>

      <fieldset className="stack" style={{ gap: 8, border: "1px solid var(--line)", borderRadius: "var(--radius)", padding: 16, margin: 0 }}>
        <legend className="strong" style={{ padding: "0 6px" }}>{t("cs.g.milestones")}</legend>
        <table className="table">
          <thead><tr><th>{t("cs.f.stage")}</th><th>{t("cs.ms.planned")}</th><th>{t("cs.ms.actual")}</th></tr></thead>
          <tbody>
            {settings.stages.map((s) => (
              <tr key={s.key}>
                <td>{s.label}</td>
                <td><input type="date" disabled={ro} value={f.milestones[s.key]?.planned ?? ""} aria-label={`${s.label} ${t("cs.ms.planned")}`}
                           onChange={(e) => ms(s.key, "planned", e.target.value)} /></td>
                <td><input type="date" disabled={ro} value={f.milestones[s.key]?.actual ?? ""} aria-label={`${s.label} ${t("cs.ms.actual")}`}
                           onChange={(e) => ms(s.key, "actual", e.target.value)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </fieldset>

      <fieldset className="stack" style={{ gap: 8, border: "1px solid var(--line)", borderRadius: "var(--radius)", padding: 16, margin: 0 }}>
        <legend className="strong" style={{ padding: "0 6px" }}>{t("cs.g.links")}</legend>
        <div className="small muted">{t("cs.links_hint")}</div>
        <ListEditor ro={ro} rows={f.links} empty={{ label: "", url: "" }} onChange={(rows) => set("links", rows)}
                    addLabel={t("cs.link_add")}
                    cols={[{ key: "label", ph: t("cs.link_label") }, { key: "url", ph: "https://" }]} />
        <Field label={t("cs.f.notes")} wide>
          <textarea rows={3} disabled={ro} value={f.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
        </Field>
      </fieldset>

      {!ro && (
        <div className="inline" style={{ gap: 8, justifyContent: "flex-end", alignItems: "center" }}>
          {ok && <span className="small" style={{ color: "var(--green)" }}>{t("cs.saved")}</span>}
          <button className="btn-sm" disabled={busy || !f.title.trim()} onClick={save}>{t("action.save")}</button>
        </div>
      )}
    </div>
  );
}

/** A small editable list of rows with the same text columns (contacts, links). */
function ListEditor<T extends Record<string, string>>({ rows, cols, empty, onChange, addLabel, ro }: {
  rows: T[]; cols: { key: keyof T & string; ph: string }[]; empty: T; onChange: (rows: T[]) => void;
  addLabel: string; ro: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="stack" style={{ gap: 6 }}>
      {rows.map((r, i) => (
        <div key={i} className="inline" style={{ gap: 6 }}>
          {cols.map((c) => (
            <input key={c.key} placeholder={c.ph} aria-label={c.ph} value={r[c.key] ?? ""} disabled={ro} style={{ flex: 1 }}
                   onChange={(e) => onChange(rows.map((x, j) => j === i ? { ...x, [c.key]: e.target.value } : x))} />
          ))}
          {!ro && <button type="button" className="btn-ghost btn-sm" aria-label={t("action.remove")}
                          onClick={() => onChange(rows.filter((_, j) => j !== i))}>✕</button>}
        </div>
      ))}
      {!ro && <div><button type="button" className="btn-secondary btn-sm" onClick={() => onChange([...rows, { ...empty }])}>{addLabel}</button></div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The journal
// ---------------------------------------------------------------------------

type EntryDraft = { date: string; kind: JournalKind; people: string; text: string; in_recap: boolean; link: string };
const newDraft = (): EntryDraft => ({ date: todayIso(), kind: "note", people: "", text: "", in_recap: false, link: "" });

function JournalPart({ p, onChanged }: { p: Project; onChanged: () => void }) {
  const { t, lang } = useI18n();
  const [d, setD] = useState<EntryDraft>(newDraft());
  const [recapTouched, setRecapTouched] = useState(false);
  const [kind, setKind] = useState<"" | JournalKind>("");
  const [editing, setEditing] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const entries = (p.journal ?? []).filter((e) => !kind || e.kind === kind);

  const setKindDraft = (k: JournalKind) =>
    setD((x) => ({ ...x, kind: k, in_recap: recapTouched ? x.in_recap : RECAP_BY_DEFAULT.includes(k) }));

  async function add() {
    setBusy(true); setErr(null);
    try {
      const links: Link[] = d.link.trim() ? [{ label: "", url: d.link.trim() }] : [];
      await api.post(`/api/cs/projects/${p.id}/journal`, { date: d.date, kind: d.kind, people: d.people, text: d.text, in_recap: d.in_recap, links });
      setD(newDraft()); setRecapTouched(false); onChanged();
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }
  async function patch(e: JournalEntry, body: Partial<JournalEntry>) {
    setErr(null);
    try { await api.put(`/api/cs/journal/${e.id}`, body); setEditing(null); onChanged(); }
    catch (x) { setErr(errorText(x)); }
  }
  async function remove(e: JournalEntry) {
    if (!window.confirm(t("cs.j.delete_confirm"))) return;
    try { await api.del(`/api/cs/journal/${e.id}`); onChanged(); } catch (x) { setErr(errorText(x)); }
  }

  return (
    <div className="stack" style={{ gap: 16 }}>
      {err && <ErrorBanner message={err} />}
      {p.can_edit && (
        <div className="card stack" style={{ gap: 10 }}>
          <div className="strong">{t("cs.j.add")}</div>
          <div className="grid" style={{ gridTemplateColumns: "160px 180px 1fr", gap: 8 }}>
            <input type="date" aria-label={t("cs.j.date")} value={d.date} onChange={(e) => setD({ ...d, date: e.target.value })} />
            <select aria-label={t("cs.j.kind")} value={d.kind} onChange={(e) => setKindDraft(e.target.value as JournalKind)}>
              {JOURNAL_KINDS.map((k) => <option key={k} value={k}>{t(`cs.jk.${k}`)}</option>)}
            </select>
            <input placeholder={t("cs.j.people")} aria-label={t("cs.j.people")} value={d.people} maxLength={500}
                   onChange={(e) => setD({ ...d, people: e.target.value })} />
          </div>
          <textarea rows={3} placeholder={t("cs.j.text")} aria-label={t("cs.j.text")} value={d.text}
                    onChange={(e) => setD({ ...d, text: e.target.value })} />
          <input placeholder={t("cs.j.link")} aria-label={t("cs.j.link")} value={d.link} onChange={(e) => setD({ ...d, link: e.target.value })} />
          <div className="between" style={{ alignItems: "center" }}>
            <Toggle checked={d.in_recap} onChange={(v) => { setRecapTouched(true); setD({ ...d, in_recap: v }); }}>{t("cs.j.in_recap")}</Toggle>
            <button className="btn-sm" disabled={busy || !d.text.trim()} onClick={add}>{t("action.add")}</button>
          </div>
        </div>
      )}
      <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
        <Chip on={!kind} onToggle={() => setKind("")}>{t("cs.j.all")}</Chip>
        {JOURNAL_KINDS.map((k) => <Chip key={k} on={kind === k} onToggle={() => setKind(kind === k ? "" : k)}>{t(`cs.jk.${k}`)}</Chip>)}
      </div>
      {entries.length === 0 ? <div className="small muted">{t("cs.j.none")}</div> : (
        <div className="stack" style={{ gap: 8 }}>
          {entries.map((e) => editing === e.id
            ? <EntryEdit key={e.id} e={e} onCancel={() => setEditing(null)} onSave={(b) => patch(e, b)} />
            : (
              <div key={e.id} className="card stack" style={{ gap: 4, padding: 12 }}>
                <div className="between" style={{ alignItems: "center", gap: 8 }}>
                  <div className="inline small" style={{ gap: 8, flexWrap: "wrap" }}>
                    <span className="strong">{fmtDate(e.date, lang)}</span>
                    <span className="badge badge-navy">{t(`cs.jk.${e.kind}`)}</span>
                    {e.people && <span className="muted">{e.people}</span>}
                    {e.new && <span className="badge badge-green">{t("cs.j.new")}</span>}
                    {!e.in_recap && <span className="badge badge-grey">{t("cs.j.out_of_recap")}</span>}
                  </div>
                  {p.can_edit && (
                    <div className="inline" style={{ gap: 4 }}>
                      <button className="btn-ghost btn-sm" onClick={() => patch(e, { in_recap: !e.in_recap })}>
                        {e.in_recap ? t("cs.j.remove_recap") : t("cs.j.put_recap")}
                      </button>
                      <button className="btn-ghost btn-sm" onClick={() => setEditing(e.id)}>{t("action.edit")}</button>
                      <button className="btn-ghost btn-sm" onClick={() => remove(e)}>{t("action.delete")}</button>
                    </div>
                  )}
                </div>
                <div style={{ whiteSpace: "pre-wrap" }}>{e.text}</div>
                {e.links.map((l, i) => <a key={i} className="small" href={l.url} target="_blank" rel="noreferrer noopener">{l.label || l.url}</a>)}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function EntryEdit({ e, onCancel, onSave }: { e: JournalEntry; onCancel: () => void; onSave: (b: Partial<JournalEntry>) => void }) {
  const { t } = useI18n();
  const [d, setD] = useState({ date: e.date, kind: e.kind, people: e.people ?? "", text: e.text });
  return (
    <div className="card stack" style={{ gap: 8, padding: 12 }}>
      <div className="grid" style={{ gridTemplateColumns: "160px 180px 1fr", gap: 8 }}>
        <input type="date" aria-label={t("cs.j.date")} value={d.date} onChange={(x) => setD({ ...d, date: x.target.value })} />
        <select aria-label={t("cs.j.kind")} value={d.kind} onChange={(x) => setD({ ...d, kind: x.target.value as JournalKind })}>
          {JOURNAL_KINDS.map((k) => <option key={k} value={k}>{t(`cs.jk.${k}`)}</option>)}
        </select>
        <input aria-label={t("cs.j.people")} value={d.people} onChange={(x) => setD({ ...d, people: x.target.value })} />
      </div>
      <textarea rows={3} aria-label={t("cs.j.text")} value={d.text} onChange={(x) => setD({ ...d, text: x.target.value })} />
      <div className="inline" style={{ gap: 8, justifyContent: "flex-end" }}>
        <button className="btn-secondary btn-sm" onClick={onCancel}>{t("action.cancel")}</button>
        <button className="btn-sm" disabled={!d.text.trim()} onClick={() => onSave(d)}>{t("action.save")}</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Points to follow
// ---------------------------------------------------------------------------

function ItemsPart({ p, onChanged }: { p: Project; onChanged: () => void }) {
  const { t, lang } = useI18n();
  const [d, setD] = useState({ kind: "action" as ItemKind, label: "", owner: "", due: "" });
  const [showDone, setShowDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const items = (p.items ?? []).filter((i) => showDone || !i.done);
  const today = todayIso();

  async function add() {
    setErr(null);
    try {
      await api.post(`/api/cs/projects/${p.id}/items`, { ...d, due: d.due || null });
      setD({ kind: d.kind, label: "", owner: "", due: "" }); onChanged();
    } catch (e) { setErr(errorText(e)); }
  }
  async function patch(i: Item, body: Partial<Item>) {
    setErr(null);
    try { await api.put(`/api/cs/items/${i.id}`, body); onChanged(); } catch (e) { setErr(errorText(e)); }
  }
  async function remove(i: Item) {
    if (!window.confirm(t("cs.i.delete_confirm"))) return;
    try { await api.del(`/api/cs/items/${i.id}`); onChanged(); } catch (e) { setErr(errorText(e)); }
  }

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="small muted">{t("cs.i.hint")}</div>
      {err && <ErrorBanner message={err} />}
      {p.can_edit && (
        <div className="grid" style={{ gridTemplateColumns: "150px 1fr 200px 160px auto", gap: 8, alignItems: "center" }}>
          <select aria-label={t("cs.i.kind")} value={d.kind} onChange={(e) => setD({ ...d, kind: e.target.value as ItemKind })}>
            {ITEM_KINDS.map((k) => <option key={k} value={k}>{t(`cs.ik.${k}`)}</option>)}
          </select>
          <input placeholder={t("cs.i.label")} aria-label={t("cs.i.label")} value={d.label} maxLength={500}
                 onChange={(e) => setD({ ...d, label: e.target.value })} />
          <input placeholder={t("cs.i.owner")} aria-label={t("cs.i.owner")} value={d.owner} maxLength={255}
                 onChange={(e) => setD({ ...d, owner: e.target.value })} />
          <input type="date" aria-label={t("cs.i.due")} value={d.due} onChange={(e) => setD({ ...d, due: e.target.value })} />
          <button className="btn-sm" disabled={!d.label.trim()} onClick={add}>{t("action.add")}</button>
        </div>
      )}
      <Toggle checked={showDone} onChange={setShowDone}>{t("cs.i.show_done")}</Toggle>
      {items.length === 0 ? <div className="small muted">{t("cs.i.none")}</div> : (
        <table className="table">
          <thead><tr>
            <th>{t("cs.i.kind")}</th><th>{t("cs.i.label")}</th><th>{t("cs.i.owner")}</th>
            <th>{t("cs.i.since")}</th><th>{t("cs.i.due")}</th><th>{t("cs.i.done")}</th><th></th>
          </tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id} style={i.done ? { opacity: 0.6 } : undefined}>
                <td><span className={`badge ${i.kind === "blocker" ? "badge-red" : i.kind === "risk" ? "badge-orange" : "badge-navy"}`}>{t(`cs.ik.${i.kind}`)}</span></td>
                <td>{i.label}</td>
                <td className="small">{i.owner}</td>
                <td className="small">{fmtDate(i.opened_on, lang)}</td>
                <td className="small" style={!i.done && i.due && i.due < today ? { color: "var(--red)" } : undefined}>{fmtDate(i.due, lang)}</td>
                <td><Toggle checked={i.done} disabled={!p.can_edit} onChange={(v) => patch(i, { done: v })}>
                  <span className="sr-only">{t("cs.i.done")}</span></Toggle></td>
                <td style={{ textAlign: "right" }}>
                  {p.can_edit && <button className="btn-ghost btn-sm" onClick={() => remove(i)}>{t("action.delete")}</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Who contributes, and deleting the project (CS leaders)
// ---------------------------------------------------------------------------

type Person = { id: number; name: string; email: string | null; tribe_id: number | null };

function AccessPart({ p, onSaved, onDeleted }: { p: Project; onSaved: (p: Project) => void; onDeleted: () => void }) {
  const { t } = useI18n();
  const [people, setPeople] = useState<Person[]>([]);
  const [ids, setIds] = useState<number[]>((p.contributors ?? []).map((c) => c.id));
  const [pick, setPick] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  useEffect(() => {
    api.get<Person[]>("/api/tribes/people").then((ps) => setPeople(ps.filter((x) => x.tribe_id === p.tribe_id))).catch(() => {});
  }, [p.tribe_id]);
  const name = (id: number) => people.find((x) => x.id === id)?.name ?? p.contributors?.find((c) => c.id === id)?.name ?? `#${id}`;

  async function save() {
    setErr(null); setOk(false);
    try { onSaved(await api.put<Project>(`/api/cs/projects/${p.id}`, { contributor_user_ids: ids })); setOk(true); }
    catch (e) { setErr(errorText(e)); }
  }
  async function del() {
    if (!window.confirm(t("cs.delete_confirm", { title: p.title }))) return;
    try { await api.del(`/api/cs/projects/${p.id}`); onDeleted(); } catch (e) { setErr(errorText(e)); }
  }

  return (
    <div className="stack" style={{ gap: 16 }}>
      {err && <ErrorBanner message={err} />}
      <div className="stack" style={{ gap: 8 }}>
        <div className="strong">{t("cs.contrib.title")}</div>
        <div className="small muted">{t("cs.contrib.hint")}</div>
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          {ids.length === 0 && <span className="small muted">{t("cs.contrib.none")}</span>}
          {ids.map((id) => <Chip key={id} on onToggle={() => setIds(ids.filter((x) => x !== id))}>{name(id)}</Chip>)}
        </div>
        <div className="inline" style={{ gap: 8 }}>
          <select aria-label={t("cs.contrib.pick")} value={pick} onChange={(e) => setPick(e.target.value)} style={{ minWidth: 240 }}>
            <option value="">{t("cs.contrib.pick")}</option>
            {people.filter((x) => !ids.includes(x.id)).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
          <button className="btn-secondary btn-sm" disabled={!pick} onClick={() => { setIds([...ids, Number(pick)]); setPick(""); }}>{t("action.add")}</button>
          <button className="btn-sm" onClick={save}>{t("action.save")}</button>
          {ok && <span className="small" style={{ color: "var(--green)" }}>{t("cs.saved")}</span>}
        </div>
      </div>
      <div className="stack" style={{ gap: 8, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
        <div className="strong">{t("cs.delete_title")}</div>
        <div className="small muted">{t("cs.delete_hint")}</div>
        <div><button className="btn-danger btn-sm" onClick={del}>{t("cs.delete")}</button></div>
      </div>
    </div>
  );
}
