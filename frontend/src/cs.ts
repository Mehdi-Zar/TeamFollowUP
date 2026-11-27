// Customer Success types (ADR 0020, docs/37). Keep in sync with
// backend/app/routers/cs.py and backend/app/csconfig.py.
//
// A project is flat: client, offer and people are free text. Its blocker, next
// action, last contact and badges are computed by the server from the journal and
// the points to follow, never typed.

export type Health = "green" | "amber" | "red";
export type JournalKind = "request" | "decision" | "proposal" | "delivery" | "reminder" | "blocker" | "note";
export type ItemKind = "action" | "risk" | "blocker";

export const JOURNAL_KINDS: JournalKind[] = ["request", "decision", "proposal", "delivery", "reminder", "blocker", "note"];
/** Ticked "in the recap" by default (same rule as the server). */
export const RECAP_BY_DEFAULT: JournalKind[] = ["request", "decision", "proposal", "delivery"];
export const ITEM_KINDS: ItemKind[] = ["action", "risk", "blocker"];
export const HEALTHS: Health[] = ["green", "amber", "red"];

export type Stage = { key: string; label: string; color: string; closed: boolean };
export type CsSettings = {
  tribe_id: number; stages: Stage[]; offers: string[]; stale_days: number; access_warn_days: number;
  recap_intro: string; recap_marked_at: string | null; can_run: boolean;
};

export type Link = { label: string; url: string };
export type Contact = { name: string; role: string };
export type JournalEntry = {
  id: number; date: string; kind: JournalKind; people: string | null; text: string;
  links: Link[]; in_recap: boolean; new: boolean;
};
export type Item = {
  id: number; kind: ItemKind; label: string; owner: string | null; due: string | null;
  opened_on: string | null; done: boolean; done_on: string | null;
};

export type Project = {
  id: number; tribe_id: number; title: string; client: string | null; requesters: string | null;
  contacts: Contact[]; tags: string[]; stage: string; health: Health | null; offer: string | null;
  delivery_mode: string | null; gcp_project: string | null;
  planned_delivery: string | null; actual_delivery: string | null;
  build_amount: number | null; quote_signed: boolean; cost_code: string | null;
  consumption_billing: "uncapped" | "capped" | null; consumption_cap: string | null;
  users_count: number | null; models: string | null; data_classification: string | null;
  max_duration: string | null; access_end: string | null;
  milestones: Record<string, { planned: string | null; actual: string | null }>;
  links: Link[]; notes: string | null; updated_at: string | null;
  can_edit: boolean; can_run: boolean;
  // Computed by the server.
  closed: boolean; blocked: boolean;
  blocker: { id: number; label: string; owner: string | null; since: string | null; days: number | null } | null;
  next_action: { id: number; label: string; owner: string | null; due: string | null; overdue: boolean } | null;
  last_contact: string | null; days_since_contact: number; stale: boolean; overdue_items: number;
  access_days: number | null; access_soon: boolean; access_over: boolean;
  // Only on GET /api/cs/projects/{id}.
  journal?: JournalEntry[]; items?: Item[];
  contributors?: { id: number; name: string; email?: string | null }[];
};

export type Dashboard = {
  tribe_id: number; total: number; open: number; blocked: number; delivered_year: number; year: number;
  build_signed: number; build_pending: number; overdue_items: number; overdue_projects: number;
  access_soon: number; access_over: number; stale: number; by_stage: Record<string, number>;
  stale_days: number; access_warn_days: number;
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

/** "2026-10-19" as "19/10/2026" (fr) or "19 Oct 2026" (en). */
export function fmtDate(iso: string | null | undefined, lang: string): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(lang === "en" ? "en-GB" : "fr-FR", { day: "2-digit", month: lang === "en" ? "short" : "2-digit", year: "numeric" });
}

export function fmtAmount(v: number | null | undefined, lang: string): string {
  if (v === null || v === undefined) return "";
  return new Intl.NumberFormat(lang === "en" ? "en-GB" : "fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(v);
}

export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
