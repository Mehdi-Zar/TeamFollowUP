// Customer Success types (ADR 0020, docs/37). Keep in sync with
// backend/app/routers/cs.py and backend/app/csconfig.py.
//
// A project is flat: client and people are free text. Its blocker, next
// action, last contact and badges are computed by the server from the journal and
// the points to follow, never typed.

export type Health = "green" | "amber" | "red";
export type JournalKind = "request" | "decision" | "proposal" | "delivery" | "reminder" | "blocker" | "note";
export type ItemKind = "action" | "risk" | "blocker" | "note";

export const JOURNAL_KINDS: JournalKind[] = ["request", "decision", "proposal", "delivery", "reminder", "blocker", "note"];
/** Ticked "in the recap" by default (same rule as the server). */
export const RECAP_BY_DEFAULT: JournalKind[] = ["request", "decision", "proposal", "delivery"];
export const ITEM_KINDS: ItemKind[] = ["action", "risk", "blocker", "note"];
export const HEALTHS: Health[] = ["green", "amber", "red"];

export type Stage = { key: string; label: string; color: string; closed: boolean };
export type CsSettings = {
  tribe_id: number; stages: Stage[]; stale_days: number;
  recap_intro: string; recap_marked_at: string | null; can_run: boolean;
};

export type Link = { label: string; url: string };
export type JournalEntry = {
  id: number; date: string; kind: JournalKind; people: string | null; text: string;
  links: Link[]; in_recap: boolean; new: boolean;
};
export type Item = {
  id: number; kind: ItemKind; label: string; owner: string | null; due: string | null;
  opened_on: string | null; done: boolean; done_on: string | null;
};

/** Where a project's billing stands: to invoice, invoiced (waiting for the payment), paid. */
export const BILLINGS = ["todo", "invoiced", "paid"] as const;
export type Billing = typeof BILLINGS[number];

export type Project = {
  id: number; tribe_id: number; title: string; client: string | null; requesters: string | null;
  stage: string; health: Health | null;
  planned_delivery: string | null; actual_delivery: string | null;
  /** The amount, where its billing stands, and the cost code. */
  build_amount: number | null; billing: Billing; cost_code: string | null;
  /** A discount on the price, in percent or in euros; net_amount is the price after it. */
  discount_value: number | null; discount_kind: DiscountKind; net_amount: number | null;
  links: Link[]; notes: string | null; updated_at: string | null;
  can_edit: boolean; can_run: boolean;
  // Computed by the server.
  closed: boolean; blocked: boolean;
  blocker: { id: number; label: string; owner: string | null; since: string | null; days: number | null } | null;
  next_action: { id: number; label: string; owner: string | null; due: string | null; overdue: boolean } | null;
  last_contact: string | null; days_since_contact: number; stale: boolean; overdue_items: number;
  // Only on GET /api/cs/projects/{id}.
  journal?: JournalEntry[]; items?: Item[];
  contributors?: { id: number; name: string; email?: string | null }[];
};

export type Dashboard = {
  tribe_id: number; total: number; open: number; blocked: number; delivered_year: number; year: number;
  todo_total: number; invoiced_total: number; paid_total: number; overdue_items: number; overdue_projects: number;
  stale: number; by_stage: Record<string, number>;
  stale_days: number;
};

/** What the signed-in user may do in Customer Success (from /api/auth/me/permissions). */
export type CsRights = {
  read: boolean; run: boolean; all_tribes: boolean;
  run_tribe_ids: number[]; read_tribe_ids: number[]; designate_tribe_ids: number[];
  contribute: boolean; contribute_project_ids: number[]; contribute_tribe_ids: number[];
};
export const NO_CS: CsRights = {
  read: false, run: false, all_tribes: false, run_tribe_ids: [], read_tribe_ids: [], designate_tribe_ids: [],
  contribute: false, contribute_project_ids: [], contribute_tribe_ids: [],
};

export const opensCs = (r: CsRights) => r.read || r.run || r.contribute || r.designate_tribe_ids.length > 0;

/** The default stages as first stored (French). While a stage keeps one of these
 *  labels, the screen shows the translated name (cs.stage.<key>); a renamed stage
 *  shows its own label. Mirrors csconfig.stage_label on the server. */
const DEFAULT_FR: Record<string, string> = {
  request: "Demande", scoping: "Cadrage", proposal: "Proposition", agreement: "Accord client",
  build: "Build", delivered: "Livré", closed: "Clos",
};
export function stageName(s: Stage, t: (k: string) => string): string {
  return DEFAULT_FR[s.key] === s.label ? t(`cs.stage.${s.key}`) : s.label;
}
/** The settings with each stage's label as it should read on screen. */
export function shownSettings(cfg: CsSettings, t: (k: string) => string): CsSettings {
  return { ...cfg, stages: cfg.stages.map((s) => ({ ...s, label: stageName(s, t) })) };
}

/** "2026-10-19" as "19/10/2026" (fr) or "19 Oct 2026" (en). */
export function fmtDate(iso: string | null | undefined, lang: string): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(lang === "en" ? "en-GB" : "fr-FR", { day: "2-digit", month: lang === "en" ? "short" : "2-digit", year: "numeric" });
}

export type DiscountKind = "pct" | "amount";

/** The price after the discount, never below zero (as the server computes it). */
export function netAmount(price: number | null, value: number | null, kind: DiscountKind): number | null {
  if (price === null) return null;
  const off = !value ? 0 : kind === "pct" ? price * value / 100 : value;
  return Math.max(0, Math.round((price - off) * 100) / 100);
}

export function fmtAmount(v: number | null | undefined, lang: string): string {
  if (v === null || v === undefined) return "";
  return new Intl.NumberFormat(lang === "en" ? "en-GB" : "fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(v);
}

export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
