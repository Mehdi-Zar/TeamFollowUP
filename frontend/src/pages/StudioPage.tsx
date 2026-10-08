// StudioPage: the Studio des exports (docs/35). Where the documents the app
// produces (dashboard, weekly report, roadmap, dependencies, initiatives,
// steerco, org chart) are laid out: templates per scope, their live preview on
// real data, their versions, which scope uses which, and the themes and files
// they draw on.
//
// The screen opens on what people come for: their documents, each with the
// layout it uses and one button, "Modifier". That button opens (or creates) the
// template of the chosen scope in the simple editor, and "Enregistrer et
// appliquer" saves, publishes and assigns it in one go. Templates, assignments,
// themes, files, versions and locks stay available under "Gestion avancée".
import { useEffect, useMemo, useState } from "react";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { useSetPageChrome } from "../components/pageChrome";
import { EmptyState, ErrorBanner, Modal, Spinner } from "../components/ui";
import SpecEditor from "../studio/SpecEditor";
import SimpleEditor from "../studio/SimpleEditor";
import Preview from "../studio/Preview";
import {
  Asset, Catalog, DocContext, DocKind, Spec, TemplateDetail, TemplateMeta, Theme, clone, downloadPost, same,
} from "../studio/model";

type Tab = "templates" | "assignments" | "themes" | "files";

export default function StudioPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("templates");
  const [cat, setCat] = useState<Catalog | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [themes, setThemes] = useState<Theme[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [open, setOpen] = useState<{ id: number; applyTo?: ScopeOpt } | null>(null);
  const [advanced, setAdvanced] = useState(false);

  const loadLib = () => Promise.all([
    api.get<Theme[]>("/api/exports/themes").then(setThemes).catch(() => {}),
    api.get<Asset[]>("/api/exports/assets").then(setAssets).catch(() => {}),
  ]);
  useEffect(() => {
    api.get<Catalog>("/api/exports/catalog").then(setCat).catch((e) => setErr(errorText(e)));
    loadLib();
  }, []);

  useSetPageChrome({
    title: t("studio.title"),
    tabs: open || !advanced ? [] : [
      { key: "templates", label: t("studio.tab_templates") },
      { key: "assignments", label: t("studio.tab_assignments") },
      { key: "themes", label: t("studio.tab_themes") },
      { key: "files", label: t("studio.tab_files") },
    ],
    activeTab: tab,
    onTab: (k) => setTab(k as Tab),
    actions: open ? undefined : (
      <button className="btn-ghost btn-sm" onClick={() => setAdvanced((a) => !a)}>
        {advanced ? `← ${t("simple.home")}` : t("simple.advanced")}
      </button>
    ),
  }, [tab, open, advanced, t]);

  if (err) return <ErrorBanner message={err} />;
  if (!cat) return <Spinner />;
  if (!cat.designer) {
    return <EmptyState message={t("studio.not_designer")} />;
  }
  if (open) {
    return <TemplateEditor id={open.id} applyTo={open.applyTo} cat={cat} themes={themes} assets={assets}
                           onClose={() => setOpen(null)} onLib={loadLib} />;
  }
  if (!advanced) {
    return <StudioHome cat={cat} onOpen={(id, applyTo) => setOpen({ id, applyTo })} />;
  }
  return (
    <div className="stack" style={{ gap: 16 }}>
      {tab === "templates" && <TemplatesTab cat={cat} onOpen={(id) => setOpen({ id })} />}
      {tab === "assignments" && <AssignmentsTab cat={cat} />}
      {tab === "themes" && <ThemesTab cat={cat} themes={themes} assets={assets} onChanged={loadLib} />}
      {tab === "files" && <FilesTab cat={cat} assets={assets} onChanged={loadLib} />}
    </div>
  );
}


// ------------------------------------------------------------------------------
// Home: my documents, one button each
// ------------------------------------------------------------------------------
const KINDS_FOR: Record<string, DocKind[]> = {
  squad: ["dashboard", "weekly", "roadmap"],
  platform: ["steerco"],
};

