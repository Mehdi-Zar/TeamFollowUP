// Shared Steerco types. A PLATFORM reports a monthly SNAPSHOT (this month's KPI
// counts, this month's SLA per COTS, this month's incident count, plus events).
// Snapshots accumulate one per (platform, period); the backend aggregates the year to
// build the KPI/incident charts and the annual SLA row automatically. Keep field names
// in sync with backend/app/routers/steerco.py.
//
// A platform is fed by one or more squads, and its TEMPLATE says which contributing
// squad owns each KPI card and each SLA column. The snapshot is positional against
// that template: data.kpis[i] is the value of template.kpis[i]. The form shows the
// whole slide and only lets you type in the items you own, so two squad leaders can
// fill one slide without ever overwriting each other.

export type Trend = "up" | "down" | "flat";
export type SlaStatus = "ok" | "warn" | "ko";
export type EventSev = "red" | "amber" | "green" | "ice";

/** One KPI card: a label, a count value, a trend vs the previous month, and optional
 *  sub-metrics shown small below (e.g. Software Factory -> GitLab / Artifactory / SonarQube).
 *  `trend` / `delta` are COMPUTED from the previous month's value, never typed in. */
export type SteercoKpi = { label: string; value: string; unit?: string; trend?: Trend; delta?: string; sub?: { label: string; value: string }[] };
/** One SLA cell: a displayed value + a RAG status COMPUTED from that value. */
export type SlaCell = { v: string; s?: SlaStatus | null };
/** A timeline event (last / next): date label, text, short tag, severity colour, and
 *  the contributing squad that wrote it. Events are the one shared section of a
 *  platform slide, so each line carries its author: everybody adds, nobody can
 *  rewrite a colleague's line. */
export type SteercoEvent = { date: string; text: string; tag?: string; sev?: EventSev; squad_id?: number | string | null };

/** The monthly snapshot stored per (squad, period). */
export type SteercoData = {
  kpis?: SteercoKpi[];
  /** This month's SLA: service columns + one value/status per column. */
  sla?: { services: string[]; cells: SlaCell[] };
  /** Incidents opened this month (feeds the 12-month incident chart). */
  incidents?: string;
  last_events?: SteercoEvent[];
  next_events?: SteercoEvent[];
};

export const EVENT_SEVS: EventSev[] = ["red", "amber", "green", "ice"];
export const TREND_ARROW: Record<Trend, string> = { up: "▲", down: "▼", flat: "▬" };
export const SLA_ICON: Record<SlaStatus, string> = { ok: "🟢", warn: "🟠", ko: "🔴" };
// Severity and series colours live only in the backend renderer: the one-pager and
// its charts are server-rendered (SVG / PPTX), the frontend only collects values.

/** One item of a platform's slide: a label, and the contributing squad that owes
 *  the figure (null = nobody assigned yet, only leadership can fill it). */
export type TemplateItem = { label: string; owner_squad_id: number | null; sub?: string[] };
/** A platform's slide definition, owned by the tribe leader. */
export type PlatformTemplate = { kpis: TemplateItem[]; sla: TemplateItem[]; incidents: { owner_squad_id: number | null } };
/** Which items the signed-in user may type in, by index. */
export type EditableItems = { kpis: number[]; sla: number[]; incidents: boolean; events: boolean };
/** A platform as the API returns it. */
export type Platform = {
  id: number; tribe_id: number; name: string; description?: string | null;
  display_order: number; steerco_enabled: boolean;
  template: PlatformTemplate;
  contributors: { id: number; name: string }[];
  editable_squad_ids: number[];
  can_manage: boolean;
  editable: EditableItems;
};

/** The empty snapshot matching a template: labels in place, values empty.
 *  Mirrors app/platforms.py:blank_data, which is the authority. */
export function dataFromTemplate(tpl: PlatformTemplate): SteercoData {
  return {
    kpis: (tpl.kpis ?? []).map((k) => ({
      label: k.label, value: "",
      ...(k.sub?.length ? { sub: k.sub.map((l) => ({ label: l, value: "" })) } : {}),
    })),
    sla: { services: (tpl.sla ?? []).map((x) => x.label), cells: (tpl.sla ?? []).map(() => ({ v: "", s: null })) },
    incidents: "",
    last_events: [],
    next_events: [],
  };
}

/** Default period label for a steerco input: the current month, "YYYY-MM" (monthly). */
export function currentSteercoPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** The 12 month keys ("YYYY-MM") of the given period's calendar year, January to
 *  December. This is the Steerco window everywhere (charts, wizard, backfill), so the
 *  charts always start in January and the entered months match the charted months. */
export function yearMonths(period: string): string[] {
  const y = Number(period.split("-")[0]);
  return Array.from({ length: 12 }, (_, i) => `${y}-${String(i + 1).padStart(2, "0")}`);
}

/** Short month label "YYYY-MM" -> "MM/YY". */
export function monthShort(key: string): string {
  const [y, m] = key.split("-");
  return `${m}/${y.slice(2)}`;
}

/** Long month label "2026-07" -> "July 2026" / "juillet 2026" (viewer's language). */
export function monthLongLabel(period: string, lang: string): string {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return period;
  const s = new Date(y, m - 1, 1).toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { month: "long", year: "numeric" });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Parse a number from a cell (accepts "%", commas). Returns null when not a number. */
export function parseNum(s: string): number | null {
  const n = Number((s || "").replace("%", "").replace(",", ".").trim());
  return (s || "").trim() === "" || Number.isNaN(n) ? null : n;
}

// --- Auto-computed indicators (nothing below is ever typed in by the user) -----

/** SLA colour thresholds: above 90% green, 80 to 90% amber, below 80% red. */
export const SLA_GREEN = 90;
export const SLA_AMBER = 80;

/** SLA values are percentages: keep them inside 0 to 100 (a typo like 994 becomes
 *  100). Non-numeric text is left alone so the field stays usable while typing. */
export function clampPct(s: string): string {
  const n = parseNum(s);
  if (n === null || (n >= 0 && n <= 100)) return s;
  const c = Math.min(Math.max(n, 0), 100);
  return s.trim().endsWith("%") ? `${c}%` : String(c);
}

/** RAG status of an SLA value, derived from the number itself. Null when empty. */
export function slaStatus(v: string | undefined | null): SlaStatus | null {
  const n = parseNum(v ?? "");
  if (n === null) return null;
  return n > SLA_GREEN ? "ok" : n >= SLA_AMBER ? "warn" : "ko";
}

/** Previous month key: "2026-01" -> "2025-12". */
export function prevPeriod(period: string): string {
  const [y, m] = period.split("-").map(Number);
  const d = new Date(y, m - 2, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Signed delta as text: 12 -> "+12", -1.5 -> "-1,5", 0 -> "0". */
function fmtDelta(d: number): string {
  const r = Math.round(d * 10) / 10;
  if (r === 0) return "0";
  return `${r > 0 ? "+" : ""}${r}`.replace(".", ",");
}

/** A KPI's change vs the previous month, computed from both values. */
export function kpiChange(cur: string | undefined, prev: string | undefined): { trend: Trend; delta: string } {
  const c = parseNum(cur ?? ""), p = parseNum(prev ?? "");
  if (c === null || p === null) return { trend: "flat", delta: "" };
  const d = c - p;
  return { trend: d > 0 ? "up" : d < 0 ? "down" : "flat", delta: fmtDelta(d) };
}
