import { useI18n } from "../i18n";
import { ProgressChange, ProgressKind, ProgressPoint } from "../types";
import { Dot } from "./ui";

// --- Confidence (1..5), no emoji to match the charter ---
export function confidenceDot(n?: number | null): "green" | "amber" | "red" {
  if (!n) return "red";
  if (n >= 4) return "green";
  if (n === 3) return "amber";
  return "red";
}

export function ConfidenceBadge({ value }: { value?: number | null }) {
  const { t } = useI18n();
  if (!value) return null;
  return (
    <span className="inline" style={{ gap: 6 }}>
      <Dot status={confidenceDot(value)} />
      <span className="small">{t(`progress.confidence.${value}`)} ({value}/5)</span>
    </span>
  );
}

export function kindLabel(kind: ProgressKind, t: (k: string) => string): string {
  return t(`progress.kind.${kind}`);
}

// --- Human-readable change rendering ---
export function useChangeText() {
  const { t, roadmap, rag, trend } = useI18n();
  return (c: ProgressChange): string => {
    switch (c.kind) {
      case "jalon_added":
        return `${t("progress.ch.jalon_added")} « ${c.label} » (${roadmap(c.to as any)})`;
      case "jalon_status":
        return `${c.label} : ${roadmap(c.from as any)} → ${roadmap(c.to as any)}`;
      case "quarter_pct":
        return `${c.label} : ${c.from}% → ${c.to}%`;
      case "objective_rag":
        return `${t("progress.ch.objective")} « ${c.label} » : ${rag(c.from as any)} → ${rag(c.to as any)}`;
      case "kpi_trend":
        return `KPI ${c.label} : ${trend(c.from as any)} → ${trend(c.to as any)}`;
      default:
        return `${c.label}`;
    }
  };
}

export function ChangeList({ changes, max }: { changes: ProgressChange[]; max?: number }) {
  const text = useChangeText();
  const shown = max ? changes.slice(0, max) : changes;
  if (changes.length === 0) return null;
  return (
    <ul className="change-list">
      {shown.map((c, i) => (
        <li key={i} className="small">{text(c)}</li>
      ))}
      {max && changes.length > max && (
        <li className="small muted">+{changes.length - max}…</li>
      )}
    </ul>
  );
}

export function DeltaBadge({ value }: { value: number }) {
  const cls = value > 0 ? "progress-delta-up" : value < 0 ? "progress-delta-down" : "progress-delta-flat";
  const sign = value > 0 ? "+" : "";
  return <span className={cls}>{sign}{value} pts</span>;
}

// --- Timeline (most recent first), with delta vs previous chronological point ---
export function ProgressTimeline({ points }: { points: ProgressPoint[] }) {
  const { t, formatDateTime } = useI18n();
  if (points.length === 0) return <div className="small muted">{t("progress.no_data")}</div>;
  // points come ascending; show newest first with delta vs the previous one.
  const rows = points.map((p, i) => ({ p, delta: i > 0 ? p.progress_pct - points[i - 1].progress_pct : 0 }));
  rows.reverse();
  return (
    <div className="stack" style={{ gap: 0 }}>
      {rows.map(({ p, delta }) => (
        <div key={p.id} className={`progress-point k-${p.kind}`}>
          <div className="between" style={{ alignItems: "flex-start", gap: 10 }}>
            <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
              <span className="badge badge-grey">{kindLabel(p.kind, t)}</span>
              <span className="small muted">{formatDateTime(p.created_at)}</span>
              {p.author_name && <span className="small muted">· {p.author_name}</span>}
            </div>
            <div className="inline" style={{ gap: 10 }}>
              <span className="strong">{p.progress_pct}%</span>
              {delta !== 0 && <DeltaBadge value={delta} />}
            </div>
          </div>
          <div className="inline small muted" style={{ gap: 12, marginTop: 2, flexWrap: "wrap" }}>
            {p.blocked_count > 0 && <span><Dot status="red" /> {p.blocked_count}</span>}
            {p.at_risk_count > 0 && <span><Dot status="amber" /> {p.at_risk_count}</span>}
            {p.confidence ? <ConfidenceBadge value={p.confidence} /> : null}
          </div>
          {p.note && <div className="small" style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>{p.note}</div>}
          <ChangeList changes={p.changes} max={6} />
        </div>
      ))}
    </div>
  );
}

// --- Evolution curve (progress % over time) ---
export function ProgressCurve({ points, height = 130 }: { points: ProgressPoint[]; height?: number }) {
  const { t } = useI18n();
  const pts = points.filter((p) => p.total_count >= 0);
  if (pts.length < 2) return <div className="small muted">{t("progress.curve_need_more")}</div>;

  const W = 600;
  const H = height;
  const padX = 8;
  const padY = 14;
  const n = pts.length;
  const x = (i: number) => padX + (i * (W - 2 * padX)) / (n - 1);
  const y = (v: number) => padY + (1 - v / 100) * (H - 2 * padY);

  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.progress_pct).toFixed(1)}`).join(" ");
  const area = `${line} L${x(n - 1).toFixed(1)},${(H - padY).toFixed(1)} L${x(0).toFixed(1)},${(H - padY).toFixed(1)} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" role="img" aria-label={t("progress.curve")}>
      {[0, 50, 100].map((g) => (
        <g key={g}>
          <line x1={padX} x2={W - padX} y1={y(g)} y2={y(g)} stroke="var(--line)" strokeWidth={1} />
          <text x={2} y={y(g) - 2} fontSize={9} fill="var(--grey)">{g}</text>
        </g>
      ))}
      <path d={area} fill="rgba(23,92,211,.10)" stroke="none" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      {pts.map((p, i) => (
        <circle key={p.id} cx={x(i)} cy={y(p.progress_pct)} r={3}
          fill={p.blocked_count > 0 ? "var(--red)" : p.at_risk_count > 0 ? "var(--orange)" : "var(--accent)"}>
          <title>{`${new Date(p.created_at).toLocaleDateString()} - ${p.progress_pct}%`}</title>
        </circle>
      ))}
    </svg>
  );
}
