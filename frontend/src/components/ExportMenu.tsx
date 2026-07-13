import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { useAuth } from "../auth";
import { Squad, Tribe } from "../types";
import { Modal } from "./ui";
import { HtmlPreviewModal } from "./HtmlPreview";

/** One tidy "Export / Share" dropdown that groups every export & email action
 *  (HTML/PPTX report, roadmap with squad selection, send by mail). HTML opens in
 *  an in-app window (not a new tab). Items appear only when their module/SMTP
 *  allows it. Report subscriptions live in the "Subscribe to a report" popup. */
type Props = {
  year?: number;
  squadId?: number;
  sinceDays?: number;
};

type View = "menu" | "emailReport";
type Preview = { url: string; title: string };

/** Render an export's HTML to a JPG (image equivalent of the HTML export):
 *  fetch the HTML, lay it out in an isolated off-screen iframe, html2canvas it. */
async function renderHtmlToJpg(url: string, filename: string): Promise<void> {
  const iframe = document.createElement("iframe");
  try {
    const html = await (await fetch(url, { credentials: "include" })).text();
    Object.assign(iframe.style, { position: "fixed", left: "-10000px", top: "0", width: "1160px", height: "1200px", border: "0" });
    document.body.appendChild(iframe);
    await new Promise<void>((resolve) => { iframe.onload = () => resolve(); iframe.srcdoc = html; });
    await new Promise((r) => setTimeout(r, 400)); // let fonts / layout settle
    const doc = iframe.contentDocument!;
    const body = doc.body;
    const w = Math.max(1160, body.scrollWidth);
    const h = Math.max(body.scrollHeight, doc.documentElement.scrollHeight);
    iframe.style.height = h + "px";
    const html2canvas = (await import("html2canvas")).default;
    const canvas = await html2canvas(body, { scale: 2, backgroundColor: "#F5F7FA", useCORS: true, windowWidth: w, windowHeight: h, width: w, height: h });
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/jpeg", 0.95);
    a.download = filename; a.click();
  } finally {
    iframe.remove();
  }
}

