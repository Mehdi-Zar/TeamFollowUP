import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { CandidateJalon, OtdReport, SquadDetail } from "../types";
import { Modal, PickItem } from "./ui";

const fmtDate = (d?: string | null) => (d ? d.slice(0, 10) : "-");
const STATUS_CLASS: Record<string, string> = {
  on_track: "badge-green", delivered: "badge-navy", at_risk: "badge-orange", late: "badge-red",
};

/** OTD (On-Time Delivery) inside the squad's management, not a separate menu.
 *  The tribe leader (or admin) sets a dated delivery commitment on this squad's
 *  leader and attaches this squad's milestones; the squad leader reads it. Adding
 *  or editing an OTD opens ONE detail popup carrying every field (name, committed
 *  date, description, and the covered milestones). */
export function OtdPanel({ squad, canManage, onChange }:
  { squad: SquadDetail; canManage: boolean; onChange?: () => void }) {
  const { t } = useI18n();
  const [items, setItems] = useState<OtdReport[] | null>(null);
  const [editing, setEditing] = useState<Partial<OtdReport> | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api.get<OtdReport[]>(`/api/otds?year=${squad.year}`)
      .then((all) => setItems(all.filter((o) =>
        o.owner_user_id === squad.leader_user_id || o.jalons.some((j) => j.squad_id === squad.id))))
      .catch(() => setItems([]));
  }, [squad.id, squad.year, squad.leader_user_id, reload]);

  const refresh = () => { setReload((n) => n + 1); onChange?.(); };

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between" style={{ alignItems: "center" }}>
        <span className="strong">{t("otd.title")}</span>
        {canManage && (
          <button className="btn-secondary btn-sm"
            onClick={() => setEditing({ tribe_id: squad.tribe_id, year: squad.year, title: "",
              owner_user_id: squad.leader_user_id ?? null })}>+ {t("otd.new")}</button>
        )}
      </div>
      <div className="small muted">{canManage ? t("otd.panel_hint_manage") : t("otd.panel_hint_read")}</div>

      {items === null ? (
        <div className="small muted">{t("common.loading")}</div>
      ) : items.length === 0 ? (
        <div className="small muted">{t("otd.panel_empty")}</div>
      ) : (
        items.map((o) => (
          <div key={o.id} className="card stack" style={{ gap: 8, padding: 10 }}>
            <div className="between" style={{ alignItems: "flex-start" }}>
              <button className="otd-open" onClick={() => canManage && setEditing(o)}
                style={{ background: "none", border: 0, padding: 0, cursor: canManage ? "pointer" : "default", textAlign: "left" }}>
                <span className="inline" style={{ gap: 8, alignItems: "center" }}>
                  <span className="strong">{o.title}</span>
                  <span className={`badge ${STATUS_CLASS[o.status] ?? "badge-grey"}`}>{t(`otd.status.${o.status}`)}</span>
                </span>
              </button>
              {canManage && (
                <div className="inline" style={{ gap: 4 }}>
                  <button className="btn-ghost btn-sm" onClick={() => setEditing(o)}>{t("action.edit")}</button>
                  <button className="btn-ghost btn-sm" onClick={async () => {
                    if (confirm(t("otd.confirm_del"))) { await api.del(`/api/otds/${o.id}`); refresh(); }
                  }}>✕</button>
                </div>
              )}
            </div>
            <div className="small muted">
              {t("otd.committed")}: {fmtDate(o.committed_date)}
              {" · "}{t("otd.counts", { total: o.counts.total, done: o.counts.done, blocked: o.counts.blocked, at_risk: o.counts.at_risk })}
            </div>
            {o.jalons.length > 0 && (
              <div className="stack" style={{ gap: 2 }}>
                {o.jalons.map((j) => (
                  <div key={j.id} className="small" style={{ display: "flex", gap: 8 }}>
                    <span className="muted">Q{j.quarter}</span>
                    <span style={{ flex: 1 }}>{j.title}</span>
                    <span className="muted">{t(`otd.jstatus.${j.status}`)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))
      )}

      {editing && (
        <OtdDetailModal otd={editing} squad={squad}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} t={t} />
      )}
    </div>
  );
}

/** One popup with the full OTD detail: assigned leader, name, committed date,
 *  description, and the covered milestones (this squad's jalons). Create and edit
 *  both go through here; on save it writes the OTD and its milestone set together. */
function OtdDetailModal({ otd, squad, onClose, onSaved, t }: any) {
  const [f, setF] = useState<Partial<OtdReport>>(otd);
  const [cands, setCands] = useState<CandidateJalon[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));

  // This squad's milestones, with those already in THIS OTD pre-checked.
  useEffect(() => {
    api.get<CandidateJalon[]>(`/api/otds/candidate-jalons?year=${squad.year}&tribe_id=${squad.tribe_id}`)
      .then((rows) => {
        const own = rows.filter((r) => r.squad_id === squad.id);
        setCands(own);
        if (otd.id) setSel(new Set(own.filter((r) => r.otd_id === otd.id).map((r) => r.id)));
      })
      .catch(() => setCands([]));
  }, [otd.id, squad.id, squad.tribe_id, squad.year]);

  const toggle = (id: number) => setSel((prev) => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  async function save() {
    if (!f.title?.trim() || busy) return;
    setBusy(true);
    try {
      const body: any = {
        title: f.title.trim(),
        description: f.description?.trim() || null,
        committed_date: f.committed_date ? `${String(f.committed_date).slice(0, 10)}T00:00:00Z` : null,
        owner_user_id: squad.leader_user_id ?? null,
      };
      let id = f.id;
      if (id) await api.put(`/api/otds/${id}`, body);
      else id = (await api.post<any>("/api/otds", { ...body, tribe_id: squad.tribe_id, year: squad.year })).id;
      await api.put(`/api/otds/${id}/jalons`, { jalon_ids: Array.from(sel) });
      onSaved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal width={640} title={f.id ? t("otd.edit") : t("otd.new")} onClose={onClose}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
        <button onClick={save} disabled={!f.title?.trim() || busy}>{busy ? "…" : t("action.save")}</button>
      </>}>
      <div className="stack" style={{ gap: 16 }}>
        <div className="banner small">{t("otd.detail_intro")}</div>

        <div className="small muted">
          {t("otd.owner")}: <span className="strong">{squad.leader?.display_name ?? "-"}</span>
        </div>

        <div className="stack" style={{ gap: 4 }}>
          <label className="field-label">{t("otd.title_field")} *</label>
          <input value={f.title ?? ""} placeholder={t("otd.title_ph")} style={{ fontSize: 15 }}
                 onChange={(e) => set("title", e.target.value)} />
        </div>

        <div className="stack" style={{ gap: 4 }}>
          <label className="field-label">{t("otd.committed")} *</label>
          <input type="date" value={f.committed_date ? String(f.committed_date).slice(0, 10) : ""}
                 onChange={(e) => set("committed_date", e.target.value)} />
          <span className="small muted">{t("otd.committed_hint")}</span>
        </div>

        <div className="stack" style={{ gap: 4 }}>
          <label className="field-label">{t("otd.description")}</label>
          <textarea rows={2} value={f.description ?? ""} onChange={(e) => set("description", e.target.value)} />
        </div>

        <div className="stack" style={{ gap: 6 }}>
          <label className="field-label">{t("otd.jalons_section")}</label>
          {cands === null ? (
            <div className="small muted">{t("common.loading")}</div>
          ) : cands.length === 0 ? (
            <div className="small muted">{t("otd.pick_empty")}</div>
          ) : (
            <div className="pick-list" style={{ maxHeight: 260, overflowY: "auto" }}>
              {cands.map((r) => {
                const takenElsewhere = r.otd_id != null && r.otd_id !== otd.id;
                return (
                  <PickItem key={r.id} selected={sel.has(r.id)} disabled={takenElsewhere}
                    onToggle={() => toggle(r.id)}
                    title={r.title} meta={`Q${r.quarter}`}
                    tag={takenElsewhere ? t("otd.taken") : undefined} />
                );
              })}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
