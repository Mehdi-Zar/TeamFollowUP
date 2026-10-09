// OtdPanel: les engagements OTD d'une squad, dans leurs deux portees.
//
// Un engagement « management » est fixe par le tribe leader (ou l'admin) sur le
// leader de la squad. Un engagement « squad » est celui que le squad leader prend
// lui-meme: il le cree, le date et y rattache ses jalons sans demander
// l'autorisation, parce que c'est son engagement.
//
// Les deux se lisent dans le meme tableau, distingues par une couleur et un
// libelle, comme dans les documents exportes: deux listes separees obligeraient a
// comparer deux dates en changeant de bloc, alors que la question posee est « que
// livre-t-on, et quand ».
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText } from "../api";
import { useI18n } from "../i18n";
import { CandidateJalon, OtdReport, OtdScope, SquadDetail } from "../types";
import { Collapsible, ErrorBanner, Modal, PickItem } from "./ui";
import { Sorted, SortTh } from "./tableView";

/** The colour of a status: green kept, orange to watch, red missed, grey out of play. */
const STATUS_TONE: Record<string, string> = {
  on_track: "badge-navy", at_risk: "badge-orange", late: "badge-red", delivered: "badge-green",
  delivered_late: "badge-orange", not_delivered: "badge-red", cancelled: "badge-grey", unscoped: "badge-grey",
};

/** The status of an OTD, with why in its tooltip. */
export function OtdStatusBadge({ o }: { o: OtdReport }) {
  const { t } = useI18n();
  return (
    <span className={`badge ${STATUS_TONE[o.status] ?? "badge-navy"}`}
          title={(o.reasons ?? []).map((r) => t(`otd.reason.${r}`)).join(". ")}>
      {t(`otd.status.${o.status}`)}
    </span>
  );
}

/** What there is to know about an OTD besides its status: a moved date, a
 *  carry-over, a cancellation, milestones planned after the date or moved to
 *  another year, and the part of this squad. */
function otdNotes(o: OtdReport, t: any, fmtDate: (d?: string | null) => string, squadId?: number): string[] {
  const out: string[] = [];
  if (o.cancelled_at) out.push(t("otd.note_cancelled", { reason: o.cancel_reason ?? "" }));
  if (o.declared_status) out.push(t("otd.note_declared") + (o.declared_note ? `${t("common.colon")}${o.declared_note}` : ""));
  if (o.replanned_days) {
    out.push(t("otd.note_replanned", { d: fmtDate(o.initial_committed_date),
                                       n: `${o.replanned_days > 0 ? "+" : ""}${o.replanned_days}` }));
  }
  if (o.carried_from) out.push(t("otd.note_carried_from", { year: o.carried_from.year }));
  if (o.carried_from && !o.committed_date) out.push(t("otd.note_no_date"));
  if (o.carried_to) out.push(t("otd.note_carried_to", { year: o.carried_to.year }));
  if (o.beyond_date?.length) out.push(t("otd.note_beyond", { list: o.beyond_date.join(", ") }));
  if (o.slipped?.length) out.push(t("otd.note_slipped", { list: o.slipped.map((j) => `${j.title} (${j.year})`).join(", ") }));
  const share = squadId != null && (o.by_squad?.length ?? 0) > 1 ? o.by_squad.find((s) => s.squad_id === squadId) : undefined;
  if (share) out.push(t("otd.note_share", { done: share.done, total: share.total, late: share.late }));
  return out;
}

/** The status block of the OTD window: the status, why, what to know, and the
 *  rules, one click away. */