export default function ExportMenu({ year, squadId, sinceDays = 7 }: Props) {
  const { t, lang } = useI18n();
  const { smtp_enabled } = useConfig();
  const m = useModule();
  const { user, can } = useAuth();
  // A document is only offered when its module is on AND the persona holds the
  // capability of the section it exports - the same pair the API now enforces
  // (backend/app/routers/reports.py). This menu also shows on the squad page,
  // which has no capability guard of its own, so the check has to live here.
  const reportOn = m("review", "weekly_report") && can("dashboard");
  const roadmapOn = m("squad_content", "roadmap") && can("roadmap");
  const dashboardOn = m("dashboard") && can("dashboard");

  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("menu");
  const [to, setTo] = useState(user?.email || "");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // HTML exports open in this in-app window rather than a new browser tab.
  const [preview, setPreview] = useState<Preview | null>(null);
  // Global roadmap / dashboard: pick which squads appear (in a dedicated modal).
  const [roadmapModal, setRoadmapModal] = useState(false);
  const [dashModal, setDashModal] = useState(false);

  const rqs = `since_days=${sinceDays}${squadId ? `&squad_id=${squadId}` : ""}&lang=${lang}`;
  // Per-squad → the squad's own roadmap; otherwise (dashboard/roadmap/tribe) → the
  // global roadmap matrix with squad selection. Both gated by the roadmap module.
  const roadmapAvail = roadmapOn;
  const roadmapBase = squadId ? `/api/squads/${squadId}/roadmap` : "/api/reports/roadmap";
  const roadmapQs = squadId ? `${year ? `year=${year}&` : ""}lang=${lang}` : rqs;

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) { setOpen(false); setView("menu"); }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const hasDownloads = roadmapAvail || dashboardOn;
  const hasEmail = smtp_enabled && reportOn;
  if (!hasDownloads && !hasEmail) return null;

  async function sendReport() {
    if (!to.trim()) return;
    setBusy(true); setMsg(null);
    try {
      await api.post("/api/reports/weekly/email", { to: to.trim(), since_days: sinceDays, squad_id: squadId ?? null, lang });
      setMsg(t("export.sent", { to: to.trim() }));
    } catch (e) { setMsg(e instanceof ApiError ? e.message : "Erreur"); } finally { setBusy(false); }
  }
  // JPG equivalent of an HTML export (renders the export HTML to an image).
  async function htmlToJpg(url: string, filename: string) {
    setOpen(false); setBusy(true); setMsg(t("export.jpg_busy"));
    try {
      await renderHtmlToJpg(url, filename);
      setMsg(null);
    } catch {
      setMsg(t("export.jpg_fail"));
    } finally {
      setBusy(false);
    }
  }

  const Item = ({ children, onClick, href, download }: any) =>
    href ? (
      <a className="menu-item" href={href} target={download ? undefined : "_blank"} rel="noreferrer" onClick={() => setOpen(false)}>{children}</a>
    ) : (
      <button className="menu-item" onClick={onClick}>{children}</button>
    );
  // One row per document; the three formats sit in a tidy segmented control.
  const ExportRow = ({ label, html, pptx }: { label: string; html: string; pptx: string }) => (
    <div className="export-row">
      <span className="export-row-label">{label}</span>
      <span className="seg">
        <button onClick={() => { setPreview({ url: html, title: label }); setOpen(false); }}>HTML</button>
        <button onClick={() => htmlToJpg(html, `${label}.jpg`)}>JPG</button>
        <a href={pptx} download onClick={() => setOpen(false)}>PPTX</a>
      </span>
    </div>
  );

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button className="btn btn-secondary btn-sm" onClick={() => { setOpen((o) => !o); setView("menu"); setMsg(null); }}>
        {t("export.menu")} ▾
      </button>
      {open && (
        <div className="card menu-pop export-pop" style={{ position: "absolute", right: 0, top: 42, zIndex: 60 }}>
          {view === "menu" && (
            <>
              {hasDownloads && <div className="menu-label">{t("export.group_download")}</div>}
              {dashboardOn && squadId && <ExportRow label={t("export.doc_dashboard")} html={`/api/reports/dashboard.html?${rqs}`} pptx={`/api/reports/dashboard.pptx?${rqs}`} />}
              {dashboardOn && !squadId && <Item onClick={() => { setDashModal(true); setOpen(false); }}>{t("export.doc_dashboard")} …</Item>}
              {roadmapAvail && squadId && <ExportRow label={t("export.doc_roadmap")} html={`${roadmapBase}.html?${roadmapQs}`} pptx={`${roadmapBase}.pptx?${roadmapQs}`} />}
              {roadmapAvail && !squadId && <Item onClick={() => { setRoadmapModal(true); setOpen(false); }}>{t("export.doc_roadmap")} …</Item>}
              {roadmapAvail && <ExportRow label={t("export.doc_dependencies")} html={`/api/reports/dependencies.html?${rqs}`} pptx={`/api/reports/dependencies.pptx?${rqs}`} />}

              {hasEmail && <div className="menu-label" style={{ marginTop: 6 }}>{t("export.group_email")}</div>}
              {hasEmail && <Item onClick={() => { setView("emailReport"); setMsg(null); }}>{t("export.send_report")} …</Item>}
            </>
          )}

          {view === "emailReport" && (
            <div className="export-form stack" style={{ gap: 12 }}>
              <button className="export-back" onClick={() => setView("menu")}>← {t("export.send_report")}</button>
              <div>
                <label className="field-label">{t("export.to")}</label>
                <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="nom@exemple.com" />
              </div>
              <div className="inline" style={{ justifyContent: "flex-end", gap: 8 }}>
                <button className="btn-ghost btn-sm" onClick={() => setView("menu")}>{t("action.cancel")}</button>
                <button className="btn btn-sm" disabled={busy || !to.trim()} onClick={sendReport}>{busy ? "…" : t("export.send")}</button>
              </div>
            </div>
          )}

          {msg && <div className="small muted" style={{ padding: "8px 8px 2px" }}>{msg}</div>}
        </div>
      )}
      {roadmapModal && (
        <SquadExportPicker base="roadmap" title={t("export.roadmap_modal_title")}
          htmlLabel={t("export.roadmap_html")} pptxLabel={t("export.roadmap_pptx")}
          sinceDays={sinceDays} year={year} lang={lang} onClose={() => setRoadmapModal(false)}
          onPreview={(url, title) => setPreview({ url, title })} />
      )}
      {dashModal && (
        <SquadExportPicker base="dashboard" title={t("export.dashboard_modal_title")}
          htmlLabel={t("export.dashboard_html")} pptxLabel={t("export.dashboard_pptx")}
          sinceDays={sinceDays} year={year} lang={lang} onClose={() => setDashModal(false)}
          onPreview={(url, title) => setPreview({ url, title })} />
      )}
      {preview && <HtmlPreviewModal url={preview.url} title={preview.title} onClose={() => setPreview(null)} />}
    </div>
  );
}

/** Wide, easy-to-use modal to pick which squads (grouped by tribe) appear in a
 *  global export (roadmap or dashboard). Responsive multi-column grid. */