function StudioHome({ cat, onOpen }: { cat: Catalog; onOpen: (id: number, applyTo: ScopeOpt) => void }) {
  const { t } = useI18n();
  const scopes = scopeOptions(cat, t);
  // Start where the person works: the organisation for the admin, the tribe for
  // a tribe leader, their squad for a squad leader.
  const [key, setKey] = useState(scopes[0]?.key || "");
  const scope = scopes.find((s) => s.key === key);
  const kinds = scope ? (KINDS_FOR[scope.type] || cat.doc_kinds) : [];
  type Row = { kind: DocKind; template_id: number; name: string; source: string };
  const [rows, setRows] = useState<Row[] | null>(null);
  const [assigned, setAssigned] = useState<{ doc_kind: string; scope_key: string; template_id: number }[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<DocKind | null>(null);

  useEffect(() => {
    if (!scope) return;
    setRows(null);
    const q = scope.type === "global" ? "" : `&${scope.type}_id=${scope.id}`;
    Promise.all([
      Promise.all(kinds.map((k) => api.get<{ template_id: number; name: string; source: string }>(
        `/api/exports/effective?doc_kind=${k}${q}`).then((r) => ({ kind: k, ...r })))),
      api.get<any[]>("/api/exports/assignments"),
    ]).then(([r, a]) => { setRows(r); setAssigned(a); setErr(null); }).catch((e) => setErr(errorText(e)));
  }, [key]);

  async function modify(row: Row) {
    if (!scope) return;
    setBusy(row.kind); setErr(null);
    try {
      const own = assigned.find((a) => a.doc_kind === row.kind && a.scope_key === scope.key);
      if (own) { onOpen(own.template_id, scope); return; }
      // No layout of its own yet: one is created, following the one in use.
      const r = await api.post<TemplateMeta>("/api/exports/templates", {
        doc_kind: row.kind, name: `${t(`studio.doc.${row.kind}`)}, ${scope.label}`, scope_type: scope.type,
        scope_id: scope.id, from_template_id: row.template_id, mode: "derived",
      });
      onOpen(r.id, scope);
    } catch (e) { setErr(errorText(e)); } finally { setBusy(null); }
  }

  if (!scopes.length) return <EmptyState message={t("studio.no_scope")} />;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card simple-intro">
        <div>
          <h2 style={{ margin: 0 }}>{t("simple.home_title")}</h2>
          <div className="small muted">{t("simple.home_hint")}</div>
        </div>
        {scopes.length > 1 && (
          <label className="inline" style={{ gap: 8 }}>
            <span className="small strong">{t("simple.for")}</span>
            <select value={key} onChange={(e) => setKey(e.target.value)}>
              {scopes.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
        )}
      </div>
      {scope && <div className="banner small">{t(`simple.scope_${scope.type}`)}</div>}
      {err && <ErrorBanner message={err} />}
      {!rows && !err && <Spinner />}
      {rows && (
        <div className="studio-cards">
          {rows.map((r) => {
            const own = scope && r.source === scope.key;
            return (
              <div key={r.kind} className="card studio-card simple-doc-card">
                <span className="strong" style={{ fontSize: 16 }}>{t(`studio.doc.${r.kind}`)}</span>
                <span className="small">
                  {r.source === "standard" ? t("simple.uses_standard")
                    : own ? t("simple.uses_own", { name: r.name }) : t("simple.uses_inherited", { name: r.name })}
                </span>
                {(r.kind === "weekly" || (r.kind === "dashboard" && scope?.type === "squad")) && (
                  <span className="small muted">{t(`simple.mail_${r.kind}`)}</span>
                )}
                <button className="btn btn-sm" style={{ alignSelf: "flex-start" }} disabled={busy !== null}
                        onClick={() => modify(r)}>
                  {busy === r.kind ? t("common.preparing") : t("simple.modify")}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------
// Templates
// ------------------------------------------------------------------------------
function DocPicker({ cat, value, onChange }: { cat: Catalog; value: DocKind; onChange: (k: DocKind) => void }) {
  const { t } = useI18n();
  return (
    <div className="seg studio-docs" role="tablist" aria-label={t("studio.doc_kind")}>
      {cat.doc_kinds.map((k) => (
        <button key={k} role="tab" aria-selected={k === value} className={k === value ? "active" : ""}
                onClick={() => onChange(k)}>{t(`studio.doc.${k}`)}</button>
      ))}
    </div>
  );
}

const scopeOrder = { global: 0, tribe: 1, platform: 2, squad: 3 } as const;

function scopeText(t: (k: string, v?: any) => string, m: Pick<TemplateMeta, "scope_type" | "scope_label">) {
  return m.scope_type === "global" ? t("studio.scope_global") : `${t(`studio.scope_${m.scope_type}`)} ${m.scope_label}`;
}

function TemplatesTab({ cat, onOpen }: { cat: Catalog; onOpen: (id: number) => void }) {
  const { t } = useI18n();
  const [kind, setKind] = useState<DocKind>("dashboard");
  const [rows, setRows] = useState<TemplateMeta[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);

  const load = () => api.get<TemplateMeta[]>(`/api/exports/templates?doc_kind=${kind}`)
    .then((r) => { setRows(r); setErr(null); }).catch((e) => setErr(errorText(e)));
  useEffect(() => { setRows(null); load(); }, [kind]);

  const sorted = useMemo(() => (rows || []).slice().sort((a, b) =>
    (a.system === b.system ? 0 : a.system ? -1 : 1) || scopeOrder[a.scope_type] - scopeOrder[b.scope_type]
    || a.scope_label.localeCompare(b.scope_label) || a.name.localeCompare(b.name)), [rows]);

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="between">
        <DocPicker cat={cat} value={kind} onChange={setKind} />
        <div className="inline">
          <button className="btn-secondary btn-sm" onClick={() => setImporting(true)}>{t("studio.import_file")}</button>
          <button className="btn btn-sm" onClick={() => setCreating(true)}>{t("studio.new_template")}</button>
        </div>
      </div>
      <div className="small muted">{t("studio.templates_hint")}</div>
      {err && <ErrorBanner message={err} />}
      {!rows && !err && <Spinner />}
      {rows && (
        <div className="studio-cards">
          {sorted.map((m) => (
            <div key={m.id} className="card studio-card" role="button" tabIndex={0}
                 onClick={() => onOpen(m.id)} onKeyDown={(e) => e.key === "Enter" && onOpen(m.id)}>
              <div className="between">
                <span className="strong">{m.name}</span>
                {m.system ? <span className="badge badge-navy">{t("studio.standard")}</span>
                  : m.published_number ? <span className="badge badge-green">{t("studio.published_v", { n: m.published_number })}</span>
                  : <span className="badge badge-grey">{t("studio.draft")}</span>}
              </div>
              <div className="small muted">{scopeText(t, m)}</div>
              {m.mode === "derived" && m.parent_name && (
                <div className="small">{t("studio.derived_from", { name: m.parent_name })}</div>
              )}
              {m.mode === "detached" && <div className="small">{t("studio.detached")}</div>}
              {m.unpublished_changes && m.published_number && <div className="small studio-warn">{t("studio.unpublished")}</div>}
              {m.assigned.length > 0 && (
                <div className="small">{t("studio.used_by", { n: m.assigned.length })}</div>
              )}
              {m.system && <div className="small muted">{t("studio.standard_hint")}</div>}
            </div>
          ))}
        </div>
      )}
      {creating && <NewTemplateModal cat={cat} kind={kind} templates={rows || []} onClose={() => setCreating(false)}
                                     onCreated={(id) => { setCreating(false); onOpen(id); }} />}
      {importing && <ImportModal cat={cat} onClose={() => setImporting(false)}
                                 onDone={(id) => { setImporting(false); onOpen(id); }} />}
    </div>
  );
}

type ScopeOpt = { key: string; type: TemplateMeta["scope_type"]; id: number | null; label: string; simple?: boolean };

function scopeOptions(cat: Catalog, t: (k: string, v?: any) => string, kind?: DocKind): ScopeOpt[] {
  const out: ScopeOpt[] = [];
  if (cat.scopes.global) out.push({ key: "global", type: "global", id: null, label: t("studio.scope_global") });
  cat.scopes.tribes.forEach((x) => out.push({ key: `tribe:${x.id}`, type: "tribe", id: x.id, label: `${t("studio.scope_tribe")} ${x.name}` }));
  if (!kind || kind === "steerco")
    cat.scopes.platforms.forEach((x) => out.push({ key: `platform:${x.id}`, type: "platform", id: x.id, label: `${t("studio.scope_platform")} ${x.name}` }));
  if (!kind || ["dashboard", "weekly", "roadmap"].includes(kind))
    cat.scopes.squads.forEach((x) => out.push({ key: `squad:${x.id}`, type: "squad", id: x.id, label: `${t("studio.scope_squad")} ${x.name}`, simple: x.simple }));
  return out;
}

function NewTemplateModal({ cat, kind, templates, onClose, onCreated }: {
  cat: Catalog; kind: DocKind; templates: TemplateMeta[]; onClose: () => void; onCreated: (id: number) => void;
}) {
  const { t } = useI18n();
  const scopes = scopeOptions(cat, t, kind);
  const [scope, setScope] = useState(scopes[0]?.key || "");
  const [name, setName] = useState("");
  const [from, setFrom] = useState<number | "">(templates.find((x) => x.system)?.id ?? "");
  const [mode, setMode] = useState<"derived" | "detached">("derived");
  const [err, setErr] = useState<string | null>(null);
  const sc = scopes.find((s) => s.key === scope);
  async function create() {
    if (!sc) return;
    try {
      const r = await api.post<TemplateMeta>("/api/exports/templates", {
        doc_kind: kind, name: name.trim() || t("studio.new_template"), scope_type: sc.type, scope_id: sc.id,
        from_template_id: from || null, mode: sc.simple ? "derived" : mode,
      });
      onCreated(r.id);
    } catch (e) { setErr(errorText(e)); }
  }
  return (
    <Modal title={t("studio.new_template_title", { doc: t(`studio.doc.${kind}`) })} onClose={onClose} width={600}
           footer={<div className="inline" style={{ justifyContent: "flex-end", width: "100%" }}>
             <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
             <button className="btn" disabled={!sc} onClick={create}>{t("studio.create")}</button></div>}>
      <div className="stack" style={{ gap: 12 }}>
        {err && <ErrorBanner message={err} />}
        {scopes.length === 0 && <div className="banner small">{t("studio.no_scope")}</div>}
        <div><label className="field-label">{t("studio.name")}</label>
          <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder={t("studio.name_ph")} /></div>
        <div><label className="field-label">{t("studio.scope")}</label>
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            {scopes.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
          <div className="small muted">{t("studio.scope_hint")}</div></div>
        <div><label className="field-label">{t("studio.from")}</label>
          <select value={from} onChange={(e) => setFrom(e.target.value ? Number(e.target.value) : "")}>
            {templates.filter((x) => x.system || x.published_number).map((x) => (
              <option key={x.id} value={x.id}>{x.system ? t("studio.standard") : `${x.name} (${scopeText(t, x)})`}</option>
            ))}
          </select></div>
        {!sc?.simple && (
          <div className="stack" style={{ gap: 6 }}>
            <label className="inline small" style={{ gap: 6 }}>
              <input type="radio" checked={mode === "derived"} onChange={() => setMode("derived")} />
              <span><span className="strong">{t("studio.mode_derived")}</span>, {t("studio.mode_derived_hint")}</span>
            </label>
            <label className="inline small" style={{ gap: 6 }}>
              <input type="radio" checked={mode === "detached"} onChange={() => setMode("detached")} />
              <span><span className="strong">{t("studio.mode_detached")}</span>, {t("studio.mode_detached_hint")}</span>
            </label>
          </div>
        )}
        {sc?.simple && <div className="small muted">{t("studio.simple_hint")}</div>}
      </div>
    </Modal>
  );
}

function ImportModal({ cat, onClose, onDone }: { cat: Catalog; onClose: () => void; onDone: (id: number) => void }) {
  const { t } = useI18n();
  const scopes = scopeOptions(cat, t).filter((s) => !s.simple);
  const [scope, setScope] = useState(scopes[0]?.key || "");
  const [file, setFile] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  async function go() {
    const sc = scopes.find((s) => s.key === scope);
    if (!sc || !file) return;
    try {
      const r = await api.post<TemplateMeta>("/api/exports/templates/import", { scope_type: sc.type, scope_id: sc.id, file });
      onDone(r.id);
    } catch (e) { setErr(errorText(e)); }
  }
  return (
    <Modal title={t("studio.import_file")} onClose={onClose} width={560}
           footer={<div className="inline" style={{ justifyContent: "flex-end", width: "100%" }}>
             <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
             <button className="btn" disabled={!file || !scope} onClick={go}>{t("studio.import")}</button></div>}>
      <div className="stack" style={{ gap: 12 }}>
        {err && <ErrorBanner message={err} />}
        <div className="small muted">{t("studio.import_hint")}</div>
        <input type="file" accept="application/json,.json" onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          try { setFile(JSON.parse(await f.text())); setErr(null); } catch { setErr(t("studio.import_bad")); }
        }} />
        {file?.name && <div className="small">{file.name} ({t(`studio.doc.${file.doc_kind}`)})</div>}
        <div><label className="field-label">{t("studio.scope")}</label>
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            {scopes.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select></div>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------------------
// The editor of one template
// ------------------------------------------------------------------------------
function defaultContext(m: TemplateMeta): DocContext {
  const d = new Date();
  const ctx: DocContext = {};
  if (m.scope_type === "tribe") ctx.tribe_id = m.scope_id;
  if (m.scope_type === "squad") ctx.squad_id = m.scope_id;
  if (m.scope_type === "platform") ctx.platform_id = m.scope_id;
  if (m.doc_kind === "steerco") ctx.period = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  return ctx;
}

function TemplateEditor({ id, applyTo, cat, themes, assets, onClose, onLib }: {
  id: number; applyTo?: ScopeOpt; cat: Catalog; themes: Theme[]; assets: Asset[]; onClose: () => void; onLib: () => void;
}) {
  const { t, lang } = useI18n();
  const [d, setD] = useState<TemplateDetail | null>(null);
  const [spec, setSpec] = useState<Spec | null>(null);
  const [locks, setLocks] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ctx, setCtx] = useState<DocContext>({});
  const [modal, setModal] = useState<null | "publish" | "versions" | "assign">(null);
  const [simple, setSimple] = useState(true);

  async function load() {
    try {
      const r = await api.get<TemplateDetail>(`/api/exports/templates/${id}`);
      setD(r); setSpec(clone(r.spec)); setLocks(r.locks); setName(r.name);
      setCtx((c) => (Object.keys(c).length ? c : { ...defaultContext(r), lang }));
    } catch (e) { setErr(errorText(e)); }
  }
  useEffect(() => { load(); }, [id]);

  const dirty = !!d && !!spec && (!same(spec, d.spec) || !same(locks, d.locks) || name !== d.name);
  const editable = !!d?.can_edit;
  const mode = d?.simple_only ? "simple" : "full";

  async function save(): Promise<boolean> {
    if (!d || !spec) return false;
    setBusy(true); setMsg(null);
    try {
      const r = await api.put<TemplateDetail>(`/api/exports/templates/${id}`, { name, spec, locks });
      setD(r); setSpec(clone(r.spec)); setLocks(r.locks); setName(r.name);
      setMsg(t("studio.saved"));
      return true;
    } catch (e) { setErr(errorText(e)); return false; } finally { setBusy(false); }
  }
  /** Save, publish and (from the home) assign: the one button of the simple view. */
  async function apply() {
    if (!d) return;
    if (dirty && !(await save())) return;
    setBusy(true);
    try {
      const r = await api.post<TemplateDetail>(`/api/exports/templates/${id}/publish`, { comment: "" });
      if (applyTo && !r.assigned.includes(applyTo.key)) {
        await api.put("/api/exports/assignments", { doc_kind: d.doc_kind, scope_type: applyTo.type,
                                                   scope_id: applyTo.id, template_id: id });
      }
      const fresh = await api.get<TemplateDetail>(`/api/exports/templates/${id}`);
      setD(fresh); setSpec(clone(fresh.spec)); setLocks(fresh.locks);
      setMsg(applyTo ? t("simple.applied", { scope: applyTo.label }) : t("studio.published_msg"));
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }

  async function detach() {
    if (!window.confirm(t("studio.detach_confirm"))) return;
    try { await api.post(`/api/exports/templates/${id}/detach`); await load(); } catch (e) { setErr(errorText(e)); }
  }
  async function remove() {
    if (!d || !window.confirm(t("studio.delete_confirm", { name: d.name }))) return;
    try { await api.del(`/api/exports/templates/${id}`); onClose(); } catch (e) { setErr(errorText(e)); }
  }
  async function download() {
    if (!spec || !d) return;
    setBusy(true);
    try {
      await downloadPost("/api/exports/render", { doc_kind: d.doc_kind, spec, template_id: d.id, context: ctx }, `${d.doc_kind}.pptx`);
    } catch (e: any) { setErr(e?.message || String(e)); } finally { setBusy(false); }
  }

  if (err && !d) return <ErrorBanner message={err} />;
  if (!d || !spec) return <Spinner />;

  const simpleBar = (
    <div className="card studio-bar">
      <div className="between">
        <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
          <button className="btn-ghost btn-sm" onClick={() => { if (!dirty || window.confirm(t("studio.leave_confirm"))) onClose(); }}>
            ← {t("simple.back")}
          </button>
          <span className="strong" style={{ fontSize: 16 }}>{t(`studio.doc.${d.doc_kind}`)}</span>
          <span className="small muted">{applyTo ? applyTo.label : scopeText(t, d)}</span>
          {dirty && <span className="badge badge-orange">{t("simple.not_saved")}</span>}
        </div>
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          {editable && <button className="btn-secondary btn-sm" disabled={!dirty || busy}
                               onClick={() => { setSpec(clone(d.spec)); setLocks(d.locks); setName(d.name); }}>{t("simple.undo")}</button>}
          <button className="btn-secondary btn-sm" disabled={busy} onClick={download}>{t("studio.download_pptx")}</button>
          {editable && <button className="btn btn-sm" disabled={busy} onClick={apply}>
            {applyTo ? t("simple.save_apply") : t("simple.save_publish")}</button>}
          <button className="btn-ghost btn-sm" onClick={() => setSimple(false)}>{t("simple.advanced_editor")}</button>
        </div>
      </div>
      {err && <div style={{ marginTop: 8 }}><ErrorBanner message={err} /></div>}
      {msg && <div className="small" style={{ marginTop: 6, color: "var(--green)" }}>{msg}</div>}
      {!editable && <div className="small muted" style={{ marginTop: 6 }}>{t("simple.read_only")}</div>}
    </div>
  );

  if (simple) {
    return (
      <div className="studio-page">
        {simpleBar}
        <div className="studio-work">
          <div className="card" style={{ margin: 0 }}>
            <SimpleEditor cat={cat} spec={spec} onChange={setSpec} inherited={d.inherited_locks}
                          canAdd={!d.simple_only} themes={themes} assets={assets} showTheme={!d.simple_only}
                          readOnly={!editable} />
          </div>
          <div className="studio-right">
            <ContextBar kind={d.doc_kind} cat={cat} ctx={ctx} onChange={setCtx} />
            <Preview docKind={d.doc_kind} spec={spec} templateId={d.id} context={ctx} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="studio-page">
      <div className="card studio-bar">
        <div className="between">
          <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
            <button className="btn-ghost btn-sm" onClick={() => { if (!dirty || window.confirm(t("studio.leave_confirm"))) onClose(); }}>
              ← {t("studio.back")}
            </button>
            {editable ? (
              <input className="studio-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)}
                     aria-label={t("studio.name")} />
            ) : <span className="strong">{d.system ? t("studio.standard") : d.name}</span>}
            <span className="badge badge-grey">{t(`studio.doc.${d.doc_kind}`)}</span>
            <span className="small muted">{scopeText(t, d)}</span>
            {d.mode === "derived" && d.parent_name && <span className="badge badge-navy">{t("studio.derived_from", { name: d.parent_name })}</span>}
            {d.published_number ? <span className="badge badge-green">{t("studio.published_v", { n: d.published_number })}</span>
              : <span className="badge badge-grey">{t("studio.draft")}</span>}
            {(dirty || d.unpublished_changes) && !d.system && <span className="badge badge-orange">{t("studio.unpublished")}</span>}
            {d.simple_only && editable && <span className="badge badge-grey">{t("studio.simple_mode")}</span>}
          </div>
          <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
            <button className="btn-ghost btn-sm" onClick={() => setSimple(true)}>{t("simple.simple_editor")}</button>
            <button className="btn-secondary btn-sm" disabled={busy} onClick={download}>{t("studio.download_pptx")}</button>
            <button className="btn-secondary btn-sm" onClick={() => setModal("versions")}>{t("studio.versions")}</button>
            {editable && <button className="btn-secondary btn-sm" onClick={() => setModal("assign")}>{t("studio.assign")}</button>}
            {editable && <button className="btn-secondary btn-sm" disabled={!dirty || busy} onClick={save}>{t("studio.save_draft")}</button>}
            {editable && <button className="btn btn-sm" disabled={busy} onClick={() => setModal("publish")}>{t("studio.publish")}</button>}
            {!d.system && (
              <details className="studio-more">
                <summary className="btn-ghost btn-sm">{t("studio.more")}</summary>
                <div className="card menu-pop">
                  <a className="menu-item" href={`/api/exports/templates/${id}/file`} download>{t("studio.export_file")}</a>
                  {editable && d.mode === "derived" && !d.simple_only && <button className="menu-item" onClick={detach}>{t("studio.detach")}</button>}
                  {editable && <button className="menu-item" onClick={remove}>{t("studio.delete")}</button>}
                </div>
              </details>
            )}
          </div>
        </div>
        {d.system && <div className="small muted" style={{ marginTop: 6 }}>{t("studio.standard_edit_hint")}</div>}
        {err && <div style={{ marginTop: 8 }}><ErrorBanner message={err} /></div>}
        {msg && <div className="small muted" style={{ marginTop: 6 }}>{msg}</div>}
        {d.skipped.length > 0 && (
          <div className="banner small" style={{ marginTop: 8 }}>
            {t("studio.skipped_intro")}
            <ul style={{ margin: "4px 0 0 18px" }}>
              {d.skipped.map((s, i) => <li key={i}>{s.path}: {t(`studio.skipped_${s.reason}`)}</li>)}
            </ul>
          </div>
        )}
      </div>

      <div className="studio-work">
        <SpecEditor cat={cat} spec={spec} onChange={setSpec} parent={d.parent_spec} inherited={d.inherited_locks}
                    locks={locks} onLocks={editable && !d.simple_only ? setLocks : undefined} mode={mode}
                    themes={themes} assets={assets} readOnly={!editable} />
        <div className="studio-right">
          <ContextBar kind={d.doc_kind} cat={cat} ctx={ctx} onChange={setCtx} />
          <Preview docKind={d.doc_kind} spec={spec} templateId={d.id} context={ctx} />
        </div>
      </div>

      {modal === "publish" && (
        <PublishModal onClose={() => setModal(null)} onPublish={async (comment) => {
          if (dirty && !(await save())) return;
          try {
            const r = await api.post<TemplateDetail>(`/api/exports/templates/${id}/publish`, { comment });
            setD(r); setSpec(clone(r.spec)); setLocks(r.locks); setModal(null); setMsg(t("studio.published_msg"));
          } catch (e) { setErr(errorText(e)); }
        }} />
      )}
      {modal === "versions" && <VersionsModal d={d} onClose={() => setModal(null)} onRestored={() => { setModal(null); load(); }} />}
      {modal === "assign" && <AssignModal cat={cat} d={d} onClose={() => { setModal(null); load(); onLib(); }} />}
    </div>
  );
}

/** Which data the preview runs on: the scope, the version date, the language. */
function ContextBar({ kind, cat, ctx, onChange }: { kind: DocKind; cat: Catalog; ctx: DocContext; onChange: (c: DocContext) => void }) {
  const { t } = useI18n();
  const report = ["dashboard", "weekly", "roadmap"].includes(kind);
  const val = ctx.squad_id ? `squad:${ctx.squad_id}` : ctx.platform_id ? `platform:${ctx.platform_id}` : ctx.tribe_id ? `tribe:${ctx.tribe_id}` : "";
  const opts = scopeOptions(cat, t, kind).filter((o) => o.type !== "global" && (o.type !== "squad" || report));
  return (
    <div className="studio-context">
      <label className="small">{t("studio.preview_on")}</label>
      <select value={val} onChange={(e) => {
        const [type, id] = e.target.value.split(":");
        const n: DocContext = { lang: ctx.lang, period: ctx.period, as_of: ctx.as_of };
        if (type === "tribe") n.tribe_id = Number(id);
        if (type === "squad") n.squad_id = Number(id);
        if (type === "platform") n.platform_id = Number(id);
        onChange(n);
      }}>
        <option value="">{cat.scopes.global ? t("studio.scope_all") : t("studio.scope_mine")}</option>
        {opts.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
      </select>
      {kind === "steerco" && (
        <input type="month" value={ctx.period || ""} onChange={(e) => onChange({ ...ctx, period: e.target.value })}
               aria-label={t("studio.period")} />
      )}
      {report && (
        <input type="date" value={ctx.as_of || ""} title={t("studio.as_of_hint")} aria-label={t("studio.as_of")}
               onChange={(e) => onChange({ ...ctx, as_of: e.target.value || undefined })} />
      )}
      <select value={ctx.lang || "fr"} onChange={(e) => onChange({ ...ctx, lang: e.target.value })} aria-label={t("studio.lang")}>
        <option value="fr">FR</option><option value="en">EN</option>
      </select>
    </div>
  );
}

function PublishModal({ onClose, onPublish }: { onClose: () => void; onPublish: (comment: string) => void }) {
  const { t } = useI18n();
  const [comment, setComment] = useState("");
  return (
    <Modal title={t("studio.publish")} onClose={onClose} width={520}
           footer={<div className="inline" style={{ justifyContent: "flex-end", width: "100%" }}>
             <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
             <button className="btn" onClick={() => onPublish(comment)}>{t("studio.publish")}</button></div>}>
      <div className="stack" style={{ gap: 10 }}>
        <div className="small">{t("studio.publish_hint")}</div>
        <div><label className="field-label">{t("studio.publish_comment")}</label>
          <input value={comment} maxLength={300} onChange={(e) => setComment(e.target.value)} /></div>
      </div>
    </Modal>
  );
}

type Change = { path: string; before: any; after: any };

function ChangesList({ changes }: { changes: Change[] }) {
  const { t } = useI18n();
  const show = (v: any) => (v === null || v === undefined || v === "" ? t("studio.none") : typeof v === "boolean"
    ? t(v ? "studio.yes" : "studio.no") : Array.isArray(v) ? v.join(", ") : String(v));
  if (!changes.length) return <div className="small muted">{t("studio.no_change")}</div>;
  return (
    <table className="studio-changes">
      <thead><tr><th>{t("studio.change_what")}</th><th>{t("studio.change_before")}</th><th>{t("studio.change_after")}</th></tr></thead>
      <tbody>{changes.map((c, i) => <tr key={i}><td>{c.path}</td><td>{show(c.before)}</td><td>{show(c.after)}</td></tr>)}</tbody>
    </table>
  );
}

function VersionsModal({ d, onClose, onRestored }: { d: TemplateDetail; onClose: () => void; onRestored: () => void }) {
  const { t, formatDateTime } = useI18n();
  const [cmp, setCmp] = useState<{ label: string; changes: Change[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function compare(a: string, b: string, label: string) {
    try {
      const r = await api.get<{ changes: Change[] }>(`/api/exports/templates/${d.id}/compare?a=${a}&b=${b}`);
      setCmp({ label, changes: r.changes });
    } catch (e) { setErr(errorText(e)); }
  }
  async function restore(vid: number) {
    if (!window.confirm(t("studio.restore_confirm"))) return;
    try { await api.post(`/api/exports/templates/${d.id}/restore`, { version_id: vid }); onRestored(); }
    catch (e) { setErr(errorText(e)); }
  }
  return (
    <Modal title={t("studio.versions")} onClose={onClose} width={760}>
      <div className="stack" style={{ gap: 12 }}>
        {err && <ErrorBanner message={err} />}
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          <button className="btn-secondary btn-sm" onClick={() => compare("published", "draft", t("studio.cmp_draft"))}>{t("studio.cmp_draft")}</button>
          {d.parent_spec && <button className="btn-secondary btn-sm" onClick={() => compare("parent", "draft", t("studio.cmp_parent"))}>{t("studio.cmp_parent")}</button>}
        </div>
        {d.versions.length === 0 && <div className="small muted">{t("studio.no_version")}</div>}
        {d.versions.length > 0 && (
          <table>
            <thead><tr><th>{t("studio.version")}</th><th>{t("studio.when")}</th><th>{t("studio.who")}</th><th>{t("studio.comment")}</th><th /></tr></thead>
            <tbody>
              {d.versions.map((v) => (
                <tr key={v.id}>
                  <td>v{v.number} {v.current && <span className="badge badge-green">{t("studio.current")}</span>}</td>
                  <td className="small">{formatDateTime(v.created_at)}</td>
                  <td className="small">{v.author || ""}</td>
                  <td className="small">{v.comment}</td>
                  <td className="inline" style={{ gap: 4 }}>
                    <button className="btn-ghost btn-xs" onClick={() => compare(String(v.id), "draft", t("studio.cmp_version", { n: v.number }))}>{t("studio.compare")}</button>
                    {d.can_edit && <button className="btn-ghost btn-xs" onClick={() => restore(v.id)}>{t("studio.restore")}</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {cmp && (
          <div className="stack" style={{ gap: 6 }}>
            <div className="strong small">{cmp.label}</div>
            <ChangesList changes={cmp.changes} />
          </div>
        )}
      </div>
    </Modal>
  );
}

function AssignModal({ cat, d, onClose }: { cat: Catalog; d: TemplateDetail; onClose: () => void }) {
  const { t } = useI18n();
  const scopes = scopeOptions(cat, t, d.doc_kind);
  const [rows, setRows] = useState<{ scope_key: string; template_id: number; template_name: string | null }[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api.get<any[]>(`/api/exports/assignments?doc_kind=${d.doc_kind}`).then(setRows).catch((e) => setErr(errorText(e)));
  useEffect(() => { load(); }, []);
  async function set(s: ScopeOpt, on: boolean) {
    try {
      await api.put("/api/exports/assignments", { doc_kind: d.doc_kind, scope_type: s.type, scope_id: s.id, template_id: on ? d.id : null });
      await load();
    } catch (e) { setErr(errorText(e)); }
  }
  return (
    <Modal title={t("studio.assign_title", { name: d.name })} onClose={onClose} width={640}>
      <div className="stack" style={{ gap: 10 }}>
        {err && <ErrorBanner message={err} />}
        {!d.published_number && <div className="banner small">{t("studio.assign_publish_first")}</div>}
        <div className="small muted">{t("studio.assign_hint")}</div>
        <table>
          <tbody>
            {scopes.map((s) => {
              const cur = rows.find((r) => r.scope_key === s.key);
              const mine = cur?.template_id === d.id;
              return (
                <tr key={s.key}>
                  <td>{s.label}</td>
                  <td className="small muted">{cur ? (mine ? t("studio.uses_this") : t("studio.uses_other", { name: cur.template_name || "" })) : t("studio.inherits")}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className={mine ? "btn-secondary btn-sm" : "btn btn-sm"} disabled={!d.published_number}
                            onClick={() => set(s, !mine)}>{mine ? t("studio.unassign") : t("studio.assign_here")}</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------------------
// Assignments overview
// ------------------------------------------------------------------------------
function AssignmentsTab({ cat }: { cat: Catalog }) {
  const { t } = useI18n();
  const [kind, setKind] = useState<DocKind>("dashboard");
  const [rows, setRows] = useState<{ scope_key: string; template_id: number }[]>([]);
  const [tpls, setTpls] = useState<TemplateMeta[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const load = () => Promise.all([
    api.get<any[]>(`/api/exports/assignments?doc_kind=${kind}`).then(setRows),
    api.get<TemplateMeta[]>(`/api/exports/templates?doc_kind=${kind}`).then(setTpls),
  ]).catch((e) => setErr(errorText(e)));
  useEffect(() => { load(); }, [kind]);
  const scopes = scopeOptions(cat, t, kind);
  const usable = tpls.filter((x) => x.published_number);
  async function set(s: ScopeOpt, tid: string) {
    try {
      await api.put("/api/exports/assignments", { doc_kind: kind, scope_type: s.type, scope_id: s.id, template_id: tid ? Number(tid) : null });
      await load();
    } catch (e) { setErr(errorText(e)); }
  }
  const nameOf = (id: number) => tpls.find((x) => x.id === id)?.name ?? "";
  // What a scope uses when it has no assignment of its own.
  function inherited(s: ScopeOpt): string {
    const chain: string[] = [];
    if (s.type === "squad") {
      const sq = cat.scopes.squads.find((x) => x.id === s.id);
      if (sq) chain.push(`tribe:${sq.tribe_id}`);
    }
    if (s.type === "platform") {
      const p = cat.scopes.platforms.find((x) => x.id === s.id);
      if (p) chain.push(`tribe:${p.tribe_id}`);
    }
    if (s.type !== "global") chain.push("global");
    for (const k of chain) {
      const r = rows.find((x) => x.scope_key === k);
      if (r) return nameOf(r.template_id);
    }
    return t("studio.standard");
  }
  return (
    <div className="stack" style={{ gap: 14 }}>
      <DocPicker cat={cat} value={kind} onChange={setKind} />
      <div className="small muted">{t("studio.assignments_hint")}</div>
      {err && <ErrorBanner message={err} />}
      <div className="card">
        <table>
          <thead><tr><th>{t("studio.scope")}</th><th>{t("studio.template")}</th><th>{t("studio.effective")}</th></tr></thead>
          <tbody>
            {scopes.map((s) => {
              const cur = rows.find((r) => r.scope_key === s.key);
              return (
                <tr key={s.key}>
                  <td>{s.label}</td>
                  <td>
                    <select value={cur?.template_id ?? ""} onChange={(e) => set(s, e.target.value)}>
                      <option value="">{t("studio.inherits")}</option>
                      {usable.map((x) => <option key={x.id} value={x.id}>{x.system ? t("studio.standard") : `${x.name} (${scopeText(t, x)})`}</option>)}
                    </select>
                  </td>
                  <td className="small muted">{cur ? nameOf(cur.template_id) : inherited(s)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------
// Themes
// ------------------------------------------------------------------------------
const THEME_DEFAULTS: Record<string, string> = {
  primary: "#1E2761", primary_deep: "#141B47", accent: "#175CD3", green: "#027A48", orange: "#B54708",
  red: "#B42318", ink: "#111827", muted: "#55606E", line: "#E2E8F0", card: "#F1F5F9", background: "#F5F7FA",
  zebra: "#F8FAFC",
};

function ThemesTab({ cat, themes, assets, onChanged }: { cat: Catalog; themes: Theme[]; assets: Asset[]; onChanged: () => void }) {
  const { t } = useI18n();
  const [edit, setEdit] = useState<Theme | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const tribes = cat.scopes.tribes;
  async function remove(th: Theme) {
    if (!window.confirm(t("studio.theme_delete_confirm", { name: th.name }))) return;
    try { await api.del(`/api/exports/themes/${th.id}`); onChanged(); } catch (e) { setErr(errorText(e)); }
  }
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="between">
        <div className="small muted">{t("studio.themes_hint")}</div>
        <button className="btn btn-sm" onClick={() => setEdit({ id: 0, name: "", tribe_id: cat.scopes.global ? null : tribes[0]?.id ?? null,
          master_asset_id: null, can_edit: true, config: { palette: {}, font: "", font_scale: 1.15 } })}>{t("studio.new_theme")}</button>
      </div>
      {err && <ErrorBanner message={err} />}
      {themes.length === 0 && <EmptyState message={t("studio.no_theme")} />}
      <div className="studio-cards">
        {themes.map((th) => (
          <div key={th.id} className="card studio-card">
            <div className="between"><span className="strong">{th.name}</span>
              <span className="small muted">{th.tribe_id ? tribes.find((x) => x.id === th.tribe_id)?.name ?? "" : t("studio.scope_global")}</span></div>
            <div className="studio-swatches">
              {cat.theme_keys.map((k) => <span key={k} title={t(`studio.color.${k}`)} style={{ background: th.config.palette[k] || THEME_DEFAULTS[k] }} />)}
            </div>
            <div className="small muted">{th.config.font || t("studio.font_master")}, {Math.round(th.config.font_scale * 100)} %</div>
            {th.can_edit && (
              <div className="inline" style={{ gap: 6 }}>
                <button className="btn-secondary btn-sm" onClick={() => setEdit(th)}>{t("action.edit")}</button>
                <button className="btn-ghost btn-sm" onClick={() => remove(th)}>{t("studio.delete")}</button>
              </div>
            )}
          </div>
        ))}
      </div>
      {edit && <ThemeModal cat={cat} theme={edit} assets={assets} onClose={() => setEdit(null)}
                           onSaved={() => { setEdit(null); onChanged(); }} />}
    </div>
  );
}

function ThemeModal({ cat, theme, assets, onClose, onSaved }: {
  cat: Catalog; theme: Theme; assets: Asset[]; onClose: () => void; onSaved: () => void;
}) {
  const { t } = useI18n();
  const [th, setTh] = useState<Theme>(clone(theme));
  const [err, setErr] = useState<string | null>(null);
  const pal = th.config.palette;
  async function save() {
    try {
      const body = { name: th.name, tribe_id: th.tribe_id, config: th.config, master_asset_id: th.master_asset_id };
      if (th.id) await api.put(`/api/exports/themes/${th.id}`, body);
      else await api.post("/api/exports/themes", body);
      onSaved();
    } catch (e) { setErr(errorText(e)); }
  }
  return (
    <Modal title={th.id ? t("studio.edit_theme") : t("studio.new_theme")} onClose={onClose} width={720} dirty
           footer={<div className="inline" style={{ justifyContent: "flex-end", width: "100%" }}>
             <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
             <button className="btn" disabled={!th.name.trim()} onClick={save}>{t("action.save")}</button></div>}>
      <div className="stack" style={{ gap: 12 }}>
        {err && <ErrorBanner message={err} />}
        <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div><label className="field-label">{t("studio.name")}</label>
            <input value={th.name} maxLength={120} onChange={(e) => setTh({ ...th, name: e.target.value })} /></div>
          {!th.id && (
            <div><label className="field-label">{t("studio.scope")}</label>
              <select value={th.tribe_id ?? ""} onChange={(e) => setTh({ ...th, tribe_id: e.target.value ? Number(e.target.value) : null })}>
                {cat.scopes.global && <option value="">{t("studio.scope_global")}</option>}
                {cat.scopes.tribes.map((x) => <option key={x.id} value={x.id}>{t("studio.scope_tribe")} {x.name}</option>)}
              </select></div>
          )}
        </div>
        <div><label className="field-label">{t("studio.master")}</label>
          <select value={th.master_asset_id ?? ""} onChange={(e) => setTh({ ...th, master_asset_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">{t("studio.master_default")}</option>
            {assets.filter((a) => a.kind === "pptx").map((a) => <option key={a.id} value={a.id}>{a.filename}</option>)}
          </select>
          <div className="small muted">{t("studio.master_hint")}</div></div>
        <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div><label className="field-label">{t("studio.font")}</label>
            <select value={th.config.font} onChange={(e) => setTh({ ...th, config: { ...th.config, font: e.target.value } })}>
              {cat.fonts.map((f) => <option key={f} value={f}>{f || t("studio.font_master")}</option>)}
            </select></div>
          <div><label className="field-label">{t("studio.font_scale", { n: Math.round(th.config.font_scale * 100) })}</label>
            <input type="range" min={0.8} max={1.5} step={0.05} value={th.config.font_scale}
                   onChange={(e) => setTh({ ...th, config: { ...th.config, font_scale: Number(e.target.value) } })} /></div>
        </div>
        <div>
          <label className="field-label">{t("studio.colors")}</label>
          <div className="studio-colors">
            {cat.theme_keys.map((k) => (
              <label key={k} className="studio-color">
                <input type="color" value={pal[k] || THEME_DEFAULTS[k]}
                       onChange={(e) => setTh({ ...th, config: { ...th.config, palette: { ...pal, [k]: e.target.value.toUpperCase() } } })} />
                <span className="small">{t(`studio.color.${k}`)}</span>
                {pal[k] && <button type="button" className="btn-ghost btn-xs" onClick={() => {
                  const n = { ...pal }; delete n[k]; setTh({ ...th, config: { ...th.config, palette: n } });
                }}>{t("studio.clear")}</button>}
              </label>
            ))}
          </div>
          <div className="small muted">{t("studio.colors_hint")}</div>
        </div>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------------------
// Files
// ------------------------------------------------------------------------------
function FilesTab({ cat, assets, onChanged }: { cat: Catalog; assets: Asset[]; onChanged: () => void }) {
  const { t } = useI18n();
  const [err, setErr] = useState<string | null>(null);
  const [tribe, setTribe] = useState<string>(cat.scopes.global ? "" : String(cat.scopes.tribes[0]?.id ?? ""));
  const [busy, setBusy] = useState(false);
  async function upload(f: File) {
    setBusy(true); setErr(null);
    const form = new FormData();
    form.append("file", f);
    if (tribe) form.append("tribe_id", tribe);
    try { await api.postForm("/api/exports/assets", form); onChanged(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }
  async function remove(a: Asset) {
    if (!window.confirm(t("studio.file_delete_confirm", { name: a.filename }))) return;
    try { await api.del(`/api/exports/assets/${a.id}`); onChanged(); } catch (e) { setErr(errorText(e)); }
  }
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="card stack" style={{ gap: 10 }}>
        <div className="small muted">{t("studio.files_hint")}</div>
        <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
          <select value={tribe} onChange={(e) => setTribe(e.target.value)} aria-label={t("studio.scope")}>
            {cat.scopes.global && <option value="">{t("studio.scope_global")}</option>}
            {cat.scopes.tribes.map((x) => <option key={x.id} value={x.id}>{t("studio.scope_tribe")} {x.name}</option>)}
          </select>
          <input type="file" disabled={busy} accept=".pptx,image/png,image/jpeg,image/gif"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
          {busy && <span className="small muted">{t("common.sending")}</span>}
        </div>
      </div>
      {err && <ErrorBanner message={err} />}
      {assets.length === 0 ? <EmptyState message={t("studio.no_file_yet")} /> : (
        <div className="card">
          <table>
            <thead><tr><th /><th>{t("studio.file")}</th><th>{t("studio.kind")}</th><th>{t("studio.size")}</th><th /></tr></thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.id}>
                  <td style={{ width: 64 }}>{a.kind === "image" && <img src={`/api/exports/assets/${a.id}/raw`} alt="" style={{ maxWidth: 56, maxHeight: 36 }} />}</td>
                  <td>{a.filename}</td>
                  <td className="small">{t(`studio.kind_${a.kind}`)}</td>
                  <td className="small">{Math.round(a.size / 1024)} Ko</td>
                  <td style={{ textAlign: "right" }}><button className="btn-ghost btn-sm" onClick={() => remove(a)}>{t("studio.delete")}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
