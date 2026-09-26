/**
 * OrgPage - the tribe organisation chart (entities + squads).
 *
 * Renders a tribe's org structure as either a tree (with optional embedded squad
 * teams, a fit-to-screen frame and a zoomable fullscreen mode) or a flat list.
 * Nodes are either free-form "entities" or "squad" nodes linking to a squad.
 * Editing (add/edit/delete nodes) is allowed only on the viewer's OWN tribe -
 * admins may edit any tribe they select (`editable`). Other tribes are read-only.
 * An export button produces the chart as HTML/PPTX with a branch picker.
 */
import { MouseEvent as ReactMouseEvent, ReactNode, WheelEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { Member, OrgNode, Squad, SquadDetail, Tribe, TribeOrg, Role } from "../types";
import { Spinner, ErrorBanner, FitScale, Modal } from "../components/ui";
import { HtmlPreviewButton } from "../components/HtmlPreview";
import { useSetPageChrome } from "../components/pageChrome";
import { canEditOrg, canEditSquadInScope } from "../perms";
import { TeamModal } from "../components/TeamModal";

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

/** Flatten the tree into indented `{id,label}` rows for the "attach to" parent
 *  <select> (label prefixed with "- " per depth level). */
function flatten(nodes: OrgNode[], depth = 0, acc: Flat[] = []): Flat[] {
  for (const n of nodes) {
    acc.push({ id: n.id, label: `${"- ".repeat(depth)}${n.title}`, depth });
    flatten(n.children, depth + 1, acc);
  }
  return acc;
}

/** Flatten the tree preserving depth, for the indented list view. */
function flattenNodes(nodes: OrgNode[], depth = 0, acc: { node: OrgNode; depth: number }[] = []) {
  for (const n of nodes) {
    acc.push({ node: n, depth });
    flattenNodes(n.children, depth + 1, acc);
  }
  return acc;
}

/** All descendant ids of a node - used to forbid re-parenting a node under
 *  itself or one of its own descendants. */
function descendantIds(node: OrgNode, acc: number[] = []): number[] {
  for (const c of node.children) {
    acc.push(c.id);
    descendantIds(c, acc);
  }
  return acc;
}

/** Depth-first lookup of a node by id within the tree. */
function findNode(nodes: OrgNode[], id: number): OrgNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const found = findNode(n.children, id);
    if (found) return found;
  }
  return null;
}

/**
 * Org chart root. Loads the tree + squads for the selected tribe, resolves edit
 * rights (own tribe, or admin on any tribe), and hosts the tree/list views, the
 * node create/edit form, fullscreen mode and the export button.
 */
