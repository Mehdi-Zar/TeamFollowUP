// Studio des exports: the live preview. It sends the specification being edited
// (never saved for that) with the document context, and shows the slides the
// server drew from the very deck the export would produce, scaled to the pane.
// Under it, what a projected slide cannot afford, each line taking you to its
// slide.
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { DocContext, DocKind, PreviewResult, Spec } from "./model";

export default function Preview({ docKind, spec, templateId, context, onResult }: {
  docKind: DocKind; spec?: Spec | null; templateId?: number | null;
  context: DocContext; onResult?: (r: PreviewResult | null) => void;
}) {
  const { t } = useI18n();
  const [res, setRes] = useState<PreviewResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [zoom, setZoom] = useState(0.5);
  const frame = useRef<HTMLIFrameElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const seq = useRef(0);
  const key = JSON.stringify({ docKind, spec, templateId, context });

  useEffect(() => {
    const n = ++seq.current;
    setBusy(true);
    const h = setTimeout(async () => {
      try {
        const body: any = { doc_kind: docKind, context };
        if (spec) body.spec = spec;
        if (templateId) body.template_id = templateId;
        const r = await api.post<PreviewResult>("/api/exports/preview", body);
        if (n !== seq.current) return;
        setRes(r); setErr(null); onResult?.(r);
      } catch (e) {
        if (n !== seq.current) return;
        setErr(errorText(e)); onResult?.(null);
      } finally {
        if (n === seq.current) setBusy(false);
      }
    }, 450);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // The deck is 1280 px wide; the pane decides the scale.
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setZoom(Math.max(0.2, Math.min(1, (el.clientWidth - 40) / ((res?.width || 1280))))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [res?.width]);

  const doc = res ? `<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;padding:16px;background:#E5E7EB}${res.css}
    .deck{zoom:${zoom}}</style></head><body>${res.html}</body></html>` : "";

  function goTo(slide: number) {
    const d = frame.current?.contentDocument;
    d?.querySelector(`[data-index="${slide}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const lintGroups = (res?.lints || []).reduce<Record<string, number>>((acc, l) => {
    acc[l.kind] = (acc[l.kind] || 0) + 1; return acc;
  }, {});

  return (
    <div className="studio-preview" ref={box}>
      <div className="between studio-preview-head">
        <span className="small">
          {res ? t("studio.preview_slides", { n: res.slides }) : t("studio.preview")}
          {busy && <span className="muted"> {t("studio.preview_busy")}</span>}
        </span>
        {res && <span className="small muted">{res.filename}</span>}
      </div>
      {err && <div className="banner banner-red small" role="alert">{err}</div>}
      {res && (
        <iframe ref={frame} title={t("studio.preview")} className="studio-preview-frame" srcDoc={doc}
                sandbox="allow-same-origin" />
      )}
      {!res && !err && <div className="studio-preview-empty small muted">{t("studio.preview_wait")}</div>}
      {res && (res.lints.length > 0 || res.warnings.length > 0) && (
        <div className="studio-lints">
          <div className="small strong">
            {t("studio.checks")}{" "}
            {Object.entries(lintGroups).map(([k, n]) => (
              <span key={k} className={`badge ${k === "banned_char" || k === "overflow" ? "badge-orange" : "badge-grey"}`} style={{ marginLeft: 4 }}>
                {t(`studio.lint.${k}`)} {n}
              </span>
            ))}
          </div>
          <ul>
            {res.warnings.map((w, i) => (
              <li key={`w${i}`} className="small">{t(`studio.warn.${w.kind}`)} {w.section && <span className="muted">({w.section})</span>}</li>
            ))}
            {res.lints.slice(0, 60).map((l, i) => (
              <li key={i} className="small">
                <button type="button" className="btn-link" onClick={() => goTo(l.slide)}>
                  {t("studio.slide_n", { n: l.slide })}
                </button>{" "}
                {t(`studio.lint.${l.kind}`)}
                {l.size ? ` (${l.size} pt)` : ""}{l.ratio ? ` (${l.ratio}:1)` : ""}
                {": "}<span className="muted">{l.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {res && res.lints.length === 0 && res.warnings.length === 0 && (
        <div className="small muted studio-lints-ok">{t("studio.checks_ok")}</div>
      )}
    </div>
  );
}
