// Studio des exports: the shapes exchanged with /api/exports, and the small pure
// helpers the editor needs (a section's label, what differs from the parent, a
// fresh id). The authority on a specification is the server (exportspec.py): the
// editor sends the whole thing and gets back the cleaned version.

export type DocKind = "dashboard" | "weekly" | "roadmap" | "dependencies" | "initiatives" | "steerco" | "org";

export type ParamKind = "bool" | "int" | "enum" | "multi" | "text" | "longtext" | "color" | "asset";
export type ParamSpec = { kind: ParamKind; default?: any; options?: string[]; min?: number; max?: number };
export type Params = Record<string, any>;

export type Block = { enabled: boolean; params: Params };
export type Item = { id: string; widget: string; zone: [number, number, number, number]; params: Params };
export type Section = {
  id: string; type: string; enabled: boolean; params: Params; blocks: Record<string, Block>; items?: Item[];
};
export type Spec = { doc_kind: DocKind; theme_id: number | null; doc: Params; sections: Section[] };

export type SectionType = {
  data: string | null; repeat: string;
  params: Record<string, ParamSpec>;
  blocks: Record<string, { params?: Record<string, ParamSpec> }>;
};

export type Scopes = {
  global: boolean;
  tribes: { id: number; name: string }[];
  squads: { id: number; name: string; tribe_id: number; simple: boolean }[];
  platforms: { id: number; name: string; tribe_id: number }[];
};

export type Catalog = {
  doc_kinds: DocKind[];
  doc_data: Record<DocKind, string>;
  sections: Record<string, SectionType>;
  widgets: Record<string, { needs: string | null; params: Record<string, ParamSpec> }>;
  doc_params: Record<string, ParamSpec>;
  sections_for: Record<DocKind, string[]>;
  grid: { cols: number; rows: number };
  tokens: string[];
  theme_keys: string[];
  fonts: string[];
  designer: boolean;
  scopes: Scopes;
};

export type TemplateMeta = {
  id: number; doc_kind: DocKind; name: string; scope_type: "global" | "tribe" | "squad" | "platform";
  scope_id: number | null; scope_label: string; parent_id: number | null; parent_name: string | null;
  parent_scope_label: string | null; mode: "root" | "derived" | "detached"; system: boolean; shared: boolean;
  published_number: number | null; unpublished_changes: boolean; can_edit: boolean; simple_only: boolean;
  assigned: string[]; updated_at: string | null;
};

export type Skipped = { path: string; reason: "locked" | "orphan" };

export type TemplateDetail = TemplateMeta & {
  spec: Spec; published_spec: Spec; parent_spec: Spec | null; skipped: Skipped[];
  inherited_locks: string[]; locks: string[]; lock_paths: string[];
  versions: { id: number; number: number; comment: string; created_at: string | null; author: string | null; current: boolean }[];
  children: number[];
};

export type Theme = {
  id: number; name: string; tribe_id: number | null; master_asset_id: number | null; can_edit: boolean;
  config: { palette: Record<string, string>; font: string; font_scale: number };
};

export type Asset = { id: number; kind: "pptx" | "image"; filename: string; mime: string; size: number;
  tribe_id: number | null; created_at: string | null };

export type Lint = { slide: number; kind: string; text: string; size?: number; ratio?: number };
export type PreviewResult = {
  html: string; css: string; slides: number; lints: Lint[]; warnings: { kind: string; section: string }[];
  filename: string; width: number; height: number;
};

/** The document context a preview or a render runs on (same parameters as the
 *  export endpoints). */
export type DocContext = {
  tribe_id?: number | null; squad_id?: number | null; squad_ids?: number[]; platform_id?: number | null;
  year?: number; lang?: string; as_of?: string; period?: string; mode?: string; since_days?: number;
};

export const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

/** A section id not used yet in the specification. */
export function freshId(spec: Spec, base: string): string {
  const ids = new Set(spec.sections.map((s) => s.id));
  let n = 1;
  let id = base;
  while (ids.has(id)) id = `${base}${++n}`;
  return id;
}

/** A new section of this type with every parameter at its default. */
export function newSection(cat: Catalog, spec: Spec, type: string): Section {
  const st = cat.sections[type];
  const params: Params = {};
  for (const [k, p] of Object.entries(st.params)) params[k] = clone(p.default ?? null);
  const blocks: Record<string, Block> = {};
  for (const [b, bd] of Object.entries(st.blocks)) {
    const bp: Params = {};
    for (const [k, p] of Object.entries(bd.params || {})) bp[k] = clone(p.default ?? null);
    blocks[b] = { enabled: true, params: bp };
  }
  const sec: Section = { id: freshId(spec, type), type, enabled: true, params, blocks };
  if (type === "custom") sec.items = [];
  return sec;
}

/** A new widget, placed in the first free row of the grid. */
export function newItem(cat: Catalog, sec: Section, widget: string): Item {
  const params: Params = {};
  for (const [k, p] of Object.entries(cat.widgets[widget].params)) params[k] = clone(p.default ?? null);
  const taken = new Set((sec.items || []).map((i) => i.id));
  let n = (sec.items || []).length + 1;
  while (taken.has(`w${n}`)) n++;
  const bottom = Math.max(0, ...(sec.items || []).map((i) => i.zone[3]));
  const r0 = Math.min(cat.grid.rows - 2, bottom);
  return { id: `w${n}`, widget, zone: [0, r0, cat.grid.cols, Math.min(cat.grid.rows, r0 + 2)], params };
}

export const same = (a: any, b: any) => JSON.stringify(a) === JSON.stringify(b);

/** Is this path locked for the template being edited (by a parent's lock). */
export const lockedBy = (inherited: string[], ...paths: string[]) => paths.some((p) => inherited.includes(p));

/** The parent's section with this id (to show and undo an override). */
export const parentSection = (parent: Spec | null, id: string) => parent?.sections.find((s) => s.id === id) ?? null;

/** Does a section differ from the parent's (what the editor badges "modified"). */
export function sectionChanged(parent: Spec | null, sec: Section): "new" | "changed" | null {
  if (!parent) return null;
  const p = parentSection(parent, sec.id);
  if (!p || p.type !== sec.type) return "new";
  return same({ ...p }, { ...sec }) ? null : "changed";
}

/** The query string of a context, for the GET export URLs. */
export function contextQuery(ctx: DocContext): string {
  const q: string[] = [];
  for (const [k, v] of Object.entries(ctx)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => q.push(`${k}=${encodeURIComponent(String(x))}`));
    else q.push(`${k}=${encodeURIComponent(String(v))}`);
  }
  return q.join("&");
}

/** Download what a POST answers (a one-off render), under the server's file name. */
export async function downloadPost(url: string, body: unknown, fallbackName: string): Promise<void> {
  const resp = await fetch(url, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let msg = String(resp.status);
    try { msg = (await resp.json()).detail || msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  const blob = await resp.blob();
  const cd = resp.headers.get("Content-Disposition") || "";
  const m = /filename="([^"]+)"/.exec(cd);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = m ? m[1] : fallbackName;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}


/** The widgets a free layout of this document and repetition may place (mirror
 *  of exportspec.widgets_for). */
export function widgetsFor(cat: Catalog, doc: DocKind, repeat: string): string[] {
  const fam = cat.doc_data[doc];
  return Object.entries(cat.widgets).filter(([, w]) => {
    const need = w.needs;
    return need === null || (need === "report" && fam === "report")
      || (need === "squad" && fam === "report" && repeat === "per_squad")
      || (need === "platform" && fam === "steerco" && repeat === "per_platform");
  }).map(([k]) => k);
}
