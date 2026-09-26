/**
 * Status-to-presentation mapping helpers.
 *
 * Pure functions that collapse the various status enums onto the shared RAG
 * (red/amber/green) scale and then to CSS class names, so every widget colours
 * statuses identically. Language-independent - localized text lives in i18n.tsx.
 */
import { QuarterHealth, Rag, RoadmapStatus, Trend } from "./types";

// Pure, language-independent helpers. Localized labels live in i18n.tsx.

/** Map a roadmap milestone status to RAG: blocked=red, at_risk=amber, else green. */
export function roadmapRag(status: RoadmapStatus): Rag {
  if (status === "blocked") return "red";
  if (status === "at_risk") return "amber";
  return "green"; // on_track | done
}

/** Map a quarter-health value to RAG. */
export function qhToRag(h: QuarterHealth): Rag {
  if (h === "blocked") return "red";
  if (h === "at_risk") return "amber";
  return "green";
}

/** Map a KPI trend to RAG: missed=red, under_pressure=amber, on_target=green. */
export function trendRag(trend: Trend): Rag {
  if (trend === "missed") return "red";
  if (trend === "under_pressure") return "amber";
  return "green";
}

/** RAG -> base colour class (note: amber maps to the "orange" class name). */
export function ragClass(status: Rag): string {
  return status === "red" ? "red" : status === "amber" ? "orange" : "green";
}

/** RAG -> badge CSS class. */
export function badgeClass(status: Rag): string {
  return status === "red" ? "badge-red" : status === "amber" ? "badge-orange" : "badge-green";
}

/** RAG -> status-dot CSS class. */
export function dotClass(status: Rag): string {
  return status === "red" ? "dot-red" : status === "amber" ? "dot-orange" : "dot-green";
}