export default function OrgPage() {
  const { user, effectiveRole } = useAuth();
  const { t } = useI18n();
  // A box's "⋯" menu closes on a click elsewhere or on Escape.
  useEffect(() => {
    const closeAll = (keep?: Element | null) =>
      document.querySelectorAll("details.org-menu[open]").forEach((d) => { if (d !== keep) d.removeAttribute("open"); });
    const onClick = (e: MouseEvent) => closeAll((e.target as Element | null)?.closest("details.org-menu"));
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeAll(); };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("click", onClick); document.removeEventListener("keydown", onKey); };
  }, []);
  const role = (effectiveRole ?? "member") as Role;
  const isAdmin = role === "admin";

  const [tree, setTree] = useState<OrgNode[] | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  // Le nombre de squads par tribu: c'est ce que l'ancienne page « Tribus »
  // apportait et que la liste deroulante ne disait pas. Best effort, la barre
  // sait s'afficher sans.
  const [counts, setCounts] = useState<Record<number, number>>({});
  const [tribeId, setTribeId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A failed write (403, 400 on a loop...) is shown above the chart. Routed to
  // `error`, it replaced the whole page, chart and form included.
  const [actionError, setActionError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  // La liste d'abord: l'arbre est la belle vue, la liste est celle qui repond a
  // « ou est ma squad » sans faire defiler.
  const [view, setView] = useState<OrgView>("list");
  const [showAllMembers, setShowAllMembers] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  // The squad whose team is being edited, and a counter bumped after each edit so
  // the embedded team charts (SquadTeam) fetch again.
  const [team, setTeam] = useState<{ id: number; name: string } | null>(null);
  const [teamVersion, setTeamVersion] = useState(0);

  // editing only allowed on one's OWN tribe (admin: any tribe they select)
  const isOwnTribe = tribeId !== null && tribeId === user?.tribe_id;
  const editable = canEditOrg(role) && (isAdmin || isOwnTribe);
  // Editing a squad's members is a squad right, not an org-chart one: a squad
  // leader edits the team of the squads they lead (deps.can_edit_squad).
  const squadById = new Map(squads.map((s) => [s.id, s]));
  // This tribe's squads, and those already in the chart (the add form and the
  // "not placed yet" notice read them).
  const tribeSquads = squads.filter((s) => s.tribe_id === tribeId);
  const placedIds = new Set(flattenNodes(tree ?? []).map((f) => f.node.squad_id).filter((x): x is number => !!x));
  const unplaced = tribeSquads.filter((s) => !placedIds.has(s.id));
  const canEditTeam = (squadId: number | null | undefined) => {
    const s = squadId != null ? squadById.get(squadId) : undefined;
    return !!s && canEditSquadInScope(role, user, s);
  };
  const openTeam = (n: OrgNode) => n.squad_id && setTeam({ id: n.squad_id, name: squadById.get(n.squad_id)?.name ?? n.title });

  function load(tid: number | null) {
    const q = tid ? `?tribe_id=${tid}` : "";
    api.get<OrgNode[]>(`/api/org${q}`).then(setTree).catch((e) => setError(e.message));
    api.get<Squad[]>(`/api/squads${q}`).then(setSquads).catch(() => {});
  }
  const [searchParams] = useSearchParams();
  useEffect(() => {
    api.get<TribeOrg[]>("/api/tribes/org-overview")
      .then((rows) => setCounts(Object.fromEntries(rows.map((r) => [r.tribe_id, r.squads_count]))))
      .catch(() => {});
  }, []);
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

  // Create or update a node. A "squad" node borrows the squad's name as its title.
  async function save() {
    if (!form) return;
    let title = form.title;
    let squad_id: number | null = null;
    if (form.kind === "squad" && form.squad_id) {
      squad_id = Number(form.squad_id);
      title = squads.find((s) => s.id === squad_id)?.name || form.title;
    }
    const body: any = { title, squad_id, parent_id: form.parent_id };
    // The form does not edit the person's name: sending null on an update erased
    // the one an import had set.
    if (form.mode === "create") body.person_name = null;
    if (isAdmin && form.mode === "create") body.tribe_id = tribeId;
    setActionError(null);
    try {
      if (form.mode === "create") await api.post("/api/org", body);
      else await api.put(`/api/org/${form.id}`, body);
      setForm(null);
      load(tribeId);
    } catch (e: any) {
      setActionError(e.message);
    }
  }

  // Poser l'organigramme a partir de ce que l'application sait deja: une racine
  // au nom de la tribu, puis une boite par squad. C'est le point de depart que
  // tout le monde recree a la main, en moins bien.
  const [seeding, setSeeding] = useState(false);
  // Place the squads that have no box, under the chart's first root.
  async function placeUnplaced() {
    if (!tree?.length || !unplaced.length) return;
    setSeeding(true);
    try {
      const base: any = { person_name: null, parent_id: tree![0].id };
      if (isAdmin) base.tribe_id = tribeId;
      for (const sq of unplaced) await api.post("/api/org", { ...base, title: sq.name, squad_id: sq.id });
      load(tribeId);
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setSeeding(false);
    }
  }

  async function seedFromSquads() {
    if (!squads.length) return;
    setSeeding(true);
    try {
      const tribeName = tribes.find((x) => x.id === tribeId)?.name || t("org.root_default");
      const base: any = { person_name: null, squad_id: null, parent_id: null };
      if (isAdmin) base.tribe_id = tribeId;
      const root = await api.post<OrgNode>("/api/org", { ...base, title: tribeName });
      for (const sq of squads) {
        await api.post("/api/org", { ...base, title: sq.name, squad_id: sq.id, parent_id: root.id });
      }
      load(tribeId);
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setSeeding(false);
    }
  }

  async function remove(n: OrgNode) {
    if (!confirm(t("org.del_confirm"))) return;
    setActionError(null);
    try {
      await api.del(`/api/org/${n.id}`);
      load(tribeId);
    } catch (e: any) {
      setActionError(e.message);
    }
  }

  useSetPageChrome(
    {
      tabs: [
        { key: "list", label: t("org.view_list") },
        { key: "tree", label: t("org.view_tree") },
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
    [view, tribeId, editable, isOwnTribe, showAllMembers, t]
  );

  if (error) return <ErrorBanner message={error} />;
  if (!tree) return <Spinner />;

  // Parent options for the form: every node except (when editing) the node itself
  // and its descendants, which would create a cycle.
  let exclude: number[] = [];
  if (form?.mode === "edit" && form.id) {
    const node = findNode(tree, form.id);
    exclude = node ? [form.id, ...descendantIds(node)] : [form.id];
  }
  const parentOptions = flatten(tree).filter((f) => !exclude.includes(f.id));

  const treeContent = (
    <div className="row" style={{ justifyContent: "center", alignItems: "flex-start", gap: 24, flexWrap: "nowrap" }}>
      {tree.map((n) => (
        <NodeView key={n.id} node={n} editable={editable} linkSquads={isAdmin || isOwnTribe} forceShowTeam={showAllMembers} canEditTeam={canEditTeam} onTeam={openTeam} teamVersion={teamVersion} onAdd={openCreate} onEdit={openEdit} onDelete={remove} />
      ))}
    </div>
  );

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="muted small">{editable ? t("org.subtitle_edit") : t("org.subtitle_ro")}</div>

      {/* La barre des tribus: choisir celle qu'on regarde, et voir du meme coup ce
          qu'elle pese. Elle remplace a la fois la liste deroulante de l'entete et
          l'ancienne page « Tribus », qui posaient la meme question. */}
      {tribes.length > 1 && (
        <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
          {tribes.map((tr) => (
            <button key={tr.id}
                    className={`tribe-chip${tr.id === tribeId ? " on" : ""}`}
                    onClick={() => { setTribeId(tr.id); load(tr.id); }}>
              <span className="strong">{tr.name}</span>
              {counts[tr.id] !== undefined && (
                <span className="small muted">{t("tribes.squads_n", { n: counts[tr.id] })}</span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Squads of this tribe with no box yet: said, with a way to place them. */}
      {tree.length > 0 && editable && unplaced.length > 0 && (
        <div className="banner between" style={{ alignItems: "center", gap: 10 }}>
          <span className="small">{t("org.unplaced", { n: unplaced.length, names: unplaced.map((s) => s.name).join(", ") })}</span>
          <button className="btn-secondary btn-sm" disabled={seeding} onClick={placeUnplaced}>{t("org.place_them")}</button>
        </div>
      )}

      {tree.length === 0 && (
        <div className="card stack" style={{ gap: 10 }}>
          <div className="muted">{t("org.empty")} {editable ? t("org.empty_edit") : ""}</div>
          {editable && squads.length > 0 && (
            <>
              <div className="small muted">{t("org.empty_squads", { n: squads.length })}</div>
              <div>
                <button className="btn btn-sm" disabled={seeding} onClick={seedFromSquads}>
                  {seeding ? t("common.preparing") : t("org.seed_from_squads")}
                </button>
              </div>
            </>
          )}
        </div>
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
                {node.person_name && <span className="small muted"> ({node.person_name})</span>}
                {node.squad_id && (isAdmin || isOwnTribe) && (
                  <Link className="small" to={`/squads/${node.squad_id}`} style={{ marginLeft: 8 }}>
                    {t("org.see_squad")}
                  </Link>
                )}
                {canEditTeam(node.squad_id) && (
                  <button className="btn-ghost btn-sm" style={{ marginLeft: 8 }} onClick={() => openTeam(node)}>
                    ✎ {t("org.edit_team")}
                  </button>
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

      {team && (
        <TeamModal squadId={team.id} squadName={team.name}
                   onClose={() => setTeam(null)} onChange={() => setTeamVersion((v) => v + 1)} />
      )}

      {actionError && <ErrorBanner message={actionError} />}
      {form && (
        <NodeForm form={form} squads={tribeSquads.filter((s) => !placedIds.has(s.id) || String(s.id) === String(form.squad_id))}
                  parentOptions={parentOptions} onChange={setForm} onSave={save} onCancel={() => setForm(null)} />
      )}
    </div>
  );
}

/**
 * Recursive tree node. Renders one org box (a squad node links to the squad when
 * `linkSquads`), optional per-node edit controls (`editable`), and its children.
 * A squad node can reveal its team (SquadTeam) on demand or via `forceShowTeam`.
 * Terminal-only children are stacked vertically to keep the chart compact.
 */
function NodeView({
  node,
  editable,
  linkSquads,
  forceShowTeam,
  canEditTeam,
  onTeam,
  teamVersion,
  onAdd,
  onEdit,
  onDelete,
}: {
  node: OrgNode;
  editable: boolean;
  linkSquads: boolean;
  forceShowTeam: boolean;
  canEditTeam: (squadId: number | null | undefined) => boolean;
  onTeam: (n: OrgNode) => void;
  teamVersion: number;
  onAdd: (parentId: number) => void;
  onEdit: (n: OrgNode) => void;
  onDelete: (n: OrgNode) => void;
}) {
  const { t, roadmap } = useI18n();
  const [showTeam, setShowTeam] = useState(false);
  const teamVisible = forceShowTeam || showTeam;
  const isSquad = !!node.squad_id;
  // A squad says how it goes: coloured dot, grey when it never reported.
  const st = node.squad_status;
  const statusDot = isSquad ? (
    <span className={`org-status org-status--${st ?? "none"}`} role="img"
          aria-label={st ? roadmap(st) : t("org.status_none")} title={st ? roadmap(st) : t("org.status_none")} />
  ) : null;
  return (
    <div className="org-subtree">
      <div className={`org-box org-node${isSquad ? " org-node--squad" : ""}`}>
        {isSquad && linkSquads ? (
          <Link to={`/squads/${node.squad_id}`} className="strong small org-squad-link" title={t("org.see_squad")}>
            {statusDot}{node.title}
          </Link>
        ) : (
          <div className="strong small">{statusDot}{node.title}</div>
        )}
        {node.person_name && <div className="small muted">{node.person_name}</div>}
        {(() => {
          const teamLinks = !!node.squad_id && linkSquads && !forceShowTeam;
          const teamEdit = !!node.squad_id && canEditTeam(node.squad_id);
          if (!teamLinks && !teamEdit && !editable) return null;
          // One quiet "⋯" in the corner; the actions live in its short menu.
          const close = (e: React.MouseEvent) => (e.currentTarget.closest("details") as HTMLDetailsElement | null)?.removeAttribute("open");
          return (
            <details className="org-menu">
              <summary aria-label={t("org.actions")} title={t("org.actions")}>⋯</summary>
              <div className="org-menu-list" onClick={close}>
                {teamLinks && (
                  <button type="button" onClick={() => setShowTeam((v) => !v)}>
                    {showTeam ? t("org.hide_team") : t("org.see_team")}
                  </button>
                )}
                {teamEdit && <button type="button" onClick={() => onTeam(node)}>{t("org.edit_team")}</button>}
                {editable && (
                  <>
                    <button type="button" onClick={() => onAdd(node.id)}>{t("org.add_below")}</button>
                    <button type="button" onClick={() => onEdit(node)}>{t("action.edit")}</button>
                    <button type="button" className="danger" onClick={() => onDelete(node)}>{t("action.delete")}</button>
                  </>
                )}
              </div>
            </details>
          );
        })()}
      </div>
      {teamVisible && node.squad_id && <SquadTeam key={teamVersion} squadId={node.squad_id} />}
      {node.children.length > 0 && (() => {
        const kids = node.children.map((c) => (
          <NodeView key={c.id} node={c} editable={editable} linkSquads={linkSquads} forceShowTeam={forceShowTeam} canEditTeam={canEditTeam} onTeam={onTeam} teamVersion={teamVersion} onAdd={onAdd} onEdit={onEdit} onDelete={onDelete} />
        ));
        // Terminal children (a domain's squads), more than three: a compact grid
        // in a tray under their parent, so the whole chart fits one page instead
        // of a long column. Up to four per row.
        const grid = node.children.length > 3 && node.children.every((c) => c.children.length === 0)
          && !forceShowTeam;
        const cols = Math.min(4, Math.ceil(Math.sqrt(node.children.length)));
        return (
          <>
            <div className="org-connector" />
            {grid ? (
              <div className="org-tray" style={{ gridTemplateColumns: `repeat(${cols}, 170px)` }}>{kids}</div>
            ) : (
              <div className="org-children">{kids}</div>
            )}
          </>
        );
      })()}
    </div>
  );
}

/**
 * Embedded squad team sub-chart shown under a squad node. Fetches the squad and
 * renders its members as a reporting tree (grouped by manager_id, like SquadOrg).
 * Renders nothing if the fetch fails (e.g. no access to that squad).
 */
function SquadTeam({ squadId }: { squadId: number }) {
  const { t } = useI18n();
  const [data, setData] = useState<SquadDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.get<SquadDetail>(`/api/squads/${squadId}`).then(setData).catch(() => setFailed(true));
  }, [squadId]);

  if (failed) return <div className="small muted" style={{ marginTop: 8 }}>{t("org.team_hidden")}</div>;
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

/**
 * Create/edit form for an org node: kind (entity vs squad), the entity title or
 * a squad picker, and the parent to attach under. Save is disabled until the
 * required field for the chosen kind is filled.
 */
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
    <div className="card">
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