function OtdStatusBlock({ o, squadId }: { o: OtdReport; squadId?: number }) {
  const { t, formatDate } = useI18n();
  const notes = otdNotes(o, t, formatDate, squadId);
  return (
    <div className="otd-status-block">
      <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
        <span className="field-label" style={{ margin: 0 }}>{t("otd.status_section")}</span>
        <OtdStatusBadge o={o} />
        <span className="small muted">{(o.reasons ?? []).map((r) => t(`otd.reason.${r}`)).join(". ")}</span>
      </div>
      {notes.length > 0 && (
        <ul className="otd-notes small">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
      )}
      <details className="otd-how small">
        <summary>{t("otd.how")}</summary>
        <ol>{[1, 2, 3, 4, 5, 6, 7].map((n) => <li key={n}>{t(`otd.how_${n}`)}</li>)}</ol>
      </details>
    </div>
  );
}

/** Longueur maximale d'un titre d'OTD, la meme que cote API (schemas.OTD_TITLE_MAX). */
const OTD_TITLE_MAX = 30;

/** La portee d'un engagement, avec son defaut: les lignes d'avant la distinction
 *  sont, par definition, des engagements du management. */
const scopeOf = (o: Partial<OtdReport>): OtdScope => (o.scope === "squad" ? "squad" : "management");

