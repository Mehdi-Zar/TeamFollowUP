// InitiativesPage - the "Initiatives" tab of the dashboard.
// Shows a flat, year-scoped list of initiatives (the top of the reporting chain).
// Everyone can read it; tribe leaders manage their own tribe's initiatives and
// admins can manage any tribe (and filter by tribe). Includes HTML/PPTX export.
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { useConfig, useModule } from "../config";
import { Initiative, Squad, Tribe } from "../types";
import { Spinner, ErrorBanner, EmptyState, Modal } from "../components/ui";
import { HtmlPreviewButton } from "../components/HtmlPreview";
import { useSetPageChrome } from "../components/pageChrome";
import { ListControls, ListSearch, SortSpec, applyListView, useListView } from "../components/listView";

/** Trim an ISO datetime to its YYYY-MM-DD date part, or show a dash when absent. */

/**
 * Global flat list of initiatives (initiative / owner / squad / deadline), set by
 * the tribe leader and visible to everyone. Each one surfaces in its squad's report.
 *
 * Business logic:
 * - `canEdit` = admin or tribe_leader; only they see create/edit/delete controls.
 * - Admins can pick any tribe via the tribe selector (`tribeId`); tribe leaders are
 *   implicitly scoped to their own `user.tribe_id`. `tribeForNew` resolves which
 *   tribe a newly created initiative belongs to.
 * - `qs` builds the shared query string (year, and tribe filter for admins) reused
 *   by both the list fetch and the export URLs.
 * - Data reloads whenever year/tribe/role changes or after a mutation (`reload`).
 *
 * Access: read = everyone; write = admin / tribe_leader (backend enforces scope).
 */
