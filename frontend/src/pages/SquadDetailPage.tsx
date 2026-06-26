import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useModule } from "../config";
import { Budget, DependentItem, Initiative, KeyMessageKind, Member, ProgressPoint, RoadmapItem, SnapshotMeta, SquadDetail } from "../types";
import { ProgressCurve, ProgressTimeline } from "../components/progress";
import { Dot, FreshnessBadge, ProgressBar, Spinner, ErrorBanner, Collapsible } from "../components/ui";
import { useAuth } from "../auth";
import ExportMenu from "../components/ExportMenu";
import { useSetPageChrome } from "../components/pageChrome";
import { roadmapRag, trendRag } from "../labels";

export default function SquadDetailPage() {
  const { id } = useParams();
  const squadId = Number(id);
  const { t, rag, roadmap, trend, formatDate } = useI18n();
  const [params, setParams] = useSearchParams();
  const yearParam = params.get("year");
  const [squad, setSquad] = useState<SquadDetail | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [openJalon, setOpenJalon] = useState<RoadmapItem | null>(null);
  const [progress, setProgress] = useState<ProgressPoint[]>([]);
  const [dependents, setDependents] = useState<DependentItem[]>([]);
  const [initiatives, setInitiatives] = useState<Initiative[]>([]);
  const moduleOn = useModule();
  const roadmapOn = moduleOn("squad_content", "roadmap");
  const objectivesOn = moduleOn("squad_content", "objectives");
  const kpisOn = moduleOn("squad_content", "kpis");
  const reviewOn = moduleOn("review");
  const { user, effectiveRole } = useAuth();

  // Re-fetch the squad in place (no spinner flash) after a budget / key-message edit.
  const reload = () => {
    const q = yearParam ? `?year=${yearParam}` : "";
    api.get<SquadDetail>(`/api/squads/${squadId}${q}`).then(setSquad).catch((e) => setError(e.message));
  };

  useEffect(() => {
    const q = yearParam ? `?year=${yearParam}` : "";
    setSquad(null);
    api.get<SquadDetail>(`/api/squads/${squadId}${q}`).then(setSquad).catch((e) => setError(e.message));
    api.get<SnapshotMeta[]>(`/api/squads/${squadId}/snapshots`).then(setSnapshots).catch(() => {});
  }, [squadId, yearParam]);

  useEffect(() => {
    if (!squad) return;
    api.get<ProgressPoint[]>(`/api/squads/${squadId}/progress?year=${squad.year}`).then(setProgress).catch(() => {});
    api.get<DependentItem[]>(`/api/squads/${squadId}/dependents?year=${squad.year}`).then(setDependents).catch(() => {});
    api.get<Initiative[]>(`/api/initiatives?year=${squad.year}&squad_id=${squadId}`).then(setInitiatives).catch(() => {});
  }, [squadId, squad?.year]);

  useSetPageChrome(
    squad
      ? {
          title: squad.name,
          actions: (
            <>
              <div className="seg">
                {[squad.year - 1, squad.year, squad.year + 1].map((y) => (
                  <button key={y} className={y === squad.year ? "active" : ""} onClick={() => setParams({ year: String(y) })}>{y}</button>
                ))}
              </div>
              <ExportMenu year={squad.year} squadId={squadId} />
            </>
          ),
        }
      : {},
    [squad?.name, squad?.year, squadId]
  );

  if (error) return <ErrorBanner message={error} />;
  if (!squad) return <Spinner />;

  // Annual objectives & KPIs are set by the tribe leader and visible only to the
  // squad leader (of this squad), its tribe leader, and admins.
  const role = effectiveRole ?? "member";
  const privileged =
    role === "admin" ||
    (role === "tribe_leader" && user?.tribe_id === squad.tribe_id) ||
    (role === "squad_leader" && squad.leader_user_id === user?.id);
  // Enabling/disabling budget tracking is a tribe-leader (or admin) decision.
  const canToggleBudget = role === "admin" || (role === "tribe_leader" && user?.tribe_id === squad.tribe_id);

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="between">
        <div>
          <Link to="/" className="small muted">
            {t("common.back_dashboard")}
          </Link>
          <div className="inline" style={{ gap: 12, marginTop: 6 }}>
            <span className="badge badge-navy">{t("dash.annual")} {squad.annual_progress}%</span>
            {squad.counts.roadmap_blocked > 0 && <span className="badge badge-red">{squad.counts.roadmap_blocked} {t("card.blocked")}</span>}
            {squad.counts.roadmap_at_risk > 0 && <span className="badge badge-orange">{squad.counts.roadmap_at_risk} {t("card.atrisk")}</span>}
          </div>
          <div className="inline" style={{ marginTop: 4 }}>
            <span className="muted small">{t("squad.squad_leader")} : <span className="strong">{squad.leader?.display_name || "-"}</span></span>
            <FreshnessBadge freshness={squad.freshness} />
          </div>
          {(squad.products?.length ?? 0) > 0 && (
            <div className="inline" style={{ marginTop: 6, gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span className="muted small">{t("squad.products")} :</span>
              {squad.products!.map((p) => <span key={p} className="badge badge-navy">{p}</span>)}
            </div>
          )}
          {(squad.hardware?.length ?? 0) > 0 && (
            <div className="inline" style={{ marginTop: 4, gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span className="muted small">{t("squad.hardware")} :</span>
              {squad.hardware!.map((h) => <span key={h} className="badge badge-grey">{h}</span>)}
            </div>
          )}
        </div>
      </div>

      {squad.description && <div className="muted small">{squad.description}</div>}

      {/* Initiatives assignées à la squad (définies par le tribe leader) - tout en haut, au-dessus des OTD */}
      {initiatives.length > 0 && (
        <div className="card">
          <h2>{t("nav.initiatives")}</h2>
          <table className="init-tbl">
            <thead><tr>
              <th>{t("init.h_initiative")}</th><th>{t("init.h_owner")}</th><th>{t("init.h_deadline")}</th>
            </tr></thead>
            <tbody>
              {initiatives.map((i) => (
                <tr key={i.id}>
                  <td><strong>{i.title}</strong></td>
                  <td>{i.owner || "-"}</td>
                  <td>{i.deadline ? i.deadline.slice(0, 10) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* OTD - objectifs annuels engagés, en tête de page (définis par le tribe leader) */}
      {objectivesOn && privileged && (
      <div className="card">
        <h2>{t("squad.otd_section", { year: squad.year })}</h2>
        <div className="small muted" style={{ marginBottom: 6 }}>{t("squad.otd_hint")}</div>
        {squad.objectives.length === 0 && <div className="small muted">{t("squad.no_obj")}</div>}
        {squad.objectives.map((o) => (
          <div key={o.id} className="item-row">
            <Dot status={o.rag_status} />
            <div className="grow">
              <div>{o.title}</div>
              {o.description && <div className="small muted">{o.description}</div>}
            </div>
            <span className="small muted">
              {rag(o.rag_status)}
              {o.target_date ? ` · ${formatDate(o.target_date)}` : ""}
            </span>
          </div>
        ))}
      </div>
      )}

      {/* Roadmap par quarter */}
      {roadmapOn && (
      <div className="card">
        <h2>{t("squad.roadmap", { year: squad.year })}</h2>
        <div className="small muted" style={{ marginBottom: 10 }}>{t("jalon.view_hint")}</div>
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
          {[1, 2, 3, 4].map((q) => {
            const cell = squad.quarter_progress[String(q)];
            const items = squad.roadmap_items.filter((r) => r.quarter === q);
            return (
              <div key={q} className="quarter-block">
                <div className="between">
                  <h4>Q{q}</h4>
                  <span className="small muted">{cell?.progress_pct ?? 0}%</span>
                </div>
                <ProgressBar pct={cell?.progress_pct ?? 0} />
                {cell?.comment && <div className="small muted" style={{ marginTop: 6 }}>{cell.comment}</div>}
                <div style={{ marginTop: 8 }}>
                  {items.length === 0 && <div className="small muted">{t("squad.no_jalon")}</div>}
                  {items.map((r) => (
                    <div key={r.id} className="item-row clickable-row" onClick={() => setOpenJalon(r)} title={t("jalon.details")}>
                      <Dot status={roadmapRag(r.status)} />
                      <span className="grow small">{r.title}</span>
                      <span className="badge badge-navy" style={{ fontSize: 10 }}>{r.release_stage}</span>
                      <span className="small muted">{roadmap(r.status)}</span>
                      <span className="chevron">›</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      )}

      {/* Messages clés + Budget, directement sous la roadmap */}
      <div className="grid" style={{ gridTemplateColumns: privileged ? "repeat(auto-fit, minmax(320px, 1fr))" : "1fr", gap: 18, alignItems: "start" }}>
        <KeyMessagesPanel squad={squad} canEdit={privileged} onChange={reload} />
        {privileged && <BudgetPanel squad={squad} canEdit={privileged} canToggle={canToggleBudget} onChange={reload} />}
      </div>

      {/* What other squads are waiting on from this squad (incoming dependencies). */}
      {roadmapOn && dependents.length > 0 && (
        <div className="card">
          <h2>{t("dep.incoming_title")}</h2>
          <div className="small muted" style={{ marginBottom: 10 }}>{t("dep.incoming_hint")}</div>
          {dependents.map((d, i) => (
            <div key={i} className="item-row">
              <Dot status={roadmapRag(d.status)} />
              <Link to={`/squads/${d.squad_id}${squad.year ? `?year=${squad.year}` : ""}`} className="grow">
                <span className="strong small">{d.squad_name}</span>
                <span className="small muted"> · Q{d.quarter} · {d.title}</span>
              </Link>
              <span className="badge badge-grey">{d.via === "tribe" ? t("dep.via_tribe") : t("dep.via_squad")}</span>
            </div>
          ))}
        </div>
      )}

      {openJalon && <JalonView jalon={openJalon} onClose={() => setOpenJalon(null)} t={t} roadmap={roadmap} />}

      {/* KPIs (optionnels) - visibles par le squad leader / tribe leader / admin */}
      {squad.kpis_enabled && kpisOn && privileged && (
        <div className="card">
          <h2>{t("squad.kpis")}</h2>
          {squad.kpis.length === 0 && <div className="small muted">{t("squad.no_kpi")}</div>}
          {squad.kpis.map((k) => (
            <div key={k.id} className="item-row">
              <Dot status={trendRag(k.trend_status)} />
              <div className="grow">
                <div>{k.name}</div>
                {k.comment && <div className="small muted">{k.comment}</div>}
              </div>
              <span className="small muted" style={{ textAlign: "right" }}>
                <div>{trend(k.trend_status)}</div>
                {(k.current_value ?? null) !== null || (k.target_value ?? null) !== null ? (
                  <div>
                    {k.current_value ?? "-"}
                    {k.target_value != null ? ` / ${k.target_value}` : ""}
                    {k.unit ? ` ${k.unit}` : ""}
                  </div>
                ) : null}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Revue de progression - carte dépliable */}
      {reviewOn && (
        <Collapsible title={t("progress.title")} subtitle={t("progress.collapsed_hint")}>
          <div className="small muted" style={{ marginBottom: 12 }}>{t("progress.hint")}</div>
          <div className="banner" style={{ marginBottom: 12 }}>{t("progress.how_it_works")}</div>
          {progress.length === 0 ? (
            <div className="small muted">{t("progress.no_data")}</div>
          ) : (
            <>
              <ProgressCurve points={progress} />
              <div style={{ marginTop: 12 }}>
                <ProgressTimeline points={progress} />
              </div>
            </>
          )}
        </Collapsible>
      )}

      {/* Équipe / organigramme de la squad - carte dépliable */}
      <Collapsible title={t("squad.team")} subtitle={t("squad.team_collapsed_hint", { n: squad.members.length })}>
        <SquadOrg squad={squad} emptyLabel={t("squad.no_members")} />
      </Collapsible>

      <History squadId={squadId} snapshots={snapshots} />
    </div>
  );
}

function kmKindClass(k: KeyMessageKind): string {
  return k === "success" ? "badge-green" : k === "risk" ? "badge-red" : "badge-orange";
}

function KeyMessagesPanel({ squad, canEdit, onChange }:
  { squad: SquadDetail; canEdit: boolean; onChange: () => void }) {
  const { t, formatDateTime } = useI18n();
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<KeyMessageKind>("success");
  const [text, setText] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editKind, setEditKind] = useState<KeyMessageKind>("success");
  const [editText, setEditText] = useState("");

  const kinds: KeyMessageKind[] = ["success", "alert", "risk"];
  const add = () => {
    if (!text.trim()) return;
    api.post(`/api/squads/${squad.id}/key-messages?year=${squad.year}`,
      { kind, text: text.trim(), display_order: squad.key_messages.length })
      .then(() => { setText(""); setKind("success"); setAdding(false); onChange(); })
      .catch(() => {});
  };
  const startEdit = (m: { id: number; kind: KeyMessageKind; text: string }) => {
    setEditId(m.id); setEditKind(m.kind); setEditText(m.text);
  };
  const saveEdit = (id: number) => {
    if (!editText.trim()) return;
    api.put(`/api/squads/${squad.id}/key-messages/${id}`, { kind: editKind, text: editText.trim() })
      .then(() => { setEditId(null); onChange(); }).catch(() => {});
  };
  const remove = (id: number) =>
    api.del(`/api/squads/${squad.id}/key-messages/${id}`).then(onChange).catch(() => {});

  return (
    <div className="card">
      <h2>{t("km.title")}</h2>
      <div className="small muted" style={{ marginBottom: 8 }}>{t("km.hint")}</div>
      {squad.key_messages.length === 0 && <div className="small muted">{t("km.none")}</div>}
      {squad.key_messages.map((m) => (
        <div key={m.id} className="item-row">
          {editId === m.id ? (
            <div className="grow stack" style={{ gap: 6 }}>
              <select value={editKind} onChange={(e) => setEditKind(e.target.value as KeyMessageKind)}>
                {kinds.map((k) => <option key={k} value={k}>{t(`km.kind.${k}`)}</option>)}
              </select>
              <textarea rows={2} value={editText} onChange={(e) => setEditText(e.target.value)} />
              <div className="inline" style={{ gap: 8 }}>
                <button className="btn-sm" onClick={() => saveEdit(m.id)}>{t("action.save")}</button>
                <button className="btn-secondary btn-sm" onClick={() => setEditId(null)}>{t("action.cancel")}</button>
              </div>
            </div>
          ) : (
            <>
              <span className={`badge ${kmKindClass(m.kind)}`}>{t(`km.kind.${m.kind}`)}</span>
              <div className="grow">
                <div className="small">{m.text}</div>
                <div className="small muted">{formatDateTime(m.created_at)}</div>
              </div>
              {canEdit && (
                <span className="inline" style={{ gap: 6 }}>
                  <button className="btn-secondary btn-sm" onClick={() => startEdit(m)}>{t("action.edit")}</button>
                  <button className="btn-danger btn-sm" onClick={() => remove(m.id)} aria-label={t("action.delete")}>✕</button>
                </span>
              )}
            </>
          )}
        </div>
      ))}
      {canEdit && (adding ? (
        <div className="stack" style={{ gap: 6, marginTop: 10 }}>
          <select value={kind} onChange={(e) => setKind(e.target.value as KeyMessageKind)}>
            {kinds.map((k) => <option key={k} value={k}>{t(`km.kind.${k}`)}</option>)}
          </select>
          <textarea rows={2} value={text} placeholder={t("km.text_ph")} onChange={(e) => setText(e.target.value)} />
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-sm" onClick={add}>{t("action.add")}</button>
            <button className="btn-secondary btn-sm" onClick={() => setAdding(false)}>{t("action.cancel")}</button>
          </div>
        </div>
      ) : (
        <button className="btn-secondary btn-sm" style={{ marginTop: 10 }} onClick={() => setAdding(true)}>
          + {t("km.add")}
        </button>
      ))}
    </div>
  );
}

const BUDGET_STATUS_BADGE: Record<string, string> = {
  on_track: "badge-green", at_risk: "badge-orange", over: "badge-red",
};

function BudgetStatusBadge({ b, t }: { b: Budget; t: any }) {
  const cls = BUDGET_STATUS_BADGE[b.status] ?? "badge-grey";
  const label = t(`budget.status.${b.status}`);
  return (
    <span className={`badge ${cls}`}>
      {label}
      {b.status === "over" && ` ${t("budget.overrun_val", { amount: (b.overrun ?? 0).toLocaleString(), pct: b.overrun_pct })}`}
    </span>
  );
}

function BudgetPanel({ squad, canEdit, canToggle, onChange }:
  { squad: SquadDetail; canEdit: boolean; canToggle: boolean; onChange: () => void }) {
  const { t, formatDate } = useI18n();
  const b = squad.budget;
  const [editing, setEditing] = useState(false);
  const [total, setTotal] = useState("");
  const [spent, setSpent] = useState("");
  const [forecast, setForecast] = useState("");
  const [comment, setComment] = useState("");

  const fmt = (n?: number | null) => (n == null ? "-" : n.toLocaleString());

  if (!squad.budget_enabled) {
    return (
      <div className="card">
        <h2>{t("budget.title")}</h2>
        <div className="small muted">{t("budget.disabled")}</div>
        {canToggle && (
          <button className="btn-secondary btn-sm" style={{ marginTop: 10 }}
            onClick={() => api.put(`/api/squads/${squad.id}`, { budget_enabled: true })
              .then(() => { setEditing(true); onChange(); }).catch(() => {})}>
            {t("budget.enable_cta")}
          </button>
        )}
      </div>
    );
  }

  const openEdit = () => {
    setTotal(b?.total != null ? String(b.total) : "");
    setSpent(b?.spent != null ? String(b.spent) : "");
    setForecast(b?.forecast != null ? String(b.forecast) : "");
    setComment(b?.comment ?? "");
    setEditing(true);
  };
  const save = () => {
    api.put(`/api/squads/${squad.id}/budget?year=${squad.year}`, {
      total: total === "" ? null : Number(total),       // ignored server-side for a squad leader
      spent: spent === "" ? null : Number(spent),
      forecast: forecast === "" ? null : Number(forecast),
      comment: comment.trim() || null,
    }).then(() => { setEditing(false); onChange(); }).catch(() => {});
  };

  const reference = b?.forecast ?? b?.spent ?? null;            // where the squad will land
  const remaining = b?.total != null && reference != null ? b.total - reference : null;
  const hasFigures = b != null && (b.total != null || b.spent != null || b.forecast != null);
  const barPct = Math.min(100, (b?.forecast_pct ?? b?.spent_pct) ?? 0);
  const barColor = b?.status === "over" ? "var(--red)" : b?.status === "at_risk" ? "var(--orange)" : "var(--green)";

  return (
    <div className="card">
      <div className="between">
        <h2 style={{ margin: 0 }}>{t("budget.title")}</h2>
        {hasFigures && b && <BudgetStatusBadge b={b} t={t} />}
      </div>
      <div className="small muted" style={{ margin: "4px 0 10px" }}>{t("budget.hint")}</div>

      {editing ? (
        <div className="stack" style={{ gap: 8 }}>
          {canToggle ? (
            <label>{t("budget.total")}
              <input type="number" value={total} onChange={(e) => setTotal(e.target.value)} />
            </label>
          ) : (
            <div className="between"><span className="small muted">{t("budget.total")}</span>
              <span className="strong">{fmt(b?.total)} <span className="small muted">· {t("budget.total_locked")}</span></span>
            </div>
          )}
          <label>{t("budget.spent")} <span className="small muted">({t("budget.spent_hint")})</span>
            <input type="number" value={spent} onChange={(e) => setSpent(e.target.value)} />
          </label>
          <label>{t("budget.forecast")} <span className="small muted">({t("budget.forecast_hint")})</span>
            <input type="number" value={forecast} onChange={(e) => setForecast(e.target.value)} />
          </label>
          <label>{t("budget.comment")}
            <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-sm" onClick={save}>{t("action.save")}</button>
            <button className="btn-secondary btn-sm" onClick={() => setEditing(false)}>{t("action.cancel")}</button>
          </div>
        </div>
      ) : (
        <>
          {!hasFigures ? (
            <div className="small muted">{t("budget.not_set")}</div>
          ) : (
            <div className="stack" style={{ gap: 6 }}>
              <div className="between"><span className="small muted">{t("budget.total")}</span><span className="strong">{fmt(b?.total)}</span></div>
              <div className="between"><span className="small muted">{t("budget.spent")}</span>
                <span className="strong">{fmt(b?.spent)}{b?.spent_pct != null && <span className="small muted"> · {b.spent_pct}%</span>}</span>
              </div>
              <div className="between"><span className="small muted">{t("budget.forecast")}</span>
                <span className="strong">{fmt(b?.forecast)}{b?.forecast_pct != null && <span className="small muted"> · {b.forecast_pct}%</span>}</span>
              </div>
              {/* consumed/forecast gauge against the envelope */}
              <div style={{ height: 8, background: "var(--line)", borderRadius: 4, overflow: "hidden", margin: "2px 0" }}>
                <div style={{ width: `${barPct}%`, height: "100%", background: barColor }} />
              </div>
              <div className="between">
                <span className="small muted">{t("budget.remaining")}</span>
                <span className="strong" style={remaining != null && remaining < 0 ? { color: "var(--red)" } : undefined}>{fmt(remaining)}</span>
              </div>
              {b?.comment && <div className="small muted" style={{ marginTop: 4 }}>{b.comment}</div>}
              {b?.updated_at && <div className="small muted">{t("budget.updated", { date: formatDate(b.updated_at) })}</div>}
            </div>
          )}
          <div className="inline" style={{ gap: 8, marginTop: 10 }}>
            {canEdit && <button className="btn-secondary btn-sm" onClick={openEdit}>{t("budget.edit")}</button>}
            {canToggle && (
              <button className="btn-danger btn-sm"
                onClick={() => api.put(`/api/squads/${squad.id}`, { budget_enabled: false }).then(onChange).catch(() => {})}>
                {t("budget.disable_cta")}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function JalonView({ jalon, onClose, t, roadmap }: { jalon: RoadmapItem; onClose: () => void; t: any; roadmap: any }) {
  const fields: Array<[string, string | null | undefined]> = [
    [t("jalon.desc"), jalon.description],
    [t("jalon.success"), jalon.success_criteria],
    [t("jalon.benefit"), jalon.user_benefit],
    [t("jalon.deps"), jalon.dependency_label ?? jalon.dependencies],
    [t("jalon.risks"), jalon.risks],
  ];
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 560, maxHeight: "85vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="between">
          <h3 style={{ margin: 0 }}>{jalon.title}</h3>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label={t("action.close")}>✕</button>
        </div>
        <div className="inline" style={{ gap: 8, margin: "8px 0 4px", flexWrap: "wrap" }}>
          <span className="badge badge-navy">Q{jalon.quarter}</span>
          {jalon.theme && <span className="badge">{jalon.theme}</span>}
          <span className="badge">{jalon.release_stage}</span>
          <span className="small muted">{t("jalon.status")} : <span className="strong">{roadmap(jalon.status)}</span></span>
        </div>
        {jalon.owner && (
          <div className="jalon-field">
            <div className="jl">{t("jalon.owner")}</div>
            <div className="jv">{jalon.owner}</div>
          </div>
        )}
        {fields.map(([label, val]) =>
          val ? (
            <div key={label} className="jalon-field">
              <div className="jl">{label}</div>
              <div className="jv">{val}</div>
            </div>
          ) : null
        )}
      </div>
    </div>
  );
}

function SquadOrg({ squad, emptyLabel }: { squad: SquadDetail; emptyLabel: string }) {
  if (squad.members.length === 0) return <div className="small muted">{emptyLabel}</div>;
  const byManager: Record<string, Member[]> = {};
  for (const m of squad.members) {
    const key = m.manager_id == null ? "root" : String(m.manager_id);
    (byManager[key] ||= []).push(m);
  }
  const roots = byManager["root"] || [];

  const renderNode = (m: Member) => {
    const children = byManager[String(m.id)] || [];
    return (
      <div key={m.id} className="org-subtree">
        <div className="org-box">
          <div className="strong small">{m.full_name}</div>
          <div className="small muted">{m.role_title || "-"}</div>
        </div>
        {children.length > 0 && (
          <>
            <div className="org-connector" />
            <div className="org-children">{children.map(renderNode)}</div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="row" style={{ justifyContent: "center", alignItems: "flex-start", gap: 20 }}>
      {roots.map(renderNode)}
    </div>
  );
}

function History({ squadId, snapshots }: { squadId: number; snapshots: SnapshotMeta[] }) {
  const { t, formatDateTime } = useI18n();
  const [selected, setSelected] = useState<number | null>(null);
  const [compare, setCompare] = useState<any | null>(null);

  function open(snapId: number) {
    setSelected(snapId);
    setCompare(null);
    api.get<any>(`/api/squads/${squadId}/snapshots/${snapId}/compare`).then(setCompare).catch(() => {});
  }

  return (
    <Collapsible title={t("squad.history")} subtitle={t("squad.history_collapsed_hint", { n: snapshots.length })}>
      {snapshots.length === 0 && <div className="small muted">{t("squad.no_history")}</div>}
      <div className="stack">
        {snapshots.map((s) => (
          <div key={s.id} style={{ borderBottom: "1px solid var(--line)", paddingBottom: 8 }}>
            <div className="between">
              <div>
                <div className="strong">{s.cycle_label}</div>
                <div className="small muted">{formatDateTime(s.submitted_at)}</div>
              </div>
              <button className="btn-secondary btn-sm" onClick={() => open(s.id)}>
                {t("squad.compare")}
              </button>
            </div>
            {selected === s.id && <Compare compare={compare} />}
          </div>
        ))}
      </div>
    </Collapsible>
  );
}

function Compare({ compare }: { compare: any | null }) {
  const { t, formatDateTime } = useI18n();
  const kpisOn = useModule()("squad_content", "kpis");
  if (!compare) return <div className="small muted" style={{ marginTop: 8 }}>{t("common.loading")}</div>;
  if (!compare.previous) return <div className="small muted" style={{ marginTop: 8 }}>-</div>;

  const sections: Array<[string, string]> = [
    ["objectives", t("squad.objectives", { year: "" })],
    ["roadmap_items", "Roadmap"],
    ...(kpisOn ? [["kpis", "KPI"] as [string, string]] : []),
  ];
  const itemLabel = (c: any) => c.item?.title || c.item?.name || `#${c.id}`;
  const total = sections.reduce((n, [k]) => n + (compare.diff?.[k]?.length || 0), 0);

  return (
    <div className="banner" style={{ marginTop: 8, background: "var(--ice-soft)" }}>
      <div className="small muted" style={{ marginBottom: 6 }}>
        « {compare.previous.cycle_label} » - {formatDateTime(compare.previous.submitted_at)}
      </div>
      {total === 0 && <div className="small">-</div>}
      {sections.map(([key, label]) => {
        const changes = (compare.diff?.[key] || []) as any[];
        if (!changes.length) return null;
        return (
          <div key={key} style={{ marginBottom: 6 }}>
            <div className="strong small">{label}</div>
            <ul style={{ margin: "2px 0 0", paddingLeft: 18 }} className="small">
              {changes.map((c, i) => (
                <li key={i}>
                  {c.type === "added" && <span style={{ color: "var(--green)" }}>+ {itemLabel(c)}</span>}
                  {c.type === "removed" && <span style={{ color: "var(--red)" }}>− {itemLabel(c)}</span>}
                  {c.type === "changed" && (
                    <span>
                      {itemLabel(c)} -{" "}
                      {Object.entries(c.fields || {}).map(([f, v]: any) => (
                        <span key={f}>
                          {f} : {String(v.from)} → {String(v.to)};{" "}
                        </span>
                      ))}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
