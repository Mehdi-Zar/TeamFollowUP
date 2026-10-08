/**
 * EntryPage - the reporting screen where a squad's data is entered/updated.
 *
 * Lets a user pick a squad + year and edit its quarterly roadmap (milestones),
 * KPIs, quarter comments, key messages and mood, then "submit" a snapshot of the
 * current state. Which squads appear depends on the role: admins / tribe leaders
 * (and preview mode) see all squads; a squad leader only sees the squads they
 * lead. Write access is decided per squad by `canEditSquad`.
 *
 * Les initiatives et les objectifs annuels ne sont pas ici: seuls un tribe leader
 * ou un admin les ecrivent, et un tribe leader n'a pas acces a cet ecran. Les
 * engagements OTD, si: l'engagement d'une squad est ce que son leader declare, au
 * meme titre que ses jalons, et il se prend au moment ou l'on remplit son cycle.
 *
 * L'ecran est un parcours: une etape a la fois, une barre qui dit ou l'on en est
 * et ce qui reste, et un bandeau qui rappelle quelle squad et quelle semaine on
 * remplit. Les etapes sont construites a partir des services actifs, chacune
 * derriere son drapeau de module comme avant.
 */
import { Fragment, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, errorText, reportSaveError } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { Dependency, Kpi, Member, RoadmapItem, Squad, SquadDetail, Tribe, Trend, Role } from "../types";
import { Dot, Spinner, ErrorBanner, EmptyState, Modal, SectionCard as Card, StageBadge } from "../components/ui";
import { QuarterProgressEditor } from "../components/EntryExtras";
import TeamMood, { moodAge, WEEKLY_STALE_DAYS } from "../components/TeamMood";
import KeyMessagesPanel from "../components/KeyMessagesPanel";
import PickOrType from "../components/PickOrType";
import { usePeople } from "../components/usePeople";
import { OtdPanel } from "../components/OtdPanel";
import { canEditSquad, contributesTo, leadsSquad } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";
import { roadmapRag } from "../labels";
import { SortSpec, useListView } from "../components/listView";
import { currentSteercoPeriod, monthLongLabel } from "../steerco";
import SteercoWizard, { SteercoPreviewModal } from "../components/SteercoWizard";
import { BudgetPanel } from "./SquadDetailPage";


/**
 * Reporting root. Owns the squad/year selection, loads the selected SquadDetail,
 * and orchestrates the section editors plus the submit-snapshot flow. Read-only
 * when the viewer cannot write to the squad.
 */
