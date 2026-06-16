import { ReactNode, useLayoutEffect, useRef, useState } from "react";
import { Freshness, QuarterHealth, Rag } from "../types";
import { badgeClass, dotClass, qhToRag, ragClass } from "../labels";
import { useI18n } from "../i18n";

/** Scales its content down (never up) so it always fits the available width —
 *  keeps the org chart on a single page without a horizontal scrollbar. */
export function FitScale({ children }: { children: ReactNode }) {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [height, setHeight] = useState<number | undefined>(undefined);

  useLayoutEffect(() => {
    const measure = () => {
      const outer = outerRef.current, inner = innerRef.current;
      if (!outer || !inner) return;
      const avail = outer.clientWidth;
      const cw = inner.scrollWidth;
      const s = cw > avail && cw > 0 ? Math.max(0.35, avail / cw) : 1;
      setScale(s);
      setHeight(inner.scrollHeight * s);
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (outerRef.current) ro.observe(outerRef.current);
    if (innerRef.current) ro.observe(innerRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={outerRef} style={{ width: "100%", height, overflow: "hidden", display: "flex", justifyContent: "center" }}>
      <div ref={innerRef} style={{ transform: `scale(${scale})`, transformOrigin: "top center", flex: "0 0 auto" }}>
        {children}
      </div>
    </div>
  );
}

export function Dot({ status }: { status: Rag }) {
  return <span className={`dot ${dotClass(status)}`} aria-hidden />;
}

/** A card whose body collapses behind a clickable header. */
export function Collapsible({
  title,
  subtitle,
  right,
  defaultOpen = false,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card collapsible">
      <div
        className="between collapsible-head"
        style={{ cursor: "pointer", alignItems: "center", gap: 10 }}
        onClick={() => setOpen((o) => !o)}
      >
        <div className="inline" style={{ gap: 10, alignItems: "center" }}>
          <span className="collapsible-caret" style={{ transition: "transform .15s", transform: open ? "rotate(90deg)" : "none", color: "var(--accent)" }}>▸</span>
          <h2 style={{ margin: 0 }}>{title}</h2>
        </div>
        <div className="inline" style={{ gap: 10, alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
          {right}
        </div>
      </div>
      {subtitle && !open && <div className="small muted" style={{ marginTop: 4 }}>{subtitle}</div>}
      {open && <div style={{ marginTop: 14 }}>{children}</div>}
    </div>
  );
}

export function StatusBadge({ status }: { status: Rag }) {
  const { rag } = useI18n();
  return (
    <span className={`badge ${badgeClass(status)}`}>
      <Dot status={status} />
      {rag(status)}
    </span>
  );
}

/** Badge for a quarter-scoped health (on_track | at_risk | blocked). */
export function HealthBadge({ status }: { status: QuarterHealth }) {
  const { roadmap } = useI18n();
  const r = qhToRag(status);
  return (
    <span className={`badge ${badgeClass(r)}`}>
      <Dot status={r} />
      {roadmap(status)}
    </span>
  );
}

export function FreshnessBadge({ freshness }: { freshness: Freshness }) {
  const { freshness: ft, t } = useI18n();
  const text = ft(freshness);
  if (freshness.is_stale) {
    return (
      <span className="badge badge-grey">
        <span className="dot dot-grey" aria-hidden />
        {text} · {t("fresh.stale_suffix")}
      </span>
    );
  }
  return (
    <span className="badge badge-navy">
      <span className="dot" style={{ background: "var(--accent)" }} aria-hidden />
      {text}
    </span>
  );
}

export function ProgressBar({ pct, tone }: { pct: number; tone?: Rag }) {
  const cls = tone ? ragClass(tone) : "";
  return (
    <div className={`progress ${cls}`}>
      <div style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

export function QuarterBars({ progress, currentQuarter }: { progress: Record<string, number>; currentQuarter?: number }) {
  return (
    <div className="quarters">
      {[1, 2, 3, 4].map((q) => {
        const pct = progress[String(q)] ?? 0;
        return (
          <div key={q} className={`q ${currentQuarter === q ? "current" : ""}`}>
            <div className="qlabel">Q{q}</div>
            <div className="qbar">
              <div style={{ width: `${pct}%` }} />
            </div>
            <div className="qpct">{pct}%</div>
          </div>
        );
      })}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  const { t } = useI18n();
  return <div className="spinner">{label ?? t("common.loading")}</div>;
}

export function ErrorBanner({ message }: { message: string }) {
  return <div className="banner banner-red">{message}</div>;
}
