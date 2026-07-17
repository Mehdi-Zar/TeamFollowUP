// CommandPalette: the ⌘K / Ctrl+K quick switcher overlay. Merges the visible nav
// pages (passed in) with the squads fetched from the API into one searchable,
// keyboard-navigable list, and navigates on selection.
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";

// One selectable row. `hint` is the right-hand label (e.g. "Page" / "Squad");
// `key` is a stable de-dup key prefixed by source ("p:" pages, "s:" squads).
type Item = { key: string; label: string; to: string; hint: string };

/** Quick switcher: ⌘K / Ctrl+K (or the topbar button) opens a searchable list of
 *  pages and squads to jump to. Listens for the `cmdk:open` window event too. */
export default function CommandPalette({ pages }: { pages: { to: string; label: string }[] }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [squads, setSquads] = useState<{ id: number; name: string }[]>([]);
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
      else if (e.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("cmdk:open", onOpen);
    return () => { document.removeEventListener("keydown", onKey); window.removeEventListener("cmdk:open", onOpen); };
  }, []);

  useEffect(() => {
    if (!open) return;
    setQ(""); setIdx(0);
    setTimeout(() => inputRef.current?.focus(), 0);
    api.get<{ id: number; name: string }[]>("/api/squads")
      .then((s) => setSquads(s.map((x) => ({ id: x.id, name: x.name })))).catch(() => {});
  }, [open]);

  const items: Item[] = useMemo(() => {
    const all: Item[] = [
      ...pages.map((p) => ({ key: `p:${p.to}`, label: p.label, to: p.to, hint: t("cmd.page") })),
      ...squads.map((s) => ({ key: `s:${s.id}`, label: s.name, to: `/squads/${s.id}`, hint: t("cmd.squad") })),
    ];
    const needle = q.trim().toLowerCase();
    return (needle ? all.filter((i) => i.label.toLowerCase().includes(needle)) : all).slice(0, 12);
  }, [pages, squads, q, t]);

  useEffect(() => { if (idx >= items.length) setIdx(0); }, [items.length, idx]);

  if (!open) return null;
  const go = (i: Item) => { navigate(i.to); setOpen(false); };

  return (
    <div className="cmd-overlay no-print" onClick={() => setOpen(false)}>
      <div className="cmd" role="dialog" aria-modal="true" aria-label={t("cmd.placeholder")} onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef} className="cmd-input" placeholder={t("cmd.placeholder")} value={q}
          onChange={(e) => { setQ(e.target.value); setIdx(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, items.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
            else if (e.key === "Enter" && items[idx]) { e.preventDefault(); go(items[idx]); }
          }}
        />
        <div className="cmd-list">
          {items.length === 0 ? (
            <div className="cmd-empty">{t("cmd.none")}</div>
          ) : items.map((it, i) => (
            <button key={it.key} className={`cmd-item${i === idx ? " active" : ""}`}
                    onMouseEnter={() => setIdx(i)} onClick={() => go(it)}>
              <span>{it.label}</span>
              <span className="cmd-hint">{it.hint}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
