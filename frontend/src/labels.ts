import { QuarterHealth, Rag, RoadmapStatus, Trend } from "./types";

// Pure, language-independent helpers. Localized labels live in i18n.tsx.

export function roadmapRag(status: RoadmapStatus): Rag {
  if (status === "blocked") return "red";
  if (status === "at_risk") return "amber";
  return "green"; // on_track | done
}

export function qhToRag(h: QuarterHealth): Rag {
  if (h === "blocked") return "red";
  if (h === "at_risk") return "amber";
  return "green";
}

export function trendRag(trend: Trend): Rag {
  if (trend === "missed") return "red";
  if (trend === "under_pressure") return "amber";
  return "green";
}

export function ragClass(status: Rag): string {
  return status === "red" ? "red" : status === "amber" ? "orange" : "green";
}

export function badgeClass(status: Rag): string {
  return status === "red" ? "badge-red" : status === "amber" ? "badge-orange" : "badge-green";
}

export function dotClass(status: Rag): string {
  return status === "red" ? "dot-red" : status === "amber" ? "dot-orange" : "dot-green";
}
