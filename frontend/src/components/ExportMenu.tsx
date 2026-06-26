import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { useAuth } from "../auth";
import { Squad, Tribe } from "../types";
import { Modal } from "./ui";

/** One tidy "Export / Share" dropdown that groups every export & email action
 *  (HTML/PPTX report, roadmap with squad selection, printable view, send by mail,
 *  auto-subscribe). Items appear only when their module/SMTP allows it. */
type Props = {
  year?: number;
  squadId?: number;
  sinceDays?: number;
};

type Sub = { interval_days: number };
type View = "menu" | "emailReport" | "subscribe";
const INTERVALS = [7, 14, 30];

export default function ExportMenu({ year, squadId, sinceDays = 7 }: Props) {
  const { t, lang } = useI18n();
  const { smtp_enabled } = useConfig();
  const m = useModule();
  const { user } = useAuth();
  const reportOn = m("review", "weekly_report");
  const roadmapOn = m("squad_content", "roadmap");
  const dashboardOn = m("dashboard");

  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("menu");
  const [to, setTo] = useState(user?.email || "");
  const [sub, setSub] = useState<Sub | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
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

  useEffect(() => {
    if (open && view === "subscribe" && reportOn) {
      api.get<Sub>(`/api/reports/subscription${squadId ? `?squad_id=${squadId}` : ""}`).then(setSub).catch(() => {});
    }
  }, [open, view, squadId, reportOn]);

  const hasDownloads = reportOn || roadmapAvail || dashboardOn;
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
  async function subscribe(days: number) {
    setMsg(null);
    try {
      const out = await api.put<Sub>("/api/reports/subscription", { interval_days: days, squad_id: squadId ?? null });
      setSub(out);
      setMsg(days ? t("sub.saved_on", { n: days }) : t("sub.saved_off"));
    } catch (e) { setMsg(e instanceof ApiError ? e.message : "Erreur"); }
  }

  const Item = ({ children, onClick, href, download }: any) =>
    href ? (
      <a className="menu-item" href={href} target={download ? undefined : "_blank"} rel="noreferrer" onClick={() => setOpen(false)}>{children}</a>
    ) : (
      <button className="menu-item" onClick={onClick}>{children}</button>
    );

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button className="btn btn-secondary btn-sm" onClick={() => { setOpen((o) => !o); setView("menu"); setMsg(null); }}>
        {t("export.menu")} ▾
      </button>
      {open && (
        <div className="card menu-pop" style={{ position: "absolute", right: 0, top: 38, zIndex: 60, width: 268, padding: 8 }}>
          {view === "menu" && (
            <>
              {hasDownloads && <div className="menu-label">{t("export.group_download")}</div>}
              {dashboardOn && squadId && <Item href={`/api/reports/dashboard.html?${rqs}`}>{t("export.dashboard_html")}</Item>}
              {dashboardOn && squadId && <Item href={`/api/reports/dashboard.pptx?${rqs}`} download>{t("export.dashboard_pptx")}</Item>}
              {dashboardOn && !squadId && <Item onClick={() => { setDashModal(true); setOpen(false); }}>{t("export.dashboard")} …</Item>}
              {reportOn && <Item href={`/api/reports/weekly.html?${rqs}`}>{t("export.report_html")}</Item>}
              {reportOn && <Item href={`/api/reports/weekly.pptx?${rqs}`} download>{t("export.report_pptx")}</Item>}
              {roadmapAvail && squadId && <Item href={`${roadmapBase}.html?${roadmapQs}`}>{t("export.roadmap_html")}</Item>}
              {roadmapAvail && squadId && <Item href={`${roadmapBase}.pptx?${roadmapQs}`} download>{t("export.roadmap_pptx")}</Item>}
              {roadmapAvail && !squadId && <Item onClick={() => { setRoadmapModal(true); setOpen(false); }}>{t("export.roadmap")} …</Item>}

              {hasEmail && <div className="menu-label" style={{ marginTop: 6 }}>{t("export.group_email")}</div>}
              {smtp_enabled && reportOn && <Item onClick={() => { setView("emailReport"); setMsg(null); }}>{t("export.send_report")} …</Item>}
              {reportOn && smtp_enabled && <Item onClick={() => { setView("subscribe"); setMsg(null); }}>{t("export.auto") } …</Item>}
            </>
          )}

          {view === "emailReport" && (
            <div className="stack" style={{ gap: 8, padding: 6 }}>
              <button className="btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => setView("menu")}>← {t("action.cancel")}</button>
              <label className="small">{t("export.to")}</label>
              <input value={to} onChange={(e) => setTo(e.target.value)} />
              <button className="btn-sm" disabled={busy || !to.trim()} onClick={sendReport}>{t("export.send")}</button>
            </div>
          )}

          {view === "subscribe" && (
            <div className="stack" style={{ gap: 6, padding: 6 }}>
              <button className="btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => setView("menu")}>← {t("action.cancel")}</button>
              <div className="small muted">{t("sub.intro")}</div>
              {INTERVALS.map((d) => (
                <button key={d} className={sub?.interval_days === d ? "btn-sm" : "btn-secondary btn-sm"} onClick={() => subscribe(d)}>
                  {t(`sub.every.${d}`)}{sub?.interval_days === d ? " ✓" : ""}
                </button>
              ))}
              {(sub?.interval_days ?? 0) > 0 && <button className="btn-ghost btn-sm" onClick={() => subscribe(0)}>{t("sub.unsubscribe")}</button>}
            </div>
          )}

          {msg && <div className="small muted" style={{ padding: "6px 8px 2px" }}>{msg}</div>}
        </div>
      )}
      {roadmapModal && (
        <SquadExportPicker base="roadmap" title={t("export.roadmap_modal_title")}
          htmlLabel={t("export.roadmap_html")} pptxLabel={t("export.roadmap_pptx")}
          sinceDays={sinceDays} year={year} lang={lang} onClose={() => setRoadmapModal(false)} />
      )}
      {dashModal && (
        <SquadExportPicker base="dashboard" title={t("export.dashboard_modal_title")}
          htmlLabel={t("export.dashboard_html")} pptxLabel={t("export.dashboard_pptx")}
          sinceDays={sinceDays} year={year} lang={lang} onClose={() => setDashModal(false)} />
      )}
    </div>
  );
}

/** Wide, easy-to-use modal to pick which squads (grouped by tribe) appear in a
 *  global export (roadmap or dashboard). Responsive multi-column grid. */
function SquadExportPicker({ base, title, htmlLabel, pptxLabel, sinceDays, year, lang, onClose }: {
  base: "roadmap" | "dashboard"; title: string; htmlLabel: string; pptxLabel: string;
  sinceDays: number; year?: number; lang: string; onClose: () => void;
}) {
  const { t } = useI18n();
  const [squads, setSquads] = useState<Squad[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [sel, setSel] = useState<Set<number>>(new Set());

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
            <a className={`btn btn-secondary${selIds.length ? "" : " disabled"}`}
               href={selIds.length ? url("html") : undefined} target="_blank" rel="noreferrer"
               aria-disabled={!selIds.length} onClick={() => selIds.length && onClose()}>{htmlLabel}</a>
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
