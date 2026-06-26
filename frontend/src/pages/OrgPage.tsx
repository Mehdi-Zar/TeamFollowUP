import { MouseEvent as ReactMouseEvent, ReactNode, WheelEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { Member, OrgNode, Squad, SquadDetail, Tribe, Role } from "../types";
import { Spinner, ErrorBanner, FitScale, Modal } from "../components/ui";
import { HtmlPreviewButton } from "../components/HtmlPreview";
import { useSetPageChrome } from "../components/pageChrome";
import { canEditOrg } from "../perms";

type OrgView = "tree" | "list";

type Kind = "squad" | "entity";
interface FormState {
  mode: "create" | "edit";
  id?: number;
  kind: Kind;
  parent_id: number | null;
  title: string;
  squad_id: string;
}

interface Flat {
  id: number;
  label: string;
  depth: number;
}

function flatten(nodes: OrgNode[], depth = 0, acc: Flat[] = []): Flat[] {
  for (const n of nodes) {
    acc.push({ id: n.id, label: `${"- ".repeat(depth)}${n.title}`, depth });
    flatten(n.children, depth + 1, acc);
  }
  return acc;
}

function flattenNodes(nodes: OrgNode[], depth = 0, acc: { node: OrgNode; depth: number }[] = []) {
  for (const n of nodes) {
    acc.push({ node: n, depth });
    flattenNodes(n.children, depth + 1, acc);
  }
  return acc;
}

function descendantIds(node: OrgNode, acc: number[] = []): number[] {
  for (const c of node.children) {
    acc.push(c.id);
    descendantIds(c, acc);
  }
  return acc;
}

function findNode(nodes: OrgNode[], id: number): OrgNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const found = findNode(n.children, id);
    if (found) return found;
  }
  return null;
}

