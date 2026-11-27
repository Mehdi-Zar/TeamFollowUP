// Customer Success > Projets: a band of figures, the filters, then the projects in
// one table, one line per project (docs/37, section 4).
//
// The indicators come from GET /api/cs/dashboard. Those that count projects are
// also filters: clicking one keeps only the projects it counts. The filters
// (stage, health, delivered and closed) narrow the same table.
// Each user chooses the indicators and the columns they see ("Personnaliser");
// the choice is kept in the browser. The table sorts on every column (shared
// tableView), never scrolls sideways (a long text is cut, its whole text shows on
// hover). Only the Update button at the end of a line opens the project.
import { Fragment, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { CsSettings, Dashboard, DiscountKind, HEALTHS, Project, fmtAmount, fmtDate, shownSettings } from "../../cs";
import { EmptyState, ErrorBanner, Modal, Spinner, Toggle } from "../ui";
import { Col, SortTh, TableSearch, useTableView } from "../tableView";
import CsProjectModal, { DiscountInput } from "./CsProjectModal";
import CsRecapModal from "./CsRecapModal";
import ExportMenu from "../ExportMenu";

type Quick = "" | "open" | "blocked" | "overdue" | "stale" | "todo" | "invoiced";
/** A status is chosen as words; its colour follows from it. */
const HEALTH_COLOR: Record<string, string> = { green: "var(--green)", amber: "var(--orange)", red: "var(--red)" };
const HEALTH_RANK: Record<string, number> = { red: 0, amber: 1, green: 2 };

const KPIS = ["open", "blocked", "overdue", "stale", "delivered", "todo", "invoiced", "paid"] as const;
type KpiKey = typeof KPIS[number];
/** The optional columns, with their share of the table's width. "project" is always shown. */
const COLS = { client: 13, requesters: 14, stage: 11, health: 11, follow: 24, contact: 9, build: 9, planned: 9 } as const;
type ColKey = keyof typeof COLS;
const COL_KEYS = Object.keys(COLS) as ColKey[];
const COL_CLASS: Record<ColKey, string> = {
  client: "c-client", requesters: "c-req", stage: "c-stage", health: "c-health", follow: "c-follow",
  contact: "c-contact", build: "c-build", planned: "c-planned",
};
const PROJECT_W = 20;
type ViewCfg = { kpis: KpiKey[]; cols: ColKey[] };
const DEFAULT_VIEW: ViewCfg = {
  kpis: ["open", "blocked", "todo", "invoiced"],
  cols: ["client", "requesters", "stage", "health", "follow", "contact"],
};
// v4: the billing figures; an older choice is replaced by the new default.
const VIEW_KEY = "cs.view4";

function readView(): ViewCfg {
  try {
    const v = JSON.parse(localStorage.getItem(VIEW_KEY) || "null");
    if (v && Array.isArray(v.kpis) && Array.isArray(v.cols)) {
      return {
        kpis: KPIS.filter((k) => v.kpis.includes(k)),
        cols: (v.cols as string[]).filter((k, i, a): k is ColKey => k in COLS && a.indexOf(k) === i),
      };
    }
  } catch { /* a broken value falls back to the default */ }
  return DEFAULT_VIEW;
}

export default function CsProjects({ tribeId, canRun }: { tribeId: number; canRun: boolean }) {
  const { t, lang } = useI18n();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [cfg, setCfg] = useState<CsSettings | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // The project open in its window, if any.
  const [openId, setOpenId] = useState<number | undefined>(undefined);
  const [creating, setCreating] = useState(false);
  // The project just created: its line is marked and a message offers to complete it.
  const [created, setCreated] = useState<{ id: number; title: string } | null>(null);
  const [recap, setRecap] = useState(false);
  const [custom, setCustom] = useState(false);
  const [viewCfg, setViewCfg] = useState<ViewCfg>(readView);
  const saveView = (v: ViewCfg) => { setViewCfg(v); localStorage.setItem(VIEW_KEY, JSON.stringify(v)); };
  const [drag, setDrag] = useState<ColKey | null>(null);
  const [dragOver, setDragOver] = useState<ColKey | null>(null);
  /** Puts column `from` where column `to` is (dragged right: after it; left: before it). */
  const moveCol = (from: ColKey, to: ColKey) => {
    if (from === to) return;
    const cols = viewCfg.cols.filter((c) => c !== from);
    const at = cols.indexOf(to) + (viewCfg.cols.indexOf(from) < viewCfg.cols.indexOf(to) ? 1 : 0);
    cols.splice(at, 0, from);
    saveView({ ...viewCfg, cols });
  };
  const [quick, setQuick] = useState<Quick>("");
  const [stage, setStage] = useState("");
  const [health, setHealth] = useState("");
  const [client, setClient] = useState("");
  const [showClosed, setShowClosed] = useState(() => localStorage.getItem("cs.show_closed") !== "0");

  const load = useCallback(() => {
    setErr(null);
    Promise.all([
      api.get<Project[]>(`/api/cs/projects?tribe_id=${tribeId}`),
      api.get<Dashboard>(`/api/cs/dashboard?tribe_id=${tribeId}`),
      api.get<CsSettings>(`/api/cs/settings?tribe_id=${tribeId}`),
    ]).then(([p, d, c]) => { setProjects(p); setDash(d); setCfg(c); })
      .catch((e) => setErr(errorText(e)));
  }, [tribeId]);
  useEffect(() => { setProjects(null); load(); }, [load]);

  // The stages as they read on screen (a default stage in the user's language).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const ui = useMemo(() => (cfg ? shownSettings(cfg, t) : null), [cfg, lang]);
  const stages = ui?.stages ?? [];
  const stageIdx = (key: string) => { const i = stages.findIndex((s) => s.key === key); return i < 0 ? 99 : i; };

  const filtered = useMemo(() => (projects ?? []).filter((p) => {
    if (!showClosed && p.closed && quick === "") return false;
    if (stage && p.stage !== stage) return false;
    if (client && (p.client ?? "") !== client) return false;
    if (health && (health === "none" ? p.health !== null : p.health !== health)) return false;
    if (quick === "open" && p.closed) return false;
    if (quick === "blocked" && !p.blocked) return false;
    if (quick === "overdue" && !p.overdue_items) return false;
    if (quick === "stale" && !p.stale) return false;
    if ((quick === "todo" || quick === "invoiced") && !(p.billing === quick && p.build_amount !== null)) return false;
    return true;
  }), [projects, quick, stage, health, client, showClosed]);
  const clients = useMemo(() => [...new Set((projects ?? []).map((p) => p.client).filter((c): c is string => !!c))]
    .sort((a, b) => a.localeCompare(b)), [projects]);
  const filtering = !!(quick || stage || health || client);
  const clearFilters = () => { setQuick(""); setStage(""); setHealth(""); setClient(""); };

  const followText = (p: Project) => p.blocker ? p.blocker.label : p.next_action?.label ?? "";
  const cols: Col<Project>[] = useMemo(() => [
    // Blocked first, then open by stage, then closed.
    { key: "status", value: (p) => (p.blocked ? 0 : p.closed ? 2000 : 1000) + stageIdx(p.stage), text: () => "" },
    { key: "title", value: (p) => p.title, text: (p) => [p.client, p.title, p.requesters].join(" ") },
    { key: "client", value: (p) => p.client ?? "", text: () => "" },
    { key: "stage", value: (p) => stageIdx(p.stage), text: (p) => stages.find((s) => s.key === p.stage)?.label ?? p.stage },
    { key: "health", value: (p) => (p.health ? HEALTH_RANK[p.health] : null), text: () => "" },
    { key: "requesters", value: (p) => p.requesters ?? "" },
    // Blockers first, then the next actions by due date.
    { key: "follow", value: (p) => (p.blocker ? `0 ${p.blocker.since ?? ""}` : p.next_action ? `1 ${p.next_action.due ?? "9999"}` : ""), text: followText },
    { key: "contact", value: (p) => p.last_contact ?? "", text: () => "" },
    { key: "build", value: (p) => p.net_amount ?? null, text: () => "" },
    { key: "planned", value: (p) => p.actual_delivery ?? p.planned_delivery ?? "", text: () => "" },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [stages]);
  const view = useTableView("cs.projects", filtered, cols, "status");

  if (err) return <ErrorBanner message={err} />;
  if (projects === null || dash === null || ui === null) return <Spinner />;

  const red = { color: "var(--red)" };
  const orange = { color: "var(--orange)" };
  const kpi: Record<KpiKey, { n: string | number; label: string; quick?: Quick; tone?: "red" | "orange" }> = {
    open: { n: dash.open, label: t("cs.kpi.open"), quick: "open" },
    blocked: { n: dash.blocked, label: t("cs.kpi.blocked"), quick: "blocked", tone: dash.blocked ? "red" : undefined },
    overdue: { n: dash.overdue_projects, label: t("cs.badge.overdue"), quick: "overdue", tone: dash.overdue_projects ? "red" : undefined },
    stale: { n: dash.stale, label: t("cs.badge.stale", { n: dash.stale_days }), quick: "stale", tone: dash.stale ? "orange" : undefined },
    delivered: { n: dash.delivered_year, label: t("cs.kpi.delivered", { year: dash.year }) },
    todo: { n: fmtAmount(dash.todo_total, lang) || "0", label: t("cs.kpi.todo"), quick: "todo", tone: dash.todo_total ? "orange" : undefined },
    invoiced: { n: fmtAmount(dash.invoiced_total, lang) || "0", label: t("cs.kpi.invoiced"), quick: "invoiced",
                tone: dash.invoiced_total ? "orange" : undefined },
    paid: { n: fmtAmount(dash.paid_total, lang) || "0", label: t("cs.kpi.paid") },
  };
  const shown = viewCfg.cols;
  const muted = <span className="muted">-</span>;
  const colTitle = (k: ColKey) => ({
    client: t("cs.f.client"), requesters: t("cs.f.requesters"), stage: t("cs.f.stage"), health: t("cs.f.health"),
    follow: t("cs.h.follow"), contact: t("cs.h.contact"), planned: t("cs.h.delivery"),
    build: t("cs.h.build"),
  })[k];
  /** One cell of a project's line. */
  const cell = (k: ColKey, p: Project): ReactNode => {
    switch (k) {
      case "client": return <td className="c-client" title={p.client ?? undefined}>{p.client || muted}</td>;
      case "requesters": return <td className="c-req" title={p.requesters ?? undefined}>{p.requesters || muted}</td>;
      case "stage": return <td className="c-stage">{stages.find((s) => s.key === p.stage)?.label ?? p.stage}</td>;
      case "health": return (
        <td className="c-health">{p.health ? <span style={{ color: HEALTH_COLOR[p.health] }}>{t(`cs.hv.${p.health}`)}</span> : muted}</td>
      );
      case "follow": {
        const follow = p.blocker ? t("cs.card.blocked", { label: p.blocker.label })
          : p.next_action ? [p.next_action.label, p.next_action.due && fmtDate(p.next_action.due, lang)].filter(Boolean).join(", ")
          : "";
        const tip = [follow, p.blocker?.days != null && t("cs.h.since_days", { n: p.blocker.days }),
          p.overdue_items > 0 && t("cs.card.overdue", { n: p.overdue_items })].filter(Boolean).join(", ");
        return <td className="c-follow" title={tip || undefined} style={p.blocker || p.next_action?.overdue ? red : undefined}>{follow || muted}</td>;
      }
      case "contact": return (
        <td className="c-contact" style={p.stale ? orange : undefined}
            title={p.stale ? t("cs.h.no_news", { n: p.days_since_contact }) : undefined}>
          {p.last_contact ? fmtDate(p.last_contact, lang) : muted}
        </td>
      );
      case "planned": return (
        <td className="c-planned">
          {p.actual_delivery ? fmtDate(p.actual_delivery, lang)
            : p.planned_delivery ? <span className="muted">{t("cs.h.planned_on", { d: fmtDate(p.planned_delivery, lang) })}</span>
            : muted}
        </td>
      );
      case "build": return (
        <td className="c-build" style={p.build_amount !== null && p.billing !== "paid" ? orange : undefined}
            title={p.build_amount !== null ? t(`cs.bill.${p.billing}`) + (p.discount_value
              ? `, ${t("cs.f.discount_on", { off: p.discount_kind === "pct" ? `${p.discount_value} %` : fmtAmount(p.discount_value, lang), price: fmtAmount(p.build_amount, lang) })}`
              : "") : undefined}>
          {fmtAmount(p.net_amount, lang) || muted}
        </td>
      );
    }
  };
  // The last column holds the button that opens a project to bring it up to date.
  const ACT_W = 11;
  const totalW = PROJECT_W + ACT_W + shown.reduce((s, c) => s + COLS[c], 0);
  const w = (n: number) => ({ width: `${(100 * n) / totalW}%` });
  const newBtn = canRun && <button className="btn-sm" onClick={() => setCreating(true)}>{t("cs.new")}</button>;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {viewCfg.kpis.length > 0 && (
        <div className="cs-band">
          {viewCfg.kpis.map((k) => {
            const x = kpi[k];
            const body = <>
              <span className="cs-band-n" style={x.tone === "red" ? red : x.tone === "orange" ? orange : undefined}>{x.n}</span>
              <span className="cs-band-l" title={x.label}>{x.label}</span>
            </>;
            return x.quick
              ? <button key={k} type="button" className={`cs-band-item${quick === x.quick ? " on" : ""}`} aria-pressed={quick === x.quick}
                        title={t("cs.kpi.filter_hint")} onClick={() => setQuick(quick === x.quick ? "" : x.quick!)}>{body}</button>
              : <div key={k} className="cs-band-item">{body}</div>;
          })}
        </div>
      )}

      {projects.length === 0 ? (
        <div className="stack" style={{ gap: 12 }}>
          {newBtn && <div>{newBtn}</div>}
          <EmptyState message={canRun ? t("cs.empty_run") : t("cs.empty")} />
        </div>
      ) : (
        <div className="card stack" style={{ gap: 12 }}>
          {created && (
            <div className="banner banner-green between" role="status" style={{ gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <span>{t("cs.created", { title: created.title })}</span>
              <span className="inline" style={{ gap: 8 }}>
                <button className="btn-sm" onClick={() => { setOpenId(created.id); setCreated(null); }}>{t("cs.complete_now")}</button>
                <button className="btn-ghost btn-sm" aria-label={t("action.close")} onClick={() => setCreated(null)}>×</button>
              </span>
            </div>
          )}
          <TableSearch view={view} id="cs-projects-search" right={
            <div className="inline" style={{ gap: 8, flexWrap: "wrap", alignItems: "center", marginLeft: "auto" }}>
              <button className="btn-ghost btn-sm" onClick={() => setCustom(true)}>{t("cs.custom.open")}</button>
              <button className="btn-secondary btn-sm" onClick={() => setRecap(true)}>{t("cs.recap.open")}</button>
              <ExportMenu docs={["cs"]} cs={{ tribeId }} />
              {newBtn}
            </div>
          } />
          <div className="cs-filters">
            <select className="w-auto" aria-label={t("cs.f.stage")} value={stage} onChange={(e) => setStage(e.target.value)}>
              <option value="">{t("cs.flt.all_stages")}</option>
              {stages.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
            {clients.length > 1 && (
              <select className="w-auto" aria-label={t("cs.f.client")} value={client} onChange={(e) => setClient(e.target.value)}>
                <option value="">{t("cs.flt.all_clients")}</option>
                {clients.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            )}
            <select className="w-auto" aria-label={t("cs.f.health")} value={health} onChange={(e) => setHealth(e.target.value)}>
              <option value="">{t("cs.flt.all_health")}</option>
              {HEALTHS.map((h) => <option key={h} value={h}>{t(`cs.hv.${h}`)}</option>)}
              <option value="none">{t("cs.health.none")}</option>
            </select>
            <Toggle checked={showClosed} onChange={(v) => { setShowClosed(v); localStorage.setItem("cs.show_closed", v ? "1" : "0"); }}>
              {t("cs.show_closed")}
            </Toggle>
            <span className="small muted" style={{ marginLeft: "auto" }}>{t("cs.flt.count", { n: view.rows.length, total: projects.length })}</span>
            {filtering && <button className="btn-ghost btn-sm" onClick={clearFilters}>{t("cs.flt.clear")}</button>}
          </div>

          {/* Never a horizontal scroll: fixed columns, one line per project, a long text cut.
              A column header can be dragged onto another to move the column. */}
          <table className="table cs-table">
            <thead>
              <tr>
                <SortTh view={view} col="title" className="c-project" style={w(PROJECT_W)}>{t("cs.h.project")}</SortTh>
                {shown.map((k) => (
                  <SortTh key={k} view={view} col={k} className={`${COL_CLASS[k]} cs-drag${dragOver === k && drag !== k ? " cs-drop" : ""}`}
                          style={w(COLS[k])} thProps={{
                            draggable: true, title: t("cs.custom.drag_hint"),
                            onDragStart: (e) => { setDrag(k); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", k); },
                            onDragOver: (e) => { if (drag) { e.preventDefault(); setDragOver(k); } },
                            onDragLeave: () => setDragOver(null),
                            onDrop: (e) => { e.preventDefault(); if (drag) moveCol(drag, k); setDrag(null); setDragOver(null); },
                            onDragEnd: () => { setDrag(null); setDragOver(null); },
                          }}>
                    {colTitle(k)}
                  </SortTh>
                ))}
                <th className="c-act" style={w(ACT_W)}><span className="sr-only">{t("cs.update")}</span></th>
              </tr>
            </thead>
            <tbody>
              {view.rows.length === 0 && (
                <tr><td colSpan={2 + shown.length} className="small muted">{t("list.no_match")}</td></tr>
              )}
              {view.rows.map((p) => (
                <tr key={p.id} className={`cs-row${created?.id === p.id ? " cs-row-new" : ""}`} style={p.closed ? { opacity: 0.6 } : undefined}>
                  <td className="c-project strong" title={p.title}>{p.title}</td>
                  {shown.map((k) => <Fragment key={k}>{cell(k, p)}</Fragment>)}
                  <td className="c-act">
                    <button className="btn-secondary btn-sm" onClick={() => setOpenId(p.id)}>
                      {p.can_edit ? t("cs.update") : t("cs.view")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openId !== undefined && <CsProjectModal projectId={openId} settings={ui} onClose={() => setOpenId(undefined)} onChanged={load} />}
      {recap && <CsRecapModal tribeId={tribeId} settings={ui} projects={projects} canRun={canRun}
                              onClose={() => setRecap(false)} onSaved={load} />}
      {creating && <CreateModal tribeId={tribeId} onClose={() => setCreating(false)}
                                onCreated={(p) => { setCreating(false); load(); setCreated({ id: p.id, title: p.title }); }} />}
      {custom && <CustomizeModal value={viewCfg} onClose={() => setCustom(false)}
                                 onSave={(v) => { saveView(v); setCustom(false); }} />}
    </div>
  );
}

/** A new project: only what the request says. The rest is brought up to date later,
 *  by opening the project from the table (CsProjectModal). */
function CreateModal({ tribeId, onClose, onCreated }: { tribeId: number; onClose: () => void; onCreated: (p: Project) => void }) {
  const { t } = useI18n();
  const [d, setD] = useState({ title: "", client: "", requesters: "", notes: "", planned: "", price: "" });
  const [disc, setDisc] = useState<{ value: number | null; kind: DiscountKind }>({ value: null, kind: "pct" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = Object.values(d).some((x) => x.trim());
  async function create() {
    setBusy(true); setErr(null);
    try {
      const p = await api.post<Project>("/api/cs/projects", {
        tribe_id: tribeId, title: d.title, client: d.client || null, requesters: d.requesters || null, notes: d.notes || null,
        planned_delivery: d.planned || null, build_amount: d.price === "" ? null : Number(d.price),
        discount_value: d.price === "" ? null : disc.value, discount_kind: disc.kind,
      });
      onCreated(p);
    } catch (e) { setErr(errorText(e)); setBusy(false); }
  }
  const field = (k: keyof typeof d, label: string, wide = false) => (
    <label className={`cs-field${wide ? " cs-wide" : ""}`}>
      <span className="cs-label">{label}</span>
      <input value={d[k]} autoFocus={k === "title"} maxLength={k === "requesters" ? 500 : 255}
             onChange={(e) => setD({ ...d, [k]: e.target.value })} />
    </label>
  );
  return (
    <Modal title={t("cs.new")} onClose={onClose} width={620} dirty={dirty}
           footer={<div className="inline" style={{ gap: 8, justifyContent: "flex-end", width: "100%" }}>
             <button className="btn-secondary btn-sm" onClick={onClose}>{t("action.cancel")}</button>
             <button className="btn-sm" disabled={busy || !d.title.trim()} onClick={create}>{t("cs.create")}</button>
           </div>}>
      <div className="stack" style={{ gap: 16 }}>
        <div className="small muted">{t("cs.create_hint")}</div>
        {err && <ErrorBanner message={err} />}
        <div className="cs-form">
          {field("title", t("cs.f.title"), true)}
          {field("client", t("cs.f.client"))}
          {field("requesters", t("cs.f.requesters"))}
          <label className="cs-field cs-wide">
            <span className="cs-label">{t("cs.f.notes")}</span>
            <textarea rows={4} value={d.notes} onChange={(e) => setD({ ...d, notes: e.target.value })} />
          </label>
          <label className="cs-field">
            <span className="cs-label">{t("cs.f.amount")}</span>
            <input type="number" min={0} step="0.01" value={d.price} onChange={(e) => setD({ ...d, price: e.target.value })} />
          </label>
          <DiscountInput price={d.price === "" ? null : Number(d.price)} value={disc.value} kind={disc.kind}
                         disabled={d.price === ""} onChange={(value, kind) => setDisc({ value, kind })} />
          <label className="cs-field">
            <span className="cs-label">{t("cs.f.wanted")}</span>
            <input type="date" value={d.planned} onChange={(e) => setD({ ...d, planned: e.target.value })} />
          </label>
        </div>
      </div>
    </Modal>
  );
}

/** Which indicators and which columns this user sees, and in which order. Kept in the browser. */
function CustomizeModal({ value, onClose, onSave }: { value: ViewCfg; onClose: () => void; onSave: (v: ViewCfg) => void }) {
  const { t } = useI18n();
  const [kpis, setKpis] = useState<KpiKey[]>(value.kpis);
  // Every column, the visible ones first in their order; a tick shows or hides one.
  const [order, setOrder] = useState<ColKey[]>([...value.cols, ...COL_KEYS.filter((k) => !value.cols.includes(k))]);
  const [on, setOn] = useState<ColKey[]>(value.cols);
  const [drag, setDrag] = useState<number | null>(null);
  const reset = () => {
    setKpis(DEFAULT_VIEW.kpis);
    setOrder([...DEFAULT_VIEW.cols, ...COL_KEYS.filter((k) => !DEFAULT_VIEW.cols.includes(k))]);
    setOn(DEFAULT_VIEW.cols);
  };
  const move = (from: number, to: number) => {
    if (from === to) return;
    const next = [...order];
    const [x] = next.splice(from, 1);
    next.splice(to, 0, x);
    setOrder(next);
  };
  return (
    <Modal title={t("cs.custom.title")} onClose={onClose} width={620}
           footer={<div className="between" style={{ width: "100%" }}>
             <button className="btn-ghost btn-sm" onClick={reset}>{t("cs.custom.reset")}</button>
             <div className="inline" style={{ gap: 8 }}>
               <button className="btn-secondary btn-sm" onClick={onClose}>{t("action.cancel")}</button>
               <button className="btn-sm" onClick={() => onSave({
                 kpis: KPIS.filter((k) => kpis.includes(k)),
                 cols: order.filter((k) => on.includes(k)),
               })}>{t("action.save")}</button>
             </div>
           </div>}>
      <div className="stack" style={{ gap: 20 }}>
        <div className="small muted">{t("cs.custom.hint")}</div>
        <div className="stack" style={{ gap: 8 }}>
          <div className="strong">{t("cs.custom.kpis")}</div>
          <div className="cs-checks">
            {KPIS.map((k) => (
              <label key={k} className="cs-check">
                <input type="checkbox" checked={kpis.includes(k)}
                       onChange={() => setKpis(kpis.includes(k) ? kpis.filter((x) => x !== k) : [...kpis, k])} />
                {t(`cs.custom.kpi.${k}`)}
              </label>
            ))}
          </div>
        </div>
        <div className="stack" style={{ gap: 8 }}>
          <div className="strong">{t("cs.custom.cols")}</div>
          <div className="small muted">{t("cs.custom.cols_hint")}</div>
          <ol className="cs-order">
            {order.map((k, i) => (
              <li key={k} draggable className={drag === i ? "dragging" : ""}
                  onDragStart={(e) => { setDrag(i); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", k); }}
                  onDragOver={(e) => { e.preventDefault(); if (drag !== null && drag !== i) { move(drag, i); setDrag(i); } }}
                  onDragEnd={() => setDrag(null)}>
                <span className="cs-grip" aria-hidden>⋮⋮</span>
                <label className="cs-check">
                  <input type="checkbox" checked={on.includes(k)}
                         onChange={() => setOn(on.includes(k) ? on.filter((x) => x !== k) : [...on, k])} />
                  {t(`cs.custom.col.${k}`)}
                </label>
                <span className="cs-order-btns">
                  <button type="button" className="btn-ghost btn-sm" disabled={i === 0} aria-label={t("cs.custom.up")}
                          onClick={() => move(i, i - 1)}>↑</button>
                  <button type="button" className="btn-ghost btn-sm" disabled={i === order.length - 1} aria-label={t("cs.custom.down")}
                          onClick={() => move(i, i + 1)}>↓</button>
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Modal>
  );
}
