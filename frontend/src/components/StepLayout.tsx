// StepLayout: the body of a window walked through in steps (a squad's set-up, a
// platform's Steerco report). A numbered menu on the left, with under each step
// what it already holds, and the current step on the right under its title.
//
// One component for every such window, so they read the same way: the menu says
// which steps lead to which and what is already done, as the reporting's step bar
// does on its page.
import { ReactNode } from "react";

export type StepItem = {
  key: string;
  title: string;
  /** What the step already holds ("2 OTD", "3/5"): a glance, without opening it. */
  meta?: string;
  /** Ticked in the menu when nothing is left to do there. */
  done?: boolean;
};

export function StepLayout({ steps, at, onGo, desc, aside, children, ariaLabel }: {
  steps: StepItem[]; at: number; onGo: (i: number) => void;
  /** One sentence under the step's title: what it is for. */
  desc?: ReactNode;
  /** Shown right of the title (a status, the context of the window). */
  aside?: ReactNode;
  children: ReactNode;
  ariaLabel?: string;
}) {
  const current = steps[at];
  return (
    <div className="sq-layout">
      <nav className="sq-nav" aria-label={ariaLabel}>
        {steps.map((s, i) => (
          <button key={s.key} type="button" className={`sq-nav-item${i === at ? " on" : ""}`}
                  onClick={() => onGo(i)} aria-current={i === at ? "step" : undefined}>
            <span className={`step-num${i === at ? " on" : s.done ? " done" : ""}`}>
              {s.done && i !== at ? "✓" : i + 1}
            </span>
            <span className="sq-nav-text">
              <span className="sq-nav-title">{s.title}</span>
              {s.meta && <span className="sq-nav-meta">{s.meta}</span>}
            </span>
          </button>
        ))}
      </nav>

      <div className="sq-panel">
        <div className="sq-panel-head between" style={{ alignItems: "flex-start", gap: 12 }}>
          <div>
            <h3>{current?.title}</h3>
            {desc && <p>{desc}</p>}
          </div>
          {aside}
        </div>
        {children}
      </div>
    </div>
  );
}

/** A titled block inside a step: a theme, its title, a line of help, its fields.
 *  Fields stacked one under the other without groups read as a single list that
 *  did not say which went together. */
export function StepSection({ title, hint, children }: { title?: string; hint?: string; children: ReactNode }) {
  return (
    <section className="sq-section">
      {(title || hint) && (
        <div className="sq-section-head">
          {title && <h4>{title}</h4>}
          {hint && <p>{hint}</p>}
        </div>
      )}
      {children}
    </section>
  );
}
