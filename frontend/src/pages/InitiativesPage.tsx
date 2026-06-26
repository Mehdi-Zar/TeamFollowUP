import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { Initiative, Squad, Tribe } from "../types";
import { Spinner, ErrorBanner, EmptyState, Modal } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";

const CUR_YEAR = new Date().getFullYear();
const fmtDate = (d?: string | null) => (d ? d.slice(0, 10) : "-");

/** Global flat list of initiatives (initiative / owner / squad / deadline), set by
 *  the tribe leader and visible to everyone. Each one surfaces in its squad's report. */
export default function InitiativesPage() {
  const { t } = useI18n();
  const { effectiveRole, user } = useAuth();
  const isAdmin = effectiveRole === "admin";
  const canEdit = isAdmin || effectiveRole === "tribe_leader";
  const navigate = useNavigate();

  const [year, setYear] = useState<number>(CUR_YEAR);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeId, setTribeId] = useState<string>("");
  const [items, setItems] = useState<Initiative[] | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Partial<Initiative> | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [reload, setReload] = useState(0);

  const tribeForNew = isAdmin ? (tribeId ? Number(tribeId) : tribes[0]?.id) : user?.tribe_id;
  const qs = `?year=${year}${isAdmin && tribeId ? `&tribe_id=${tribeId}` : ""}`;

  useEffect(() => { if (isAdmin) api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {}); }, [isAdmin]);
  useEffect(() => {
    setItems(null); setError(null);
    api.get<Initiative[]>(`/api/initiatives${qs}`).then(setItems).catch((e) => setError(e.message));
    api.get<Squad[]>(`/api/squads${isAdmin && tribeId ? `?tribe_id=${tribeId}` : ""}`).then(setSquads).catch(() => {});
  }, [year, tribeId, isAdmin, reload]);

  const refresh = () => setReload((n) => n + 1);

  useSetPageChrome({
    title: t("nav.dashboard"),
    tabs: [{ key: "overview", label: t("dash.tab_overview") }, { key: "initiatives", label: t("nav.initiatives") }],
    activeTab: "initiatives",
    onTab: (k) => { if (k === "overview") navigate("/"); },
    actions: (
      <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
        <div className="seg">
          {[CUR_YEAR - 1, CUR_YEAR, CUR_YEAR + 1].map((y) => (
            <button key={y} className={y === year ? "active" : ""} onClick={() => setYear(y)}>{y}</button>
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
  }, [isAdmin, tribes, tribeId, year, t, tribeForNew, canEdit]);

  if (error) return <ErrorBanner message={error} />;
  if (!items) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="small muted">{t("init.subtitle", { year })}</div>
      {items.length === 0 ? (
        <EmptyState message={t("init.empty")} />
      ) : (
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
              {items.map((i) => (
                <tr key={i.id}>
                  <td><strong>{i.title}</strong></td>
                  <td>{i.owner || "-"}</td>
                  <td>{i.squad_name || "-"}</td>
                  <td>{fmtDate(i.deadline)}</td>
                  {canEdit && (
                    <td>
                      <div className="inline" style={{ gap: 4 }}>
                        <button className="btn-ghost btn-sm" onClick={() => setEditing(i)}>{t("action.edit")}</button>
                        <button className="btn-ghost btn-sm" onClick={async () => { if (confirm(t("init.confirm_del"))) { await api.del(`/api/initiatives/${i.id}`); refresh(); } }}>✕</button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <InitiativeEditor init={editing} squads={squads} tribeId={Number(tribeForNew)}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} t={t} />
      )}
      {exportOpen && <ExportModal qs={qs} onClose={() => setExportOpen(false)} t={t} />}
    </div>
  );
}

function InitiativeEditor({ init, squads, tribeId, onClose, onSaved, t }: any) {
  const [f, setF] = useState<Partial<Initiative>>(init);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));

  async function save() {
    if (!f.title?.trim()) return;
    const body = {
      tribe_id: f.tribe_id ?? tribeId, year: f.year,
      title: f.title, squad_id: f.squad_id ?? null,
      owner: f.owner?.trim() || null,
      deadline: f.deadline ? `${String(f.deadline).slice(0, 10)}T00:00:00Z` : null,
    };
    if (f.id) await api.put(`/api/initiatives/${f.id}`, body);
    else await api.post("/api/initiatives", body);
    onSaved();
  }

  return (
    <Modal width={620} title={f.id ? t("init.edit") : t("init.new")} onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
        <button onClick={save} disabled={!f.title?.trim()}>{t("action.save")}</button></>}>
      <div className="stack" style={{ gap: 14 }}>
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

function ExportModal({ qs, onClose, t }: { qs: string; onClose: () => void; t: any }) {
  return (
    <Modal width={460} title={t("init.export_title")} onClose={onClose}
      footer={
        <div className="inline" style={{ gap: 8 }}>
          <button className="btn-secondary" onClick={onClose}>{t("action.close")}</button>
          <a className="btn btn-secondary" href={`/api/initiatives/report.html${qs}`} target="_blank" rel="noreferrer" onClick={onClose}>HTML</a>
          <a className="btn" href={`/api/initiatives/report.pptx${qs}`} download onClick={onClose}>PPTX</a>
        </div>
      }>
      <div className="small muted">{t("init.export_hint")}</div>
    </Modal>
  );
}
