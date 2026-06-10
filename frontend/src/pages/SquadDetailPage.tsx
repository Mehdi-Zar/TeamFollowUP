import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { Member, RoadmapItem, SnapshotMeta, SquadDetail } from "../types";
import { Dot, FreshnessBadge, ProgressBar, Spinner, ErrorBanner } from "../components/ui";
import EmailExport from "../components/EmailExport";
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

  useEffect(() => {
    const q = yearParam ? `?year=${yearParam}` : "";
    setSquad(null);
    api.get<SquadDetail>(`/api/squads/${squadId}${q}`).then(setSquad).catch((e) => setError(e.message));
    api.get<SnapshotMeta[]>(`/api/squads/${squadId}/snapshots`).then(setSnapshots).catch(() => {});
  }, [squadId, yearParam]);

  if (error) return <ErrorBanner message={error} />;
  if (!squad) return <Spinner />;

  const years = [squad.year - 1, squad.year, squad.year + 1];

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="between">
        <div>
          <Link to="/" className="small muted">
            {t("common.back_dashboard")}
          </Link>
          <h1 className="inline" style={{ gap: 12, marginTop: 6 }}>
            {squad.name}
            <span className="badge badge-navy">{t("dash.annual")} {squad.annual_progress}%</span>
            {squad.counts.roadmap_blocked > 0 && <span className="badge badge-red">{squad.counts.roadmap_blocked} {t("card.blocked")}</span>}
            {squad.counts.roadmap_at_risk > 0 && <span className="badge badge-orange">{squad.counts.roadmap_at_risk} {t("card.atrisk")}</span>}
          </h1>
          <div className="inline" style={{ marginTop: 4 }}>
            <span className="muted small">{t("squad.squad_leader")} : <span className="strong">{squad.leader?.display_name || "—"}</span></span>
            <FreshnessBadge freshness={squad.freshness} />
          </div>
        </div>
        <div className="inline">
          <div className="seg">
            {years.map((y) => (
              <button key={y} className={y === squad.year ? "active" : ""} onClick={() => setParams({ year: String(y) })}>
                {y}
              </button>
            ))}
          </div>
          <a className="btn btn-secondary btn-sm" href={`/api/exports/squad/${squadId}.csv?year=${squad.year}`}>
            {t("action.csv")}
          </a>
          <Link className="btn btn-secondary btn-sm" to={`/print/squad/${squadId}?year=${squad.year}`} target="_blank">
            {t("action.report")}
          </Link>
          <EmailExport endpoint={`/api/exports/squad/${squadId}/email`} year={squad.year} />
        </div>
      </div>

      {squad.description && <div className="muted small">{squad.description}</div>}

      {/* Roadmap par quarter */}
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

      {openJalon && <JalonView jalon={openJalon} onClose={() => setOpenJalon(null)} t={t} roadmap={roadmap} />}

      {/* Objectifs annuels */}
      <div className="card">
        <h2>{t("squad.objectives", { year: squad.year })}</h2>
        <div className="small muted" style={{ marginBottom: 6 }}>{t("squad.objectives_hint")}</div>
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

      {/* KPIs (optionnels) */}
      {squad.kpis_enabled && (
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
                    {k.current_value ?? "—"}
                    {k.target_value != null ? ` / ${k.target_value}` : ""}
                    {k.unit ? ` ${k.unit}` : ""}
                  </div>
                ) : null}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Équipe / organigramme de la squad */}
      <div className="card">
        <h2>{t("squad.team")}</h2>
        <SquadOrg squad={squad} emptyLabel={t("squad.no_members")} />
      </div>

      <History squadId={squadId} snapshots={snapshots} />
    </div>
  );
}

function JalonView({ jalon, onClose, t, roadmap }: { jalon: RoadmapItem; onClose: () => void; t: any; roadmap: any }) {
  const fields: Array<[string, string | null | undefined]> = [
    [t("jalon.desc"), jalon.description],
    [t("jalon.success"), jalon.success_criteria],
    [t("jalon.benefit"), jalon.user_benefit],
    [t("jalon.deps"), jalon.dependencies],
    [t("jalon.risks"), jalon.risks],
  ];
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 560, maxHeight: "85vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="between">
          <h3 style={{ margin: 0 }}>{jalon.title}</h3>
          <button className="btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <div className="inline" style={{ gap: 8, margin: "8px 0 4px" }}>
          <span className="badge badge-navy">Q{jalon.quarter}</span>
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
          <div className="small muted">{m.role_title || "—"}</div>
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
    <div className="card">
      <h2>{t("squad.history")}</h2>
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
    </div>
  );
}

function Compare({ compare }: { compare: any | null }) {
  const { t, formatDateTime } = useI18n();
  if (!compare) return <div className="small muted" style={{ marginTop: 8 }}>{t("common.loading")}</div>;
  if (!compare.previous) return <div className="small muted" style={{ marginTop: 8 }}>—</div>;

  const sections: Array<[string, string]> = [
    ["objectives", t("squad.objectives", { year: "" })],
    ["roadmap_items", "Roadmap"],
    ["kpis", "KPI"],
  ];
  const itemLabel = (c: any) => c.item?.title || c.item?.name || `#${c.id}`;
  const total = sections.reduce((n, [k]) => n + (compare.diff?.[k]?.length || 0), 0);

  return (
    <div className="banner" style={{ marginTop: 8, background: "var(--ice-soft)" }}>
      <div className="small muted" style={{ marginBottom: 6 }}>
        « {compare.previous.cycle_label} » — {formatDateTime(compare.previous.submitted_at)}
      </div>
      {total === 0 && <div className="small">—</div>}
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
                      {itemLabel(c)} —{" "}
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
