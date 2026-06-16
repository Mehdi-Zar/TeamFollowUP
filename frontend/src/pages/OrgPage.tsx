import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { Member, OrgNode, Squad, SquadDetail, Tribe, Role } from "../types";
import { Spinner, ErrorBanner, FitScale } from "../components/ui";
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
    acc.push({ id: n.id, label: `${"— ".repeat(depth)}${n.title}`, depth });
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
  useEffect(() => {
    api.get<Tribe[]>("/api/tribes").then((ts) => {
      setTribes(ts);
      const def = user?.tribe_id ?? (ts.length ? ts[0].id : null);
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

      {fullscreen && (
        <div className="org-fullscreen" onClick={() => setFullscreen(false)}>
          <div className="org-fullscreen-bar">
            <span className="strong">{t("nav.org")}</span>
            <button className="btn-secondary btn-sm" onClick={() => setFullscreen(false)}>✕ {t("action.close")}</button>
          </div>
          <div className="org-fullscreen-body" onClick={(e) => e.stopPropagation()}>
            {treeContent}
          </div>
        </div>
      )}

      {tree.length > 0 && view === "list" && (
        <div className="card stack" style={{ gap: 0 }}>
          {flattenNodes(tree).map(({ node, depth }) => (
            <div key={node.id} className="item-row">
              <div className="grow" style={{ paddingLeft: depth * 22 }}>
                <span className="strong small">{node.title}</span>
                {node.person_name && <span className="small muted"> — {node.person_name}</span>}
                {node.squad_id && (isAdmin || isOwnTribe) && (
                  <Link className="small" to={`/squads/${node.squad_id}`} style={{ marginLeft: 8 }}>
                    {t("org.see_squad")}
                  </Link>
                )}
              </div>
              {editable && (
                <div className="inline" style={{ gap: 4 }}>
                  <button className="btn-ghost btn-sm" title={t("org.add_below")} onClick={() => openCreate(node.id)}>+</button>
                  <button className="btn-ghost btn-sm" title={t("action.save")} onClick={() => openEdit(node)}>✎</button>
                  <button className="btn-danger btn-sm" title={t("action.delete")} onClick={() => remove(node)}>✕</button>
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
      {node.children.length > 0 && (
        <>
          <div className="org-connector" />
          <div className="org-children">
            {node.children.map((c) => (
              <NodeView key={c.id} node={c} editable={editable} linkSquads={linkSquads} forceShowTeam={forceShowTeam} onAdd={onAdd} onEdit={onEdit} onDelete={onDelete} />
            ))}
          </div>
        </>
      )}
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
              <option value="">—</option>
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