export default function OrgPage() {
  const { user, effectiveRole } = useAuth();
  const { t } = useI18n();
  const role = (effectiveRole ?? "member") as Role;
  const isAdmin = role === "admin";

  const [tree, setTree] = useState<OrgNode[] | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeId, setTribeId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [view, setView] = useState<OrgView>("tree");
  const [showAllMembers, setShowAllMembers] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  // editing only allowed on one's OWN tribe (admin: any tribe they select)
  const isOwnTribe = tribeId !== null && tribeId === user?.tribe_id;
  const editable = canEditOrg(role) && (isAdmin || isOwnTribe);

  function load(tid: number | null) {
    const q = tid ? `?tribe_id=${tid}` : "";
    api.get<OrgNode[]>(`/api/org${q}`).then(setTree).catch((e) => setError(e.message));
    api.get<Squad[]>(`/api/squads${q}`).then(setSquads).catch(() => {});
  }
  const [searchParams] = useSearchParams();
  useEffect(() => {
    api.get<Tribe[]>("/api/tribes").then((ts) => {
      setTribes(ts);
      // Optional ?tribe=ID (e.g. from the admin "all tribes" overview).
      const wanted = Number(searchParams.get("tribe")) || null;
      const def = (wanted && ts.some((x) => x.id === wanted) ? wanted : null)
        ?? user?.tribe_id ?? (ts.length ? ts[0].id : null);
      setTribeId(def);
      load(def);
    });
  }, []);

  function openCreate(parent_id: number | null) {
    setForm({ mode: "create", kind: "entity", parent_id, title: "", squad_id: "" });
  }
  function openEdit(n: OrgNode) {
    setForm({
      mode: "edit",
      id: n.id,
      kind: n.squad_id ? "squad" : "entity",
      parent_id: n.parent_id ?? null,
      title: n.title,
      squad_id: n.squad_id ? String(n.squad_id) : "",
    });
  }

  async function save() {
    if (!form) return;
    let title = form.title;
    let squad_id: number | null = null;
    if (form.kind === "squad" && form.squad_id) {
      squad_id = Number(form.squad_id);
      title = squads.find((s) => s.id === squad_id)?.name || form.title;
    }
    const body: any = { title, person_name: null, squad_id, parent_id: form.parent_id };
    if (isAdmin && form.mode === "create") body.tribe_id = tribeId;
    try {
      if (form.mode === "create") await api.post("/api/org", body);
      else await api.put(`/api/org/${form.id}`, body);
      setForm(null);
      load(tribeId);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(n: OrgNode) {
    if (!confirm(t("org.del_confirm"))) return;
    await api.del(`/api/org/${n.id}`);
    load(tribeId);
  }

  useSetPageChrome(
    {
      tabs: [
        { key: "tree", label: t("org.view_tree") },
        { key: "list", label: t("org.view_list") },
      ],
      activeTab: view,
      onTab: (k) => setView(k as OrgView),
      actions: (
        <>
          {view === "tree" && (
            <button
              className={showAllMembers ? "btn-secondary btn-sm" : "btn-ghost btn-sm"}
              onClick={() => setShowAllMembers((v) => !v)}
            >
              {showAllMembers ? t("org.hide_members") : t("org.show_members")}
            </button>
          )}
          {tribes.length > 1 && (
            <select
              className="w-auto"
              value={tribeId ?? ""}
              onChange={(e) => {
                const v = Number(e.target.value);
                setTribeId(v);
                load(v);
              }}
            >
              {tribes.map((tr) => (
                <option key={tr.id} value={tr.id}>
                  {tr.name}
                </option>
              ))}
            </select>
          )}
          {!editable && !isOwnTribe && tribeId !== null && (
            <span className="badge badge-grey">{t("org.view_only_other")}</span>
          )}
          {tribeId !== null && <OrgExportButton tribeId={tribeId} />}
          {editable && (
            <button className="btn-secondary btn-sm" onClick={() => openCreate(null)}>
              + {t("org.add_top")}
            </button>
          )}
        </>
      ),
    },
    [view, tribes, tribeId, editable, isOwnTribe, showAllMembers, t]
  );

  if (error) return <ErrorBanner message={error} />;
  if (!tree) return <Spinner />;

  // parent options: all nodes except (when editing) self and its descendants
  let exclude: number[] = [];
  if (form?.mode === "edit" && form.id) {
    const node = findNode(tree, form.id);
    exclude = node ? [form.id, ...descendantIds(node)] : [form.id];
  }
  const parentOptions = flatten(tree).filter((f) => !exclude.includes(f.id));

  const treeContent = (
    <div className="row" style={{ justifyContent: "center", alignItems: "flex-start", gap: 24, flexWrap: "nowrap" }}>
      {tree.map((n) => (
        <NodeView key={n.id} node={n} editable={editable} linkSquads={isAdmin || isOwnTribe} forceShowTeam={showAllMembers} onAdd={openCreate} onEdit={openEdit} onDelete={remove} />
      ))}
    </div>
  );

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="muted small">{editable ? t("org.subtitle_edit") : t("org.subtitle_ro")}</div>

      {tree.length === 0 && (
        <div className="card muted">{t("org.empty")} {editable ? t("org.empty_edit") : ""}</div>
      )}

      {tree.length > 0 && view === "tree" && (
        <div className="card">
          <div className="between" style={{ marginBottom: 8, alignItems: "center" }}>
            <span className="small muted">{t("org.fit_hint")}</span>
            <button className="btn-secondary btn-sm" onClick={() => setFullscreen(true)}>⛶ {t("org.fullscreen")}</button>
          </div>
          <FitScale>{treeContent}</FitScale>
        </div>
      )}

      {fullscreen && <OrgFullscreen onClose={() => setFullscreen(false)}>{treeContent}</OrgFullscreen>}

      {tree.length > 0 && view === "list" && (
        <div className="card stack" style={{ gap: 0 }}>
          {flattenNodes(tree).map(({ node, depth }) => (
            <div key={node.id} className="item-row">
              <div className="grow" style={{ paddingLeft: depth * 22 }}>
                <span className="strong small">{node.title}</span>
                {node.person_name && <span className="small muted"> - {node.person_name}</span>}
                {node.squad_id && (isAdmin || isOwnTribe) && (
                  <Link className="small" to={`/squads/${node.squad_id}`} style={{ marginLeft: 8 }}>
                    {t("org.see_squad")}
                  </Link>
                )}
              </div>
              {editable && (
                <div className="inline" style={{ gap: 4 }}>
                  <button className="btn-ghost btn-sm" title={t("org.add_below")} onClick={() => openCreate(node.id)}>+</button>
                  <button className="btn-ghost btn-sm" title={t("action.edit")} aria-label={t("action.edit")} onClick={() => openEdit(node)}>✎</button>
                  <button className="btn-danger btn-sm" title={t("action.delete")} aria-label={t("action.delete")} onClick={() => remove(node)}>✕</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {form && (
        <NodeForm form={form} squads={squads} parentOptions={parentOptions} onChange={setForm} onSave={save} onCancel={() => setForm(null)} />
      )}
    </div>
  );
}

function NodeView({
  node,
  editable,
  linkSquads,
  forceShowTeam,
  onAdd,
  onEdit,
  onDelete,
}: {
  node: OrgNode;
  editable: boolean;
  linkSquads: boolean;
  forceShowTeam: boolean;
  onAdd: (parentId: number) => void;
  onEdit: (n: OrgNode) => void;
  onDelete: (n: OrgNode) => void;
}) {
  const { t } = useI18n();
  const [showTeam, setShowTeam] = useState(false);
  const teamVisible = forceShowTeam || showTeam;
  const isSquad = !!node.squad_id;
  return (
    <div className="org-subtree">
      <div className={`org-box org-node${isSquad ? " org-node--squad" : ""}`}>
        {isSquad && linkSquads ? (
          <Link to={`/squads/${node.squad_id}`} className="strong small org-squad-link" title={t("org.see_squad")}>
            {node.title} ↗
          </Link>
        ) : (
          <div className="strong small">{node.title}</div>
        )}
        {node.person_name && <div className="small muted">{node.person_name}</div>}
        {node.squad_id && linkSquads && !forceShowTeam && (
          <div className="inline" style={{ gap: 8, marginTop: 4, justifyContent: "center", flexWrap: "wrap" }}>
            <button className="btn-ghost btn-sm" onClick={() => setShowTeam((v) => !v)}>
              {showTeam ? t("org.hide_team") : t("org.see_team")}
            </button>
          </div>
        )}
        {editable && (
          <div className="inline" style={{ justifyContent: "center", marginTop: 6, gap: 4 }}>
            <button className="btn-ghost btn-sm" title={t("org.add_below")} onClick={() => onAdd(node.id)}>
              +
            </button>
            <button className="btn-ghost btn-sm" title={t("action.save")} onClick={() => onEdit(node)}>
              ✎
            </button>
            <button className="btn-danger btn-sm" title={t("action.delete")} onClick={() => onDelete(node)}>
              ✕
            </button>
          </div>
        )}
      </div>
      {teamVisible && node.squad_id && <SquadTeam squadId={node.squad_id} />}
      {node.children.length > 0 && (() => {
        // Stack terminal children (e.g. a domain's squads) vertically so the
        // chart stays compact and readable instead of spreading very wide.
        const vertical = node.children.every((c) => c.children.length === 0);
        return (
          <>
            {!vertical && <div className="org-connector" />}
            <div className={vertical ? "org-children org-children--vertical" : "org-children"}>
              {node.children.map((c) => (
                <NodeView key={c.id} node={c} editable={editable} linkSquads={linkSquads} forceShowTeam={forceShowTeam} onAdd={onAdd} onEdit={onEdit} onDelete={onDelete} />
              ))}
            </div>
          </>
        );
      })()}
    </div>
  );
}

function SquadTeam({ squadId }: { squadId: number }) {
  const { t } = useI18n();
  const [data, setData] = useState<SquadDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.get<SquadDetail>(`/api/squads/${squadId}`).then(setData).catch(() => setFailed(true));
  }, [squadId]);

  if (failed) return null;
  if (!data) return <div className="small muted" style={{ marginTop: 8 }}>…</div>;
  if (data.members.length === 0) {
    return (
      <>
        <div className="org-connector" />
        <div className="org-box" style={{ minWidth: 160 }}><div className="small muted">{t("squad.no_members")}</div></div>
      </>
    );
  }

  const byManager: Record<string, Member[]> = {};
  for (const m of data.members) {
    const key = m.manager_id == null ? "root" : String(m.manager_id);
    (byManager[key] ||= []).push(m);
  }
  const roots = byManager["root"] || [];

  const renderMember = (m: Member) => (
    <div className="org-subtree" key={m.id}>
      <div className="org-box org-node" style={{ width: 168, minHeight: 0 }}>
        <div className="strong small">{m.full_name}</div>
        {m.role_title && <div className="small muted">{m.role_title}</div>}
      </div>
      {(byManager[String(m.id)]?.length ?? 0) > 0 && (
        <>
          <div className="org-connector" />
          <div className="org-children">{byManager[String(m.id)].map(renderMember)}</div>
        </>
      )}
    </div>
  );

  return (
    <>
      <div className="org-connector" />
      <div className="org-children">{roots.map(renderMember)}</div>
    </>
  );
}

function NodeForm({
  form,
  squads,
  parentOptions,
  onChange,
  onSave,
  onCancel,
}: {
  form: FormState;
  squads: Squad[];
  parentOptions: Flat[];
  onChange: (f: FormState) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const valid = form.kind === "squad" ? !!form.squad_id : !!form.title.trim();
  return (
    <div className="card" style={{ borderLeft: "4px solid var(--accent)" }}>
      <h3>{form.mode === "create" ? t("org.new") : t("org.edit")}</h3>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <div style={{ width: 220 }}>
          <label>{t("org.kind")}</label>
          <select value={form.kind} onChange={(e) => onChange({ ...form, kind: e.target.value as Kind })}>
            <option value="entity">{t("org.kind.entity")}</option>
            <option value="squad">{t("org.kind.squad")}</option>
          </select>
        </div>

        {form.kind === "squad" ? (
          <div style={{ width: 240 }}>
            <label>{t("org.pick_squad")}</label>
            <select value={form.squad_id} onChange={(e) => onChange({ ...form, squad_id: e.target.value })}>
              <option value="">-</option>
              {squads.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div style={{ width: 240 }}>
            <label>{t("org.entity_label")}</label>
            <input value={form.title} onChange={(e) => onChange({ ...form, title: e.target.value })} />
          </div>
        )}

        <div style={{ width: 240 }}>
          <label>{t("org.attach")}</label>
          <select value={form.parent_id ?? ""} onChange={(e) => onChange({ ...form, parent_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">{t("org.attach_top")}</option>
            {parentOptions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        <button onClick={onSave} disabled={!valid}>
          {t("action.save")}
        </button>
        <button className="btn-secondary" onClick={onCancel}>
          {t("action.cancel")}
        </button>
      </div>
    </div>
  );
}

/** Fullscreen org chart with a zoom (magnifier) control. Starts fitted to the
 *  screen; zoom in to read details - the view becomes pannable (scroll). */
function OrgFullscreen({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  const { t } = useI18n();
  const bodyRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState(1);
  const [zoom, setZoom] = useState(1);

  useLayoutEffect(() => {
    const measure = () => {
      const body = bodyRef.current, c = contentRef.current;
      if (!body || !c) return;
      const cw = c.scrollWidth, ch = c.scrollHeight;
      if (cw === 0 || ch === 0) return;
      const f = Math.max(0.3, Math.min(body.clientWidth / cw, body.clientHeight / ch, 1));
      setFit(f);
      setZoom((z) => (z === 1 ? f : z)); // initialise to the fit scale once
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (contentRef.current) ro.observe(contentRef.current);
    return () => ro.disconnect();
  }, []);

  const clamp = (z: number) => Math.max(0.2, Math.min(3, z));

  // Zoom while keeping the point under the cursor fixed (magnifier feel).
  function zoomAt(clientX: number, clientY: number, factor: number) {
    const body = bodyRef.current;
    if (!body) { setZoom((z) => clamp(z * factor)); return; }
    const rect = body.getBoundingClientRect();
    const ox = clientX - rect.left, oy = clientY - rect.top;
    setZoom((z) => {
      const nz = clamp(z * factor);
      const contentX = (body.scrollLeft + ox) / z;
      const contentY = (body.scrollTop + oy) / z;
      requestAnimationFrame(() => {
        body.scrollLeft = contentX * nz - ox;
        body.scrollTop = contentY * nz - oy;
      });
      return nz;
    });
  }

  const onWheel = (e: WheelEvent) => {
    if (e.ctrlKey) { e.preventDefault(); zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.12 : 0.9); }
  };
  const onClick = (e: ReactMouseEvent) => {
    // Let clicks on a squad link open the squad; otherwise click = zoom.
    if ((e.target as HTMLElement).closest("a")) return;
    e.stopPropagation();
    zoomAt(e.clientX, e.clientY, e.shiftKey || e.altKey ? 1 / 1.4 : 1.4);
  };

  return (
    <div className="org-fullscreen" onClick={onClose}>
      <div className="org-fullscreen-bar" onClick={(e) => e.stopPropagation()}>
        <span className="strong">{t("nav.org")}</span>
        <div className="inline" style={{ gap: 8, alignItems: "center" }}>
          <span className="small muted" style={{ marginRight: 4 }}>{t("org.zoom_hint")}</span>
          <button className="btn-secondary btn-sm" title={t("org.zoom_out")} onClick={() => setZoom((z) => clamp(z * 0.85))}>−</button>
          <span className="small" style={{ minWidth: 46, textAlign: "center" }}>{Math.round(zoom * 100)}%</span>
          <button className="btn-secondary btn-sm" title={t("org.zoom_in")} onClick={() => setZoom((z) => clamp(z * 1.18))}>+</button>
          <button className="btn-ghost btn-sm" onClick={() => setZoom(fit)}>{t("org.fit")}</button>
          <button className="btn-secondary btn-sm" onClick={onClose}>✕ {t("action.close")}</button>
        </div>
      </div>
      <div
        ref={bodyRef}
        className="org-fullscreen-body org-zoomable"
        style={{ display: "block", overflow: "auto" }}
        onClick={onClick}
        onWheel={onWheel}
      >
        <div ref={contentRef} style={{ transform: `scale(${zoom})`, transformOrigin: "0 0", width: "max-content" }}>
          {children}
        </div>
      </div>
    </div>
  );
}

/** Export the org chart (HTML / PPTX) with a picker for which top-level branches
 *  to include. Mirrors the roadmap export UX. */
function OrgExportButton({ tribeId }: { tribeId: number }) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  const [branches, setBranches] = useState<{ id: number; title: string; count: number }[]>([]);
  const [sel, setSel] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!open) return;
    api.get<{ id: number; title: string; count: number }[]>(`/api/org/export/branches?tribe_id=${tribeId}`)
      .then((b) => { setBranches(b); setSel(new Set(b.map((x) => x.id))); })
      .catch(() => setBranches([]));
  }, [open, tribeId]);

  const selIds = Array.from(sel);
  const allOn = branches.length > 0 && sel.size === branches.length;
  const toggle = (id: number) => setSel((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  // No selection = whole chart (the export treats empty node_ids as "all").
  const url = (fmt: "html" | "pptx") =>
    `/api/org/export.${fmt}?tribe_id=${tribeId}&lang=${lang}` +
    (allOn ? "" : selIds.map((id) => `&node_ids=${id}`).join(""));
  const canExport = branches.length === 0 || selIds.length > 0;

  return (
    <>
      <button className="btn-secondary btn-sm" onClick={() => setOpen(true)}>{t("orgexport.btn")}</button>
      {open && (
        <Modal
          width={640}
          title={t("orgexport.title")}
          onClose={() => setOpen(false)}
          footer={
            <div className="between" style={{ width: "100%", alignItems: "center" }}>
              <span className="small muted">{t("orgexport.selected", { n: sel.size, total: branches.length })}</span>
              <div className="inline" style={{ gap: 8 }}>
                <button className="btn-secondary" onClick={() => setOpen(false)}>{t("action.close")}</button>
                <HtmlPreviewButton url={canExport ? url("html") : ""} title={t("orgexport.title")} label="HTML"
                   className="btn btn-secondary" disabled={!canExport} />
                <a className={`btn${canExport ? "" : " disabled"}`} href={canExport ? url("pptx") : undefined} download
                   aria-disabled={!canExport} onClick={() => canExport && setOpen(false)}>PPTX</a>
              </div>
            </div>
          }
        >
          <div className="between" style={{ marginBottom: 10 }}>
            <div className="small muted">{t("orgexport.pick")}</div>
            <button className="btn-ghost btn-sm" onClick={() => setSel(allOn ? new Set() : new Set(branches.map((b) => b.id)))}>
              {allOn ? t("export.none") : t("export.all")}
            </button>
          </div>
          <div className="rm-pick-grid">
            {branches.length === 0 ? <div className="small muted">{t("common.loading")}</div> : branches.map((b) => {
              const on = sel.has(b.id);
              return (
                <label key={b.id} className={`rm-pick-chip${on ? " on" : ""}`} onClick={(e) => { e.preventDefault(); toggle(b.id); }}>
                  <input type="checkbox" checked={on} readOnly />
                  <span className="rm-pick-name">{b.title} <span className="muted">({b.count})</span></span>
                </label>
              );
            })}
          </div>
        </Modal>
      )}
    </>
  );
}
