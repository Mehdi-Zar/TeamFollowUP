// Customer Success > Projets: the dashboard, then the projects as cards.
//
// The figures and the three badges (overdue points, access ending soon, no news)
// come from GET /api/cs/dashboard; nothing is sent by mail (docs/37, section 4).
// A badge is also a filter: clicking it keeps only the projects it counts.
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { CsSettings, Dashboard, Project, fmtAmount, fmtDate } from "../../cs";
import { EmptyState, ErrorBanner, Modal, Spinner } from "../ui";
import CsProjectModal from "./CsProjectModal";
import CsRecapModal from "./CsRecapModal";

type Badge = "" | "blocked" | "overdue" | "access" | "stale";

export default function CsProjects({ tribeId, canRun }: { tribeId: number; canRun: boolean }) {
  const { t, lang } = useI18n();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [cfg, setCfg] = useState<CsSettings | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [recap, setRecap] = useState(false);
  const [q, setQ] = useState("");
  const [offer, setOffer] = useState("");
  const [badge, setBadge] = useState<Badge>("");

  const load = useCallback(() => {
    setErr(null);
    Promise.all([
      api.get<Project[]>(`/api/cs/projects?tribe_id=${tribeId}`),
      api.get<Dashboard>(`/api/cs/dashboard?tribe_id=${tribeId}`),
      api.get<CsSettings>(`/api/cs/settings?tribe_id=${tribeId}`),
    ]).then(([p, d, c]) => { setProjects(p); setDash(d); setCfg(c); })
      .catch((e) => setErr(errorText(e)));
  }, [tribeId]);
  useEffect(() => { setProjects(null); load(); }, [load]);

  const stageOf = (key: string) => cfg?.stages.find((s) => s.key === key);
  const offers = useMemo(() => Array.from(new Set([...(cfg?.offers ?? []),
    ...(projects ?? []).map((p) => p.offer).filter((o): o is string => !!o)])).sort(), [cfg, projects]);

  const shown = useMemo(() => (projects ?? []).filter((p) => {
    if (offer && p.offer !== offer) return false;
    if (badge === "blocked" && !p.blocked) return false;
    if (badge === "overdue" && !p.overdue_items) return false;
    if (badge === "access" && !(p.access_soon || p.access_over)) return false;
    if (badge === "stale" && !p.stale) return false;
    if (q.trim()) {
      const hay = [p.title, p.client, p.requesters, p.gcp_project, p.offer, ...(p.tags ?? [])].join(" ").toLowerCase();
      if (!hay.includes(q.trim().toLowerCase())) return false;
    }
    return true;
  }), [projects, offer, badge, q]);

  if (err) return <ErrorBanner message={err} />;
  if (projects === null || dash === null || cfg === null) return <Spinner />;

  const groups: { key: string; label: string; items: Project[] }[] = [
    { key: "blocked", label: t("cs.group.blocked"), items: shown.filter((p) => p.blocked) },
    { key: "open", label: t("cs.group.open"), items: shown.filter((p) => !p.blocked && !p.closed) },
    { key: "closed", label: t("cs.group.closed"), items: shown.filter((p) => p.closed) },
  ];

  const badgeBtn = (key: Badge, n: number, label: string, tone: string) => (
    <button type="button" className={`btn-sm ${badge === key ? "" : "btn-secondary"}`} disabled={!n && badge !== key}
            aria-pressed={badge === key} onClick={() => setBadge(badge === key ? "" : key)}>
      <span className={`badge ${n ? tone : "badge-grey"}`} style={{ marginRight: 6 }}>{n}</span>{label}
    </button>
  );

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
        <div className="kpi"><div className="v">{dash.open}</div><div className="l">{t("cs.kpi.open")}</div></div>
        <div className="kpi"><div className={`v ${dash.blocked ? "red" : ""}`}>{dash.blocked}</div><div className="l">{t("cs.kpi.blocked")}</div></div>
        <div className="kpi"><div className="v">{dash.delivered_year}</div><div className="l">{t("cs.kpi.delivered", { year: dash.year })}</div></div>
        <div className="kpi"><div className="v">{fmtAmount(dash.build_signed, lang) || "0"}</div><div className="l">{t("cs.kpi.build_signed")}</div></div>
        <div className="kpi"><div className="v">{fmtAmount(dash.build_pending, lang) || "0"}</div><div className="l">{t("cs.kpi.build_pending")}</div></div>
      </div>

      <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
        {badgeBtn("blocked", dash.blocked, t("cs.badge.blocked"), "badge-red")}
        {badgeBtn("overdue", dash.overdue_projects, t("cs.badge.overdue"), "badge-red")}
        {badgeBtn("access", dash.access_soon + dash.access_over, t("cs.badge.access", { n: dash.access_warn_days }), "badge-orange")}
        {badgeBtn("stale", dash.stale, t("cs.badge.stale", { n: dash.stale_days }), "badge-orange")}
      </div>

      <div className="between" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
          <input type="search" placeholder={t("cs.search")} aria-label={t("cs.search")} value={q}
                 onChange={(e) => setQ(e.target.value)} style={{ minWidth: 220 }} />
          {offers.length > 0 && (
            <select className="w-auto" aria-label={t("cs.f.offer")} value={offer} onChange={(e) => setOffer(e.target.value)}>
              <option value="">{t("cs.all_offers")}</option>
              {offers.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          )}
        </div>
        <div className="inline" style={{ gap: 8 }}>
          <button className="btn-secondary btn-sm" onClick={() => setRecap(true)} disabled={!projects.length}>{t("cs.recap.open")}</button>
          {canRun && <button className="btn-sm" onClick={() => setCreating(true)}>{t("cs.new")}</button>}
        </div>
      </div>

      {projects.length === 0 ? (
        <EmptyState message={canRun ? t("cs.empty_run") : t("cs.empty")} />
      ) : groups.map((g) => (
        <section key={g.key} className="stack" style={{ gap: 8 }}>
          <h2 style={{ margin: 0 }}>{g.label} <span className="muted small">({g.items.length})</span></h2>
          {g.items.length === 0 ? <div className="small muted">{t("cs.group.none")}</div> : (
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
              {g.items.map((p) => (
                <ProjectCard key={p.id} p={p} stages={cfg.stages} stageLabel={stageOf(p.stage)?.label ?? p.stage}
                             onOpen={() => setOpenId(p.id)} />
              ))}
            </div>
          )}
        </section>
      ))}

      {openId !== null && (
        <CsProjectModal projectId={openId} settings={cfg} onClose={() => setOpenId(null)} onChanged={load} />
      )}
      {creating && (
        <CreateModal tribeId={tribeId} offers={cfg.offers} onClose={() => setCreating(false)}
                     onCreated={(id) => { setCreating(false); load(); setOpenId(id); }} />
      )}
      {recap && <CsRecapModal tribeId={tribeId} settings={cfg} projects={projects} canRun={canRun}
                              onClose={() => setRecap(false)} onSaved={load} />}
    </div>
  );
}

