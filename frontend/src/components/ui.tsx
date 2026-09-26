// ui: the shared design-system primitives used across the app. Selectable list
// items, the modal dialog, collapsible cards, RAG/health/freshness badges,
// progress indicators, spinner, and error/empty states. Keeping them here makes
// every screen look and behave consistently and accessibly.
import { ReactNode, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Freshness, Rag } from "../types";
import { dotClass, ragClass } from "../labels";
import { useI18n } from "../i18n";

/** A clean, consistent selectable item (checkbox row/chip). Use everywhere a user
 *  ticks items in a list (squad export picker, OTD milestones, ...) so selection
 *  always looks the same and tidy. */
export function PickItem({ selected, disabled, onToggle, title, meta, tag }: {
  selected: boolean; onToggle: () => void; disabled?: boolean;
  title: ReactNode; meta?: ReactNode; tag?: ReactNode;
}) {
  return (
    <div
      className={`pick-item${selected ? " on" : ""}${disabled ? " disabled" : ""}`}
      role="checkbox" aria-checked={selected} aria-disabled={disabled} tabIndex={disabled ? -1 : 0}
      onClick={() => !disabled && onToggle()}
      onKeyDown={(e) => { if (!disabled && (e.key === " " || e.key === "Enter")) { e.preventDefault(); onToggle(); } }}
    >
      <span className="pick-box">{selected ? "✓" : ""}</span>
      <span className="pick-main">
        <span className="pick-title">{title}</span>
        {meta != null && <span className="pick-meta">{meta}</span>}
      </span>
      {tag != null && <span className="pick-tag">{tag}</span>}
    </div>
  );
}

/** Scales its content down (never up) so it always fits the available space -
 *  keeps the org chart readable on one page without scrollbars. With fitHeight
 *  it fits BOTH width and height of its container (for a fullscreen view). */
export function FitScale({ children, fitHeight }: { children: ReactNode; fitHeight?: boolean }) {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [height, setHeight] = useState<number | undefined>(undefined);

  useLayoutEffect(() => {
    const measure = () => {
      const outer = outerRef.current, inner = innerRef.current;
      if (!outer || !inner) return;
      const cw = inner.scrollWidth, ch = inner.scrollHeight;
      let s = cw > 0 ? outer.clientWidth / cw : 1;
      if (fitHeight && ch > 0) s = Math.min(s, outer.clientHeight / ch);
      s = Math.max(0.45, Math.min(1, s));
      setScale(s);
      setHeight(fitHeight ? undefined : ch * s);
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (outerRef.current) ro.observe(outerRef.current);
    if (innerRef.current) ro.observe(innerRef.current);
    return () => ro.disconnect();
  }, [fitHeight]);

  return (
    <div
      ref={outerRef}
      style={{
        width: "100%",
        height: fitHeight ? "100%" : height,
        overflow: "hidden",
        display: "flex",
        justifyContent: "center",
        alignItems: fitHeight ? "center" : "flex-start",
      }}
    >
      <div ref={innerRef} style={{ transform: `scale(${scale})`, transformOrigin: fitHeight ? "center" : "top center", flex: "0 0 auto" }}>
        {children}
      </div>
    </div>
  );
}

/** Small coloured RAG status dot. Pass `decorative` when an adjacent text label
 *  already names the status, so screen readers don't announce it twice. */
export function Dot({ status, decorative }: { status: Rag; decorative?: boolean }) {
  const { rag } = useI18n();
  // Status conveyed by colour needs a text alternative (colour-blind + SR), unless
  // an adjacent text label already says it (decorative → hidden from the a11y tree).
  if (decorative) return <span className={`dot ${dotClass(status)}`} aria-hidden />;
  return <span className={`dot ${dotClass(status)}`} role="img" aria-label={rag(status)} title={rag(status)} />;
}

/** Centered modal dialog with an overlay. */
export function Modal({ title, onClose, children, footer, width = 560, dirty = false }: {
  title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; width?: number;
  /** Something was typed: a click beside the window or Escape no longer closes it
   *  (and loses the typing); the explicit buttons still do. */
  dirty?: boolean;
}) {
  const { t } = useI18n();
  const cardRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  // Focus moves into the dialog once, when it opens, and goes back to what
  // opened it when it closes (the keyboard user stays where they were).
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    cardRef.current?.focus();
    return () => { if (opener && document.contains(opener)) opener.focus(); };
  }, []);
  // Escape closes (unless edited); Tab stays inside the window.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !dirty) onClose();
      if (e.key === "Tab" && cardRef.current) {
        const f = cardRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, dirty]);
  return (
    <div className="modal-overlay" onClick={() => { if (!dirty) onClose(); }}>
      <div ref={cardRef} className="modal-card" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
           style={{ maxWidth: `min(${width}px, calc(100vw - 32px))` }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3 id={titleId} style={{ margin: 0 }}>{title}</h3>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label={t("action.close")}>✕</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
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
        role="button"
        tabIndex={0}
        aria-expanded={open}
        style={{ cursor: "pointer", alignItems: "center", gap: 10 }}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen((o) => !o); } }}
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


/** Badge showing how recently something was updated; when `is_stale` it switches
 *  to a muted grey variant with a "stale" suffix to flag data needing a refresh. */
export function FreshnessBadge({ freshness }: { freshness: Freshness }) {
  const { freshness: ft, t } = useI18n();
  const text = ft(freshness);
  if (freshness.is_stale) {
    return (
      <span className="badge badge-grey">
        <span className="dot dot-grey" aria-hidden />
        {text}, {t("fresh.stale_suffix")}
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

/** Horizontal progress bar. `pct` is clamped to 0..100; optional `tone` colours
 *  the fill with a RAG class. */
export function ProgressBar({ pct, tone }: { pct: number; tone?: Rag }) {
  const cls = tone ? ragClass(tone) : "";
  return (
    <div className={`progress ${cls}`} role="progressbar" aria-valuemin={0} aria-valuemax={100}
         aria-valuenow={Math.round(Math.max(0, Math.min(100, pct)))}>
      <div style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}


/** Inline loading indicator with a polite live region; defaults to a translated
 *  "loading…" label when none is supplied. */
/** Section wrapper used by the reporting editors: title, optional hint + action slot.
 *  Lives here rather than in EntryPage so a section can be written in its own file
 *  without importing the page that renders it. */
export function SectionCard({ title, hint, action, children }: {
  title: ReactNode; hint?: ReactNode; action?: ReactNode; children: ReactNode;
}) {
  return (
    <div className="card">
      <div className="between">
        <h2 style={{ marginBottom: hint ? 2 : 12 }}>{title}</h2>
        {action}
      </div>
      {hint && <div className="small muted" style={{ marginBottom: 10 }}>{hint}</div>}
      {children}
    </div>
  );
}


export function Spinner({ label }: { label?: string }) {
  const { t } = useI18n();
  return <div className="spinner" role="status" aria-live="polite">{label ?? t("common.loading")}</div>;
}

/** Red alert banner for error messages (announced via role="alert"). */
export function ErrorBanner({ message }: { message: string }) {
  return <div className="banner banner-red" role="alert">{message}</div>;
}

/** Shared friendly empty-state card (replaces ad-hoc `.card muted` blocks). */
export function EmptyState({ message }: { message: ReactNode }) {
  return <div className="card muted" style={{ textAlign: "center", padding: 28 }}>{message}</div>;
}