export default function EntryPage() {
  const { user, effectiveRole } = useAuth();
  // The team is set up in My squads: the link only for whoever may open it (a
  // contributor does the reporting, not the team).
  const { t, roadmap, trend, freshness, formatDate } = useI18n();
  const { default_year } = useConfig();
  const moduleOn = useModule();
  const roadmapOn = moduleOn("squad_content", "roadmap");
  const kpisOn = moduleOn("squad_content", "kpis");
  const progressOn = moduleOn("squad_content", "quarter_progress");
  const steercoOn = moduleOn("steerco");
  const role = (effectiveRole ?? "member") as Role;
  const [squads, setSquads] = useState<Squad[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [squadId, setSquadId] = useState<number | null>(null);
  const [params] = useSearchParams();
  const navigate = useNavigate();
  // A link that names the year (?year=, from the squad page) wins over the default.
  const askedYear = Number(params.get("year")) || null;
  const [year, setYear] = useState<number>(askedYear ?? default_year);
  const [yearTouched, setYearTouched] = useState(askedYear !== null);
  useEffect(() => { if (!yearTouched) setYear(default_year); }, [default_year]);
  const [squad, setSquad] = useState<SquadDetail | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [recapError, setRecapError] = useState<string | null>(null);
  // The Steerco step's state, told by its section once it has read the platforms.
  const [steercoDone, setSteercoDone] = useState<boolean | null>(null);
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
  // The preview shows what the simulated person sees: no extra squads.
  const canPickAll = role === "admin" || role === "tribe_leader";
  // Leading it, or being named its contributor: both do the squad's reporting.
  const leads = (s: Squad) => s.leader_user_id === user?.id || (s.co_leader_user_ids ?? []).includes(user?.id ?? -1)
    || contributesTo(user?.id, s);
  const editable = useMemo(() => (canPickAll ? squads : squads.filter(leads)), [squads, user, canPickAll]);

  useEffect(() => {
    api.get<Squad[]>("/api/squads").then(setSquads).catch((e) => setError(e.message));
    api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {});
  }, []);
  useEffect(() => {
    // Open on the squad one leads: a squad leader lands on their own squad, and so
    // does a tribe leader or admin who also leads one.
    // A link "update in the reporting" names the squad (?squad=): open that one.
    if (editable.length && squadId === null) {
      const asked = Number(params.get("squad"));
      const target = editable.find((s) => s.id === asked) ?? editable.find(leads) ?? editable[0];
      setSquadId(target.id);
    }
  }, [editable, squadId]);

  // The latest request wins: switching squad or year quickly used to let an older
  // answer land last, showing squad A under squad B's name.
  const reqRef = useRef(0);
  async function reload() {
    if (squadId === null) return;
    const n = ++reqRef.current;
    try {
      const d = await api.get<SquadDetail>(`/api/squads/${squadId}?year=${year}`);
      if (n === reqRef.current) { setSquad(d); setActionError(null); }
    } catch (e) {
      if (n !== reqRef.current) return;
      // Without the catch a 403/404 left the spinner turning forever. Once the page
      // is up, a failed refresh is a banner, not the whole screen.
      if (squad) setActionError(errorText(e)); else setError(errorText(e));
    }
  }
  useEffect(() => {
    setSquad(null);
    if (squadId !== null) reload();
  }, [squadId, year]);

  // What changed since the squad's last submission of this year, step by step
  // (GET .../snapshots/pending): it drives each step's state and the badge.
  const [pending, setPending] = useState<Pending | null>(null);
  useEffect(() => {
    if (squadId === null) return;
    let alive = true;  // the answer of another squad or year is dropped
    api.get<Pending>(`/api/squads/${squadId}/snapshots/pending?year=${year}`)
      .then((p) => { if (alive) setPending(p); }).catch(() => { if (alive) setPending(null); });
    return () => { alive = false; };
  }, [squadId, year, squad]);

  async function confirmSubmit() {
    if (squadId === null) return;
    setRecapError(null);
    try {
      await api.post(`/api/squads/${squadId}/snapshots`, { year });
      setRecap(false);
      // Leave the form: staying on it looked as if nothing had happened. The squad
      // page says it was received and holds the new snapshot in its history.
      navigate(`/squads/${squadId}?year=${year}`, { state: { submitted: true } });
    } catch (e) {
      // Said in the recap window, which stays open to retry.
      setRecapError(errorText(e));
    }
  }

  // Per-squad write permission (drives read-only banner + disabled submit).
  const contributes = squad ? contributesTo(user?.id, squad) : false;
  const writeAllowed = squad ? canEditSquad(role, user?.id, squad) || contributes : false;
  // L'engagement d'une squad appartient a qui la dirige, co-leaders compris, et
  // pas au tribe leader qui passe par cet ecran en apercu. Meme regle que le
  // serveur (routers/otds.py, `_leads`), pour qu'aucun bouton ne finisse en 403.
  // A contributor does the reporting as well (deps.reports_for_squad).
  const ownsSquad = squad ? leadsSquad(role, user?.id, squad) || contributes : false;

  useSetPageChrome(
    editable.length
      ? {
          actions: (
            <>
              {/* A choice only when there is one to make: with a single squad (the
                  usual squad leader) its name stands where the picker was. */}
              {editable.length > 1 ? (
                <select className="w-auto" aria-label={t("entry.pick_squad")} value={squadId ?? ""} onChange={(e) => setSquadId(Number(e.target.value))}>
                  {editable.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              ) : (
                <span className="strong">{editable[0].name}</span>
              )}
              <div className="seg">
                {[year - 1, year, year + 1].map((y) => (
                  <button key={y} className={y === year ? "active" : ""} aria-pressed={y === year} onClick={() => { setYear(y); setYearTouched(true); }}>{y}</button>
                ))}
              </div>
            </>
          ),
        }
      : {},
    [editable, squadId, year, t]
  );

  if (error) return <ErrorBanner message={error} />;
  if (editable.length === 0) return <EmptyState message={t("entry.no_squad")} />;

  // Les etapes, construites a partir des services actifs: une etape vide apprend
  // a traverser les etapes. `done` n'est pas une condition de passage, c'est un
  // etat: rien n'empeche de sauter une etape, on veut seulement qu'elle le dise.
  // Pas d'etape pour les initiatives et les objectifs annuels: seuls un tribe
  // leader ou un admin peuvent les ecrire, et un tribe leader n'a pas acces a cet
  // ecran, si bien que l'etape ouvrait le parcours sur des cartes en lecture
  // seule. Elles ont leur ecran: « Mes squads » pour les editer, la page de la
  // squad pour les lire.
  // A step's state says what the squad has to do now: fill it (never submitted),
  // or submit what changed since the last submission. A mood from March no
  // longer ticks this week's step.
  const submitted = !!pending?.last;
  // Submitted, nothing changed since, but long enough ago that the dashboard
  // shows the squad as stale: the page asks for a confirmation too, instead of
  // saying "up to date" while the dashboard says the opposite.
  const staleConfirm = submitted && !pending?.any && !!squad?.freshness?.is_stale;
  const stateOf = (hasContent: boolean, section: PendingSection, optional = false): StepState => {
    if (submitted) return pending!.changed[section] ? "changed" : hasContent ? "unchanged" : optional ? "optional" : "todo";
    return hasContent ? "done" : optional ? "optional" : "todo";
  };
  // The squad's own leadership submits; a tribe leader reading this screen
  // corrects what the server lets them, but does not submit for the squad.
  const maySubmit = writeAllowed && ownsSquad;
  const steps: Step[] = squad ? [
    // Les OTD d'abord: on pose ce a quoi la squad s'engage, puis les jalons, qui
    // s'y rattachent dans leur propre fenetre (deux listes, OTD de la tribe et OTD
    // de la squad). L'OTD de la squad s'ecrit ici; celui du management se lit.
    {
      key: "otd",
      state: stateOf((squad.otd_count ?? 0) > 0, "otds", true),
      node: <OtdPanel squad={squad} canManage={false} canOwn={ownsSquad} onChange={reload} />,
    },
    ...(roadmapOn ? [{
      key: "jalons",
      state: stateOf(squad.roadmap_items.length > 0, "roadmap"),
      // Milestones and key messages belong to the squad's own leadership: the
      // server refuses the tribe leader (assert_leads_squad), so does the screen.
      node: <RoadmapEditor squad={squad} year={year} onChange={reload} readonly={!ownsSquad}
                           t={t} roadmap={roadmap} squads={squads} tribes={tribes} />,
    }] : []),
    ...(kpisOn && squad.kpis_enabled ? [{
      key: "kpis",
      state: stateOf(squad.kpis.length > 0, "kpis"),
      node: <KpisEditor squad={squad} onChange={reload} readonly={!writeAllowed} t={t} trend={trend} />,
    }] : []),
    ...(progressOn ? [{
      key: "progress",
      state: stateOf([1, 2, 3, 4].some((q) => !!squad.quarter_progress?.[String(q)]?.comment), "progress"),
      node: <QuarterProgressEditor squad={squad} year={year} readonly={!writeAllowed} onChange={reload} t={t} />,
    }] : []),
    {
      key: "km",
      state: stateOf(squad.key_messages.length > 0, "key_messages"),
      node: <KeyMessagesPanel squad={squad} canEdit={ownsSquad} onChange={reload} />,
    },
    {
      key: "mood",
      // A mood from another week no longer answers this week's question.
      state: squad.mood && (moodAge(squad.mood_at) ?? 0) > WEEKLY_STALE_DAYS
        ? "refresh" as StepState : stateOf(!!squad.mood, "mood"),
      node: (
        <div className="step-center">
          <TeamMood squadId={squad.id} mood={squad.mood as any} moodAt={squad.mood_at}
                    comment={squad.mood_comment} canEdit={writeAllowed} onChange={reload} big />
        </div>
      ),
    },
    // Le budget se renseigne avec le reste du reporting: le consomme et
    // l'atterrissage de la squad, par sa direction (leader, co-leaders), jamais
    // par ses contributeurs, a qui le serveur ne l'envoie pas. L'enveloppe reste
    // au tribe leader (le serveur ignore un total envoye par quelqu'un d'autre).
    ...(squad.budget_enabled && squad.budget ? [{
      key: "budget",
      state: (squad.budget.spent != null || squad.budget.forecast != null ? "done" : "todo") as StepState,
      node: <BudgetPanel squad={squad} canEdit={canEditSquad(role, user?.id, squad)} onChange={reload}
                         canToggle={role === "admin" || role === "tribe_leader"} />,
    }] : []),
    // Le Steerco n'est une etape que pour une squad qui contribue a une
    // plateforme: ailleurs, l'etape n'ouvrait que sur « demandez a votre tribe
    // leader ». Une etape ou il n'y a rien a faire se traverse quand meme, et
    // fait douter d'avoir oublie quelque chose.
    ...(steercoOn && squad.steerco_enabled ? [{
      key: "steerco",
      // Done when every platform the squad feeds has this month's figures.
      state: (steercoDone === null ? "optional" : steercoDone ? "done" : "todo") as StepState,
      node: <SteercoSection squad={squad} readonly={!writeAllowed} t={t} onStatus={setSteercoDone} />,
    }] : []),
    {
      key: "submit",
      state: (pending?.any || staleConfirm ? "tosubmit" : submitted ? "uptodate" : "todo") as StepState,
      node: (
        <div className="step-center stack" style={{ gap: 14, alignItems: "center" }}>
          <SubmitChecklist squad={squad} t={t} flags={{ roadmapOn, progressOn, kpisOn }} />
          <button className="btn" disabled={!maySubmit} onClick={() => setRecap(true)}>
            {t("action.submit")}
          </button>
          {!ownsSquad && writeAllowed && <div className="small muted">{t("entry.submit_owner_only")}</div>}
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

      {actionError && <ErrorBanner message={actionError} />}

      {!squad ? (
        <Spinner />
      ) : (
        <>
          {!writeAllowed && <div className="banner" style={{ background: "var(--ice-soft)" }}>{t("entry.readonly")}</div>}
          {writeAllowed && !ownsSquad && (
            <div className="banner" style={{ background: "var(--ice-soft)" }}>{t("entry.not_owner")}</div>
          )}
          {pending && (pending.last ? pending.any || staleConfirm : maySubmit) && at !== steps.length - 1 && (
            <div className="banner between" style={{ alignItems: "center", gap: 10 }}>
              <span className="small">
                {pending.last
                  ? pending.any
                    ? t("entry.unsubmitted", { date: formatDate(pending.last.submitted_at) })
                    : t("entry.confirm_stale", { date: formatDate(pending.last.submitted_at) })
                  : t("entry.never_submitted", { year })}
              </span>
              <button className="btn-secondary btn-sm" onClick={() => setStep(steps.length - 1)}>{t("entry.go_submit")}</button>
            </div>
          )}

          {/* La barre d'etapes: ce qui reste a faire, et par ou passer. Elle a
              remplace la bande decorative qui annoncait la meme demarche sans
              permettre de la suivre. */}
          <StepRail steps={steps} at={at} onGo={setStep} t={t} />

          <div className="step-panel stack" style={{ gap: 16 }}>
            <div>
              {/* Le meme rang qu'en tete de la barre: on doit pouvoir dire ou
                  l'on est sans remonter les yeux. */}
              <h2 style={{ margin: 0 }}>
                <span className="step-panel-num">{at + 1}</span>
                {t(`entry.step.${current.key}_t`)}
              </h2>
              <div className="small muted">{t(`entry.step.${current.key}_d`)}</div>
            </div>
            {current.node}
          </div>

          <div className="between" style={{ flexWrap: "wrap", gap: 10 }}>
            <button className="btn-secondary btn-sm" disabled={at === 0}
                    onClick={() => setStep(at - 1)}>‹ {t("common.prev")}</button>
            <span className="small muted">{t("entry.step_of", { n: at + 1, total: steps.length })}</span>
            {/* The last step ends on its own Submit button: no "next" after it. */}
            {at < steps.length - 1
              ? <button className="btn-sm" onClick={() => setStep(at + 1)}>{t("common.next")} ›</button>
              : <span />}
          </div>
        </>
      )}

      {recap && squad && <SubmitRecap squad={squad} year={year} pending={pending} formatDate={formatDate}
                                      flags={{ roadmapOn, progressOn, kpisOn }}
                                      error={recapError}
                                      onConfirm={confirmSubmit} onCancel={() => { setRecap(false); setRecapError(null); }} t={t} />}
    </div>
  );
}


/** The state of a step, against the squad's last submission of the year. */
type StepState = "todo" | "done" | "optional" | "changed" | "unchanged" | "tosubmit" | "uptodate" | "refresh";
type PendingSection = "roadmap" | "otds" | "key_messages" | "mood" | "kpis" | "progress";
/** GET /api/squads/{id}/snapshots/pending */
type Pending = {
  last: { cycle_label: string; submitted_at: string } | null;
  changed: Record<PendingSection, boolean>;
  any: boolean;
};

/** Une etape du reporting: son rang, son etat, et ce qu'elle montre. */
type Step = {
  key: string;
  state: StepState;
  node: ReactNode;
};


/**
 * La barre d'etapes.
 *
 * Elle remplace la bande decorative qui listait les memes temps sans y mener. Un
 * mode d'emploi qui ne fait pas avancer se lit une fois puis se saute; celui-ci
 * est le chemin lui-meme, et il dit en plus ce qui est deja rempli.
 */
/** States shown with a tick: nothing left to do on that step. */
const OK_STATES = new Set<StepState>(["done", "unchanged", "uptodate"]);

function StepRail({ steps, at, onGo, t }: {
  steps: Step[]; at: number; onGo: (i: number) => void; t: (k: string, v?: any) => string;
}) {
  return (
    <ol className="step-rail">
      {steps.map((s, i) => (
        <Fragment key={s.key}>
          {/* Le chevron entre deux etapes: il dit que l'une mene a l'autre. Une
              rangee de cartes posees cote a cote se lit comme un menu, ou l'on
              choisit; une suite fleche se lit comme un parcours, ou l'on avance. */}
          {i > 0 && <li className="step-arrow" aria-hidden>›</li>}
          <li>
            <button className={`step-chip${i === at ? " on" : ""}`} onClick={() => onGo(i)}
                    aria-current={i === at ? "step" : undefined}>
              {/* Le numero, et le coche quand l'etape est remplie. La pastille
                  portait une icone par etape, mais deux etapes partageaient la
                  meme et aucune ne nommait la sienne: un rang, lui, dit ou l'on
                  en est dans la suite, ce qui est la seule chose qu'on lui
                  demande. */}
              <span className={`step-num${i === at ? " on" : OK_STATES.has(s.state) ? " done" : ""}`}>
                {OK_STATES.has(s.state) ? "✓" : i + 1}
              </span>
              <span className="step-body">
                <span className="step-title">{t(`entry.step.${s.key}_t`)}</span>
                <span className="step-state">{t(`entry.state.${s.state}`)}</span>
              </span>
            </button>
          </li>
        </Fragment>
      ))}
    </ol>
  );
}

/**
 * Ce qui est rempli et ce qui ne l'est pas, avant d'envoyer.
 *
 * Aucune de ces lignes ne bloque l'envoi: une squad peut legitimement n'avoir ni
 * KPI ni engagement propre. Seul ce que le reporting fait remplir y figure:
 * l'equipe se regle dans Mes squads, elle n'a rien a faire ici. Elles sont montrees sur la derniere etape, la ou l'on
 * peut encore y faire quelque chose, et non plus seulement dans la fenetre de
 * confirmation.
 */
function SubmitChecklist({ squad, t, flags }: {
  squad: any; t: (k: string) => string;
  flags: { roadmapOn: boolean; progressOn: boolean; kpisOn: boolean };
}) {
  // Only what this screen lets one fill, for the services that are on: the
  // progress percentage is computed (its comment is what one writes), and a KPI
  // line only exists when the squad tracks KPIs.
  const items: Array<[boolean, string]> = [
    ...(flags.roadmapOn ? [[squad.roadmap_items.length > 0, t("entry.check.jalons")] as [boolean, string]] : []),
    ...(flags.progressOn ? [[[1, 2, 3, 4].some((q: number) => !!squad.quarter_progress[String(q)]?.comment),
                             t("entry.check.progress")] as [boolean, string]] : []),
    // Une squad peut legitimement n'avoir pris aucun engagement propre: la ligne
    // le dit, elle ne l'exige pas. Comme toutes les autres.
    [(squad.otd_count ?? 0) > 0, t("entry.check.otd")],
    ...(flags.kpisOn && squad.kpis_enabled ? [[squad.kpis.length > 0, t("entry.check.kpis")] as [boolean, string]] : []),
    [(squad.key_messages?.length ?? 0) > 0, t("entry.check.km")],
    [!!squad.mood, t("entry.check.mood")],
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
function SubmitRecap({ squad, year, pending, formatDate, flags, error, onConfirm, onCancel, t }: any) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={t("entry.submit_recap_year", { name: squad.name, year })} onClose={onCancel} dirty={busy}>
        {/* What "Submit" does, said once and plainly: it was nowhere. */}
        <div className="small">{t("entry.submit_what", { year })}</div>
        {pending?.last && !pending.any && (
          <div className="small muted" style={{ marginTop: 6 }}>
            {t("entry.submit_nothing_new", { date: formatDate(pending.last.submitted_at) })}
          </div>
        )}
        <div className="stack" style={{ margin: "12px 0" }}>
          <SubmitChecklist squad={squad} t={t} flags={flags} />
        </div>
        {error && <ErrorBanner message={error} />}
        <div className="inline" style={{ justifyContent: "flex-end", gap: 8 }}>
          <button className="btn-secondary" onClick={onCancel} disabled={busy}>{t("action.cancel")}</button>
          <button disabled={busy} onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } }}>
            {busy ? t("common.sending") : error ? t("common.retry") : t("entry.submit_confirm")}
          </button>
        </div>
    </Modal>
  );
}