export function OtdPanel({ squad, canManage, canOwn, onChange, editTo, editLabel }:
  { squad: SquadDetail; canManage: boolean; canOwn?: boolean; onChange?: () => void;
    /** Where these commitments are edited, when not here (the squad page). */
    editTo?: string; editLabel?: string }) {
  const { t, formatDate: fmtDate } = useI18n();
  const [all, setAll] = useState<OtdReport[] | null>(null);
  const [editing, setEditing] = useState<Partial<OtdReport> | null>(null);
  // A commitment one cannot edit still opens, to read which milestones hold it.
  const [viewing, setViewing] = useState<OtdReport | null>(null);
  const [reload, setReload] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  // The commitment whose deletion waits for a second click.
  const [deleting, setDeleting] = useState<number | null>(null);

  useEffect(() => {
    // A failed load says so: an empty list here read as "no commitment".
    api.get<OtdReport[]>(`/api/otds?year=${squad.year}`).then(setAll)
      .catch((e) => { setAll([]); setErr(e instanceof Error && e.message ? e.message : t("common.error")); });
  }, [squad.year, reload]);

  /** Ce qui engage cette squad: ce qu'elle a pris elle-meme, et ce que le
   *  management a pose sur elle, par son leader ou par un de ses jalons. */
  const concerns = (o: OtdReport) =>
    (scopeOf(o) === "squad" && o.squad_id === squad.id) ||
    (scopeOf(o) === "management" && o.tribe_id === squad.tribe_id &&
      // Set on this squad, or carrying one of its milestones. The owner only
      // counts for an older one with neither: a leader of two squads saw every
      // commitment of one under the other (same rule as report.concerns_squad).
      (o.squad_id === squad.id || o.jalons.some((j) => j.squad_id === squad.id) ||
        (o.squad_id == null && o.jalons.length === 0 && squad.leader_user_id != null
          && o.owner_user_id === squad.leader_user_id)));

  const items = all === null ? null : all.filter(concerns);

  const refresh = () => { setReload((n) => n + 1); onChange?.(); };

  /** Qui peut ecrire cette ligne: la meme regle que le serveur, pour que l'ecran
   *  ne propose pas un bouton qui finira en 403. */
  const canWrite = (o: Partial<OtdReport>) =>
    scopeOf(o) === "squad" ? !!canOwn : canManage;

  const blank = (scope: OtdScope): Partial<OtdReport> => ({
    tribe_id: squad.tribe_id, year: squad.year, title: "", scope,
    squad_id: scope === "squad" ? squad.id : null,
    owner_user_id: squad.leader_user_id ?? null,
  });

  /** Le tableau d'une liste d'engagements. On vient ici pour comparer des dates,
   *  et des colonnes alignees se comparent. Le detail des jalons couverts est dans
   *  la fenetre de l'engagement, qui est aussi la ou on les rattache. */
  const otdTable = (list: OtdReport[]) => (
    <div style={{ overflowX: "auto" }}>
      <Sorted storageKey="otd.table" rows={list} cols={[{ key: "title", value: (o: OtdReport) => o.title }, { key: "scope", value: (o) => scopeOf(o) }, { key: "date", value: (o) => o.committed_date || "" }, { key: "status", value: (o) => o.status }, { key: "jalons", value: (o) => o.counts.total }]}>{(v) => (
      <table className="otd-tbl">
        <thead>
          <tr>
            <SortTh view={v} col="title">{t("otd.h_title")}</SortTh>
            <SortTh view={v} col="scope" style={{ width: 150 }}>{t("otd.h_scope")}</SortTh>
            <SortTh view={v} col="date" style={{ width: 140 }}>{t("otd.committed")}</SortTh>
            <SortTh view={v} col="status" style={{ width: 120 }}>{t("otd.h_status")}</SortTh>
            <SortTh view={v} col="jalons" style={{ width: 190 }}>{t("otd.h_jalons")}</SortTh>
            <th style={{ width: 110 }} />
          </tr>
        </thead>
        <tbody>
          {v.rows.map((o) => {
            const scope = scopeOf(o);
            const writable = canWrite(o);
            return (
              <tr key={o.id}>
                <td>
                  <button className="otd-open" style={{ cursor: "pointer" }}
                          onClick={() => (writable ? setEditing(o) : setViewing(o))}>
                    {/* Le filet de couleur dit la portee sans ajouter un mot a
                        lire: c'est la meme couleur que sur la frise exportee. */}
                    <span className={`otd-scope-bar otd-scope-${scope}`} aria-hidden="true" />
                    <span className="strong">{o.title}</span>
                  </button>
                </td>
                <td>
                  <span className={`badge otd-scope-badge otd-scope-${scope}`}>
                    {t(`otd.scope_${scope}`)}
                  </span>
                </td>
                <td>
                  {fmtDate(o.committed_date)}
                  {o.replanned_days !== 0 && o.replanned_days != null && (
                    <div className="small muted" title={t("otd.initial_date", { d: fmtDate(o.initial_committed_date) })}>
                      {t("otd.replanned_short", { n: `${o.replanned_days > 0 ? "+" : ""}${o.replanned_days}` })}
                    </div>
                  )}
                </td>
                <td>
                  {/* The status says whether the promise holds: its colour is
                      what the eye looks for first (the bar on the left says the
                      scope). Why is in its tooltip and in the window. */}
                  <OtdStatusBadge o={o} />
                  {o.carried_from && <div className="small muted">{t("otd.note_carried_from", { year: o.carried_from.year })}</div>}
                  {o.carried_to && <div className="small muted">{t("otd.note_carried_to", { year: o.carried_to.year })}</div>}
                </td>
                <td className="small muted">
                  {t("otd.counts", { total: o.counts.total, done: o.counts.done,
                                     blocked: o.counts.blocked, at_risk: o.counts.at_risk })}
                  {(o.by_squad?.length ?? 0) > 1 && (() => {
                    const sh = o.by_squad.find((s) => s.squad_id === squad.id);
                    return sh ? <div>{t("otd.note_share", { done: sh.done, total: sh.total, late: sh.late })}</div> : null;
                  })()}
                </td>
                <td>
                  {writable && (
                    <div className="inline" style={{ gap: 4 }}>
                      <button className="btn-ghost btn-sm" onClick={() => setEditing(o)}>{t("action.edit")}</button>
                      {deleting === o.id ? (
                        <>
                          <button className="btn-danger btn-sm" onClick={async () => {
                            setDeleting(null); setErr(null);
                            try { await api.del(`/api/otds/${o.id}`); refresh(); }
                            catch (e) { setErr(errorText(e)); }
                          }}>{t("action.delete")}</button>
                          <button className="btn-ghost btn-sm" onClick={() => setDeleting(null)}>{t("action.cancel")}</button>
                        </>
                      ) : (
                        <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => setDeleting(o.id)}>✕</button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      )}</Sorted>
    </div>
  );

  return (
    <Collapsible title={t("otd.title")} defaultOpen
                 subtitle={t("otd.collapsed_hint", { n: items?.length ?? 0 })}
                 right={!(canManage || canOwn) && editTo ? (
                   <Link to={editTo} className="btn btn-secondary btn-sm">{editLabel}</Link>
                 ) : (canManage || canOwn) ? (
                   <div className="inline" style={{ gap: 6 }}>
                     {canOwn && (
                       <button className="btn-secondary btn-sm" onClick={() => setEditing(blank("squad"))}>
                         + {canManage ? t("otd.new_squad") : t("otd.new")}
                       </button>
                     )}
                     {canManage && (
                       <button className="btn-secondary btn-sm" onClick={() => setEditing(blank("management"))}>
                         + {canOwn ? t("otd.new_management") : t("otd.new")}
                       </button>
                     )}
                   </div>
                 ) : undefined}>
      <div className="small muted" style={{ marginBottom: 10 }}>
        {canOwn && !canManage ? t("otd.panel_hint_own")
          : canManage ? t("otd.panel_hint_manage") : t("otd.panel_hint_read")}
      </div>
      {err && <ErrorBanner message={err} />}

      {items === null ? (
        <div className="small muted">{t("common.loading")}</div>
      ) : items.length === 0 ? (
        <div className="small muted">{t("otd.panel_empty")}</div>
      ) : otdTable(items)}

      {editing && (
        <OtdDetailModal otd={editing} squad={squad}
          onClose={() => { setEditing(null); refresh(); }} onSaved={() => { setEditing(null); refresh(); }} t={t} />
      )}
      {viewing && (
        <Modal width={560} title={viewing.title} onClose={() => setViewing(null)}
               footer={<button className="btn-sm" onClick={() => setViewing(null)}>{t("action.close")}</button>}>
          <div className="stack" style={{ gap: 10 }}>
            <div className="small">
              <span className={`badge otd-scope-badge otd-scope-${scopeOf(viewing)}`}>{t(`otd.scope_${scopeOf(viewing)}`)}</span>{" "}
              {t("otd.committed")}{t("common.colon")}<span className="strong">{fmtDate(viewing.committed_date)}</span>
            </div>
            <OtdStatusBlock o={viewing} squadId={squad.id} />
            {viewing.description && <div className="small">{viewing.description}</div>}
            <div className="small strong">{t("otd.jalons_section")}</div>
            {viewing.jalons.length === 0 ? <div className="small muted">{t("otd.pick_empty")}</div> : (
              <div className="stack" style={{ gap: 4 }}>
                {viewing.jalons.map((j) => (
                  <div key={j.id} className="small">
                    {j.year !== viewing.year ? `${j.year} ` : ""}Q{j.quarter}, {j.title} <span className="muted">({j.squad_name})</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Modal>
      )}
    </Collapsible>
  );
}

/** Une fenetre avec tout le detail d'un engagement: son intitule, sa date, sa
 *  description et les jalons couverts. Creation et edition passent par ici; a
 *  l'enregistrement, l'engagement et son ensemble de jalons partent ensemble.
 *
 *  La portee ne se choisit pas ici: elle vient du bouton qui a ouvert la fenetre
 *  et ne change plus ensuite, parce que changer la portee d'un engagement change
 *  qui a le droit de l'ecrire. */
function OtdDetailModal({ otd, squad, onClose, onSaved, t }: any) {
  const { formatDate: fmtDate } = useI18n();
  const [f, setF] = useState<Partial<OtdReport>>(otd);
  const [cands, setCands] = useState<CandidateJalon[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  // Cancelling asks for a reason: the OTD stays in the reports, and the reason
  // is what a reader of the document will want to know.
  const [cancelled, setCancelled] = useState<boolean>(!!otd.cancelled_at);
  const needsReason = cancelled && !(f.cancel_reason ?? "").trim();
  const day = (d?: string | null) => (d ? `${String(d).slice(0, 10)}T00:00:00Z` : null);
  // Un titre saisi avant la limite peut la depasser: il faut le raccourcir pour enregistrer.
  const tooLong = (f.title ?? "").trim().length > OTD_TITLE_MAX;
  const scope: OtdScope = scopeOf(otd);
  // Chaque portee a son propre lien vers le jalon; lire celui de l'autre ferait
  // apparaitre comme « deja pris » un jalon que cette portee peut parfaitement
  // engager, ce qui est justement ce que le double lien evite.
  const linkOf = (r: CandidateJalon) => (scope === "squad" ? r.squad_otd_id : r.otd_id);

  const [candsFailed, setCandsFailed] = useState(false);
  // Les jalons de cette squad, avec ceux deja dans CET engagement coches.
  useEffect(() => {
    // Named by squad: its milestones, whoever reports for it and from whatever tribe.
    api.get<CandidateJalon[]>(`/api/otds/candidate-jalons?year=${squad.year}&tribe_id=${squad.tribe_id}&squad_id=${squad.id}`)
      .then((rows) => {
        const own = rows.filter((r) => r.squad_id === squad.id);
        setCands(own);
        if (otd.id) setSel(new Set(own.filter((r) => linkOf(r) === otd.id).map((r) => r.id)));
        setCandsFailed(false);
      })
      .catch(() => { setCands([]); setCandsFailed(true); });
  }, [otd.id, squad.id, squad.tribe_id, squad.year]);

  const toggle = (id: number) => setSel((prev) => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  async function save() {
    if (!f.title?.trim() || tooLong || !f.committed_date || needsReason || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const body: any = {
        title: f.title.trim(),
        description: f.description?.trim() || null,
        committed_date: day(f.committed_date),
        owner_user_id: squad.leader_user_id ?? null,
        declared_status: f.declared_status || null,
        declared_on: f.declared_status ? day(f.declared_on) : null,
        declared_note: f.declared_status ? (f.declared_note?.trim() || null) : null,
      };
      let id = f.id;
      if (id) await api.put(`/api/otds/${id}`, { ...body, cancelled, cancel_reason: cancelled ? f.cancel_reason?.trim() : null });
      else {
        id = (await api.post<any>("/api/otds", {
          ...body, tribe_id: squad.tribe_id, year: squad.year,
          // Both scopes carry the squad: a management commitment set here is about
          // this squad, and shows under it rather than under its owner's squads.
          scope, squad_id: squad.id,
        })).id;
        // Created: a retry after a failed link below must update it, not create
        // a second one.
        set("id", id);
      }
      // Milestones that could not be loaded are not "none": saving an empty list
      // then detached every milestone already linked, silently.
      if (!candsFailed) await api.put(`/api/otds/${id}/jalons`, { jalon_ids: Array.from(sel) });
      onSaved();
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal width={640} title={f.id ? t("otd.edit") : t(`otd.scope_${scope}`)} onClose={onClose}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
        <button onClick={save} disabled={!f.title?.trim() || tooLong || !f.committed_date || needsReason || busy}>{busy ? t("common.saving") : t("action.save")}</button>
      </>}>
      <div className="stack" style={{ gap: 16 }}>
        {err && <ErrorBanner message={err} />}
        <div className="banner small">
          {scope === "squad" ? t("otd.detail_intro_squad") : t("otd.detail_intro")}
        </div>

        <div className="small muted">
          {t("otd.owner")}{t("common.colon")}<span className="strong">{squad.leader?.display_name ?? "-"}</span>
        </div>

        {otd.id && otd.status && <OtdStatusBlock o={otd as OtdReport} squadId={squad.id} />}

        <div className="stack" style={{ gap: 4 }}>
          <label className="field-label">{t("otd.title_field")} *</label>
          <input value={f.title ?? ""} placeholder={t("otd.title_ph")} style={{ fontSize: 15 }}
                 maxLength={OTD_TITLE_MAX} onChange={(e) => set("title", e.target.value)} />
          <div className="small muted" style={{ textAlign: "right", color: tooLong ? "var(--red)" : undefined }}>
            {(f.title ?? "").trim().length}/{OTD_TITLE_MAX}
          </div>
        </div>

        <div className="stack" style={{ gap: 4 }}>
          <label className="field-label">{t("otd.committed")} *</label>
          <input type="date" value={f.committed_date ? String(f.committed_date).slice(0, 10) : ""}
                 onChange={(e) => set("committed_date", e.target.value)} />
          <span className="small muted">
            {t("otd.committed_hint")}
            {f.initial_committed_date && String(f.initial_committed_date).slice(0, 10) !== String(f.committed_date ?? "").slice(0, 10)
              ? ` ${t("otd.initial_date", { d: fmtDate(f.initial_committed_date) })}` : ""}
          </span>
        </div>

        <div className="stack" style={{ gap: 4 }}>
          <label className="field-label">{t("otd.description")}</label>
          <textarea rows={2} value={f.description ?? ""} onChange={(e) => set("description", e.target.value)} />
        </div>

        <div className="otd-facts">
          <div className="stack" style={{ gap: 4 }}>
            <label className="field-label" htmlFor="otd-declared">{t("otd.declared_label")}</label>
            <select id="otd-declared" value={f.declared_status ?? ""}
                    onChange={(e) => set("declared_status", e.target.value || null)}>
              <option value="">{t("otd.declared_none")}</option>
              {(["delivered", "delivered_late", "not_delivered"] as const).map((s) => (
                <option key={s} value={s}>{t(`otd.status.${s}`)}</option>
              ))}
            </select>
            <span className="small muted">{t("otd.declared_hint")}</span>
          </div>
          {f.declared_status && (
            <div className="row">
              <div className="col" style={{ maxWidth: 220 }}>
                <label htmlFor="otd-declared-on">{t("otd.declared_on")}</label>
                <input id="otd-declared-on" type="date" value={f.declared_on ? String(f.declared_on).slice(0, 10) : ""}
                       onChange={(e) => set("declared_on", e.target.value || null)} />
              </div>
              <div className="col">
                <label htmlFor="otd-declared-note">{t("otd.declared_note")}</label>
                <input id="otd-declared-note" value={f.declared_note ?? ""} onChange={(e) => set("declared_note", e.target.value)} />
              </div>
            </div>
          )}
          {f.id && (
            <div className="stack" style={{ gap: 4 }}>
              <label className="inline" style={{ gap: 8, cursor: "pointer" }}>
                <input type="checkbox" checked={cancelled} onChange={(e) => setCancelled(e.target.checked)} />
                <span className="strong">{t("otd.cancel_label")}</span>
              </label>
              <span className="small muted">{t("otd.cancel_hint")}</span>
              {cancelled && (
                <>
                  <label htmlFor="otd-cancel-reason">{t("otd.cancel_reason")} *</label>
                  <textarea id="otd-cancel-reason" rows={2} value={f.cancel_reason ?? ""}
                            onChange={(e) => set("cancel_reason", e.target.value)} />
                </>
              )}
            </div>
          )}
        </div>

        <div className="stack" style={{ gap: 6 }}>
          <label className="field-label">{t("otd.jalons_section")}</label>
          {candsFailed && <div className="small" style={{ color: "var(--orange)" }}>{t("otd.jalons_load_failed")}</div>}
          {cands === null ? (
            <div className="small muted">{t("common.loading")}</div>
          ) : cands.length === 0 ? (
            <div className="small muted">{t("otd.pick_empty")}</div>
          ) : (
            <div className="pick-list" style={{ maxHeight: 260, overflowY: "auto" }}>
              {cands.map((r) => {
                const taken = linkOf(r);
                const takenElsewhere = taken != null && taken !== otd.id;
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