export default function InitiativesPage() {
  const { t, lang, formatDate: fmtDate } = useI18n();
  const [delError, setDelError] = useState<string | null>(null);
  const { effectiveRole, user } = useAuth();
  const isAdmin = effectiveRole === "admin";
  const canEdit = isAdmin || effectiveRole === "tribe_leader";
  const navigate = useNavigate();
  // Mirror the Dashboard's Steerco tab here so it doesn't vanish when you switch to
  // Initiatives; selecting it returns to the dashboard with that sub-view active.
  const steercoTabOn = useModule()("steerco");  // the whole tribe reads the platforms' Steerco

  // The instance's default year (Administration), not the browser's clock.
  const { default_year } = useConfig();
  // A link may name the year (?year=, from a squad page): it wins over the default.
  const askedYear = Number(new URLSearchParams(window.location.search).get("year")) || null;
  const [year, setYear] = useState<number>(askedYear ?? default_year);
  const [yearTouched, setYearTouched] = useState(askedYear !== null);
  useEffect(() => { if (!yearTouched) setYear(default_year); }, [default_year]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeId, setTribeId] = useState<string>("");
  const [items, setItems] = useState<Initiative[] | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Partial<Initiative> | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [reload, setReload] = useState(0);
  // La table par defaut: une initiative se lit en colonnes (owner, squad, echeance).
  const view = useListView("init", "title", true);

  const tribeForNew = isAdmin ? (tribeId ? Number(tribeId) : tribes[0]?.id) : user?.tribe_id;
  const qs = `?year=${year}${isAdmin && tribeId ? `&tribe_id=${tribeId}` : ""}&lang=${lang}`;

  // Only admins get the tribe picker, so only they need the full tribe list.
  useEffect(() => { if (isAdmin) api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {}); }, [isAdmin]);
  // (Re)load initiatives + the squads used by the editor's squad dropdown.
  useEffect(() => {
    setItems(null); setError(null);
    api.get<Initiative[]>(`/api/initiatives${qs}`).then(setItems).catch((e) => setError(e.message));
    api.get<Squad[]>(`/api/squads${isAdmin && tribeId ? `?tribe_id=${tribeId}` : ""}`).then(setSquads).catch(() => {});
  }, [year, tribeId, isAdmin, reload]);

  // Bump the counter to trigger the effect above after a create/edit/delete.
  const refresh = () => setReload((n) => n + 1);

  useSetPageChrome({
    title: t("nav.dashboard"),
    tabs: [
      { key: "overview", label: t("dash.tab_overview") },
      ...(steercoTabOn ? [{ key: "steerco", label: t("steerco.tab") }] : []),
      { key: "initiatives", label: t("nav.initiatives") },
    ],
    activeTab: "initiatives",
    onTab: (k) => {
      if (k === "overview") navigate(`/?year=${year}`);
      else if (k === "steerco") navigate(`/?tab=steerco&year=${year}`);
    },
    actions: (
      <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
        <div className="seg">
          {[year - 1, year, year + 1].map((y) => (
            <button key={y} className={y === year ? "active" : ""} aria-pressed={y === year} onClick={() => { setYearTouched(true); setYear(y); }}>{y}</button>
          ))}
        </div>
        {isAdmin && (
          <select className="w-auto" value={tribeId} onChange={(e) => setTribeId(e.target.value)}>
            <option value="">{t("roadmap.all_tribes")}</option>
            {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
          </select>
        )}
        <button className="btn-secondary btn-sm" onClick={() => setExportOpen(true)}>{t("init.export")}</button>
        {canEdit && tribeForNew && (
          <button className="btn-secondary btn-sm" onClick={() => setEditing({ tribe_id: tribeForNew, year, title: "", squad_id: null, owner: "", deadline: null })}>+ {t("init.new")}</button>
        )}
      </div>
    ),
  }, [isAdmin, tribes, tribeId, year, t, tribeForNew, canEdit, steercoTabOn]);

  // Une initiative sans echeance n'est pas « en retard », elle est sans date: elle
  // passe apres celles qui en ont une, dans les deux sens du tri.
  const sorts: SortSpec<Initiative>[] = useMemo(() => [
    { key: "title", label: t("init.sort_title"), cmp: (a, b) => a.title.localeCompare(b.title) },
    { key: "owner", label: t("init.sort_owner"),
      cmp: (a, b) => (a.owner || "\uffff").localeCompare(b.owner || "\uffff") },
    { key: "squad", label: t("init.sort_squad"),
      cmp: (a, b) => (a.squad_name || "\uffff").localeCompare(b.squad_name || "\uffff") },
    { key: "deadline", label: t("init.sort_deadline"),
      cmp: (a, b) => (a.deadline || "\uffff").localeCompare(b.deadline || "\uffff") },
  ], [t]);

  const rows = useMemo(
    () => applyListView(items ?? [], view, sorts,
                        (i, q) => i.title.toLowerCase().includes(q)
                               || (i.owner || "").toLowerCase().includes(q)
                               || (i.squad_name || "").toLowerCase().includes(q)),
    [items, view.query, view.sort, view.desc, sorts]);

  if (error) return <ErrorBanner message={error} />;
  if (!items) return <Spinner />;

  const remove = async (i: Initiative) => {
    if (!confirm(t("init.confirm_del"))) return;
    setDelError(null);
    try { await api.del(`/api/initiatives/${i.id}`); refresh(); }
    catch (e) { setDelError(e instanceof Error && e.message ? e.message : t("common.error")); }
  };

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="small muted">{t("init.subtitle", { year })}</div>
      {delError && <ErrorBanner message={delError} />}
      {items.length === 0 ? (
        <EmptyState message={t("init.empty")} />
      ) : (
        <>
          <div className="card" style={{ padding: 14 }}>
            <div className="row" style={{ gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
              <ListSearch view={view} id="init-search" />
            </div>
          </div>

          <ListControls view={view} sorts={sorts} />

          {rows.length === 0 ? (
            <EmptyState message={t("list.no_match")} />
          ) : view.dense ? (
            <div className="card" style={{ padding: 8, overflowX: "auto" }}>
              <table className="init-tbl">
                <thead>
                  <tr>
                    <th>{t("init.h_initiative")}</th>
                    <th>{t("init.h_owner")}</th>
                    <th>{t("init.h_squad")}</th>
                    <th>{t("init.h_deadline")}</th>
                    {canEdit && <th style={{ width: 90 }} />}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((i) => (
                    <tr key={i.id}>
                      <td><strong>{i.title}</strong></td>
                      <td>{i.owner || "-"}</td>
                      <td>{i.squad_name || "-"}</td>
                      <td>{fmtDate(i.deadline)}</td>
                      {canEdit && (
                        <td>
                          <div className="inline" style={{ gap: 4 }}>
                            <button className="btn-ghost btn-sm" onClick={() => setEditing(i)}>{t("action.edit")}</button>
                            <button className="btn-ghost btn-sm" aria-label={`${t("action.delete")} ${i.title}`} onClick={() => remove(i)}>✕</button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="squad-grid-2">
              {rows.map((i) => (
                <div key={i.id} className="card stack" style={{ gap: 8 }}>
                  <div className="strong" style={{ fontSize: 16, color: "var(--navy)" }}>{i.title}</div>
                  <div className="small muted">
                    {t("init.h_owner")}{t("common.colon")}{i.owner || "-"}, {t("init.h_squad")}{t("common.colon")}{i.squad_name || "-"}
                  </div>
                  <div className="small muted">{t("init.h_deadline")}{t("common.colon")}{fmtDate(i.deadline)}</div>
                  {canEdit && (
                    <div className="inline" style={{ gap: 6 }}>
                      <button className="btn-secondary btn-sm" onClick={() => setEditing(i)}>{t("action.edit")}</button>
                      <button className="btn-danger btn-sm" onClick={() => remove(i)}>{t("action.delete")}</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {editing && (
        <InitiativeEditor init={editing} squads={squads} tribeId={Number(tribeForNew)}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} t={t} />
      )}
      {exportOpen && <ExportModal qs={qs} onClose={() => setExportOpen(false)} t={t} />}
    </div>
  );
}

/**
 * Modal to create or edit a single initiative (title, squad, deadline, owner).
 * Reused for both cases: an existing `id` on the form means PUT (edit), otherwise
 * POST (create). Only rendered for users with edit rights by the parent page.
 *
 * @param init     initial/partial initiative (blank template when creating)
 * @param squads   squads offered in the "squad" dropdown (optional link)
 * @param tribeId  fallback tribe id applied when the form has none
 * @param onSaved  called after a successful save so the parent can refresh
 */
function InitiativeEditor({ init, squads, tribeId, onClose, onSaved, t }: any) {
  const [f, setF] = useState<Partial<Initiative>>(init);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  // Moving an initiative to another squad detaches the milestones it had in the
  // old one (they belong to that squad): say so before saving, not after.
  const leaving = f.id && init.squad_id != null && (f.squad_id ?? null) !== init.squad_id
    ? (squads.find((s: Squad) => s.id === init.squad_id)?.name ?? "") : null;

  async function save() {
    // Title is the only required field; abort silently on empty.
    if (!f.title?.trim()) return;
    setErr(null);
    const body = {
      tribe_id: f.tribe_id ?? tribeId, year: f.year,
      title: f.title, squad_id: f.squad_id ?? null,
      owner: f.owner?.trim() || null,
      // Normalize the date-only input into a UTC datetime the API expects.
      deadline: f.deadline ? `${String(f.deadline).slice(0, 10)}T00:00:00Z` : null,
    };
    try {
      if (f.id) await api.put(`/api/initiatives/${f.id}`, body);
      else await api.post("/api/initiatives", body);
      onSaved();
    } catch (e) { setErr(e instanceof Error && e.message ? e.message : t("common.error")); }
  }

  return (
    <Modal width={620} title={f.id ? t("init.edit") : t("init.new")} onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
        <button onClick={save} disabled={!f.title?.trim()}>{t("action.save")}</button></>}>
      <div className="stack" style={{ gap: 14 }}>
        {err && <ErrorBanner message={err} />}
        <div className="stack" style={{ gap: 4 }}>
          <label className="field-label">{t("init.title")} *</label>
          <input value={f.title ?? ""} placeholder={t("init.title_ph")} style={{ fontSize: 15 }} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div className="row">
          <div className="col stack" style={{ gap: 4 }}>
            <label className="field-label">{t("init.h_squad")}</label>
            <select value={f.squad_id ?? ""} onChange={(e) => set("squad_id", e.target.value ? Number(e.target.value) : null)}>
              <option value="">{t("init.no_squad")}</option>
              {squads.map((s: Squad) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {leaving !== null && <div className="small" style={{ color: "var(--orange)" }}>{t("init.move_warning", { squad: leaving })}</div>}
          </div>
          <div className="col stack" style={{ gap: 4 }}>
            <label className="field-label">{t("init.h_deadline")}</label>
            <input type="date" value={f.deadline ? String(f.deadline).slice(0, 10) : ""} onChange={(e) => set("deadline", e.target.value)} />
          </div>
        </div>
        <div className="stack" style={{ gap: 4 }}>
          <label className="field-label">{t("init.h_owner")}</label>
          <input value={f.owner ?? ""} placeholder={t("init.owner_ph")} onChange={(e) => set("owner", e.target.value)} />
        </div>
      </div>
    </Modal>
  );
}

/**
 * Export dialog offering the current (year/tribe-filtered) initiative list as an
 * HTML preview or a downloadable PPTX. `qs` is the same query string the page
 * uses for its data fetch, so exports match exactly what is on screen.
 */
function ExportModal({ qs, onClose, t }: { qs: string; onClose: () => void; t: any }) {
  return (
    <Modal width={460} title={t("init.export_title")} onClose={onClose}
      footer={
        <div className="inline" style={{ gap: 8 }}>
          <button className="btn-secondary" onClick={onClose}>{t("action.close")}</button>
          <HtmlPreviewButton url={`/api/initiatives/report.html${qs}`} title={t("init.export_title")} label="HTML" className="btn btn-secondary" />
          <a className="btn" href={`/api/initiatives/report.pptx${qs}`} download onClick={onClose}>PPTX</a>
        </div>
      }>
      <div className="small muted">{t("init.export_hint")}</div>
    </Modal>
  );
}
