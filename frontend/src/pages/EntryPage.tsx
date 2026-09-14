/**
 * EntryPage - the reporting screen where a squad's data is entered/updated.
 *
 * Lets a user pick a squad + year and edit its objectives, quarterly roadmap
 * (milestones) and KPIs, then "submit" a snapshot of the current state. Which
 * squads appear depends on the role: admins / tribe leaders (and preview mode)
 * see all squads; a squad leader only sees the squads they lead. Write access is
 * decided per squad by `canEditSquad`; objectives editing by `canManageObjectives`.
 *
 * L'ecran est un parcours: une etape a la fois, une barre qui dit ou l'on en est
 * et ce qui reste, et un bandeau qui rappelle quelle squad et quelle semaine on
 * remplit. Les etapes sont construites a partir des services actifs, chacune
 * derriere son drapeau de module comme avant.
 */
import { ReactNode, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { Initiative, Kpi, Member, Objective, RoadmapItem, RoadmapStatus, Squad, SquadDetail, Tribe, Trend, Role } from "../types";
import { Dot, FreshnessBadge, Spinner, ErrorBanner, EmptyState, SectionCard as Card } from "../components/ui";
import { QuarterProgressEditor } from "../components/EntryExtras";
import { InitiativesCard } from "../components/InitiativesCard";
import { OtdPanel } from "../components/OtdPanel";
import TeamMood from "../components/TeamMood";
import KeyMessagesPanel from "../components/KeyMessagesPanel";
import { canEditSquad, canManageObjectives } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";
import { roadmapRag } from "../labels";
import { currentSteercoPeriod, monthLongLabel } from "../steerco";
import SteercoWizard, { SteercoPreviewModal } from "../components/SteercoWizard";

const ROADMAP_STATUSES: RoadmapStatus[] = ["on_track", "at_risk", "blocked", "done"];

/**
 * Reporting root. Owns the squad/year selection, loads the selected SquadDetail
 * and its assigned initiatives, and orchestrates the section editors plus the
 * submit-snapshot flow. Read-only when the viewer cannot write to the squad.
 */
export default function EntryPage() {
  const { user, effectiveRole, isPreview } = useAuth();
  const { t, roadmap, trend, rag, freshness, formatDate } = useI18n();
  const { default_year } = useConfig();
  const moduleOn = useModule();
  const roadmapOn = moduleOn("squad_content", "roadmap");
  const objectivesOn = moduleOn("squad_content", "objectives");
  const kpisOn = moduleOn("squad_content", "kpis");
  const progressOn = moduleOn("squad_content", "quarter_progress");
  const steercoOn = moduleOn("steerco");
  const role = (effectiveRole ?? "member") as Role;
  const [squads, setSquads] = useState<Squad[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [squadId, setSquadId] = useState<number | null>(null);
  const [year, setYear] = useState<number>(default_year);
  const [yearTouched, setYearTouched] = useState(false);
  useEffect(() => { if (!yearTouched) setYear(default_year); }, [default_year]);
  const [squad, setSquad] = useState<SquadDetail | null>(null);
  const [initiatives, setInitiatives] = useState<Initiative[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recap, setRecap] = useState(false);
  // L'etape courante. On repart de la premiere en changeant de squad ou d'annee:
  // rester au milieu d'un parcours qui n'est plus le meme desoriente plus qu'il
  // ne fait gagner du temps.
  const [step, setStep] = useState(0);
  useEffect(() => { setStep(0); }, [squadId, year]);

  // Squad picker scope: leaders/admins (and preview mode) can report on any
  // squad; a squad leader is limited to the squads they lead, as leader OR as
  // co-leader. Forgetting the second half would grant the right server-side and
  // hide the squad from the only screen that uses it.
  const canPickAll = role === "admin" || role === "tribe_leader" || isPreview;
  const leads = (s: Squad) => s.leader_user_id === user?.id || (s.co_leader_user_ids ?? []).includes(user?.id ?? -1);
  const editable = useMemo(() => (canPickAll ? squads : squads.filter(leads)), [squads, user, canPickAll]);

  useEffect(() => {
    api.get<Squad[]>("/api/squads").then(setSquads).catch((e) => setError(e.message));
    api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {});
  }, []);
  useEffect(() => {
    if (editable.length && squadId === null) setSquadId(editable[0].id);
  }, [editable, squadId]);

  async function reload() {
    if (squadId === null) return;
    setSquad(await api.get<SquadDetail>(`/api/squads/${squadId}?year=${year}`));
  }
  useEffect(() => {
    setSquad(null);
    if (squadId !== null) {
      reload();
      // Initiatives assigned to this squad (read-only here) - same data the squad
      // page shows, so the reporting opens with the same Initiatives card on top.
      api.get<Initiative[]>(`/api/initiatives?year=${year}&squad_id=${squadId}`).then(setInitiatives).catch(() => setInitiatives([]));
    } else {
      setInitiatives([]);
    }
  }, [squadId, year]);

  function flash(m: string) {
    setMessage(m);
    setTimeout(() => setMessage(null), 3000);
  }
  async function confirmSubmit() {
    if (squadId === null) return;
    try {
      await api.post(`/api/squads/${squadId}/snapshots`, { year });
      setRecap(false);
      flash(t("entry.submit_ok"));
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  }

  // Per-squad write permission (drives read-only banner + disabled submit).
  const writeAllowed = squad ? canEditSquad(role, user?.id, squad) : false;

  useSetPageChrome(
    editable.length
      ? {
          actions: (
            <>
              <select className="w-auto" value={squadId ?? ""} onChange={(e) => setSquadId(Number(e.target.value))}>
                {editable.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
              <div className="seg">
                {[year - 1, year, year + 1].map((y) => (
                  <button key={y} className={y === year ? "active" : ""} onClick={() => { setYear(y); setYearTouched(true); }}>{y}</button>
                ))}
              </div>
              <button className="btn-sm" onClick={() => setRecap(true)} disabled={!writeAllowed}>{t("action.submit")}</button>
            </>
          ),
        }
      : {},
    [editable, squadId, year, writeAllowed, t]
  );

  if (error) return <ErrorBanner message={error} />;
  if (editable.length === 0) return <EmptyState message={t("entry.no_squad")} />;

  // Objectives are managed by tribe leaders/admins, not squad leaders.
  const objAllowed = canManageObjectives(role);

  // Les etapes, construites a partir des services actifs: une etape vide apprend
  // a traverser les etapes. `done` n'est pas une condition de passage, c'est un
  // etat: rien n'empeche de sauter une etape, on veut seulement qu'elle le dise.
  const steps: Step[] = squad ? [
    ...(objectivesOn ? [{
      key: "otd", icon: FLOW_ICONS.target,
      done: squad.objectives.length > 0,
      node: (
        <>
          {/* Les engagements dates, d'abord: c'est ce que l'etape annonce. Les
              objectifs qui les servent viennent apres. */}
          <OtdPanel squad={squad} canManage={objAllowed} onChange={reload} />
          <InitiativesCard initiatives={initiatives} />
          <ObjectivesEditor squad={squad} year={year} onChange={reload} editable={objAllowed} t={t} rag={rag} />
        </>
      ),
    }] : []),
    ...(roadmapOn ? [{
      key: "jalons", icon: FLOW_ICONS.flag,
      done: squad.roadmap_items.length > 0,
      node: <RoadmapEditor squad={squad} year={year} onChange={reload} readonly={!writeAllowed}
                           t={t} roadmap={roadmap} squads={squads} tribes={tribes} />,
    }] : []),
    ...(kpisOn && squad.kpis_enabled ? [{
      key: "kpis", icon: FLOW_ICONS.check,
      done: squad.kpis.length > 0,
      node: <KpisEditor squad={squad} onChange={reload} readonly={!writeAllowed} t={t} trend={trend} />,
    }] : []),
    ...(progressOn ? [{
      key: "progress", icon: FLOW_ICONS.check,
      done: [1, 2, 3, 4].some((q) => squad.quarter_progress?.[String(q)]?.comment),
      node: <QuarterProgressEditor squad={squad} year={year} readonly={!writeAllowed} onChange={reload} t={t} />,
    }] : []),
    {
      key: "km", icon: FLOW_ICONS.message,
      done: squad.key_messages.length > 0,
      node: <KeyMessagesPanel squad={squad} canEdit={writeAllowed} onChange={reload} />,
    },
    {
      key: "mood", icon: FLOW_ICONS.mood,
      done: !!squad.mood,
      node: (
        <div className="step-center">
          <TeamMood squadId={squad.id} mood={squad.mood as any} moodAt={squad.mood_at}
                    comment={squad.mood_comment} canEdit={writeAllowed} onChange={reload} big />
        </div>
      ),
    },
    ...(steercoOn ? [{
      key: "steerco", icon: FLOW_ICONS.target,
      done: undefined,
      node: <SteercoSection squad={squad} readonly={!writeAllowed} t={t} />,
    }] : []),
    {
      key: "submit", icon: FLOW_ICONS.send,
      done: !squad.freshness?.is_stale,
      node: (
        <div className="step-center stack" style={{ gap: 14, alignItems: "center" }}>
          <div className="small muted">{t("entry.step.submit_d")}</div>
          <SubmitChecklist squad={squad} t={t} />
          <button className="btn" disabled={!writeAllowed} onClick={() => setRecap(true)}>
            {t("action.submit")}
          </button>
        </div>
      ),
    },
  ] : [];

  const at = Math.min(step, Math.max(0, steps.length - 1));
  const current = steps[at];

  return (
    <div className="stack" style={{ gap: 18 }}>
      {/* Quel reporting, pour qui: avant tout le reste, parce que savoir ou l'on
          est vient avant savoir quoi faire. */}
      {squad && <ReportingHeader squad={squad} t={t} formatDate={formatDate} freshness={freshness} />}

      {message && <div className="banner banner-green">{message}</div>}

      {!squad ? (
        <Spinner />
      ) : (
        <>
          {!writeAllowed && <div className="banner" style={{ background: "var(--ice-soft)" }}>{t("entry.readonly")}</div>}

          {/* La barre d'etapes: ce qui reste a faire, et par ou passer. Elle a
              remplace la bande decorative qui annoncait la meme demarche sans
              permettre de la suivre. */}
          <StepRail steps={steps} at={at} onGo={setStep} t={t} />

          <div className="step-panel stack" style={{ gap: 16 }}>
            <div>
              <h2 style={{ margin: 0 }}>{t(`entry.step.${current.key}_t`)}</h2>
              <div className="small muted">{t(`entry.step.${current.key}_d`)}</div>
            </div>
            {current.node}
          </div>

          <div className="between" style={{ flexWrap: "wrap", gap: 10 }}>
            <button className="btn-secondary btn-sm" disabled={at === 0}
                    onClick={() => setStep(at - 1)}>‹ {t("common.prev")}</button>
            <span className="small muted">{t("entry.step_of", { n: at + 1, total: steps.length })}</span>
            <button className="btn-sm" disabled={at >= steps.length - 1}
                    onClick={() => setStep(at + 1)}>{t("common.next")} ›</button>
          </div>
        </>
      )}

      {recap && squad && <SubmitRecap squad={squad} onConfirm={confirmSubmit} onCancel={() => setRecap(false)} t={t} />}
    </div>
  );
}


/** Une etape du reporting: son icone, son etat, et ce qu'elle montre. */
type Step = {
  key: string;
  icon: ReactNode;
  /** Rempli, vide, ou sans notion de « fait » (les actions, le steerco). */
  done: boolean | undefined;
  node: ReactNode;
};


/**
 * La barre d'etapes.
 *
 * Elle remplace la bande decorative qui listait les memes temps sans y mener. Un
 * mode d'emploi qui ne fait pas avancer se lit une fois puis se saute; celui-ci
 * est le chemin lui-meme, et il dit en plus ce qui est deja rempli.
 */
function StepRail({ steps, at, onGo, t }: {
  steps: Step[]; at: number; onGo: (i: number) => void; t: (k: string, v?: any) => string;
}) {
  return (
    <div className="step-rail">
      {steps.map((s, i) => (
        <button key={s.key} className={`step-chip${i === at ? " on" : ""}`} onClick={() => onGo(i)}
                aria-current={i === at ? "step" : undefined}>
          {/* L'icone ne porte qu'un etat: ou l'on en est. Une couleur par etape
              n'aurait rien dit, et aurait noye celles qui disent quelque chose. */}
          <span className={`step-ico${i === at ? " on" : s.done ? " done" : ""}`}>{s.icon}</span>
          <span className="step-body">
            <span className="step-title">{t(`entry.step.${s.key}_t`)}</span>
            <span className="step-state">
              {s.done === undefined ? t("entry.step_optional")
                : s.done ? t("entry.step_done") : t("entry.step_todo")}
            </span>
          </span>
          {s.done === true && <span className="step-check" aria-hidden>✓</span>}
        </button>
      ))}
    </div>
  );
}

/**
 * Ce qui est rempli et ce qui ne l'est pas, avant d'envoyer.
 *
 * Aucune de ces lignes ne bloque l'envoi: une squad peut legitimement n'avoir ni
 * KPI ni membre declare. Elles sont montrees sur la derniere etape, la ou l'on
 * peut encore y faire quelque chose, et non plus seulement dans la fenetre de
 * confirmation.
 */
function SubmitChecklist({ squad, t }: { squad: any; t: (k: string) => string }) {
  const items: Array<[boolean, string]> = [
    [squad.roadmap_items.length > 0, t("entry.check.jalons")],
    [[1, 2, 3, 4].some((q: number) => (squad.quarter_progress[String(q)]?.progress_pct ?? 0) > 0),
     t("entry.check.progress")],
    [!squad.kpis_enabled || squad.kpis.length > 0, t("entry.check.kpis")],
    [squad.members.length > 0, t("entry.check.members")],
  ];
  return (
    <div className="stack" style={{ gap: 6 }}>
      {items.map(([ok, label], i) => (
        <div key={i} className="inline">
          <span className={`badge ${ok ? "badge-green" : "badge-grey"}`}>{ok ? "✓" : "○"}</span>
          <span className="small">{label}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * Pre-submit confirmation. Shows the same readiness check as the last step, then
 * asks for the snapshot; none of the lines block submission.
 */
function SubmitRecap({ squad, onConfirm, onCancel, t }: any) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{t("entry.submit_recap")}</h3>
        <div className="stack" style={{ margin: "12px 0" }}>
          <SubmitChecklist squad={squad} t={t} />
        </div>
        <div className="inline" style={{ justifyContent: "flex-end", gap: 8 }}>
          <button className="btn-secondary" onClick={onCancel} disabled={busy}>{t("action.cancel")}</button>
          <button disabled={busy} onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } }}>
            {t("entry.submit_confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Blank milestone pre-set to the given quarter, seeding the "new jalon" form. */
function emptyJalon(year: number, quarter: number): Partial<RoadmapItem> {
  return { year, quarter, title: "", theme: "", release_stage: "EA", description: "", success_criteria: "", user_benefit: "", dependencies: "", dependency_kind: null, dependency_squad_id: null, dependency_tribe_id: null, risks: "", owner: "", status: "on_track", objective_id: null };
}

/**
 * Roadmap editor: four QuarterEditor columns plus a JalonModal for create/edit.
 * `save` decides POST (new) vs PUT (existing, stripping id/squad_id). Read-only
 * mode hides add/edit affordances. Includes a per-squad roadmap PPTX export link.
 */
function RoadmapEditor({ squad, year, onChange, readonly, t, roadmap, squads, tribes }: any) {
  const { lang } = useI18n();
  const [editing, setEditing] = useState<Partial<RoadmapItem> | null>(null);

  async function save(data: Partial<RoadmapItem>) {
    if (data.id) {
      const { id, squad_id, ...patch } = data as any;
      await api.put(`/api/roadmap-items/${data.id}`, patch);
    } else {
      await api.post("/api/roadmap-items", { ...data, squad_id: squad.id });
    }
    setEditing(null);
    onChange();
  }
  async function remove(item: RoadmapItem) {
    await api.del(`/api/roadmap-items/${item.id}`);
    onChange();
  }

  return (
    <Card title={t("squad.roadmap", { year })} hint={t("entry.roadmap_hint")}
          action={
            <a className="btn btn-secondary btn-sm" download
               href={`/api/squads/${squad.id}/roadmap.pptx?year=${year}&lang=${lang}`}>
              {t("export.roadmap_btn")}
            </a>
          }>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        {[1, 2, 3, 4].map((q) => (
          <QuarterEditor
            key={q}
            squad={squad}
            year={year}
            quarter={q}
            onChange={onChange}
            readonly={readonly}
            t={t}
            roadmap={roadmap}
            onAdd={() => setEditing(emptyJalon(year, q))}
            onEdit={(it: RoadmapItem) => setEditing(it)}
            onRemove={remove}
          />
        ))}
      </div>
      {editing && (
        <JalonModal jalon={editing} members={squad.members} objectives={squad.objectives} onSave={save} onCancel={() => setEditing(null)} t={t} roadmap={roadmap} squads={squads} tribes={tribes} currentSquadId={squad.id} />
      )}
    </Card>
  );
}

/**
 * One quarter column: its milestones and an auto-computed progress bar. Rows are
 * clickable to edit unless read-only. Progress is derived, never entered.
 */
function QuarterEditor({ squad, quarter, readonly, t, onAdd, onEdit }: any) {
  const items = squad.roadmap_items.filter((r: RoadmapItem) => r.quarter === quarter);
  // Progress is auto-derived from milestone advancement (share done), never typed.
  const total = items.length;
  const done = items.filter((r: RoadmapItem) => r.status === "done").length;
  const pct = total ? Math.round((100 * done) / total) : 0;

  return (
    <div className="quarter-block">
      <div className="between">
        <h4>Q{quarter}</h4>
        <span className="small muted" title={t("entry.progress_auto")}>{pct}%, {done}/{total}</span>
      </div>
      <div style={{ height: 8, background: "var(--line)", borderRadius: 6, overflow: "hidden", marginBottom: 4 }} aria-label={`${pct}%`}>
        <div style={{ width: `${pct}%`, height: "100%", background: "var(--navy)" }} />
      </div>
      <div style={{ marginTop: 8 }}>
        {items.map((r: RoadmapItem) => (
          <div key={r.id} className="item-row" style={{ cursor: readonly ? "default" : "pointer" }} onClick={() => !readonly && onEdit(r)}>
            <Dot status={roadmapRag(r.status)} />
            <span className="grow small">
              {r.theme ? <span className="strong" style={{ color: "#002060" }}>{r.theme}, </span> : null}
              {r.title}
            </span>
            <span className="badge badge-navy" style={{ fontSize: 10 }}>{r.release_stage}</span>
            {r.owner ? <span className="small muted">{r.owner}</span> : null}
          </div>
        ))}
      </div>
      {!readonly && (
        <button className="btn-secondary btn-sm" style={{ marginTop: 8 }} onClick={onAdd}>+ {t("jalon.add")}</button>
      )}
    </div>
  );
}

/**
 * Milestone create/edit form (modal). Beyond the plain fields it offers theme
 * reuse (datalist of existing themes), owner suggestions from squad members,
 * optional link to an objective, and a dependency that can be free text, another
 * squad, or a tribe (`depKind`). Title + theme are required to save.
 */
function JalonModal({ jalon, members, objectives, onSave, onCancel, t, roadmap, squads, tribes, currentSquadId }: any) {
  const [f, setF] = useState<Partial<RoadmapItem>>(jalon);
  const [themes, setThemes] = useState<string[]>([]);
  const set = (k: string, v: any) => setF((p) => ({ ...p, [k]: v }));
  // Existing themes for reuse: pick one from the list or type a new one.
  useEffect(() => { api.get<string[]>("/api/roadmap-items/themes").then(setThemes).catch(() => {}); }, []);
  // A dependency can be: free text, another squad, or a tribe.
  const depKind: "text" | "squad" | "tribe" = (f.dependency_kind as any) || "text";
  const setDepKind = (k: "text" | "squad" | "tribe") =>
    setF((p) => ({ ...p, dependency_kind: k, dependency_squad_id: null, dependency_tribe_id: null, dependencies: k === "text" ? (p.dependencies ?? "") : null }));
  const field = (label: string, key: string, area = false) => (
    <div>
      <label>{label}</label>
      {area ? (
        <textarea rows={2} value={(f as any)[key] ?? ""} onChange={(e) => set(key, e.target.value)} />
      ) : (
        <input value={(f as any)[key] ?? ""} onChange={(e) => set(key, e.target.value)} />
      )}
    </div>
  );
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" style={{ maxWidth: 560, maxHeight: "85vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <h3>{f.id ? t("jalon.edit") : t("jalon.new")} - Q{f.quarter}</h3>
        <div className="stack" style={{ gap: 10, marginTop: 10 }}>
          {field(t("jalon.title") + " *", "title")}
          <div>
            <label>{t("jalon.theme") + " *"}</label>
            <input list="jalon-themes" placeholder={t("jalon.theme_ph")} value={f.theme ?? ""}
                   onChange={(e) => set("theme", e.target.value)} />
            <datalist id="jalon-themes">
              {themes.map((th) => <option key={th} value={th} />)}
            </datalist>
          </div>
          <div className="row">
            <div className="col">
              <label>{t("jalon.status")}</label>
              <select value={f.status} onChange={(e) => set("status", e.target.value)}>
                {["on_track", "at_risk", "blocked", "done"].map((s) => (
                  <option key={s} value={s}>{roadmap(s)}</option>
                ))}
              </select>
            </div>
            <div className="col">
              <label>{t("jalon.stage")} *</label>
              <select value={f.release_stage ?? "EA"} onChange={(e) => set("release_stage", e.target.value)}>
                <option value="EA">EA - {t("jalon.stage_ea")}</option>
                <option value="GA">GA - {t("jalon.stage_ga")}</option>
              </select>
            </div>
          </div>
          <div className="row">
            <div className="col">
              <label>{t("jalon.owner")}</label>
              <input list="jalon-owners" placeholder={t("jalon.owner_ph")} value={f.owner ?? ""} onChange={(e) => set("owner", e.target.value)} />
              <datalist id="jalon-owners">
                {members.map((m: Member) => <option key={m.id} value={m.full_name} />)}
              </datalist>
            </div>
          </div>
          {objectives && objectives.length > 0 && (
            <div>
              <label>{t("jalon.objective")}</label>
              <select value={f.objective_id ?? ""} onChange={(e) => set("objective_id", e.target.value ? Number(e.target.value) : null)}>
                <option value="">{t("jalon.objective_none")}</option>
                {objectives.map((o: Objective) => <option key={o.id} value={o.id}>{o.title}</option>)}
              </select>
            </div>
          )}
          {field(t("jalon.desc"), "description", true)}
          {field(t("jalon.success"), "success_criteria", true)}
          {field(t("jalon.benefit"), "user_benefit", true)}
          <div>
            <label>{t("jalon.deps")}</label>
            <div className="row" style={{ gap: 8 }}>
              <select className="w-auto" value={depKind} onChange={(e) => setDepKind(e.target.value as any)}>
                <option value="squad">{t("jalon.dep_squad")}</option>
                <option value="tribe">{t("jalon.dep_tribe")}</option>
                <option value="text">{t("jalon.dep_text")}</option>
              </select>
              {depKind === "text" && (
                <input className="grow" value={f.dependencies ?? ""} onChange={(e) => set("dependencies", e.target.value)} />
              )}
              {depKind === "squad" && (
                <select className="grow" value={f.dependency_squad_id ?? ""} onChange={(e) => set("dependency_squad_id", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">-</option>
                  {squads.filter((s: Squad) => s.id !== currentSquadId).map((s: Squad) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              )}
              {depKind === "tribe" && (
                <select className="grow" value={f.dependency_tribe_id ?? ""} onChange={(e) => set("dependency_tribe_id", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">-</option>
                  {tribes.map((tr: Tribe) => (
                    <option key={tr.id} value={tr.id}>{tr.name}</option>
                  ))}
                </select>
              )}
            </div>
          </div>
          {field(t("jalon.risks"), "risks", true)}
        </div>
        <div className="inline" style={{ justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
          <button className="btn-secondary" onClick={onCancel}>{t("action.cancel")}</button>
          <button onClick={() => onSave(f)} disabled={!f.title?.trim() || !f.theme?.trim()}>{t("action.save")}</button>
        </div>
      </div>
    </div>
  );
}

/**
 * Annual objectives editor. When `editable` (tribe leader / admin) titles and
 * target dates can be changed and objectives added/removed; otherwise it is a
 * read-only list. The RAG status is auto-derived from advancement, never edited.
 */
function ObjectivesEditor({ squad, year, onChange, editable, t, rag }: any) {
  const [title, setTitle] = useState("");
  async function add() {
    if (!title.trim()) return;
    await api.post("/api/objectives", { squad_id: squad.id, year, title: title.trim() });
    setTitle("");
    onChange();
  }
  async function update(o: Objective, patch: Partial<Objective>) {
    await api.put(`/api/objectives/${o.id}`, patch);
    onChange();
  }
  async function remove(o: Objective) {
    await api.del(`/api/objectives/${o.id}`);
    onChange();
  }
  return (
    <Card title={t("squad.objectives", { year })} hint={editable ? t("entry.obj_hint_edit") : t("entry.obj_hint_ro")}>
      {squad.objectives.length === 0 && <div className="small muted">{t("squad.no_obj")}</div>}
      {squad.objectives.map((o: Objective) => (
        <div key={o.id} className="item-row" style={{ gap: 8 }}>
          {/* Status is auto-derived from advancement - shown, never edited here. */}
          <span className="inline" style={{ gap: 6 }} title={t("obj.status_auto")}>
            <Dot status={o.rag_status} />
          </span>
          {editable ? (
            <input className="grow" defaultValue={o.title} onBlur={(e) => e.target.value !== o.title && update(o, { title: e.target.value })} />
          ) : (
            <span className="grow">{o.title}</span>
          )}
          <span className="small muted" style={{ minWidth: 60 }}>{rag(o.rag_status)}</span>
          {editable ? (
            <input type="date" className="w-auto" style={{ maxWidth: 150 }} title={t("obj.deadline")}
                   value={o.target_date ? o.target_date.slice(0, 10) : ""}
                   onChange={(e) => update(o, { target_date: (e.target.value || null) as any })} />
          ) : (
            o.target_date && <span className="small muted">{o.target_date.slice(0, 10)}</span>
          )}
          {editable && <button className="btn-danger btn-sm" onClick={() => remove(o)} aria-label={`${t("action.delete")} - ${o.title}`}>✕</button>}
        </div>
      ))}
      {editable && (
        <div className="inline" style={{ marginTop: 8 }}>
          <input placeholder={t("entry.new_obj")} value={title} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} />
          <button className="btn-secondary btn-sm" onClick={add}>{t("action.add")}</button>
        </div>
      )}
    </Card>
  );
}

/**
 * KPI editor: name, trend, current/target/unit per KPI. Read-only mode disables
 * inputs. Only rendered when the squad has KPIs enabled and the module is on.
 */
function KpisEditor({ squad, onChange, readonly, t, trend }: any) {
  const [name, setName] = useState("");
  const trends: Trend[] = ["on_target", "under_pressure", "missed"];
  // Parse a numeric input into a number or null (blank / non-numeric -> null).
  const num = (v: string) => (v.trim() === "" ? null : Number.isNaN(Number(v)) ? null : Number(v));
  async function add() {
    if (!name.trim()) return;
    await api.post("/api/kpis", { squad_id: squad.id, name: name.trim(), trend_status: "on_target" });
    setName("");
    onChange();
  }
  async function update(k: Kpi, patch: Partial<Kpi>) {
    await api.put(`/api/kpis/${k.id}`, patch);
    onChange();
  }
  async function remove(k: Kpi) {
    await api.del(`/api/kpis/${k.id}`);
    onChange();
  }
  return (
    <Card title={t("squad.kpis")} hint={t("entry.kpi_hint")}>
      <>
          {squad.kpis.map((k: Kpi) => (
            <div key={k.id} className="item-row" style={{ flexWrap: "wrap" }}>
              {readonly ? <span className="grow" style={{ minWidth: 140 }}>{k.name}</span> : (
                <input className="grow" style={{ minWidth: 140 }} defaultValue={k.name} onBlur={(e) => e.target.value !== k.name && update(k, { name: e.target.value })} />
              )}
              <select className="w-auto" style={{ maxWidth: 150 }} value={k.trend_status} disabled={readonly} onChange={(e) => update(k, { trend_status: e.target.value as Trend })}>
                {trends.map((tr) => (<option key={tr} value={tr}>{trend(tr)}</option>))}
              </select>
              <input className="w-auto" style={{ width: 70 }} placeholder="val." disabled={readonly} defaultValue={k.current_value ?? ""} onBlur={(e) => update(k, { current_value: num(e.target.value) })} />
              <input className="w-auto" style={{ width: 70 }} placeholder="target" disabled={readonly} defaultValue={k.target_value ?? ""} onBlur={(e) => update(k, { target_value: num(e.target.value) })} />
              <input className="w-auto" style={{ width: 70 }} placeholder="unit" disabled={readonly} defaultValue={k.unit ?? ""} onBlur={(e) => e.target.value !== (k.unit ?? "") && update(k, { unit: e.target.value || null })} />
              {!readonly && <button className="btn-danger btn-sm" onClick={() => remove(k)} aria-label={`${t("action.delete")} - ${k.name}`}>✕</button>}
            </div>
          ))}
          {!readonly && (
            <div className="inline" style={{ marginTop: 8 }}>
              <input placeholder={t("entry.new_kpi")} value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} />
              <button className="btn-secondary btn-sm" onClick={add}>{t("action.add")}</button>
            </div>
          )}
      </>
    </Card>
  );
}


/**
 * Steerco input section. Steerco is reported per PLATFORM, and a squad contributes to
 * the platforms the tribe leader declared it on. Unlike the WEEKLY reporting this
 * section lives in, Steerco is a MONTHLY check-in: the launcher makes the cadence
 * explicit and shows, for each platform this squad feeds, whether the month is still
 * to do or already filled (with when/who), so a squad leader doing their weekly
 * reporting immediately knows what is left. The actual entry happens in a guided
 * popup wizard (one platform, one month at a time).
 *
 * A platform fed by several squads shows what the others still owe: the month is only
 * done when every contributor has filled its own items.
 */
type PlatformStatus = {
  id: number; name: string; filled: boolean; updated_at: string | null;
  updated_by: string | null; missing: string[]; contributors: { id: number; name: string }[];
};

function SteercoSection({ squad, readonly, t }: any) {
  const { lang } = useI18n();
  const [rows, setRows] = useState<PlatformStatus[] | null>(null);
  const [open, setOpen] = useState<PlatformStatus | null>(null);
  const [preview, setPreview] = useState<PlatformStatus | null>(null);
  const period = currentSteercoPeriod();
  const monthName = monthLongLabel(period, lang);

  // The platforms this squad feeds, with this month's status for each. The list is
  // the platforms where the squad is a contributor, not every platform of the tribe.
  async function load() {
    try {
      const all = await api.get<any[]>("/api/steerco/platforms");
      const mine = all.filter((p) => (p.contributors ?? []).some((c: any) => c.id === squad.id));
      const out = await Promise.all(mine.map(async (p) => {
        const r = await api.get<any>(`/api/steerco/platform/${p.id}?period=${encodeURIComponent(period)}`);
        return {
          id: p.id, name: p.name, filled: !!r.filled, updated_at: r.updated_at ?? null,
          updated_by: r.updated_by ?? null, missing: r.missing ?? [], contributors: p.contributors ?? [],
        } as PlatformStatus;
      }));
      setRows(out);
    } catch { setRows([]); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [squad.id]);

  // No platform yet: declaring one is the tribe leader's call, so the card says who
  // to ask rather than offering a button that would 403.
  if (rows !== null && rows.length === 0) {
    return (
      <Card title={t("steerco.card_title")} hint={t("steerco.no_platform_hint")}>
        <div className="inline" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <span className="badge badge-navy">{t("steerco.badge")}</span>
          <span className="small muted">{t("steerco.ask_tribe_leader")}</span>
        </div>
      </Card>
    );
  }

  return (
    <Card title={t("steerco.card_title")} hint={t("steerco.form_hint")}>
      <div className="inline" style={{ gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <span className="badge badge-navy">{t("steerco.monthly_tag")}</span>
        <span className="small muted">{t("steerco.cadence_note")}</span>
      </div>

      {rows === null ? <div className="small muted">{t("common.loading")}</div> : rows.map((p) => {
        const when = p.updated_at ? new Date(p.updated_at).toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US", { day: "2-digit", month: "2-digit", year: "numeric" }) : "";
        const by = p.updated_by ? t("steerco.done_by", { name: p.updated_by }) : "";
        return (
          <div key={p.id} className={`sc-status ${p.filled ? "done" : "todo"}`} style={{ marginBottom: 8 }}>
            <span className="sc-status-ic">{p.filled ? "✓" : "📅"}</span>
            <div className="stack" style={{ gap: 2 }}>
              <div className="strong">{p.name}, {p.filled ? t("steerco.done_title", { month: monthName }) : t("steerco.todo_title", { month: monthName })}</div>
              <div className="small muted">
                {p.filled
                  ? (p.updated_at ? t("steerco.done_sub", { when, by }) : t("steerco.done_sub_nodate"))
                  : t("steerco.todo_sub")}
              </div>
              {p.missing.length > 0 && (
                <div className="small muted">{t("steerco.still_missing", { who: p.missing.join(", ") })}</div>
              )}
            </div>
            <div className="inline" style={{ gap: 8, marginLeft: "auto" }}>
              {p.filled && (
                <button className="btn-secondary btn-sm" onClick={() => setPreview(p)}>
                  {t("steerco.wiz.preview_btn")}
                </button>
              )}
              <button className={`btn-sm ${p.filled ? "btn-secondary" : ""}`} onClick={() => setOpen(p)}>
                {readonly ? t("steerco.wiz.open_view") : p.filled ? t("steerco.edit_report") : t("steerco.wiz.open")}
              </button>
            </div>
          </div>
        );
      })}

      {open && (
        <SteercoWizard
          platformId={open.id}
          platformName={open.name}
          initialPeriod={period}
          readonly={readonly}
          onClose={() => setOpen(null)}
          onSaved={load}
        />
      )}
      {preview && (
        <SteercoPreviewModal
          platformId={preview.id}
          platformName={preview.name}
          period={period}
          onClose={() => setPreview(null)}
        />
      )}
    </Card>
  );
}


/* ---- Visual "how to report" intro: a hero line + a 4-step graphic flow ---- */
const FLOW_ICONS = {
  target: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" fill="currentColor" />
    </svg>
  ),
  flag: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 21V4" /><path d="M5 4h11l-2 3 2 3H5" />
    </svg>
  ),
  check: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" /><path d="M8.5 12.5l2.5 2.5 4.5-5" />
    </svg>
  ),
  send: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4 20-7z" />
    </svg>
  ),
  mood: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" /><path d="M8.5 14.5a4.5 4.5 0 0 0 7 0" />
      <path d="M9 9.5h.01" /><path d="M15 9.5h.01" />
    </svg>
  ),
  message: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z" />
    </svg>
  ),
};

/**
 * Le bandeau d'entete: quel reporting, pour quelle squad, quelle semaine.
 *
 * La semaine est celle d'aujourd'hui, en numerotation ISO (celle des calendriers
 * d'entreprise), avec ses deux bornes: un numero seul ne se verifie pas, une
 * plage de dates si. L'annee affichee est celle du reporting en cours, qui n'est
 * pas toujours l'annee courante en janvier comme en decembre.
 */
function ReportingHeader({ squad, t, formatDate, freshness }: {
  squad: SquadDetail;
  t: (k: string, v?: any) => string;
  formatDate: (iso?: string | null) => string;
  freshness: (f: any) => string;
}) {
  const now = new Date();
  const { week, monday, sunday } = isoWeekOf(now);
  return (
    <div className="reporting-banner">
      <div className="rb-main">
        <div className="rb-eyebrow">{t("entry.header_eyebrow")}</div>
        <div className="rb-title">{squad.name}</div>
        <div className="rb-sub">
          {t("entry.header_week", {
            week,
            from: formatDate(monday.toISOString()),
            to: formatDate(sunday.toISOString()),
          })}
        </div>
      </div>
      <div className="rb-side">
        <div className="rb-chip">
          <span className="rb-chip-label">{t("entry.header_year")}</span>
          <span className="rb-chip-value">{squad.year}</span>
        </div>
        <div className="rb-chip">
          <span className="rb-chip-label">{t("entry.header_today")}</span>
          <span className="rb-chip-value">{formatDate(now.toISOString())}</span>
        </div>
        <div className="rb-chip">
          <span className="rb-chip-label">{t("entry.last_submit")}</span>
          <span className="rb-chip-value">{freshness(squad.freshness)}</span>
        </div>
      </div>
    </div>
  );
}

/** Le numero de semaine ISO d'une date, et les lundi/dimanche qui l'encadrent.
 *
 *  ISO parce que c'est la numerotation des calendriers d'entreprise: la semaine
 *  commence le lundi et la semaine 1 est celle qui contient le premier jeudi de
 *  l'annee. Compter autrement donnerait un numero different de celui que porte
 *  l'invitation du comite. */
function isoWeekOf(d: Date): { week: number; monday: Date; sunday: Date } {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayOfWeek = t.getUTCDay() || 7;          // dimanche vaut 7, pas 0
  const monday = new Date(t);
  monday.setUTCDate(t.getUTCDate() - (dayOfWeek - 1));
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  // Le jeudi de la semaine decide de l'annee a laquelle elle appartient.
  const thursday = new Date(t);
  thursday.setUTCDate(t.getUTCDate() + 4 - dayOfWeek);
  const jan1 = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((thursday.getTime() - jan1.getTime()) / 86400000 + 1) / 7);
  return { week, monday, sunday };
}