/** Blank milestone pre-set to the given quarter, seeding the "new jalon" form. */
function emptyJalon(year: number, quarter: number): Partial<RoadmapItem> {
  return { year, quarter, title: "", theme: "", release_stage: "EA", description: "", success_criteria: "", user_benefit: "", dependencies: "", dependency_kind: null, dependency_squad_id: null, dependency_tribe_id: null, risks: "", owner: "", status: "on_track" };
}

/**
 * Roadmap editor: one QuarterEditor row per quarter, the full width, plus a
 * JalonModal for create/edit. Four columns side by side cut every title short.
 * `save` decides POST (new) vs PUT (existing, stripping id/squad_id). Read-only
 * mode hides add/edit affordances. Rien a exporter d'ici: cette page sert a saisir,
 * et les documents se prennent dans le menu Exporter de la barre de page, un seul
 * endroit pour tous les formats et toutes les portees.
 */
/** Severity order of a milestone status, the most worrying first. */
const STATUS_RANK: Record<string, number> = { blocked: 0, at_risk: 1, on_track: 2, done: 3 };

/** The filters of the milestones step, besides the search. */
type JalonFilters = { status: string; theme: string; stage: string; owner: string; otd: string };
const NO_FILTER: JalonFilters = { status: "", theme: "", stage: "", owner: "", otd: "" };

