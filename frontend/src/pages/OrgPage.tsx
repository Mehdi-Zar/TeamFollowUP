import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { OrgNode, Squad, Tribe, Role } from "../types";
import { Spinner, ErrorBanner } from "../components/ui";
import { canEditOrg } from "../perms";

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

  if (error) return <ErrorBanner message={error} />;
  if (!tree) return <Spinner />;

  // parent options: all nodes except (when editing) self and its descendants
  let exclude: number[] = [];
  if (form?.mode === "edit" && form.id) {
    const node = findNode(tree, form.id);
    exclude = node ? [form.id, ...descendantIds(node)] : [form.id];
  }
  const parentOptions = flatten(tree).filter((f) => !exclude.includes(f.id));

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="between">
        <div className="muted small">{editable ? t("org.subtitle_edit") : t("org.subtitle_ro")}</div>
        <div className="inline">
          {tribes.length > 1 && (
            <select className="w-auto" value={tribeId ?? ""} onChange={(e) => { const v = Number(e.target.value); setTribeId(v); load(v); }}>
              {tribes.map((tr) => (<option key={tr.id} value={tr.id}>{tr.name}</option>))}
            </select>
          )}
          {!editable && !isOwnTribe && tribeId !== null && <span className="badge badge-grey">{t("org.view_only_other")}</span>}
          {editable && (
            <button className="btn-secondary btn-sm" onClick={() => openCreate(null)}>
              + {t("org.add_top")}
            </button>
          )}
        </div>
      </div>

      {tree.length === 0 && (
        <div className="card muted">{t("org.empty")} {editable ? t("org.empty_edit") : ""}</div>
      )}

      <div className="card" style={{ overflowX: "auto" }}>
        <div className="row" style={{ justifyContent: "center", alignItems: "flex-start", gap: 24 }}>
          {tree.map((n) => (
            <NodeView key={n.id} node={n} editable={editable} linkSquads={isAdmin || isOwnTribe} onAdd={openCreate} onEdit={openEdit} onDelete={remove} />
          ))}
        </div>
      </div>

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
  onAdd,
  onEdit,
  onDelete,
}: {
  node: OrgNode;
  editable: boolean;
  linkSquads: boolean;
  onAdd: (parentId: number) => void;
  onEdit: (n: OrgNode) => void;
  onDelete: (n: OrgNode) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="org-subtree">
      <div className="org-box org-node">
        <div className="strong small">{node.title}</div>
        {node.person_name && <div className="small muted">{node.person_name}</div>}
        {node.squad_id && linkSquads && (
          <Link className="small" to={`/squads/${node.squad_id}`}>
            {t("org.see_squad")}
          </Link>
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
      {node.children.length > 0 && (
        <>
          <div className="org-connector" />
          <div className="org-children">
            {node.children.map((c) => (
              <NodeView key={c.id} node={c} editable={editable} linkSquads={linkSquads} onAdd={onAdd} onEdit={onEdit} onDelete={onDelete} />
            ))}
          </div>
        </>
      )}
    </div>
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