function SquadExportPicker({ base, title, htmlLabel, pptxLabel, sinceDays, year, lang, onClose, onPreview }: {
  base: "roadmap" | "dashboard"; title: string; htmlLabel: string; pptxLabel: string;
  sinceDays: number; year?: number; lang: string; onClose: () => void;
  onPreview: (url: string, title: string) => void;
}) {
  const { t } = useI18n();
  const [squads, setSquads] = useState<Squad[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [jpgBusy, setJpgBusy] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<Squad[]>("/api/squads").catch(() => [] as Squad[]),
      api.get<Tribe[]>("/api/tribes").catch(() => [] as Tribe[]),
    ]).then(([sq, tr]) => {
      setSquads(sq);
      setTribes(tr);
      setSel(new Set(sq.map((s) => s.id)));  // default: everything selected
    });
  }, []);

  const tribeName = (id: number) => tribes.find((tr) => tr.id === id)?.name ?? "-";
  // Group squads by tribe, tribes ordered by display_order then name.
  const groups = Array.from(new Set(squads.map((s) => s.tribe_id)))
    .map((tid) => ({ tid, name: tribeName(tid), squads: squads.filter((s) => s.tribe_id === tid) }))
    .sort((a, b) => a.name.localeCompare(b.name));

  const toggle = (id: number) => setSel((prev) => {
    const n = new Set(prev);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });
  const setMany = (ids: number[], on: boolean) => setSel((prev) => {
    const n = new Set(prev);
    ids.forEach((id) => (on ? n.add(id) : n.delete(id)));
    return n;
  });
  const allOn = squads.length > 0 && sel.size === squads.length;

  const selIds = Array.from(sel);
  const url = (fmt: "html" | "pptx") =>
    `/api/reports/${base}.${fmt}?since_days=${sinceDays}&lang=${lang}${year ? `&year=${year}` : ""}` +
    selIds.map((id) => `&squad_ids=${id}`).join("");

  return (
    <Modal
      width={820}
      title={title}
      onClose={onClose}
      footer={
        <div className="between" style={{ width: "100%", alignItems: "center" }}>
          <span className="small muted">{t("export.roadmap_selected", { n: sel.size, total: squads.length })}</span>
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-secondary" onClick={onClose}>{t("action.close")}</button>
            <button className={`btn btn-secondary${selIds.length ? "" : " disabled"}`}
               disabled={!selIds.length}
               onClick={() => { if (!selIds.length) return; onPreview(url("html"), title); onClose(); }}>{htmlLabel}</button>
            <button className="btn btn-secondary" disabled={!selIds.length || jpgBusy}
                    onClick={async () => { if (!selIds.length) return; setJpgBusy(true); try { await renderHtmlToJpg(url("html"), `${base}.jpg`); onClose(); } finally { setJpgBusy(false); } }}>
              {jpgBusy ? "…" : t("export.jpg")}
            </button>
            <a className={`btn${selIds.length ? "" : " disabled"}`}
               href={selIds.length ? url("pptx") : undefined} download
               aria-disabled={!selIds.length} onClick={() => selIds.length && onClose()}>{pptxLabel}</a>
          </div>
        </div>
      }
    >
      <div className="between" style={{ marginBottom: 12 }}>
        <div className="small muted">{t("export.roadmap_pick")}</div>
        <button className="btn-ghost btn-sm" onClick={() => setMany(squads.map((s) => s.id), !allOn)}>
          {allOn ? t("export.none") : t("export.all")}
        </button>
      </div>
      <div className="stack" style={{ gap: 16 }}>
        {groups.map((g) => {
          const ids = g.squads.map((s) => s.id);
          const groupOn = ids.every((id) => sel.has(id));
          return (
            <div key={g.tid}>
              <label className="inline" style={{ gap: 8, marginBottom: 8, cursor: "pointer" }}>
                <input type="checkbox" checked={groupOn} onChange={(e) => setMany(ids, e.target.checked)} />
                <span className="strong">{g.name}</span>
                <span className="small muted">({g.squads.length})</span>
              </label>
              <div className="rm-pick-grid">
                {g.squads.map((s) => {
                  const on = sel.has(s.id);
                  return (
                    <label key={s.id} className={`rm-pick-chip${on ? " on" : ""}`} onClick={(e) => { e.preventDefault(); toggle(s.id); }}>
                      <input type="checkbox" checked={on} readOnly />
                      <span className="rm-pick-name">{s.name}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          );
        })}
        {squads.length === 0 && <div className="small muted">{t("common.loading")}</div>}
      </div>
    </Modal>
  );
}
