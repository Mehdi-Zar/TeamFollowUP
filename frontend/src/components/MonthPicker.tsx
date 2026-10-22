// MonthPicker - choose a "YYYY-MM" month in a small calendar: the year with
// arrows on top, the twelve months as a grid below. Replaces the long dropdown of
// months, where finding last year's March meant scrolling through two years.
import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { currentSteercoPeriod, monthLongLabel } from "../steerco";

type Props = {
  value: string;
  onChange: (period: string) => void;
  id?: string;
  disabled?: boolean;
  width?: number | string;
};

export default function MonthPicker({ value, onChange, id, disabled, width = "100%" }: Props) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const [selY, selM] = (value || currentSteercoPeriod()).split("-").map(Number);
  const [year, setYear] = useState(selY);
  const now = currentSteercoPeriod();
  const locale = lang === "fr" ? "fr-FR" : "en-US";

  // The panel opens on the year of the chosen month.
  useEffect(() => { if (open) setYear(selY); }, [open, selY]);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const key = (m: number) => `${year}-${String(m).padStart(2, "0")}`;
  const short = (m: number) => {
    const s = new Date(year, m - 1, 1).toLocaleDateString(locale, { month: "short" });
    return s.charAt(0).toUpperCase() + s.slice(1);
  };

  return (
    <div className="month-picker" ref={ref} style={{ width }}>
      <button type="button" id={id} className="month-picker-btn" disabled={disabled}
              aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span>{monthLongLabel(value, lang)}</span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="3" y="5" width="18" height="16" rx="2" /><line x1="3" y1="10" x2="21" y2="10" />
          <line x1="8" y1="3" x2="8" y2="7" /><line x1="16" y1="3" x2="16" y2="7" />
        </svg>
      </button>
      {open && (
        <div className="month-picker-pop menu-pop" role="dialog" aria-label={t("monthpicker.title")}>
          <div className="month-picker-head">
            <button type="button" className="btn-ghost btn-sm" aria-label={t("monthpicker.prev_year")}
                    onClick={() => setYear((y) => y - 1)}>‹</button>
            <span className="strong">{year}</span>
            <button type="button" className="btn-ghost btn-sm" aria-label={t("monthpicker.next_year")}
                    onClick={() => setYear((y) => y + 1)}>›</button>
          </div>
          <div className="month-picker-grid">
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => {
              const k = key(m);
              const cls = ["month-picker-cell", year === selY && m === selM ? "is-selected" : "", k === now ? "is-now" : ""]
                .filter(Boolean).join(" ");
              return (
                <button type="button" key={k} className={cls} aria-pressed={year === selY && m === selM}
                        title={monthLongLabel(k, lang)} onClick={() => { onChange(k); setOpen(false); }}>
                  {short(m)}
                </button>
              );
            })}
          </div>
          <div className="month-picker-foot">
            <button type="button" className="btn-ghost btn-sm" onClick={() => { onChange(now); setOpen(false); }}>
              {t("monthpicker.this_month")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
