// Studio des exports: the free layout of a slide. A 12 x 8 grid on the slide's
// 16:9 frame; each widget occupies a zone of whole cells. A widget moves by
// dragging it and resizes by its corner, always snapped to the grid: a free pixel
// position would not survive data that changes from one month to the next.
import { useRef, useState } from "react";
import { useI18n } from "../i18n";
import { Item } from "./model";

type Drag = { id: string; mode: "move" | "resize"; x0: number; y0: number; zone: Item["zone"] };

export default function GridEditor({ items, cols, rows, selected, onSelect, onChange, disabled, hasTitle }: {
  items: Item[]; cols: number; rows: number; selected: string | null; onSelect: (id: string | null) => void;
  onChange: (items: Item[]) => void; disabled?: boolean; hasTitle?: boolean;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);

  function cellOf(dx: number, dy: number) {
    const el = ref.current;
    if (!el) return [0, 0];
    const r = el.getBoundingClientRect();
    return [Math.round((dx / r.width) * cols), Math.round((dy / r.height) * rows)];
  }

  function onMove(e: React.PointerEvent) {
    if (!drag) return;
    const [dc, dr] = cellOf(e.clientX - drag.x0, e.clientY - drag.y0);
    const [c0, r0, c1, r1] = drag.zone;
    let z: Item["zone"];
    if (drag.mode === "move") {
      const w = c1 - c0, h = r1 - r0;
      const nc0 = Math.max(0, Math.min(cols - w, c0 + dc));
      const nr0 = Math.max(0, Math.min(rows - h, r0 + dr));
      z = [nc0, nr0, nc0 + w, nr0 + h];
    } else {
      z = [c0, r0, Math.max(c0 + 1, Math.min(cols, c1 + dc)), Math.max(r0 + 1, Math.min(rows, r1 + dr))];
    }
    onChange(items.map((it) => (it.id === drag.id ? { ...it, zone: z } : it)));
  }

  const start = (it: Item, mode: Drag["mode"]) => (e: React.PointerEvent) => {
    if (disabled) return;
    e.stopPropagation();
    (e.target as Element).setPointerCapture?.(e.pointerId);
    onSelect(it.id);
    setDrag({ id: it.id, mode, x0: e.clientX, y0: e.clientY, zone: [...it.zone] as Item["zone"] });
  };

  return (
    <div className="studio-grid-wrap">
      {hasTitle && <div className="studio-grid-title small muted">{t("studio.grid_title_band")}</div>}
      <div ref={ref} className="studio-grid" onPointerMove={onMove} onPointerUp={() => setDrag(null)}
           onPointerLeave={() => setDrag(null)} onClick={() => onSelect(null)}
           style={{ gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${rows}, 1fr)` }}>
        {Array.from({ length: cols * rows }).map((_, i) => <div key={i} className="studio-grid-cell" />)}
        {items.map((it) => {
          const [c0, r0, c1, r1] = it.zone;
          return (
            <div key={it.id} className={`studio-grid-item${selected === it.id ? " on" : ""}`}
                 style={{ left: `${(c0 / cols) * 100}%`, top: `${(r0 / rows) * 100}%`,
                          width: `${((c1 - c0) / cols) * 100}%`, height: `${((r1 - r0) / rows) * 100}%` }}
                 onPointerDown={start(it, "move")} onClick={(e) => { e.stopPropagation(); onSelect(it.id); }}
                 role="button" tabIndex={0} aria-label={t(`studio.w.${it.widget}`)}
                 onKeyDown={(e) => {
                   if (disabled) return;
                   const d: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
                   const m = d[e.key];
                   if (!m) return;
                   e.preventDefault();
                   const w = c1 - c0, h = r1 - r0;
                   const nc0 = Math.max(0, Math.min(cols - w, c0 + m[0]));
                   const nr0 = Math.max(0, Math.min(rows - h, r0 + m[1]));
                   onChange(items.map((x) => (x.id === it.id ? { ...x, zone: [nc0, nr0, nc0 + w, nr0 + h] } : x)));
                 }}>
              <span className="studio-grid-label">{t(`studio.w.${it.widget}`)}</span>
              {!disabled && <span className="studio-grid-handle" onPointerDown={start(it, "resize")} aria-hidden />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