function RoadmapEditor({ squad, year, onChange, readonly, t, roadmap, squads, tribes }: any) {
  const [editing, setEditing] = useState<Partial<RoadmapItem> | null>(null);
  // Sort and search are reading preferences, kept per browser like the other lists.
  const view = useListView("entry.jalons", "order", true);
  const [flt, setFlt] = useState<JalonFilters>(NO_FILTER);
  const all: RoadmapItem[] = squad.roadmap_items;
  const themes = Array.from(new Set(all.map((r) => r.theme).filter(Boolean) as string[])).sort((a, b) => a.localeCompare(b));
  const owners = Array.from(new Set(all.map((r) => r.owner).filter(Boolean) as string[])).sort((a, b) => a.localeCompare(b));
  const byText = (a?: string | null, b?: string | null) => (a || "~").localeCompare(b || "~", undefined, { sensitivity: "base" });
  const sorts: SortSpec<RoadmapItem>[] = [
    { key: "order", label: t("jalon.sort_order"), cmp: (a, b) => a.display_order - b.display_order || a.id - b.id },
    { key: "status", label: t("jalon.sort_status"), cmp: (a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || byText(a.title, b.title) },
    { key: "title", label: t("jalon.sort_title"), cmp: (a, b) => byText(a.title, b.title) },
    { key: "theme", label: t("jalon.sort_theme"), cmp: (a, b) => byText(a.theme, b.theme) || byText(a.title, b.title) },
    { key: "owner", label: t("jalon.sort_owner"), cmp: (a, b) => byText(a.owner, b.owner) || byText(a.title, b.title) },
    { key: "stage", label: t("jalon.sort_stage"), cmp: (a, b) => byText(a.release_stage, b.release_stage) || byText(a.title, b.title) },
  ];
  const filtering = !!view.query.trim() || Object.values(flt).some(Boolean);
  /** The milestones of a quarter this toolbar lets through, in its order. */
  function shown(items: RoadmapItem[]): RoadmapItem[] {
    const needle = view.query.trim().toLowerCase();
    let out = items.filter((r) =>
      (!needle || [r.title, r.theme, r.owner, r.description, r.otd_label, r.squad_otd_label, r.dependency_label]
        .some((x) => (x || "").toLowerCase().includes(needle)))
      && (!flt.status || r.status === flt.status)
      && (!flt.theme || r.theme === flt.theme)
      && (!flt.stage || r.release_stage === flt.stage)
      && (!flt.owner || (flt.owner === "-" ? !r.owner : r.owner === flt.owner))
      && (!flt.otd || (flt.otd === "linked" ? !!(r.otd_id || r.squad_otd_id) : !(r.otd_id || r.squad_otd_id))));
    const spec = sorts.find((s) => s.key === view.sort) ?? sorts[0];
    out = [...out].sort(spec.cmp);
    if (view.desc) out.reverse();
    return out;
  }
  const matching = filtering ? [1, 2, 3, 4].reduce((n, q) => n + shown(all.filter((r) => r.quarter === q)).length, 0) : all.length;
  const sel = (key: keyof JalonFilters, label: string, options: [string, string][]) => (
    <div className="tb-field">
      <label htmlFor={`jf-${key}`} className="tb-label">{label}</label>
      <select id={`jf-${key}`} className={flt[key] ? "tb-on" : ""} value={flt[key]}
              onChange={(e) => setFlt((f) => ({ ...f, [key]: e.target.value }))}>
        <option value="">{t("jalon.filter_all")}</option>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  );
  // A failed save is shown in the milestone window (it stayed open, silently).
  const [err, setErr] = useState<string | null>(null);
  const fail = (e: unknown) => setErr(errorText(e));

  async function save(data: Partial<RoadmapItem>) {
    setErr(null);
    try {
      if (data.id) {
        const { id, squad_id, ...patch } = data as any;
        await api.put(`/api/roadmap-items/${data.id}`, patch);
      } else {
        await api.post("/api/roadmap-items", { ...data, squad_id: squad.id });
      }
      setEditing(null);
      onChange();
    } catch (e) { fail(e); }
  }
  async function remove(item: RoadmapItem) {
    setErr(null);
    try {
      await api.del(`/api/roadmap-items/${item.id}`);
      onChange();
    } catch (e) { fail(e); }
  }

  return (
    <Card title={t("squad.roadmap", { year })} hint={t("entry.roadmap_hint")}>
      {err && !editing && <ErrorBanner message={err} />}
      {all.length > 0 && (
        <div className="toolbar">
          <div className="toolbar-fields">
            <div className="tb-field tb-search">
              <label htmlFor="jalon-search" className="tb-label">{t("list.search")}</label>
              <input id="jalon-search" type="search" value={view.query} placeholder={t("jalon.search_ph")}
                     className={view.query ? "tb-on" : ""} onChange={(e) => view.setQuery(e.target.value)} />
            </div>
            {sel("status", t("jalon.status"), ["blocked", "at_risk", "on_track", "done"].map((s) => [s, roadmap(s)]))}
            {themes.length > 1 && sel("theme", t("jalon.theme"), themes.map((x) => [x, x]))}
            {sel("stage", t("jalon.stage"), [["EA", "EA"], ["GA", "GA"], ["NP", t("jalon.stage_np")], ["OT", t("jalon.stage_ot")]])}
            {owners.length > 0 && sel("owner", t("jalon.owner"), [...owners.map((x) => [x, x] as [string, string]), ["-", t("jalon.filter_no_owner")]])}
            {sel("otd", "OTD", [["linked", t("jalon.filter_otd_linked")], ["none", t("jalon.filter_otd_none")]])}
          </div>
          <div className="toolbar-foot">
            <span className="small muted">
              {filtering ? t("jalon.filter_count", { n: matching, total: all.length }) : t("jalon.count_all", { n: all.length })}
            </span>
            <span className="toolbar-sort">
              <label htmlFor="jalon-sort" className="small muted">{t("list.sort")}</label>
              <select id="jalon-sort" value={view.sort} onChange={(e) => view.pickSort(e.target.value)}>
                {sorts.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
              <button type="button" className="btn-secondary btn-sm tb-dir" onClick={() => view.pickSort(view.sort)}
                      title={t("list.sort_flip")} aria-label={t("list.sort_flip")}>
                {view.desc ? t("jalon.sort_desc") : t("jalon.sort_asc")}
              </button>
              {(filtering || view.sort !== "order" || view.desc) && (
                <button type="button" className="btn-ghost btn-sm" onClick={() => { view.reset(); setFlt(NO_FILTER); }}>{t("list.reset")}</button>
              )}
            </span>
          </div>
        </div>
      )}
      <div className="stack" style={{ gap: 12 }}>
        {[1, 2, 3, 4].map((q) => (
          <QuarterEditor
            key={q}
            shown={shown}
            filtering={filtering}
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
            onStatus={async (it: RoadmapItem, status: string) => {
              setErr(null);
              try { await api.put(`/api/roadmap-items/${it.id}`, { status }); onChange(); } catch (e) { fail(e); }
            }}
          />
        ))}
      </div>
      {editing && (
        <JalonModal jalon={editing} members={squad.members} onSave={save} error={err}
                    onDelete={editing.id ? async () => { await remove(editing as RoadmapItem); setEditing(null); } : undefined}
                    onCancel={() => { setEditing(null); setErr(null); }} t={t} roadmap={roadmap} squads={squads} tribes={tribes} currentSquadId={squad.id} />
      )}
    </Card>
  );
}

/**
 * One quarter, one row the full width: its header (progress derived from the
 * milestones, the N/A box when it has none, the add button), then a line per
 * milestone in aligned columns: status, theme, title, stage, owner, status menu.
 * Rows are clickable to edit unless read-only. Progress is derived, never entered.
 */
function QuarterEditor({ squad, year, quarter, readonly, t, roadmap, onAdd, onEdit, onStatus, onChange, shown, filtering }: any) {
  // Progress counts every milestone of the quarter; the list shows what the
  // toolbar lets through, in its order.
  const items = squad.roadmap_items.filter((r: RoadmapItem) => r.quarter === quarter);
  const visible: RoadmapItem[] = shown ? shown(items) : items;
  // Progress is auto-derived from milestone advancement (share done), never typed.
  const total = items.length;
  const done = items.filter((r: RoadmapItem) => r.status === "done").length;
  const pct = total ? Math.round((100 * done) / total) : 0;
  // A quarter without jalons is not "0 % done": it is either nothing planned, or
  // a quarter that does not concern the squad (it started in Q3), said N/A.
  const na = !!squad.quarter_progress?.[String(quarter)]?.not_applicable;
  const [naErr, setNaErr] = useState<string | null>(null);
  async function setNa(v: boolean) {
    setNaErr(null);
    try {
      await api.put(`/api/squads/${squad.id}/quarter-progress`, { year, quarter, not_applicable: v });
      onChange();
    } catch (e) { setNaErr(errorText(e)); }
  }
  const now = new Date();
  const isCurrent = now.getFullYear() === year && Math.floor(now.getMonth() / 3) + 1 === quarter;

  return (
    <section className={`q-row${isCurrent ? " current" : ""}`}>
      <div className="q-head">
        <span className="q-pill">Q{quarter}</span>
        <span className="strong" style={{ color: "var(--navy)" }}>{year}</span>
        {isCurrent && <span className="badge badge-navy">{t("entry.q_current")}</span>}
        {total > 0 ? (
          <span className="q-progress" title={t("entry.progress_auto")}>
            <span className="q-bar" aria-label={`${pct}%`}><span style={{ width: `${pct}%` }} /></span>
            <span className="small muted">{pct}%, {done}/{total}</span>
          </span>
        ) : (
          <span className="small muted" title={t("entry.q_na_hint")}>{na ? t("entry.q_na_short") : t("entry.q_nothing")}</span>
        )}
        <span style={{ flex: 1 }} />
        {total === 0 && (
          <label className="inline small" style={{ gap: 6 }} title={t("entry.q_na_hint")}>
            <input type="checkbox" disabled={readonly} checked={na} onChange={(e) => setNa(e.target.checked)} />
            {t("entry.q_na_box")}
          </label>
        )}
        {!readonly && (
          <button className="btn-secondary btn-sm" onClick={onAdd}>+ {t("jalon.add")}</button>
        )}
      </div>
      {naErr && <div className="small" style={{ color: "var(--red)" }}>{naErr}</div>}
      {filtering && items.length > 0 && visible.length === 0 && (
        <div className="small muted" style={{ padding: "4px 2px" }}>{t("jalon.filter_none_here", { n: items.length })}</div>
      )}
      {visible.length > 0 && (
        <div className="q-items">
          {visible.map((r: RoadmapItem) => (
            <div key={r.id} className="q-item">
              <Dot status={roadmapRag(r.status)} />
              <span className="q-theme">{r.theme ? <span className="badge badge-grey">{r.theme}</span> : null}</span>
              {/* The title opens the milestone: a button, so the keyboard reaches it. */}
              <button type="button" className="btn-ghost q-title" disabled={readonly}
                      onClick={() => onEdit(r)} title={t("jalon.details")}>
                {r.title}
              </button>
              <span><StageBadge stage={r.release_stage} other={r.release_stage_other} /></span>
              <span className="small muted q-owner">{r.owner ?? ""}</span>
              {/* The weekly gesture, in one click: the status, changed where it shows. */}
              {!readonly ? (
                <select className="small" aria-label={`${t("jalon.status")} ${r.title}`} value={r.status}
                        onChange={(e) => onStatus(r, e.target.value)}>
                  {["on_track", "at_risk", "blocked", "done"].map((st) => <option key={st} value={st}>{roadmap(st)}</option>)}
                </select>
              ) : <span className="small">{roadmap(r.status)}</span>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * Milestone create/edit form (modal). Beyond the plain fields it offers theme
 * reuse (datalist of existing themes), owner suggestions from squad members,
 * optional link to an objective, and a dependency that can be free text, another
 * squad, or a tribe (`depKind`). Title + theme are required to save.
 */
/** An OTD as the milestone window lists it (GET /api/otds). */
type OtdChoice = { id: number; tribe_id: number; year: number; title: string; scope?: "management" | "squad";
  squad_id?: number | null; owner_user_id?: number | null; committed_date?: string | null };

/**
 * The two commitments a milestone can deliver, picked from two lists: the
 * management OTD (fixed by the tribe leader) and the squad's own OTD. It is the
 * same link as the one the OTD window sets, seen from the milestone. The rights
 * mirror the server (roadmap.may_link_otd): the squad's own OTDs for whoever
 * reports for it; a management OTD for its tribe leader and the admin, and for
 * the squad leader when it was fixed on their squad or assigned to them.
 */
function JalonOtdLinks({ f, set, squadId, tribeId, t }: {
  f: Partial<RoadmapItem>; set: (k: string, v: any) => void; squadId: number; tribeId?: number; t: any;
}) {
  const { user } = useAuth();
  const { formatDate } = useI18n();
  const [otds, setOtds] = useState<OtdChoice[] | null>(null);
  const year = f.year;
  useEffect(() => {
    if (!year) return;
    let alive = true;
    api.get<OtdChoice[]>(`/api/otds?year=${year}${tribeId ? `&tribe_id=${tribeId}` : ""}`)
      .then((r) => { if (alive) setOtds(r); }).catch(() => { if (alive) setOtds([]); });
    return () => { alive = false; };
  }, [year, tribeId]);
  if (!otds) return null;
  const label = (o: OtdChoice) => o.committed_date ? `${o.title} (${formatDate(o.committed_date)})` : o.title;
  const mayManagement = (o: OtdChoice) => user?.role === "admin"
    || (user?.role === "tribe_leader" && user?.tribe_id === o.tribe_id)
    || o.squad_id === squadId || (o.owner_user_id != null && o.owner_user_id === user?.id);
  const mgmt = otds.filter((o) => (o.scope ?? "management") === "management" && (!tribeId || o.tribe_id === tribeId));
  const mgmtOptions = mgmt.filter(mayManagement);
  const current = mgmt.find((o) => o.id === f.otd_id);
  // Linked by the tribe leader to a commitment of the whole tribe: shown, not changeable here.
  const mgmtLocked = !!current && !mayManagement(current);
  const own = otds.filter((o) => o.scope === "squad" && o.squad_id === squadId);
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="small strong">{t("jalon.otd_section")}</div>
      <div className="row">
        <div className="col">
          <label htmlFor="jalon-otd">{t("jalon.otd_management")}</label>
          <select id="jalon-otd" value={f.otd_id ?? ""} disabled={mgmtLocked || (!mgmtOptions.length && !current)}
                  onChange={(e) => set("otd_id", e.target.value ? Number(e.target.value) : null)}>
            <option value="">{mgmtOptions.length || current ? t("jalon.otd_none") : t("jalon.otd_no_management")}</option>
            {mgmtLocked && current && <option value={current.id}>{label(current)}</option>}
            {mgmtOptions.map((o) => <option key={o.id} value={o.id}>{label(o)}</option>)}
          </select>
          {mgmtLocked && <div className="small muted" style={{ marginTop: 4 }}>{t("jalon.otd_locked")}</div>}
        </div>
        <div className="col">
          <label htmlFor="jalon-squad-otd">{t("jalon.otd_squad")}</label>
          <select id="jalon-squad-otd" value={f.squad_otd_id ?? ""} disabled={!own.length && !f.squad_otd_id}
                  onChange={(e) => set("squad_otd_id", e.target.value ? Number(e.target.value) : null)}>
            <option value="">{own.length ? t("jalon.otd_none") : t("jalon.otd_no_squad")}</option>
            {own.map((o) => <option key={o.id} value={o.id}>{label(o)}</option>)}
          </select>
        </div>
      </div>
      <div className="small muted">{t("jalon.otd_hint")}</div>
    </div>
  );
}

function JalonModal({ jalon, members, onSave, onCancel, onDelete, error, t, roadmap, squads, tribes, currentSquadId }: any) {
  const [f, setF] = useState<Partial<RoadmapItem>>(jalon);
  const [saving, setSaving] = useState(false);
  // Anything typed: the window no longer closes on a stray click or Escape.
  const dirty = JSON.stringify(f) !== JSON.stringify(jalon);
  // Deleting asks once more, inside the window (a browser dialog is not used here).
  const [confirmDel, setConfirmDel] = useState(false);
  const [themes, setThemes] = useState<string[]>([]);
  const set = (k: string, v: any) => setF((p) => ({ ...p, [k]: v }));
  // The owner: the squad's members first, then anyone with an account in the app.
  const people = usePeople("all");
  const memberNames: string[] = members.map((m: Member) => m.full_name);
  const ownerNames = [...memberNames, ...people.map((p) => p.name).filter((n) => !memberNames.includes(n))];
  // Existing themes for reuse: pick one from the list or type a new one.
  useEffect(() => { api.get<string[]>("/api/roadmap-items/themes").then(setThemes).catch(() => {}); }, []);
  // A milestone may depend on any squad, of any tribe: /api/squads only lists
  // one's own scope, so a dependency on another tribe's squad showed "none".
  type SquadName = { id: number; name: string; tribe_id: number; tribe_name: string };
  const [allSquads, setAllSquads] = useState<SquadName[] | null>(null);
  useEffect(() => { api.get<SquadName[]>("/api/tribes/squad-names").then(setAllSquads).catch(() => setAllSquads(null)); }, []);
  const ownTribe = squads.find((s: Squad) => s.id === currentSquadId)?.tribe_id;
  const depSquads: { id: number; label: string }[] = (allSquads
    ? [...allSquads].sort((a, b) => Number(b.tribe_id === ownTribe) - Number(a.tribe_id === ownTribe))
        .map((s) => ({ id: s.id, label: s.tribe_id === ownTribe ? s.name : `${s.name} (${s.tribe_name})` }))
    : squads.map((s: Squad) => ({ id: s.id, label: s.name })))
    .filter((s: { id: number }) => s.id !== currentSquadId);
  const field = (label: string, key: string, area = false) => (
    <div>
      <label htmlFor={`jf-${key}`}>{label}</label>
      {area ? (
        <textarea id={`jf-${key}`} rows={2} value={(f as any)[key] ?? ""} onChange={(e) => set(key, e.target.value)} />
      ) : (
        <input id={`jf-${key}`} value={(f as any)[key] ?? ""} maxLength={key === "title" ? 500 : 2000} onChange={(e) => set(key, e.target.value)} />
      )}
    </div>
  );
  return (
    <Modal title={f.id ? t("jalon.edit") : t("jalon.new")} onClose={onCancel} dirty={dirty} width={560}>
        <div className="stack" style={{ gap: 10 }}>
          {/* The quarter and the year can change: a milestone that slips from Q4 to
              next year's Q1 moves, it is not recreated (and keeps its links). */}
          <div className="row" style={{ gap: 12 }}>
            <div style={{ width: 140 }}>
              <label htmlFor="jalon-quarter">{t("jalon.quarter")}</label>
              <select id="jalon-quarter" value={f.quarter ?? 1} onChange={(e) => set("quarter", Number(e.target.value))}>
                {[1, 2, 3, 4].map((q) => <option key={q} value={q}>Q{q}</option>)}
              </select>
            </div>
            <div style={{ width: 140 }}>
              <label htmlFor="jalon-year">{t("entry.header_year")}</label>
              <select id="jalon-year" value={f.year ?? jalon.year} onChange={(e) => set("year", Number(e.target.value))}>
                {[(jalon.year ?? 0), (jalon.year ?? 0) + 1].map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
          </div>
          {field(t("jalon.title") + " *", "title")}
          <div>
            <label htmlFor="jalon-theme">{t("jalon.theme") + " *"}</label>
            {/* The themes already used, or a new one typed. */}
            <PickOrType id="jalon-theme" maxLength={120} textPlaceholder={t("jalon.theme_ph")}
              groups={[{ options: themes.map((th) => ({ value: th, label: th })) }]}
              picked={themes.includes(f.theme ?? "") ? f.theme : null}
              text={themes.includes(f.theme ?? "") ? "" : f.theme}
              onPick={(v) => set("theme", v ?? "")} onText={(txt) => set("theme", txt)} />
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
                <option value="EA">EA ({t("jalon.stage_ea")})</option>
                <option value="GA">GA ({t("jalon.stage_ga")})</option>
                <option value="NP">{t("jalon.stage_np")}</option>
                <option value="OT">{t("jalon.stage_ot")}</option>
              </select>
              {f.release_stage === "OT" && (
                <input style={{ marginTop: 6 }} maxLength={80} required placeholder={t("jalon.stage_other_ph")}
                       aria-label={t("jalon.stage_other_ph")} value={f.release_stage_other ?? ""}
                       onChange={(e) => set("release_stage_other", e.target.value)} />
              )}
              {(f.release_stage === "NP" || f.release_stage === "OT") && (
                <div className="small muted" style={{ marginTop: 4 }}>{t("jalon.stage_no_tag")}</div>
              )}
            </div>
          </div>
          <div className="row">
            <div className="col">
              <label htmlFor="jalon-owner">{t("jalon.owner")}</label>
              {/* The squad's members, else a name typed freely (someone outside the team). */}
              <PickOrType id="jalon-owner" maxLength={255} textPlaceholder={t("jalon.owner_ph")}
                groups={[
                  { label: t("pick.group_team"), options: members.map((m: Member) => ({ value: m.full_name, label: m.role_title ? `${m.full_name} (${m.role_title})` : m.full_name })) },
                  { label: t("pick.group_others"), options: ownerNames.slice(memberNames.length).map((n) => ({ value: n, label: n })) },
                ]}
                picked={ownerNames.includes(f.owner ?? "") ? f.owner : null}
                text={ownerNames.includes(f.owner ?? "") ? "" : f.owner}
                onPick={(v) => set("owner", v ?? "")} onText={(txt) => set("owner", txt)} />
            </div>
          </div>
          <JalonOtdLinks f={f} set={set} squadId={currentSquadId}
                         tribeId={squads.find((s: Squad) => s.id === currentSquadId)?.tribe_id} t={t} />
          {field(t("jalon.desc"), "description", true)}
          {field(t("jalon.success"), "success_criteria", true)}
          {field(t("jalon.benefit"), "user_benefit", true)}
          <JalonDependencies f={f} setF={setF} depSquads={depSquads} tribes={tribes} t={t} />
          {field(t("jalon.risks"), "risks", true)}
        </div>
        {error && <div style={{ marginTop: 10 }}><ErrorBanner message={error} /></div>}
        <div className="between" style={{ gap: 8, marginTop: 14, alignItems: "center" }}>
          <span>
            {onDelete && !confirmDel && (
              <button className="btn-ghost btn-sm" style={{ color: "var(--red)" }} onClick={() => setConfirmDel(true)}>{t("jalon.delete")}</button>
            )}
            {onDelete && confirmDel && (
              <span className="inline" style={{ gap: 6 }}>
                <span className="small">{t("jalon.delete_confirm")}</span>
                <button className="btn-danger btn-sm" onClick={onDelete}>{t("action.delete")}</button>
                <button className="btn-ghost btn-sm" onClick={() => setConfirmDel(false)}>{t("action.cancel")}</button>
              </span>
            )}
          </span>
          <span className="inline" style={{ gap: 8 }}>
            <button className="btn-secondary" onClick={onCancel}>{t("action.cancel")}</button>
            {/* One save at a time: a double click used to create the milestone twice. */}
            <button onClick={async () => { setSaving(true); try { await onSave(f); } finally { setSaving(false); } }}
                    disabled={saving || !f.title?.trim() || !f.theme?.trim()}>
              {saving ? t("common.saving") : t("action.save")}
            </button>
          </span>
        </div>
    </Modal>
  );
}

/**
 * The dependencies of a milestone, as a list: as many tribes, squads and free
 * texts (a vendor, a team outside the app) as it waits on. Each one is a chip
 * that can be removed; a list adds a tribe or a squad, a field adds a text.
 * The list is what the server keeps (dependency_list); the first entry is also
 * the milestone's single dependency for the older screens.
 */
function JalonDependencies({ f, setF, depSquads, tribes, t }: {
  f: Partial<RoadmapItem>; setF: (fn: (p: Partial<RoadmapItem>) => Partial<RoadmapItem>) => void;
  depSquads: { id: number; label: string }[]; tribes: Tribe[]; t: any;
}) {
  const [text, setText] = useState("");
  // A milestone written before the list carries its one dependency in the single fields.
  const deps: Dependency[] = f.dependency_list ?? (
    f.dependency_kind === "squad" && f.dependency_squad_id ? [{ kind: "squad", squad_id: f.dependency_squad_id }]
    : f.dependency_kind === "tribe" && f.dependency_tribe_id ? [{ kind: "tribe", tribe_id: f.dependency_tribe_id }]
    : f.dependencies?.trim() ? [{ kind: "text", text: f.dependencies.trim() }] : []);
  const label = (d: Dependency) => d.kind === "squad" ? (depSquads.find((s) => s.id === d.squad_id)?.label ?? d.label ?? "?")
    : d.kind === "tribe" ? (tribes.find((x) => x.id === d.tribe_id)?.name ?? d.label ?? "?") : (d.text ?? "");
  const has = (d: Dependency) => deps.some((x) => x.kind === d.kind && x.squad_id === d.squad_id && x.tribe_id === d.tribe_id
    && (x.text ?? "").toLowerCase() === (d.text ?? "").toLowerCase());
  const setList = (list: Dependency[]) => setF((p) => ({ ...p, dependency_list: list }));
  const add = (d: Dependency) => { if (!has(d)) setList([...deps, d]); };
  function addText() {
    const v = text.trim();
    if (!v) return;
    add({ kind: "text", text: v });
    setText("");
  }
  return (
    <div>
      <label htmlFor="jalon-dep-add">{t("jalon.deps")}</label>
      {deps.length > 0 ? (
        <div className="dep-chips">
          {deps.map((d, i) => (
            <span key={`${d.kind}-${d.squad_id ?? d.tribe_id ?? d.text}`} className={`dep-chip dep-${d.kind}`}>
              <span className="dep-kind">{d.kind === "text" ? t("jalon.dep_other") : t(`jalon.dep_${d.kind}`)}</span>
              {label(d)}
              <button type="button" aria-label={t("jalon.dep_remove", { name: label(d) })}
                      onClick={() => setList(deps.filter((_, k) => k !== i))}>✕</button>
            </span>
          ))}
        </div>
      ) : <div className="small muted" style={{ marginBottom: 6 }}>{t("jalon.dep_none")}</div>}
      <div className="dep-add">
        <select id="jalon-dep-add" value="" onChange={(e) => {
          const v = e.target.value;
          if (v.startsWith("t:")) add({ kind: "tribe", tribe_id: Number(v.slice(2)) });
          else if (v.startsWith("s:")) add({ kind: "squad", squad_id: Number(v.slice(2)) });
        }}>
          <option value="">{t("jalon.dep_add")}</option>
          <optgroup label={t("jalon.dep_tribe")}>
            {tribes.filter((tr) => !has({ kind: "tribe", tribe_id: tr.id })).map((tr) => (
              <option key={tr.id} value={`t:${tr.id}`}>{tr.name}</option>
            ))}
          </optgroup>
          <optgroup label={t("jalon.dep_squad")}>
            {depSquads.filter((s) => !has({ kind: "squad", squad_id: s.id })).map((s) => (
              <option key={s.id} value={`s:${s.id}`}>{s.label}</option>
            ))}
          </optgroup>
        </select>
        <span className="inline" style={{ gap: 6, flex: 1 }}>
          <input value={text} maxLength={500} placeholder={t("jalon.dep_text_ph")} aria-label={t("jalon.dep_text_ph")}
                 onChange={(e) => setText(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addText(); } }} />
          <button type="button" className="btn-secondary btn-sm" disabled={!text.trim()} onClick={addText}>{t("jalon.dep_add_text")}</button>
        </span>
      </div>
    </div>
  );
}

/**
 * KPI editor: name, trend, current/target/unit per KPI. Read-only mode disables
 * inputs. Only rendered when the squad has KPIs enabled and the module is on.
 */
export function KpisEditor({ squad, onChange, readonly, t, trend }: any) {
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  // These fields save when one leaves them: say it, or nobody knows it left.
  const [saved, setSaved] = useState(false);
  const trends: Trend[] = ["on_target", "under_pressure", "missed"];
  // Every write reports its failure here instead of an unhandled promise.
  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn(); onChange();
      setSaved(true); setTimeout(() => setSaved(false), 1800);
    } catch (e) { setErr(errorText(e)); reportSaveError(errorText(e)); }
  }
  // The KPI whose deletion waits for a second click.
  const [deleting, setDeleting] = useState<number | null>(null);
  // A name left blank is refused here, in words, and put back.
  function saveName(input: HTMLInputElement, k: Kpi) {
    const v = input.value.trim();
    if (!v) { setErr(t("entry.kpi_name_required")); input.value = k.name; return; }
    if (v !== k.name) update(k, { name: v });
  }
  // A number field: sent when readable, refused (and put back) when not.
  function saveNumber(input: HTMLInputElement, k: Kpi, key: "current_value" | "target_value") {
    const v = num(input.value);
    if (v === undefined) {
      setErr(t("entry.kpi_bad_number"));
      input.value = k[key] == null ? "" : String(k[key]);
      return;
    }
    if (v === (k[key] ?? null)) return;
    update(k, { [key]: v } as Partial<Kpi>);
  }
  // Parse a numeric input into a number or null (blank / non-numeric -> null).
  // "12,5" is a number in French: accept the comma. An unreadable value is
  // refused with a message instead of silently sent as empty (the value vanished).
  const num = (v: string): number | null | undefined => {
    const x = v.trim().replace(/\s/g, "").replace(",", ".");
    if (x === "") return null;
    const n = Number(x);
    return Number.isNaN(n) ? undefined : n;
  };
  async function add() {
    if (!name.trim()) return;
    await run(async () => {
      await api.post("/api/kpis", { squad_id: squad.id, name: name.trim(), trend_status: "on_target" });
      setName("");
    });
  }
  const update = (k: Kpi, patch: Partial<Kpi>) => run(() => api.put(`/api/kpis/${k.id}`, patch));
  const remove = (k: Kpi) => run(() => api.del(`/api/kpis/${k.id}`));
  return (
    <Card title={t("squad.kpis")} hint={t("entry.kpi_hint")}>
      <>
          {err && <ErrorBanner message={err} />}
          {saved && <div className="small" style={{ color: "var(--green)" }}>{t("common.saved")}</div>}
          {squad.kpis.map((k: Kpi) => (
            <div key={k.id} className="item-row" style={{ flexWrap: "wrap" }}>
              {readonly ? <span className="grow" style={{ minWidth: 140 }}>{k.name}</span> : (
                <input className="grow" style={{ minWidth: 140 }} aria-label={t("entry.kpi_name")} defaultValue={k.name} maxLength={255} onBlur={(e) => saveName(e.target, k)} />
              )}
              <select className="w-auto" style={{ maxWidth: 150 }} value={k.trend_status} disabled={readonly} onChange={(e) => update(k, { trend_status: e.target.value as Trend })}>
                {trends.map((tr) => (<option key={tr} value={tr}>{trend(tr)}</option>))}
              </select>
              <input className="w-auto" style={{ width: 80 }} placeholder={t("kpi.value_ph")} aria-label={t("kpi.value_ph")} disabled={readonly} defaultValue={k.current_value ?? ""} onBlur={(e) => saveNumber(e.target, k, "current_value")} />
              <input className="w-auto" style={{ width: 80 }} placeholder={t("kpi.target_ph")} aria-label={t("kpi.target_ph")} disabled={readonly} defaultValue={k.target_value ?? ""} onBlur={(e) => saveNumber(e.target, k, "target_value")} />
              <input className="w-auto" style={{ width: 80 }} placeholder={t("kpi.unit_ph")} aria-label={t("kpi.unit_ph")} disabled={readonly} maxLength={50} defaultValue={k.unit ?? ""} onBlur={(e) => e.target.value !== (k.unit ?? "") && update(k, { unit: e.target.value || null })} />
              {!readonly && (deleting === k.id ? (
                <span className="inline" style={{ gap: 6 }}>
                  <button className="btn-danger btn-sm" onClick={() => { setDeleting(null); remove(k); }}>{t("action.delete")}</button>
                  <button className="btn-ghost btn-sm" onClick={() => setDeleting(null)}>{t("action.cancel")}</button>
                </span>
              ) : (
                <button className="btn-danger btn-sm" onClick={() => setDeleting(k.id)} aria-label={`${t("action.delete")} ${k.name}`}>✕</button>
              ))}
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

function SteercoSection({ squad, readonly, t, onStatus }: any) {
  const { lang } = useI18n();
  const [rows, setRows] = useState<PlatformStatus[] | null>(null);
  const [open, setOpen] = useState<PlatformStatus | null>(null);
  const [preview, setPreview] = useState<PlatformStatus | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const period = currentSteercoPeriod();
  const monthName = monthLongLabel(period, lang);

  // The platforms this squad feeds, with this month's status for each. The list is
  // the platforms where the squad is a contributor, not every platform of the tribe.
  async function load() {
    try {
      const all = await api.get<any[]>("/api/steerco/platforms");
      // Contribuer a une plateforme dont le steerco est coupe ne donne rien a
      // saisir: la ligne aurait ouvert un wizard que l'API refuse.
      const mine = all.filter((p) => p.steerco_enabled !== false
        && (p.contributors ?? []).some((c: any) => c.id === squad.id));
      const out = await Promise.all(mine.map(async (p) => {
        const r = await api.get<any>(`/api/steerco/platform/${p.id}?period=${encodeURIComponent(period)}`);
        return {
          id: p.id, name: p.name, filled: !!r.filled, updated_at: r.updated_at ?? null,
          updated_by: r.updated_by ?? null, missing: r.missing ?? [], contributors: p.contributors ?? [],
        } as PlatformStatus;
      }));
      setRows(out);
      // This month filled for all of them (the squad's part at least): the step is done.
      onStatus?.(out.length > 0 ? out.every((r) => r.filled || !r.missing.includes(squad.name)) : null);
      setLoadErr(null);
    } catch (e) {
      // A failed load is an error, not "no platform yet, ask your tribe leader".
      setLoadErr(e instanceof Error && e.message ? e.message : t("common.error"));
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [squad.id]);

  if (loadErr) return <ErrorBanner message={loadErr} />;
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
        // Done for THIS squad when its own items are in: another contributor
        // having saved the platform used to read "already sent, nothing to do"
        // right above "waiting on: this squad".
        const mineDone = p.filled && !p.missing.includes(squad.name);
        const when = p.updated_at ? new Date(p.updated_at).toLocaleDateString(lang === "fr" ? "fr-FR" : "en-GB", { day: "2-digit", month: "2-digit", year: "numeric" }) : "";
        const by = p.updated_by ? t("steerco.done_by", { name: p.updated_by }) : "";
        return (
          <div key={p.id} className={`sc-status ${mineDone ? "done" : "todo"}`} style={{ marginBottom: 8 }}>
            <span className="sc-status-ic">{mineDone ? "✓" : "○"}</span>
            <div className="stack" style={{ gap: 2 }}>
              <div className="strong">{p.name}, {mineDone ? t("steerco.done_title", { month: monthName }) : t("steerco.todo_title", { month: monthName })}</div>
              <div className="small muted">
                {mineDone
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
  // Reporting on another year than the current one: the week of today means
  // nothing for it, the year is what is being filled.
  const otherYear = squad.year !== now.getFullYear();
  return (
    <div className="reporting-banner">
      <div className="rb-main">
        <div className="rb-eyebrow">{t("entry.header_eyebrow")}</div>
        <div className="rb-title">{squad.name}</div>
        <div className="rb-sub">
          {otherYear ? t("entry.header_other_year", { year: squad.year }) : t("entry.header_week", {
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