const HEALTH_CLASS: Record<string, string> = { green: "dot-green", amber: "dot-orange", red: "dot-red" };

function ProjectCard({ p, stages, stageLabel, onOpen }: {
  p: Project; stages: CsSettings["stages"]; stageLabel: string; onOpen: () => void;
}) {
  const { t, lang } = useI18n();
  const idx = stages.findIndex((s) => s.key === p.stage);
  return (
    <button type="button" className="card cs-card" onClick={onOpen}
            style={{ textAlign: "left", display: "flex", flexDirection: "column", gap: 8, cursor: "pointer" }}>
      <div className="between" style={{ alignItems: "flex-start", gap: 8 }}>
        <div>
          {p.client && <div className="small muted">{p.client}</div>}
          <div className="strong">{p.title}</div>
        </div>
        {p.health && <span className={`dot ${HEALTH_CLASS[p.health]}`} role="img"
                           aria-label={t(`cs.health.${p.health}`)} title={t(`cs.health.${p.health}`)} />}
      </div>
      <div className="cs-steps" aria-label={t("cs.f.stage")}>
        {stages.map((s, i) => (
          <span key={s.key} title={s.label} className="cs-step"
                style={{ background: i <= idx ? s.color : "var(--surface-3)" }} />
        ))}
      </div>
      <div className="small"><span className="strong">{stageLabel}</span>
        {p.offer && <span className="muted">, {p.offer}</span>}</div>
      {p.blocker && (
        <div className="small" style={{ color: "var(--red)" }}>
          {t("cs.card.blocked", { label: p.blocker.label })}
          {p.blocker.owner && ` (${p.blocker.owner})`}
          {p.blocker.since && `, ${t("cs.card.since", { date: fmtDate(p.blocker.since, lang), n: p.blocker.days ?? 0 })}`}
        </div>
      )}
      {p.next_action && (
        <div className="small" style={p.next_action.overdue ? { color: "var(--red)" } : undefined}>
          {t("cs.card.next", { label: p.next_action.label })}
          {p.next_action.due && `, ${fmtDate(p.next_action.due, lang)}`}
        </div>
      )}
      <div className="inline small muted" style={{ gap: 8, flexWrap: "wrap" }}>
        <span>{p.last_contact ? t("cs.card.last_contact", { date: fmtDate(p.last_contact, lang) }) : t("cs.card.no_contact")}</span>
        {p.stale && <span className="badge badge-orange">{t("cs.card.stale", { n: p.days_since_contact })}</span>}
        {p.access_soon && <span className="badge badge-orange">{t("cs.card.access_soon", { n: p.access_days ?? 0 })}</span>}
        {p.access_over && <span className="badge badge-red">{t("cs.card.access_over")}</span>}
        {p.overdue_items > 0 && <span className="badge badge-red">{t("cs.card.overdue", { n: p.overdue_items })}</span>}
      </div>
    </button>
  );
}

function CreateModal({ tribeId, offers, onClose, onCreated }: {
  tribeId: number; offers: string[]; onClose: () => void; onCreated: (id: number) => void;
}) {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [client, setClient] = useState("");
  const [offer, setOffer] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function create() {
    setBusy(true); setErr(null);
    try {
      const p = await api.post<Project>("/api/cs/projects", { tribe_id: tribeId, title, client, offer });
      onCreated(p.id);
    } catch (e) { setErr(errorText(e)); setBusy(false); }
  }
  return (
    <Modal title={t("cs.new")} onClose={onClose} dirty={!!title}
           footer={<div className="inline" style={{ gap: 8 }}>
             <button className="btn-secondary btn-sm" onClick={onClose}>{t("action.cancel")}</button>
             <button className="btn-sm" disabled={!title.trim() || busy} onClick={create}>{t("cs.create")}</button>
           </div>}>
      <div className="stack" style={{ gap: 12 }}>
        {err && <ErrorBanner message={err} />}
        <label className="stack" style={{ gap: 4 }}>{t("cs.f.title")}
          <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} /></label>
        <label className="stack" style={{ gap: 4 }}>{t("cs.f.client")}
          <input value={client} onChange={(e) => setClient(e.target.value)} maxLength={255} /></label>
        <label className="stack" style={{ gap: 4 }}>{t("cs.f.offer")}
          <input list="cs-offers-new" value={offer} onChange={(e) => setOffer(e.target.value)} maxLength={255} />
          <datalist id="cs-offers-new">{offers.map((o) => <option key={o} value={o} />)}</datalist></label>
      </div>
    </Modal>
  );
}
