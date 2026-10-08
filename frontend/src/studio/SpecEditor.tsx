// Studio des exports: the editor of a specification. Two panes: the structure of
// the document (its settings, then its sections in order, each with its blocks)
// and the properties of what is selected. Used by the Studio page on a template,
// and by the Export menu on a one-off adjustment.
//
// Inheritance is shown, not hidden: a section or a parameter that differs from the
// parent's carries a mark and a "back to inherited" button, a part the parent
// locked is greyed out with the reason, and a section the parent has that this
// template removed is listed so it can be put back.
import { DragEvent, useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { ParamField, assetKindOf } from "./fields";
import GridEditor from "./GridEditor";
import {
  Asset, Catalog, Section, Spec, Theme, clone, lockedBy, newItem, newSection, parentSection, same,
  sectionChanged, widgetsFor,
} from "./model";

type Sel = { kind: "doc" } | { kind: "section"; id: string } | { kind: "block"; id: string; block: string }
  | { kind: "item"; id: string; item: string };

export type EditorMode = "full" | "simple" | "oneshot";

export default function SpecEditor({ cat, spec, onChange, parent, inherited = [], locks, onLocks, mode = "full",
  themes = [], assets = [], readOnly = false }: {
  cat: Catalog; spec: Spec; onChange: (s: Spec) => void; parent?: Spec | null; inherited?: string[];
  locks?: string[]; onLocks?: (l: string[]) => void; mode?: EditorMode; themes?: Theme[]; assets?: Asset[];
  readOnly?: boolean;
}) {
  const { t } = useI18n();
  const [sel, setSel] = useState<Sel>({ kind: "doc" });
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [dragId, setDragId] = useState<string | null>(null);
  const par = parent ?? null;
  const canAdd = !readOnly && mode !== "simple" && !lockedBy(inherited, "add");
  const canOrder = !readOnly && !lockedBy(inherited, "order");

  const edit = (fn: (s: Spec) => void) => { const n = clone(spec); fn(n); onChange(n); };
  const secLocked = (id: string) => readOnly || lockedBy(inherited, `section/${id}`);
  const blkLocked = (id: string, b: string) => secLocked(id) || lockedBy(inherited, `section/${id}/block/${b}`);
  const lockOn = (p: string) => !!locks?.includes(p);
  const toggleLock = (p: string) => onLocks?.(lockOn(p) ? (locks || []).filter((x) => x !== p) : [...(locks || []), p]);
  const LockBtn = ({ path }: { path: string }) => onLocks && !readOnly ? (
    <button type="button" className={`btn-ghost btn-xs studio-lock${lockOn(path) ? " on" : ""}`}
            title={t(lockOn(path) ? "studio.unlock_hint" : "studio.lock_hint")} aria-pressed={lockOn(path)}
            onClick={(e) => { e.stopPropagation(); toggleLock(path); }}>
      {lockOn(path) ? t("studio.locked_short") : t("studio.lock_short")}
    </button>
  ) : null;

  function move(id: string, to: number) {
    edit((s) => {
      const i = s.sections.findIndex((x) => x.id === id);
      if (i < 0 || to < 0 || to >= s.sections.length) return;
      const [x] = s.sections.splice(i, 1);
      s.sections.splice(to, 0, x);
    });
  }
  const onDrop = (target: string) => (e: DragEvent) => {
    e.preventDefault();
    if (!dragId || dragId === target) return;
    move(dragId, spec.sections.findIndex((x) => x.id === target));
    setDragId(null);
  };

  const allowed = cat.sections_for[spec.doc_kind] || [];
  const addable = mode === "oneshot" ? allowed.filter((x) => x === "text" || x === "cover") : allowed;
  const removed = par ? par.sections.filter((p) => !spec.sections.some((s) => s.id === p.id)) : [];
  const title = (s: Section) => (s.params?.title ? `${t(`studio.sec.${s.type}`)}: ${s.params.title}` : t(`studio.sec.${s.type}`));
  const current = sel.kind === "doc" ? null : spec.sections.find((s) => s.id === sel.id) || null;

  return (
    <div className="studio-editor">
      <div className="studio-structure" aria-label={t("studio.structure")}>
        <div className={`studio-node${sel.kind === "doc" ? " on" : ""}`} role="button" tabIndex={0}
             onClick={() => setSel({ kind: "doc" })} onKeyDown={(e) => e.key === "Enter" && setSel({ kind: "doc" })}>
          <span className="strong">{t("studio.document")}</span>
          <span className="small muted">{t("studio.document_hint")}</span>
        </div>
        <div className="studio-sections">
          {spec.sections.map((s, i) => {
            const ch = sectionChanged(par, s);
            const locked = secLocked(s.id);
            const st = cat.sections[s.type];
            const blocks = Object.keys(st?.blocks || {});
            return (
              <div key={s.id} className={`studio-sec${!s.enabled ? " off" : ""}${dragId === s.id ? " dragging" : ""}`}
                   draggable={canOrder} onDragStart={() => setDragId(s.id)} onDragEnd={() => setDragId(null)}
                   onDragOver={(e) => canOrder && e.preventDefault()} onDrop={onDrop(s.id)}>
                <div className={`studio-node${sel.kind !== "doc" && sel.id === s.id && sel.kind === "section" ? " on" : ""}`}
                     role="button" tabIndex={0}
                     onClick={() => setSel({ kind: "section", id: s.id })}
                     onKeyDown={(e) => e.key === "Enter" && setSel({ kind: "section", id: s.id })}>
                  {canOrder && <span className="studio-grip" aria-hidden>⋮⋮</span>}
                  <input type="checkbox" checked={s.enabled} disabled={locked} aria-label={t("studio.enabled")}
                         onClick={(e) => e.stopPropagation()}
                         onChange={(e) => edit((n) => { n.sections[i].enabled = e.target.checked; })} />
                  <span className="studio-node-title">{title(s)}</span>
                  {st?.repeat !== "once" && <span className="badge badge-grey">{t(`studio.o.${st.repeat}`)}</span>}
                  {s.type === "custom" && s.params.repeat !== "once" && <span className="badge badge-grey">{t(`studio.o.${s.params.repeat}`)}</span>}
                  {ch === "new" && <span className="badge badge-navy">{t("studio.added")}</span>}
                  {ch === "changed" && <span className="badge badge-orange">{t("studio.changed")}</span>}
                  {lockedBy(inherited, `section/${s.id}`) && <span className="badge badge-grey" title={t("studio.locked_by_parent")}>{t("studio.locked_short")}</span>}
                  <span className="studio-node-tools">
                    <LockBtn path={`section/${s.id}`} />
                    {canOrder && <button type="button" className="btn-ghost btn-xs" aria-label={t("studio.up")} disabled={i === 0}
                                         onClick={(e) => { e.stopPropagation(); move(s.id, i - 1); }}>↑</button>}
                    {canOrder && <button type="button" className="btn-ghost btn-xs" aria-label={t("studio.down")} disabled={i === spec.sections.length - 1}
                                         onClick={(e) => { e.stopPropagation(); move(s.id, i + 1); }}>↓</button>}
                    {blocks.length > 0 && (
                      <button type="button" className="btn-ghost btn-xs" aria-expanded={!!open[s.id]}
                              onClick={(e) => { e.stopPropagation(); setOpen((o) => ({ ...o, [s.id]: !o[s.id] })); }}>
                        {open[s.id] ? "▾" : "▸"} {t("studio.blocks_n", { n: blocks.length })}
                      </button>
                    )}
                    {canAdd && !locked && (
                      <button type="button" className="btn-ghost btn-xs" aria-label={t("studio.remove_section")} title={t("studio.remove_section")}
                              onClick={(e) => { e.stopPropagation(); edit((n) => { n.sections.splice(i, 1); }); setSel({ kind: "doc" }); }}>✕</button>
                    )}
                  </span>
                </div>
                {open[s.id] && (
                  <div className="studio-blocks">
                    {blocks.map((b) => {
                      const blk = s.blocks[b];
                      const pb = parentSection(par, s.id)?.blocks?.[b];
                      const diff = !!pb && !same(pb, blk);
                      return (
                        <div key={b} className={`studio-node studio-block${sel.kind === "block" && sel.id === s.id && sel.block === b ? " on" : ""}${!blk.enabled ? " off" : ""}`}
                             role="button" tabIndex={0} onClick={() => setSel({ kind: "block", id: s.id, block: b })}
                             onKeyDown={(e) => e.key === "Enter" && setSel({ kind: "block", id: s.id, block: b })}>
                          <input type="checkbox" checked={blk.enabled} disabled={blkLocked(s.id, b)} aria-label={t(`studio.blk.${b}`)}
                                 onClick={(e) => e.stopPropagation()}
                                 onChange={(e) => edit((n) => { n.sections[i].blocks[b].enabled = e.target.checked; })} />
                          <span className="studio-node-title">{t(`studio.blk.${b}`)}</span>
                          {diff && <span className="badge badge-orange">{t("studio.changed")}</span>}
                          {lockedBy(inherited, `section/${s.id}/block/${b}`) && <span className="badge badge-grey">{t("studio.locked_short")}</span>}
                          <span className="studio-node-tools"><LockBtn path={`section/${s.id}/block/${b}`} /></span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {removed.length > 0 && !readOnly && (
          <div className="studio-removed">
            <div className="small muted">{t("studio.removed_from_parent")}</div>
            {removed.map((p) => (
              <div key={p.id} className="between small">
                <span>{title(p)}</span>
                {!lockedBy(inherited, "add") && (
                  <button type="button" className="btn-ghost btn-xs"
                          onClick={() => edit((n) => { n.sections.push(clone(p)); })}>{t("studio.restore_section")}</button>
                )}
              </div>
            ))}
          </div>
        )}
        {canAdd && (
          <select className="studio-add" value="" aria-label={t("studio.add_section")}
                  onChange={(e) => {
                    const type = e.target.value;
                    if (!type) return;
                    const sec = newSection(cat, spec, type);
                    edit((n) => { n.sections.push(sec); });
                    setSel({ kind: "section", id: sec.id });
                  }}>
            <option value="">{t("studio.add_section")}</option>
            {addable.map((x) => <option key={x} value={x}>{t(`studio.sec.${x}`)}</option>)}
          </select>
        )}
      </div>

      <div className="studio-props">
        {sel.kind === "doc" && (
          <div className="stack" style={{ gap: 10 }}>
            <h3 className="studio-props-title">{t("studio.document")}</h3>
            {mode !== "oneshot" && (
              <div className="studio-field">
                <label className="field-label between">
                  <span>{t("studio.theme")}</span>
                  <LockBtn path="theme" />
                </label>
                <select value={spec.theme_id ?? ""} disabled={readOnly || lockedBy(inherited, "theme")}
                        onChange={(e) => edit((n) => { n.theme_id = e.target.value ? Number(e.target.value) : null; })}>
                  <option value="">{t("studio.theme_standard")}</option>
                  {themes.map((th) => <option key={th.id} value={th.id}>{th.name}</option>)}
                </select>
                {lockedBy(inherited, "theme") && <div className="small muted">{t("studio.locked_by_parent")}</div>}
              </div>
            )}
            {Object.entries(cat.doc_params).map(([k, p]) => (
              <ParamField key={k} name={k} spec={p} value={spec.doc[k]}
                          disabled={readOnly || lockedBy(inherited, "doc", `doc/${k}`)}
                          inherited={par ? same(par.doc[k], spec.doc[k]) : undefined}
                          onReset={par ? () => edit((n) => { n.doc[k] = clone(par.doc[k]); }) : undefined}
                          onChange={(v) => edit((n) => { n.doc[k] = v; })} />
            ))}
            <div className="small muted">{t("studio.tokens_hint", { tokens: cat.tokens.map((x) => `{${x}}`).join(" ") })}</div>
            {onLocks && !readOnly && (
              <div className="studio-field">
                <label className="field-label">{t("studio.locks_doc")}</label>
                <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
                  <LockBtn path="doc" /><span className="small">{t("studio.lock_doc")}</span>
                  <LockBtn path="order" /><span className="small">{t("studio.lock_order")}</span>
                  <LockBtn path="add" /><span className="small">{t("studio.lock_add")}</span>
                </div>
                <div className="small muted">{t("studio.locks_hint")}</div>
              </div>
            )}
          </div>
        )}

        {current && sel.kind === "section" && (() => {
          const i = spec.sections.findIndex((s) => s.id === current.id);
          const st = cat.sections[current.type];
          const ps = parentSection(par, current.id);
          const locked = secLocked(current.id);
          return (
            <div className="stack" style={{ gap: 10 }}>
              <h3 className="studio-props-title">{title(current)}</h3>
              <div className="small muted">{t(`studio.sec_hint.${current.type}`)}</div>
              {locked && !readOnly && <div className="banner small">{t("studio.locked_by_parent")}</div>}
              {Object.entries(st.params).filter(([k]) => !(mode === "simple" && current.type === "custom" && k === "repeat")).map(([k, p]) => (
                <ParamField key={k} name={k} spec={p} value={current.params[k]} disabled={locked || (mode === "simple" && ["cover", "text", "custom", "imported"].includes(current.type))}
                            assets={assets} assetKind={assetKindOf(current.type, k)}
                            inherited={ps ? same(ps.params[k], current.params[k]) : undefined}
                            onReset={ps ? () => edit((n) => { n.sections[i].params[k] = clone(ps.params[k]); }) : undefined}
                            onChange={(v) => edit((n) => {
                              n.sections[i].params[k] = v;
                              // A free layout that changes its repetition keeps only the widgets it can still place.
                              if (current.type === "custom" && k === "repeat") {
                                const ok = widgetsFor(cat, spec.doc_kind, v);
                                n.sections[i].items = (n.sections[i].items || []).filter((it) => ok.includes(it.widget));
                              }
                            })} />
              ))}
              {current.type === "imported" && current.params.asset && (
                <ImportedSlides asset={current.params.asset} value={current.params.slide}
                                disabled={locked || mode === "simple" || readOnly}
                                onPick={(n) => edit((x) => { x.sections[i].params.slide = n; })} />
              )}
              {current.type === "custom" && (
                <CustomLayout cat={cat} spec={spec} sec={current} disabled={locked || mode === "simple" || readOnly}
                              selected={null} onSelect={(id) => id && setSel({ kind: "item", id: current.id, item: id })}
                              onChange={(items) => edit((n) => { n.sections[i].items = items; })} />
              )}
            </div>
          );
        })()}

        {current && sel.kind === "item" && (() => {
          const i = spec.sections.findIndex((s) => s.id === current.id);
          const it = (current.items || []).find((x) => x.id === sel.item);
          const locked = secLocked(current.id) || mode === "simple" || readOnly;
          if (!it) return null;
          const wspec = cat.widgets[it.widget];
          const j = (current.items || []).indexOf(it);
          return (
            <div className="stack" style={{ gap: 10 }}>
              <div className="between">
                <h3 className="studio-props-title">{t(`studio.w.${it.widget}`)}</h3>
                <button type="button" className="btn-ghost btn-xs" onClick={() => setSel({ kind: "section", id: current.id })}>
                  ← {title(current)}
                </button>
              </div>
              <CustomLayout cat={cat} spec={spec} sec={current} disabled={locked} selected={it.id}
                            onSelect={(id) => setSel(id ? { kind: "item", id: current.id, item: id } : { kind: "section", id: current.id })}
                            onChange={(items) => edit((n) => { n.sections[i].items = items; })} />
              <div className="studio-zone small">
                {t("studio.zone", { c0: it.zone[0] + 1, c1: it.zone[2], r0: it.zone[1] + 1, r1: it.zone[3] })}
              </div>
              {Object.entries(wspec.params).map(([k, p]) => (
                <ParamField key={k} name={k} spec={p} value={it.params[k]} disabled={locked} assets={assets} assetKind="image"
                            onChange={(v) => edit((n) => { (n.sections[i].items || [])[j].params[k] = v; })} />
              ))}
              {!locked && (
                <button type="button" className="btn-danger btn-sm" style={{ alignSelf: "flex-start" }}
                        onClick={() => { edit((n) => { n.sections[i].items = (n.sections[i].items || []).filter((x) => x.id !== it.id); });
                                         setSel({ kind: "section", id: current.id }); }}>
                  {t("studio.remove_widget")}
                </button>
              )}
            </div>
          );
        })()}

        {current && sel.kind === "block" && (() => {
          const i = spec.sections.findIndex((s) => s.id === current.id);
          const b = sel.block;
          const bspec = cat.sections[current.type].blocks[b]?.params || {};
          const blk = current.blocks[b];
          const pb = parentSection(par, current.id)?.blocks?.[b];
          const locked = blkLocked(current.id, b);
          return (
            <div className="stack" style={{ gap: 10 }}>
              <div className="between">
                <h3 className="studio-props-title">{t(`studio.blk.${b}`)}</h3>
                <button type="button" className="btn-ghost btn-xs" onClick={() => setSel({ kind: "section", id: current.id })}>
                  ← {title(current)}
                </button>
              </div>
              <div className="small muted">{t(`studio.blk_hint.${b}`)}</div>
              <label className="inline small" style={{ gap: 6 }}>
                <input type="checkbox" checked={blk.enabled} disabled={locked}
                       onChange={(e) => edit((n) => { n.sections[i].blocks[b].enabled = e.target.checked; })} />
                {t("studio.block_shown")}
              </label>
              {Object.entries(bspec).map(([k, p]) => (
                <ParamField key={k} name={k} spec={p} value={blk.params[k]} disabled={locked}
                            inherited={pb ? same(pb.params?.[k], blk.params[k]) : undefined}
                            onReset={pb ? () => edit((n) => { n.sections[i].blocks[b].params[k] = clone(pb.params?.[k]); }) : undefined}
                            onChange={(v) => edit((n) => { n.sections[i].blocks[b].params[k] = v; })} />
              ))}
              {pb && !same(pb, blk) && !locked && (
                <button type="button" className="btn-ghost btn-sm" style={{ alignSelf: "flex-start" }}
                        onClick={() => edit((n) => { n.sections[i].blocks[b] = clone(pb); })}>{t("studio.reset_block")}</button>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

/** The grid of a free layout and the palette of widgets it can take. */
export function CustomLayout({ cat, spec, sec, disabled, selected, onSelect, onChange }: {
  cat: Catalog; spec: Spec; sec: Section; disabled: boolean; selected: string | null;
  onSelect: (id: string | null) => void; onChange: (items: Section["items"]) => void;
}) {
  const { t } = useI18n();
  const ok = widgetsFor(cat, spec.doc_kind, sec.params.repeat || "once");
  return (
    <div className="stack" style={{ gap: 8 }}>
      <GridEditor items={sec.items || []} cols={cat.grid.cols} rows={cat.grid.rows} selected={selected}
                  onSelect={onSelect} onChange={(items) => onChange(items)} disabled={disabled}
                  hasTitle={!!sec.params.title} />
      {!disabled && (
        <select value="" aria-label={t("studio.add_widget")}
                onChange={(e) => {
                  if (!e.target.value) return;
                  const it = newItem(cat, sec, e.target.value);
                  onChange([...(sec.items || []), it]);
                  onSelect(it.id);
                }}>
          <option value="">{t("studio.add_widget")}</option>
          {ok.map((w) => <option key={w} value={w}>{t(`studio.w.${w}`)}</option>)}
        </select>
      )}
      <div className="small muted">{t("studio.grid_hint")}</div>
    </div>
  );
}

/** The slides of the PowerPoint a section imports, to pick one by its first words. */
export function ImportedSlides({ asset, value, disabled, onPick }: {
  asset: number; value: number; disabled: boolean; onPick: (n: number) => void;
}) {
  const { t } = useI18n();
  const [slides, setSlides] = useState<{ index: number; text: string }[] | null>(null);
  useEffect(() => {
    setSlides(null);
    api.get<{ slides: { index: number; text: string }[] }>(`/api/exports/assets/${asset}/slides`)
      .then((r) => setSlides(r.slides)).catch(() => setSlides([]));
  }, [asset]);
  if (!slides) return <div className="small muted">{t("common.loading")}</div>;
  return (
    <div className="studio-field">
      <label className="field-label">{t("studio.pick_slide")}</label>
      <div className="studio-slides">
        {slides.map((sl) => (
          <button key={sl.index} type="button" disabled={disabled}
                  className={`studio-slide-pick${sl.index === value ? " on" : ""}`} onClick={() => onPick(sl.index)}>
            <span className="strong">{t("studio.slide_n", { n: sl.index })}</span>
            <span className="small muted">{sl.text || t("studio.slide_no_text")}</span>
          </button>
        ))}
      </div>
      <div className="small muted">{t("studio.imported_hint")}</div>
    </div>
  );
}
