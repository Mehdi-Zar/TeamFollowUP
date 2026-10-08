// Studio des exports: the simple editor. One list, the slides of the document in
// their order. Each slide shows or hides with a box, moves with two arrows, and
// opens in place on what can be set on it: which parts it shows, then its few
// settings. Underneath, buttons to add a cover, a text, a free slide or a slide
// from a PowerPoint, and the document's look. Nothing else: locks, versions,
// inheritance and themes live in the advanced mode.
import { useState } from "react";
import { useI18n } from "../i18n";
import { ParamField, assetKindOf } from "./fields";
import { CustomLayout, ImportedSlides } from "./SpecEditor";
import { Asset, Catalog, Section, Spec, Theme, clone, lockedBy, newSection } from "./model";

const ADDABLE = ["cover", "text", "custom", "imported"];

export default function SimpleEditor({ cat, spec, onChange, inherited = [], canAdd = true, themes = [], assets = [],
  showTheme = true, readOnly = false }: {
  cat: Catalog; spec: Spec; onChange: (s: Spec) => void; inherited?: string[]; canAdd?: boolean;
  themes?: Theme[]; assets?: Asset[]; showTheme?: boolean; readOnly?: boolean;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState<string | null>(null);
  const [item, setItem] = useState<string | null>(null);
  const edit = (fn: (s: Spec) => void) => { const n = clone(spec); fn(n); onChange(n); };
  const canOrder = !readOnly && !lockedBy(inherited, "order");
  const allowed = new Set(cat.sections_for[spec.doc_kind] || []);
  const adding = canAdd && !readOnly && !lockedBy(inherited, "add");

  function move(i: number, d: number) {
    edit((s) => { const j = i + d; if (j < 0 || j >= s.sections.length) return; [s.sections[i], s.sections[j]] = [s.sections[j], s.sections[i]]; });
  }
  const name = (s: Section) => s.params?.title ? `${t(`studio.sec.${s.type}`)} : ${s.params.title}` : t(`studio.sec.${s.type}`);

  return (
    <div className="simple-editor">
      <ol className="simple-slides">
        {spec.sections.map((s, i) => {
          const locked = readOnly || lockedBy(inherited, `section/${s.id}`);
          const st = cat.sections[s.type];
          const blocks = Object.keys(st?.blocks || {});
          const isOpen = open === s.id;
          const repeat = s.type === "custom" ? s.params.repeat : st?.repeat;
          return (
            <li key={s.id} className={`simple-slide${s.enabled ? "" : " off"}${isOpen ? " open" : ""}`}>
              <div className="simple-slide-head">
                <label className="simple-check" title={t("simple.show_slide")}>
                  <input type="checkbox" checked={s.enabled} disabled={locked}
                         onChange={(e) => edit((n) => { n.sections[i].enabled = e.target.checked; })} />
                </label>
                <button type="button" className="simple-slide-name" onClick={() => { setOpen(isOpen ? null : s.id); setItem(null); }}
                        aria-expanded={isOpen}>
                  <span className="simple-num">{i + 1}</span>
                  <span>
                    <span className="strong">{name(s)}</span>
                    {repeat && repeat !== "once" && <span className="small muted"> ({t(`studio.o.${repeat}`)})</span>}
                    {locked && !readOnly && <span className="small muted"> ({t("simple.imposed")})</span>}
                    {/* What the slide is, said in the list: a name alone did not tell it. */}
                    {!isOpen && <span className="simple-desc">{t(`studio.sec_hint.${s.type}`)}</span>}
                  </span>
                  <span className="simple-caret" aria-hidden>{isOpen ? "▾" : "▸"}</span>
                </button>
                {canOrder && (
                  <span className="inline" style={{ gap: 2 }}>
                    <button type="button" className="btn-ghost btn-xs" disabled={i === 0} aria-label={t("studio.up")} onClick={() => move(i, -1)}>↑</button>
                    <button type="button" className="btn-ghost btn-xs" disabled={i === spec.sections.length - 1} aria-label={t("studio.down")} onClick={() => move(i, 1)}>↓</button>
                  </span>
                )}
                {adding && !locked && ADDABLE.includes(s.type) && (
                  <button type="button" className="btn-ghost btn-xs" aria-label={t("studio.remove_section")} title={t("studio.remove_section")}
                          onClick={() => edit((n) => { n.sections.splice(i, 1); })}>✕</button>
                )}
              </div>

              {isOpen && (
                <div className="simple-slide-body">
                  <div className="small muted">{t(`studio.sec_hint.${s.type}`)}</div>
                  {blocks.length > 0 && (
                    <div>
                      <div className="field-label">{t("simple.parts")}</div>
                      <div className="simple-parts">
                        {blocks.map((b) => (
                          <label key={b} className="simple-part">
                            <input type="checkbox" checked={s.blocks[b].enabled}
                                   disabled={locked || lockedBy(inherited, `section/${s.id}/block/${b}`)}
                                   onChange={(e) => edit((n) => { n.sections[i].blocks[b].enabled = e.target.checked; })} />
                            {t(`studio.blk.${b}`)}
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                  {/* The settings of the parts shown (table columns, counters...). */}
                  {blocks.filter((b) => s.blocks[b].enabled && Object.keys(st.blocks[b].params || {}).length).map((b) => (
                    <div key={b} className="simple-sub">
                      <div className="small strong">{t(`studio.blk.${b}`)}</div>
                      {Object.entries(st.blocks[b].params || {}).map(([k, p]) => (
                        <ParamField key={k} name={k} spec={p} value={s.blocks[b].params[k]}
                                    disabled={locked || lockedBy(inherited, `section/${s.id}/block/${b}`)}
                                    onChange={(v) => edit((n) => { n.sections[i].blocks[b].params[k] = v; })} />
                      ))}
                    </div>
                  ))}
                  {Object.entries(st.params).length > 0 && (
                    <div className="simple-params">
                      {Object.entries(st.params).map(([k, p]) => (
                        <ParamField key={k} name={k} spec={p} value={s.params[k]} disabled={locked}
                                    assets={assets} assetKind={assetKindOf(s.type, k)}
                                    onChange={(v) => edit((n) => { n.sections[i].params[k] = v; })} />
                      ))}
                    </div>
                  )}
                  {s.type === "imported" && s.params.asset && (
                    <ImportedSlides asset={s.params.asset} value={s.params.slide} disabled={locked}
                                    onPick={(v) => edit((n) => { n.sections[i].params.slide = v; })} />
                  )}
                  {s.type === "imported" && !assets.some((a) => a.kind === "pptx") && (
                    <div className="small muted">{t("simple.no_pptx")}</div>
                  )}
                  {s.type === "custom" && (
                    <>
                      <CustomLayout cat={cat} spec={spec} sec={s} disabled={locked} selected={item}
                                    onSelect={setItem} onChange={(items) => edit((n) => { n.sections[i].items = items; })} />
                      {(() => {
                        const it = (s.items || []).find((x) => x.id === item);
                        if (!it) return null;
                        const j = (s.items || []).indexOf(it);
                        return (
                          <div className="simple-sub">
                            <div className="between">
                              <span className="small strong">{t(`studio.w.${it.widget}`)}</span>
                              {!locked && (
                                <button type="button" className="btn-ghost btn-xs" onClick={() => {
                                  edit((n) => { n.sections[i].items = (n.sections[i].items || []).filter((x) => x.id !== it.id); }); setItem(null);
                                }}>{t("studio.remove_widget")}</button>
                              )}
                            </div>
                            {Object.entries(cat.widgets[it.widget].params).map(([k, p]) => (
                              <ParamField key={k} name={k} spec={p} value={it.params[k]} disabled={locked} assets={assets} assetKind="image"
                                          onChange={(v) => edit((n) => { (n.sections[i].items || [])[j].params[k] = v; })} />
                            ))}
                          </div>
                        );
                      })()}
                    </>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {adding && (
        <div className="simple-add">
          <span className="small muted">{t("simple.add")}</span>
          {ADDABLE.filter((x) => allowed.has(x)).map((x) => (
            <button key={x} type="button" className="btn-secondary btn-sm" onClick={() => {
              const sec = newSection(cat, spec, x);
              edit((n) => { n.sections.push(sec); });
              setOpen(sec.id);
            }}>+ {t(`studio.sec.${x}`)}</button>
          ))}
        </div>
      )}

      <div className="simple-doc">
        {showTheme && (
          <div className="studio-field">
            <label className="field-label">{t("studio.theme")}</label>
            <select value={spec.theme_id ?? ""} disabled={readOnly || lockedBy(inherited, "theme")}
                    onChange={(e) => edit((n) => { n.theme_id = e.target.value ? Number(e.target.value) : null; })}>
              <option value="">{t("studio.theme_standard")}</option>
              {themes.map((th) => <option key={th.id} value={th.id}>{th.name}</option>)}
            </select>
          </div>
        )}
        <ParamField name="footer" spec={cat.doc_params.footer} value={spec.doc.footer}
                    disabled={readOnly || lockedBy(inherited, "doc", "doc/footer")}
                    onChange={(v) => edit((n) => { n.doc.footer = v; })} />
        <ParamField name="page_numbers" spec={cat.doc_params.page_numbers} value={spec.doc.page_numbers}
                    disabled={readOnly || lockedBy(inherited, "doc", "doc/page_numbers")}
                    onChange={(v) => edit((n) => { n.doc.page_numbers = v; })} />
      </div>
    </div>
  );
}
