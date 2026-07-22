// Shared Steerco types. A squad reports a monthly SNAPSHOT (this month's KPI counts,
// this month's SLA per COTS, this month's incident count, plus events). Snapshots
// accumulate one per (squad, period); the backend aggregates the last 12 to build the
// KPI/incident charts and the "last 12 months" SLA row automatically. Keep field names
// in sync with backend/app/routers/steerco.py.

export type Trend = "up" | "down" | "flat";
export type SlaStatus = "ok" | "warn" | "ko";
export type EventSev = "red" | "amber" | "green" | "ice";

/** One KPI card: a label, a count value, a trend vs the previous month, and optional
 *  sub-metrics shown small below (e.g. Software Factory -> GitLab / Artifactory / SonarQube).
 *  `trend` / `delta` are COMPUTED from the previous month's value, never typed in. */
export type SteercoKpi = { label: string; value: string; unit?: string; trend?: Trend; delta?: string; sub?: { label: string; value: string }[] };
/** One SLA cell: a displayed value + a RAG status COMPUTED from that value. */
export type SlaCell = { v: string; s?: SlaStatus | null };
/** A timeline event (last / next): date label, text, short tag, severity colour. */
export type SteercoEvent = { date: string; text: string; tag?: string; sev?: EventSev };

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

/** The standard monthly structure (KPI labels + SLA service columns). */
export const STEERCO_KPI_LABELS = ["Cloud Users", "Landing Zone", "K8aaS", "DBaaS", "Software Factory"];
export const STEERCO_SWF_SUB = ["GitLab", "Artifactory", "SonarQube"];
export const STEERCO_SLA_SERVICES = ["Incidents", "Gitlab", "Artifactory", "Sonarqube"];

/** Default period label for a steerco input: the current month, "YYYY-MM" (monthly). */
export function currentSteercoPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** The last 12 month keys ("YYYY-MM"), oldest first, ending at the given period. */
export function last12Months(period: string): string[] {
  const [y, m] = period.split("-").map(Number);
  const out: string[] = [];
  for (let i = 11; i >= 0; i--) {
    const d = new Date(y, (m - 1) - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
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

/** The standard blank monthly snapshot, pre-structured so the squad leader only fills
 *  values: 5 KPI counts, the Incidents + SwF-per-COTS SLA row, an incident count. */
export function defaultSteercoData(): SteercoData {
  return {
    kpis: STEERCO_KPI_LABELS.map((label) => ({
      label, value: "",
      ...(label === "Software Factory" ? { sub: STEERCO_SWF_SUB.map((l) => ({ label: l, value: "" })) } : {}),
    })),
    sla: { services: [...STEERCO_SLA_SERVICES], cells: STEERCO_SLA_SERVICES.map(() => ({ v: "", s: null })) },
    incidents: "",
    last_events: [],
    next_events: [],
  };
}

/** Ensure the "Cloud Users" KPI is present as the first card (older entries may lack it,
 *  or may still carry the previous "Users" label - both count as present, no duplicate). */
export function ensureUsersKpi(d: SteercoData): SteercoData {
  const kpis = d.kpis ?? [];
  if (kpis.some((k) => ["users", "cloud users"].includes((k.label || "").trim().toLowerCase()))) return d;
  return { ...d, kpis: [{ label: "Cloud Users", value: "" }, ...kpis] };
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
