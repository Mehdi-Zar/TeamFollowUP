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
import { Link, useSearchParams } from "react-router-dom";
import { api, errorText, reportSaveError } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { Kpi, Member, RoadmapItem, Squad, SquadDetail, Tribe, Trend, Role } from "../types";
import { Dot, Spinner, ErrorBanner, EmptyState, Modal, SectionCard as Card } from "../components/ui";
import { QuarterProgressEditor } from "../components/EntryExtras";
import TeamMood, { moodAge, WEEKLY_STALE_DAYS } from "../components/TeamMood";
import KeyMessagesPanel from "../components/KeyMessagesPanel";
import { OtdPanel } from "../components/OtdPanel";
import { canEditSquad, contributesTo, leadsSquad } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";
import { roadmapRag } from "../labels";
import { currentSteercoPeriod, monthLongLabel } from "../steerco";
import SteercoWizard, { SteercoPreviewModal } from "../components/SteercoWizard";


/**
 * Reporting root. Owns the squad/year selection, loads the selected SquadDetail,
 * and orchestrates the section editors plus the submit-snapshot flow. Read-only
 * when the viewer cannot write to the squad.
 */
export default function EntryPage() {
  const { user, effectiveRole, can } = useAuth();
  // The team is set up in My squads: the link only for whoever may open it (a
  // contributor does the reporting, not the team).
  const teamLink = (id: number) => (can("mysquads") ? `/mes-squads?squad=${id}&step=team` : undefined);
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
  // A link that names the year (?year=, from the squad page) wins over the default.
  const askedYear = Number(params.get("year")) || null;
  const [year, setYear] = useState<number>(askedYear ?? default_year);
  const [yearTouched, setYearTouched] = useState(askedYear !== null);
  useEffect(() => { if (!yearTouched) setYear(default_year); }, [default_year]);
  const [squad, setSquad] = useState<SquadDetail | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [recapError, setRecapError] = useState<string | null>(null);
  const [justSubmitted, setJustSubmitted] = useState(false);
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

  function flash(m: string) {
    setMessage(m);
    setTimeout(() => setMessage(null), 3000);
  }
  async function confirmSubmit() {
    if (squadId === null) return;
    setRecapError(null);
    try {
      await api.post(`/api/squads/${squadId}/snapshots`, { year });
      setRecap(false);
      setJustSubmitted(true);
      flash(t("entry.submit_ok"));
      reload();
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
    ...(roadmapOn ? [{
      key: "jalons",
      state: stateOf(squad.roadmap_items.length > 0, "roadmap"),
      // Milestones and key messages belong to the squad's own leadership: the
      // server refuses the tribe leader (assert_leads_squad), so does the screen.
      node: <RoadmapEditor squad={squad} year={year} onChange={reload} readonly={!ownsSquad}
                           t={t} roadmap={roadmap} squads={squads} tribes={tribes} />,
    }] : []),
    // Les engagements, tout de suite apres les jalons: on y rattache ceux qu'on
    // vient de saisir, et l'ecran d'a cote est celui ou ils sont encore en tete.
    // L'engagement de la squad s'ecrit ici; celui du management se lit seulement,
    // et le panneau montre aussi ceux de la tribe, replies.
    {
      key: "otd",
      state: stateOf((squad.otd_count ?? 0) > 0, "otds", true),
      node: <OtdPanel squad={squad} canManage={false} canOwn={ownsSquad} onChange={reload} />,
    },
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
          <SubmitChecklist squad={squad} t={t} flags={{ roadmapOn, progressOn, kpisOn }}
                           teamTo={teamLink(squad.id)} />
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
      {message && (
        <div className="banner banner-green">
          {message}
          {/* Right after a submission: where to see what changed. */}
          {justSubmitted && squad && (
            <> <Link to={`/squads/${squad.id}?year=${year}#history`}>{t("entry.see_history")}</Link></>
          )}
        </div>
      )}

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
                                      flags={{ roadmapOn, progressOn, kpisOn }} teamTo={teamLink(squad.id)}
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
 * KPI ni membre declare. Elles sont montrees sur la derniere etape, la ou l'on
 * peut encore y faire quelque chose, et non plus seulement dans la fenetre de
 * confirmation.
 */
function SubmitChecklist({ squad, t, flags, teamTo }: {
  squad: any; t: (k: string) => string;
  flags: { roadmapOn: boolean; progressOn: boolean; kpisOn: boolean }; teamTo?: string;
}) {
  // Only what this screen lets one fill, for the services that are on: the
  // progress percentage is computed (its comment is what one writes), and a KPI
  // line only exists when the squad tracks KPIs.
  const items: Array<[boolean, string, string | undefined]> = [
    ...(flags.roadmapOn ? [[squad.roadmap_items.length > 0, t("entry.check.jalons"), undefined] as [boolean, string, undefined]] : []),
    ...(flags.progressOn ? [[[1, 2, 3, 4].some((q: number) => !!squad.quarter_progress[String(q)]?.comment),
                             t("entry.check.progress"), undefined] as [boolean, string, undefined]] : []),
    // Une squad peut legitimement n'avoir pris aucun engagement propre: la ligne
    // le dit, elle ne l'exige pas. Comme toutes les autres.
    [(squad.otd_count ?? 0) > 0, t("entry.check.otd"), undefined],
    ...(flags.kpisOn && squad.kpis_enabled ? [[squad.kpis.length > 0, t("entry.check.kpis"), undefined] as [boolean, string, undefined]] : []),
    [(squad.key_messages?.length ?? 0) > 0, t("entry.check.km"), undefined],
    [!!squad.mood, t("entry.check.mood"), undefined],
    // The team is not a step of this route: the line links to where it is kept,
    // "My squads", where the squad is managed.
    [squad.members.length > 0, t("entry.check.members"), teamTo],
  ];
  return (
    <div className="stack" style={{ gap: 6 }}>
      {items.map(([ok, label, act], i) => (
        <div key={i} className="inline">
          <span className={`badge ${ok ? "badge-green" : "badge-grey"}`}>{ok ? "✓" : "○"}</span>
          <span className="small">{label}</span>
          {!ok && act && <Link className="small" to={act}>{t("entry.check.fill")}</Link>}
        </div>
      ))}
    </div>
  );
}

/**
 * Pre-submit confirmation. Shows the same readiness check as the last step, then
 * asks for the snapshot; none of the lines block submission.
 */
function SubmitRecap({ squad, year, pending, formatDate, flags, teamTo, error, onConfirm, onCancel, t }: any) {
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
          <SubmitChecklist squad={squad} t={t} flags={flags} teamTo={teamTo} />
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
 * Roadmap editor: four QuarterEditor columns plus a JalonModal for create/edit.
 * `save` decides POST (new) vs PUT (existing, stripping id/squad_id). Read-only
 * mode hides add/edit affordances. Rien a exporter d'ici: cette page sert a saisir,
 * et les documents se prennent dans le menu Exporter de la barre de page, un seul
 * endroit pour tous les formats et toutes les portees.
 */
function RoadmapEditor({ squad, year, onChange, readonly, t, roadmap, squads, tribes }: any) {
  const [editing, setEditing] = useState<Partial<RoadmapItem> | null>(null);
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
 * One quarter column: its milestones and an auto-computed progress bar. Rows are
 * clickable to edit unless read-only. Progress is derived, never entered.
 */
function QuarterEditor({ squad, quarter, readonly, t, roadmap, onAdd, onEdit, onStatus }: any) {
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
          <div key={r.id} className="item-row">
            <Dot status={roadmapRag(r.status)} />
            {/* The title opens the milestone: a button, so the keyboard reaches it. */}
            <button type="button" className="btn-ghost grow small" style={{ textAlign: "left", padding: 0 }}
                    disabled={readonly} onClick={() => onEdit(r)} title={t("jalon.details")}>
              {r.theme ? <span className="strong" style={{ color: "var(--navy)" }}>{r.theme}, </span> : null}
              {r.title}
            </button>
            <span className="badge badge-navy" style={{ fontSize: 10 }}>{r.release_stage}</span>
            {/* The weekly gesture, in one click: the status, changed where it shows. */}
            {!readonly && (
              <select className="w-auto small" aria-label={`${t("jalon.status")} ${r.title}`} value={r.status}
                      onChange={(e) => onStatus(r, e.target.value)} style={{ maxWidth: 120 }}>
                {["on_track", "at_risk", "blocked", "done"].map((s) => <option key={s} value={s}>{roadmap(s)}</option>)}
              </select>
            )}
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
function JalonModal({ jalon, members, onSave, onCancel, onDelete, error, t, roadmap, squads, tribes, currentSquadId }: any) {
  const [f, setF] = useState<Partial<RoadmapItem>>(jalon);
  const [saving, setSaving] = useState(false);
  // Anything typed: the window no longer closes on a stray click or Escape.
  const dirty = JSON.stringify(f) !== JSON.stringify(jalon);
  // Deleting asks once more, inside the window (a browser dialog is not used here).
  const [confirmDel, setConfirmDel] = useState(false);
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
            <label>{t("jalon.theme") + " *"}</label>
            <input list="jalon-themes" placeholder={t("jalon.theme_ph")} maxLength={120} value={f.theme ?? ""}
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
                <option value="EA">EA ({t("jalon.stage_ea")})</option>
                <option value="GA">GA ({t("jalon.stage_ga")})</option>
              </select>
            </div>
          </div>
          <div className="row">
            <div className="col">
              <label>{t("jalon.owner")}</label>
              <input list="jalon-owners" placeholder={t("jalon.owner_ph")} maxLength={255} value={f.owner ?? ""} onChange={(e) => set("owner", e.target.value)} />
              <datalist id="jalon-owners">
                {members.map((m: Member) => <option key={m.id} value={m.full_name} />)}
              </datalist>
            </div>
          </div>
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


