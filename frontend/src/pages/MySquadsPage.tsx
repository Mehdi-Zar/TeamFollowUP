/**
 * MySquadsPage - "manage my squads", persona-aware.
 *
 * The one screen where a squad is managed: identity, leader, options, OTD,
 * initiatives, team, budget, committees. Whoever manages squads (tribe leader,
 * admin, a persona with the Squads tab) sees them all; a squad leader sees the
 * squads they lead, and only those, with what a leader may change. The squad page
 * reads all of it; the weekly content lives in the reporting.
 * Server-side permissions remain authoritative; the split here is only UX.
 */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError, errorText } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { CandidateInitiativeJalon, Initiative, Squad, SquadDetail, Tribe, User } from "../types";
import { ErrorBanner, Spinner, Modal, EmptyState, PickItem } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";
import { useConfig, useModule } from "../config";
import { OtdPanel } from "../components/OtdPanel";
import { leadsSquad } from "../perms";
import { TeamEditor } from "../components/TeamModal";
import { BudgetPanel, CommitteesPanel } from "./SquadDetailPage";


/** "My squads": the squads one manages. Whoever may manage squads (admin, tribe
 *  leader, or a persona given the Squads tab) gets the management view; anyone
 *  else the squads they lead. Chosen from those rights, not from the role name: a
 *  custom persona used to land on the tribe leader's view and meet refusals. */
export default function MySquadsPage() {
  const { user } = useAuth();
  const manages = user?.role === "admin" || user?.role === "tribe_leader";
  return manages ? <TribeLeaderSquads /> : <SquadLeaderSquads />;
}

/** The year a view reads and writes: the one a link names, else the instance's
 *  default year, followed until the viewer picks one. Returns [year, set, pick]. */
function useYear(asked: number | null): [number, (y: number) => void, (y: number) => void] {
  const { default_year } = useConfig();
  const [year, setYear] = useState<number>(asked ?? default_year);
  const [touched, setTouched] = useState(asked !== null);
  useEffect(() => { if (!touched) setYear(default_year); }, [default_year]);
  return [year, setYear, (y: number) => { setTouched(true); setYear(y); }];
}

/** Tribe-leader / admin view: create and edit squads, their OTD and initiatives. */
function TribeLeaderSquads() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  // The year the OTD and initiatives are read and written in: the instance's
  // default year, until one picks another. Without it only the server's year
  // could receive a management commitment.
  // A link may open one squad's window on one step and year (?squad=12&step=otd&year=2025).
  const [params, setParams] = useSearchParams();
  const openSquad = Number(params.get("squad")) || null;
  const openStep = (params.get("step") as SquadStep | null) ?? undefined;
  const [year, , pickYear] = useYear(Number(params.get("year")) || null);
  const [squads, setSquads] = useState<Squad[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  async function load() {
    // Each list on its own: a persona without the Accounts tab gets no user list
    // (the leader dropdowns then say so) but still manages its squads.
    const [sq, us, tr] = await Promise.allSettled([
      api.get<Squad[]>("/api/squads"), api.get<User[]>("/api/admin/users"), api.get<Tribe[]>("/api/tribes"),
    ]);
    if (sq.status === "fulfilled") setSquads(sq.value);
    else setError(sq.reason instanceof ApiError ? sq.reason.message : t("common.error"));
    if (us.status === "fulfilled") setUsers(us.value);
    // A tribe leader can only create squads in their own tribe; admins in any.
    if (tr.status === "fulfilled") setTribes(isAdmin ? tr.value : tr.value.filter((x) => x.id === user?.tribe_id));
  }
  useEffect(() => { load(); }, []);

  // Users eligible to be a squad's "responsible" (leader) in the dropdowns.
  // Anyone active may be named leader: the server promotes a member or a
  // contributor to squad leader, as for a co-leader.
  const leaders = users.filter((u) => u.status !== "disabled");

  useSetPageChrome(
    {
      title: t("mysquads.title"),
      actions: (
        <>
          <div className="seg" role="group" aria-label={t("entry.header_year")}>
            {[year - 1, year, year + 1].map((y) => (
              <button key={y} className={y === year ? "active" : ""} aria-pressed={y === year}
                      onClick={() => pickYear(y)}>{y}</button>
            ))}
          </div>
          <button className="btn btn-sm" onClick={() => setCreating(true)}>+ {t("mysquads.new")}</button>
        </>
      ),
    },
    [t, year]
  );

  if (error && !squads) return <ErrorBanner message={error} />;
  if (!squads) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {error && <ErrorBanner message={error} />}
      <div className="muted small">{t("mysquads.intro")}</div>

      {squads.length === 0 && <EmptyState message={t("mysquads.empty")} />}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
        {squads.map((s) => (
          <SquadCard key={`${s.id}-${year}`} squadId={s.id} year={year} leaders={leaders} tribes={tribes} isAdmin={isAdmin}
                     // A squad of another tribe that this tribe leader leads: led, not managed.
                     manager={isAdmin || s.tribe_id === user?.tribe_id}
                     autoOpen={openSquad === s.id} initialStep={openStep}
                     onClosed={() => { if (openSquad === s.id) setParams({}, { replace: true }); }}
                     onChanged={load} onError={setError} />
        ))}
      </div>

      {creating && (
        <CreateSquadModal
          isAdmin={isAdmin}
          tribes={tribes}
          leaders={leaders}
          defaultTribeId={user?.tribe_id ?? null}
          onClose={() => setCreating(false)}
          onCreated={() => { setCreating(false); load(); }}
          onError={setError}
        />
      )}
    </div>
  );
}

/**
 * A squad's summary card: name, leader, KPI/budget badges, and the button that
 * opens EditSquadModal (as a manager, or as the squad's own leader). Loads its own
 * SquadDetail so badges reflect the latest state.
 */
function SquadCard({ squadId, year, leaders, tribes, isAdmin, manager, autoOpen, initialStep, onClosed, onChanged, onError }: {
  squadId: number; year: number; leaders: User[]; tribes: Tribe[]; isAdmin: boolean; manager: boolean;
  autoOpen?: boolean; initialStep?: SquadStep; onClosed?: () => void;
  onChanged: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const [d, setD] = useState<SquadDetail | null>(null);
  const [edit, setEdit] = useState(!!autoOpen);

  async function load() {
    try { setD(await api.get<SquadDetail>(`/api/squads/${squadId}?year=${year}`)); }
    catch (e) { onError(errorText(e)); }
  }
  useEffect(() => { load(); }, [squadId]);
  const kpisOn = useModule()("squad_content", "kpis");
  const steercoOn = useModule()("steerco");
  if (!d) return <div className="card spinner">{t("common.loading")}</div>;

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div className="strong" style={{ fontSize: 16 }}>{d.name}</div>
        <button className="btn-secondary btn-sm" onClick={() => setEdit(true)}>✎ {manager ? t("action.edit") : t("mysquads.manage")}</button>
      </div>

      {d.leader ? (
        <div className="small muted">{t("squad.squad_leader")}{t("common.colon")}<span className="strong">{d.leader.display_name}</span></div>
      ) : (
        // Nobody leads it: nobody fills its reporting. Said, with the way to fix it.
        <button type="button" className="badge badge-orange" style={{ border: 0, cursor: "pointer", alignSelf: "flex-start" }}
                onClick={() => setEdit(true)}>{t("card.no_leader")}</button>
      )}
      {/* Co-leaders hold the same rights: the card names them too. */}
      {(d.co_leaders?.length ?? 0) > 0 && (
        <div className="small muted">
          {t("squad.co_leaders")}{t("common.colon")}<span className="strong">{d.co_leaders!.map((c) => c.display_name).join(", ")}</span>
        </div>
      )}
      {(d.contributors?.length ?? 0) > 0 && (
        <div className="small muted">
          {t("squad.contributors")}{t("common.colon")}<span className="strong">{d.contributors!.map((c) => c.display_name).join(", ")}</span>
        </div>
      )}
      <div className="small"><Link to={`/squads/${d.id}?year=${year}`}>{t("mysquads.open_squad_page")}</Link></div>

      <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
        {kpisOn && (
          <span className={`badge ${d.kpis_enabled ? "badge-green" : "badge-grey"}`}>
            {d.kpis_enabled ? t("mysquads.kpis_on") : t("mysquads.kpis_off")}
          </span>
        )}
        {steercoOn && d.steerco_enabled && <span className="badge badge-navy">{t("steerco.badge")}</span>}
        {d.budget_enabled && <span className="badge badge-navy">{t("budget.title")}</span>}
      </div>

      {steercoOn && d.steerco_enabled && (
        <div className="small muted">{t("steerco.contributes")}</div>
      )}

      {edit && (
        <EditSquadModal
          detail={d}
          year={year}
          initialStep={autoOpen ? initialStep : undefined}
          manager={manager}
          leaders={leaders}
          tribes={tribes}
          isAdmin={isAdmin}
          onClose={() => { setEdit(false); onClosed?.(); load(); onChanged(); }}
          onDeleted={() => { setEdit(false); onClosed?.(); onChanged(); }}
          onError={onError}
        />
      )}
    </div>
  );
}

/** The steps of the squad window, by key: a link can open one (?step=otd). */
export type SquadStep = "infos" | "options" | "otd" | "team" | "budget" | "committees";

/**
 * L'ecran de gestion d'une squad, le seul: tout ce qui la regle se modifie ici,
 * la page de la squad le lit. Deux publics, une meme fenetre:
 *   - qui gere les squads (tribe leader, admin): Infos (dont responsable et
 *     tribu), Options (KPI, budget), OTD du management et initiatives, Equipe,
 *     Budget (enveloppe comprise), Comites;
 *   - le leader de la squad: Infos (nom, description, produits, materiel), ses
 *     propres OTD, Equipe, Budget (consomme et atterrissage), Comites.
 * Le contenu de la semaine (jalons, messages, moral, valeurs des KPI) reste dans
 * la saisie, qui se soumet: la fenetre y renvoie.
 *
 * Chaque champ enregistre tout de suite (PUT) puis recharge le detail. Le pied de
 * page propose la suppression de la squad, confirmee, a qui gere les squads.
 */
function EditSquadModal({ detail, year, initialStep, leaders, tribes, isAdmin, manager, onClose, onDeleted }: {
  detail: SquadDetail; year: number; initialStep?: SquadStep; leaders: User[]; tribes: Tribe[]; isAdmin: boolean;
  onDeleted?: () => void;
  /** true: tribe leader / admin; false: the squad's own leader. */
  manager: boolean;
  onClose: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const { adminTabs, can, user } = useAuth();
  // Errors stay in this window: the page banner is hidden behind the overlay, so a
  // refused save looked like a click that did nothing.
  const [err, setErr] = useState<string | null>(null);
  const onError = (m: string) => setErr(m);
  const kpisOn = useModule()("squad_content", "kpis");
  const steercoOn = useModule()("steerco");
  const committeesOn = useModule()("committees");
  const [d, setD] = useState<SquadDetail>(detail);
  const [confirmDel, setConfirmDel] = useState(false);
  // Who may be named contributor: the active accounts of the squad's tribe (the
  // same list the team picks from), whoever opens the window.
  const [candidates, setCandidates] = useState<{ id: number; display_name: string }[]>([]);
  useEffect(() => {
    api.get<{ id: number; display_name: string }[]>(`/api/members/candidates?squad_id=${detail.id}`)
      .then(setCandidates).catch(() => setCandidates([]));
  }, [detail.id]);
  const leadership = new Set([d.leader_user_id, ...(d.co_leader_user_ids ?? [])]);
  // Leaders and co-leaders come from the squad's own tribe (the server refuses others).
  const tribePeople = leaders.filter((u) => u.tribe_id == null || u.tribe_id === d.tribe_id);

  async function reload() {
    try { setD(await api.get<SquadDetail>(`/api/squads/${detail.id}?year=${year}`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : t("common.error")); }
  }
  async function run(fn: () => Promise<any>) {
    setErr(null);
    try { await fn(); await reload(); } catch (e) { onError(e instanceof ApiError ? e.message : t("common.error")); }
  }
  const patch = (p: any) => run(() => api.put(`/api/squads/${d.id}`, p));

  const keys: SquadStep[] = [
    "infos",
    ...(manager ? ["options" as SquadStep] : []),
    "otd",
    "team",
    ...(d.budget_enabled ? ["budget" as SquadStep] : []),
    ...(committeesOn ? ["committees" as SquadStep] : []),
  ];
  const [step, setStep] = useState(Math.max(0, keys.indexOf(initialStep ?? "infos")));
  const at = Math.min(step, keys.length - 1);
  const current = keys[at];
  const last = keys.length - 1;
  const saisieTo = `/saisie?squad=${d.id}&year=${year}`;

  return (
    <Modal
      width={720}
      title={`${manager ? t("action.edit") : t("mysquads.manage")} : ${d.name}`}
      onClose={onClose}
      footer={
        <div className="between" style={{ width: "100%", alignItems: "center" }}>
          {!manager ? <span /> : confirmDel ? (
            <div className="inline" style={{ gap: 6 }}>
              <span className="small">{t("mysquads.del_confirm")}</span>
              <button className="btn-danger btn-sm" onClick={async () => {
                setErr(null);
                // Gone: close without reloading it (that read "Squad not found").
                try { await api.del(`/api/squads/${d.id}`); onDeleted ? onDeleted() : onClose(); }
                catch (e) { onError(errorText(e)); }
              }}>
                {t("action.delete")}
              </button>
              <button className="btn-secondary btn-sm" onClick={() => setConfirmDel(false)}>{t("action.cancel")}</button>
            </div>
          ) : (
            <button className="btn-danger btn-sm" onClick={() => setConfirmDel(true)}>{t("mysquads.delete_squad")}</button>
          )}
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-secondary btn-sm" disabled={at === 0} onClick={() => setStep(Math.max(0, at - 1))}>‹ {t("common.prev")}</button>
            {at < last
              ? <button className="btn-sm" onClick={() => setStep(Math.min(last, at + 1))}>{t("common.next")} ›</button>
              : <button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}
          </div>
        </div>
      }
    >
      {err && <ErrorBanner message={err} />}
      {/* Step chips: shows where you are and lets you jump. */}
      <div className="inline" style={{ gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {keys.map((k, i) => (
          <button key={k} onClick={() => setStep(i)}
            className={`badge ${i === at ? "badge-navy" : "badge-grey"}`}
            style={{ cursor: "pointer", border: 0 }}>
            {i + 1}. {t(`mysquads.step.${k}`)}
          </button>
        ))}
      </div>

      {current === "infos" && (
        <div className="stack" style={{ gap: 14 }}>
          <div className="row" style={{ gap: 12 }}>
            <div style={{ flex: 1, minWidth: 180 }}>
              <label htmlFor="sq-name">{t("admin.name")}</label>
              <input id="sq-name" defaultValue={d.name} onBlur={(e) => {
                const v = e.target.value.trim();
                if (!v) { e.target.value = d.name; return; }  // a squad keeps a name
                if (v !== d.name) patch({ name: v });
              }} />
            </div>
            {manager ? (
              <div style={{ flex: 1, minWidth: 160 }}>
                <label htmlFor="sq-leader">{t("squad.squad_leader")}</label>
                <select id="sq-leader" value={d.leader_user_id ?? ""} onChange={(e) => patch({ leader_user_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">-</option>
                  {d.leader && !tribePeople.some((u) => u.id === d.leader_user_id) && (
                    <option value={d.leader_user_id ?? ""}>{d.leader.display_name}</option>
                  )}
                  {tribePeople.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
                </select>
              </div>
            ) : (
              <div style={{ flex: 1, minWidth: 160 }}>
                <label>{t("squad.squad_leader")}</label>
                <div className="small" style={{ paddingTop: 8 }}>{d.leader?.display_name || "-"}</div>
              </div>
            )}
          </div>

          {/* Co-leaders: the same rights on this squad. Naming them is the tribe
              leader's call; the leader reads who they are. */}
          {manager ? (
            <div>
              <label>{t("squad.co_leaders")}</label>
              <div className="small muted" style={{ marginBottom: 4 }}>{t("squad.co_leaders_hint")}</div>
              <PeoplePicker options={tribePeople.filter((u) => u.id !== d.leader_user_id)}
                            value={d.co_leader_user_ids ?? []}
                            onChange={(v) => patch({ co_leader_user_ids: v })} />
            </div>
          ) : (d.co_leaders?.length ?? 0) > 0 && (
            <div className="small muted">{t("squad.co_leaders")}{t("common.colon")}{d.co_leaders!.map((c) => c.display_name).join(", ")}</div>
          )}

          {/* Contributors: they fill in and submit the squad's reporting, and
              nothing else. Named by the tribe leader or by the squad's leader. */}
          <div>
            <label>{t("squad.contributors")}</label>
            <div className="small muted" style={{ marginBottom: 4 }}>{t("squad.contributors_hint")}</div>
            <PeoplePicker options={candidates.filter((u) => !leadership.has(u.id))}
                          value={d.contributor_user_ids ?? []}
                          addLabel={t("squad.contributors_add")} noneLabel={t("squad.contributors_none")}
                          onChange={(v) => patch({ contributor_user_ids: v })} />
          </div>

          {manager && (
            <div className="row" style={{ gap: 12 }}>
              {/* Moving a squad to another tribe is an administrator's decision. */}
              {isAdmin && (
                <div style={{ flex: 1, minWidth: 160 }}>
                  <label htmlFor="sq-tribe">{t("admin.tribe")}</label>
                  <select id="sq-tribe" value={d.tribe_id} onChange={(e) => patch({ tribe_id: Number(e.target.value) })}>
                    {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
                  </select>
                </div>
              )}
              <div style={{ width: 120 }}>
                <label htmlFor="sq-order">{t("admin.order")}</label>
                <input id="sq-order" type="number" defaultValue={d.display_order}
                       onBlur={(e) => Number(e.target.value) !== d.display_order && patch({ display_order: Number(e.target.value) })} />
              </div>
            </div>
          )}

          <div>
            <label htmlFor="sq-desc">{t("admin.description")}</label>
            <textarea id="sq-desc" rows={2} defaultValue={d.description ?? ""}
                      onBlur={(e) => (e.target.value || null) !== (d.description ?? null) && patch({ description: e.target.value || null })} />
          </div>

          <div className="row" style={{ gap: 12 }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label>{t("squad.products")}</label>
              <TagListEditor value={d.products ?? []} placeholder={t("squad.products_ph")}
                             onChange={(v) => patch({ products: v })} />
            </div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label>{t("squad.hardware")}</label>
              <TagListEditor value={d.hardware ?? []} placeholder={t("squad.hardware_ph")}
                             onChange={(v) => patch({ hardware: v })} />
            </div>
          </div>

          {/* The week's content is not a setting: it lives in the reporting. */}
          {!manager && can("reporting") && (
            <div className="small muted">
              {t("mysquads.weekly_in_reporting")} <Link to={saisieTo}>{t("squad.update_in_reporting")}</Link>
            </div>
          )}
        </div>
      )}

      {current === "options" && (
        <div className="stack" style={{ gap: 16 }}>
          <div className="small muted">{t("mysquads.options_hint")}</div>
          {kpisOn && (
            <label className="switch">
              <input type="checkbox" checked={!!d.kpis_enabled} onChange={(e) => patch({ kpis_enabled: e.target.checked })} />
              <span className="track"><span className="knob" /></span>
              <span className="small">{t("admin.kpis_enabled")}</span>
            </label>
          )}
          <label className="switch">
            <input type="checkbox" checked={!!d.budget_enabled} onChange={(e) => patch({ budget_enabled: e.target.checked })} />
            <span className="track"><span className="knob" /></span>
            <span className="small">{t("mysquads.budget_enabled")}</span>
          </label>
          {/* The Steerco is managed in one place: Administration > Platforms and
              Steerco (which squads feed which platform, the skeleton). */}
          {steercoOn
            ? <div className="small muted">
                {t("mysquads.steerco_managed")}{" "}
                {adminTabs.includes("platforms")
                  ? <Link to="/admin?section=platforms">{t("admin.tab.platforms")}</Link>
                  : <span className="strong">{t("admin.tab.platforms")}</span>}
              </div>
            : <div className="small muted">{t("mysquads.module_off", { name: t("steerco.tab") })}</div>}
        </div>
      )}

      {/* OTD: the management's for whoever manages the squads, the squad's own for
          its leader (the management's shows read-only beside it). */}
      {current === "otd" && (
        <div className="stack" style={{ gap: 16 }}>
          <OtdPanel squad={d} canManage={manager}
                    canOwn={!manager || isAdmin || leadsSquad(user?.role ?? "member", user?.id, d)} onChange={reload} />
          {manager && <SquadInitiatives squad={d} onChange={reload} onError={onError} />}
        </div>
      )}

      {current === "team" && <TeamEditor squadId={d.id} onChange={reload} />}

      {current === "budget" && (
        <BudgetPanel squad={d} canEdit canToggle={manager} onChange={reload} />
      )}

      {current === "committees" && (
        <CommitteesPanel squad={d} canEdit onChange={reload} />
      )}
    </Modal>
  );
}


/**
 * Les initiatives que cette squad porte.
 *
 * Une initiative appartient a la tribu et designe la squad qui la mene
 * (Initiative.squad_id). La question « quelles initiatives pour cette squad » se
 * reglait donc dans l'ecran des initiatives, loin d'ici, alors que c'est un
 * reglage de squad comme les autres: c'est ce qui remplit ses lignes dans la
 * frise des exports.
 */
function SquadInitiatives({ squad, onChange, onError }:
  { squad: SquadDetail; onChange: () => void; onError: (m: string) => void }) {
  const { t } = useI18n();
  const [all, setAll] = useState<Initiative[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState<Initiative | null>(null);
  const [removing, setRemoving] = useState<number | null>(null);

  async function load() {
    try { setAll(await api.get<Initiative[]>(`/api/initiatives?year=${squad.year}&tribe_id=${squad.tribe_id}`)); }
    catch { setAll([]); }
  }
  useEffect(() => { load(); }, [squad.id, squad.year]);

  async function assign(init: Initiative, mine: boolean) {
    setBusy(true);
    try {
      await api.put(`/api/initiatives/${init.id}`, { squad_id: mine ? squad.id : null });
      await load();
    } catch (e) { onError(errorText(e)); }
    finally { setBusy(false); }
  }

  if (all === null) return <div className="small muted">{t("common.loading")}</div>;
  const mine = all.filter((i) => i.squad_id === squad.id);
  // Seules les initiatives libres se prennent ici. Une initiative portee par une
  // autre squad se voit, grisee avec son nom: la prendre d'ici la retirait en
  // silence a l'autre squad, jalons compris. Elle change de squad dans l'ecran des
  // initiatives, qui dit ce que le changement detache.
  const others = all.filter((i) => i.squad_id !== squad.id);

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="small strong">{t("nav.initiatives")}</div>
      <div className="small muted">{t("mysquads.initiatives_hint")}</div>
      {all.length === 0 && <div className="small muted">{t("mysquads.initiatives_none")}</div>}
      {mine.map((i) => {
        // Les jalons que porte cette initiative: c'est ce qui fait sa ligne dans
        // la frise, donc c'est ce qu'on montre a cote de son nom.
        const carried = (squad.roadmap_items ?? []).filter((j) => j.initiative_id === i.id);
        return (
          <div key={i.id} className="item-row" style={{ gap: 8 }}>
            <span className="grow strong">{i.title}</span>
            <span className="small muted">
              {t("mysquads.init_jalons_n", { n: carried.length })}
            </span>
            <button className="btn-secondary btn-sm" disabled={busy}
                    onClick={() => setPicking(i)}>{t("mysquads.init_pick")}</button>
            <button className="btn-danger btn-sm" aria-label={t("action.delete")} disabled={busy}
                    onClick={() => setRemoving(i.id)}>✕</button>
            {removing === i.id && (
              <span className="inline" style={{ gap: 6 }}>
                <span className="small">{t("init.move_warning", { squad: squad.name })}</span>
                <button className="btn-danger btn-sm" onClick={() => { setRemoving(null); assign(i, false); }}>{t("action.confirm")}</button>
                <button className="btn-ghost btn-sm" onClick={() => setRemoving(null)}>{t("action.cancel")}</button>
              </span>
            )}
          </div>
        );
      })}
      {others.length > 0 && (
        <select value="" disabled={busy} aria-label={t("mysquads.initiatives_add")}
                onChange={(e) => { const i = others.find((x) => String(x.id) === e.target.value && x.squad_id == null); if (i) assign(i, true); }}>
          <option value="">{t("mysquads.initiatives_add")}</option>
          {others.map((i) => (
            <option key={i.id} value={i.id} disabled={i.squad_id != null}>
              {i.squad_id != null ? t("mysquads.init_carried_by", { title: i.title, squad: i.squad_name ?? "?" }) : i.title}
            </option>
          ))}
        </select>
      )}

      {picking && (
        <InitiativeJalonsModal initiative={picking} squad={squad}
          onClose={() => setPicking(null)}
          onSaved={() => { setPicking(null); onChange(); }} />
      )}
    </div>
  );
}


/** Les jalons qui servent une initiative, coches dans une fenetre.
 *
 *  Le meme geste que pour un engagement, parce que c'est la meme question posee a
 *  deux niveaux. Un jalon deja pris par une autre initiative se voit, grise: le
 *  cacher laisserait croire qu'il n'existe pas. */
function InitiativeJalonsModal({ initiative, squad, onClose, onSaved }: {
  initiative: Initiative; squad: SquadDetail; onClose: () => void; onSaved: () => void;
}) {
  const { t } = useI18n();
  const [rows, setRows] = useState<CandidateInitiativeJalon[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<CandidateInitiativeJalon[]>(
      `/api/initiatives/candidate-jalons?squad_id=${squad.id}&year=${squad.year}`)
      .then((all) => {
        setRows(all);
        setSel(new Set(all.filter((r) => r.initiative_id === initiative.id).map((r) => r.id)));
      })
      .catch(() => setRows([]));
  }, [initiative.id, squad.id, squad.year]);

  const toggle = (id: number) => setSel((prev) => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  async function save() {
    if (busy) return;
    setBusy(true);
    try {
      await api.put(`/api/initiatives/${initiative.id}/jalons`, { jalon_ids: Array.from(sel) });
      onSaved();
    } catch (e) {
      setErr(errorText(e));
    } finally { setBusy(false); }
  }

  return (
    <Modal width={560} title={initiative.title} onClose={onClose}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
        <button onClick={save} disabled={busy}>{busy ? t("common.saving") : t("action.save")}</button>
      </>}>
      <div className="stack" style={{ gap: 12 }}>
        <div className="banner small">{t("mysquads.init_pick_intro")}</div>
        {err && <ErrorBanner message={err} />}
        {rows === null ? (
          <div className="small muted">{t("common.loading")}</div>
        ) : rows.length === 0 ? (
          <div className="small muted">{t("mysquads.init_pick_empty")}</div>
        ) : (
          <div className="pick-list" style={{ maxHeight: 300, overflowY: "auto" }}>
            {rows.map((r) => {
              const taken = r.initiative_id != null && r.initiative_id !== initiative.id;
              return (
                <PickItem key={r.id} selected={sel.has(r.id)} disabled={taken}
                  onToggle={() => toggle(r.id)} title={r.title} meta={`Q${r.quarter}`}
                  tag={taken ? t("mysquads.init_taken") : undefined} />
              );
            })}
          </div>
        )}
      </div>
    </Modal>
  );
}


/** Ce que la liste des plateformes renvoie, reduit a ce dont ce menu a besoin. */


/**
 * New-squad modal. Admins must pick a tribe; a tribe leader is pinned to their
 * own tribe (`defaultTribeId`, tribe field hidden). Optional leader and
 * products/hardware tags. Calls onCreated on success so the list reloads.
 */
function CreateSquadModal({ isAdmin, tribes, leaders, defaultTribeId, onClose, onCreated }: {
  isAdmin: boolean; tribes: Tribe[]; leaders: User[]; defaultTribeId: number | null;
  onClose: () => void; onCreated: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  // Errors stay in this window: the page banner is hidden behind the overlay, so a
  // refused save looked like a click that did nothing.
  const [err, setErr] = useState<string | null>(null);
  const onError = (m: string) => setErr(m);
  const [form, setForm] = useState<{ name: string; leader_user_id: string; tribe_id: string; products: string[]; hardware: string[] }>(
    { name: "", leader_user_id: "", tribe_id: isAdmin ? "" : String(defaultTribeId ?? ""), products: [], hardware: [] });

  async function create() {
    try {
      await api.post("/api/squads", {
        name: form.name.trim(),
        tribe_id: form.tribe_id ? Number(form.tribe_id) : (isAdmin ? null : defaultTribeId),
        leader_user_id: form.leader_user_id ? Number(form.leader_user_id) : null,
        products: form.products,
        hardware: form.hardware,
      });
      onCreated();
    } catch (e) { onError(errorText(e)); }
  }

  return (
    <Modal
      title={t("mysquads.new")}
      onClose={onClose}
      footer={
        <>
          <button className="btn-secondary btn-sm" onClick={onClose}>{t("action.cancel")}</button>
          <button className="btn-sm" onClick={create} disabled={!form.name.trim() || (isAdmin && !form.tribe_id)}>{t("admin.create")}</button>
        </>
      }
    >
      <div className="stack" style={{ gap: 12 }}>
        {err && <ErrorBanner message={err} />}
        <div>
          <label>{t("admin.name")}</label>
          <input autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        {isAdmin && (
          <div>
            <label>{t("admin.tribe")}</label>
            <select value={form.tribe_id} onChange={(e) => setForm({ ...form, tribe_id: e.target.value })}>
              <option value="">-</option>
              {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
            </select>
          </div>
        )}
        <div>
          <label>{t("admin.responsible")}</label>
          <select value={form.leader_user_id} onChange={(e) => setForm({ ...form, leader_user_id: e.target.value })}>
            <option value="">-</option>
            {leaders.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
        </div>
        <div>
          <label>{t("squad.products")}</label>
          <TagListEditor value={form.products} placeholder={t("squad.products_ph")}
                         onChange={(v) => setForm({ ...form, products: v })} />
        </div>
        <div>
          <label>{t("squad.hardware")}</label>
          <TagListEditor value={form.hardware} placeholder={t("squad.hardware_ph")}
                         onChange={(v) => setForm({ ...form, hardware: v })} />
        </div>
      </div>
    </Modal>
  );
}

/* ----------------------------- Squad-leader view ----------------------------- */

/** The squad leader's view: the squads they lead, and only those, each managed
 *  in full from here (details, own OTD, team, budget, committees). */
function SquadLeaderSquads() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [squads, setSquads] = useState<Squad[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [params, setParams] = useSearchParams();
  const openSquad = Number(params.get("squad")) || null;
  const openStep = (params.get("step") as SquadStep | null) ?? undefined;
  // A leader prepares next year's OTD and budget too: the same year selector.
  const [year, , pickYear] = useYear(Number(params.get("year")) || null);

  async function load() {
    try {
      const all = await api.get<Squad[]>("/api/squads");
      // Led as leader OR as co-leader: the server grants both the same rights.
      // The squads they lead, as leader or co-leader, and only those.
      setSquads(all.filter((s) => s.leader_user_id === user?.id || (s.co_leader_user_ids ?? []).includes(user?.id ?? -1)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    }
  }
  useEffect(() => { load(); }, []);
  useSetPageChrome({
    title: t("mysquads.title"),
    actions: (
      <div className="seg" role="group" aria-label={t("entry.header_year")}>
        {[year - 1, year, year + 1].map((y) => (
          <button key={y} className={y === year ? "active" : ""} aria-pressed={y === year} onClick={() => pickYear(y)}>{y}</button>
        ))}
      </div>
    ),
  }, [t, year]);

  if (error && !squads) return <ErrorBanner message={error} />;
  if (!squads) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {error && <ErrorBanner message={error} />}
      <div className="muted small">{t("mysquad.intro")}</div>
      {squads.length === 0 && <EmptyState message={t("mysquad.empty")} />}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
        {squads.map((s) => (
          <SquadCard key={`${s.id}-${year}`} squadId={s.id} year={year} leaders={[]} tribes={[]} isAdmin={false}
                     manager={false} autoOpen={openSquad === s.id} initialStep={openStep}
                     onClosed={() => { if (openSquad === s.id) setParams({}, { replace: true }); }}
                     onChanged={load} onError={setError} />
        ))}
      </div>
    </div>
  );
}

/** Choisir des personnes dans une liste deroulante, et les garder en vue.
 *
 *  Meme forme que TagListEditor juste en dessous, qui fait cela pour du texte
 *  libre: les choix restent affiches au-dessus, la liste ne propose que ce qui
 *  n'a pas encore ete pris. Choisir dans une liste est deja un geste explicite,
 *  il n'y a donc pas de bouton « ajouter » a valider derriere. */
function PeoplePicker({ options, value, onChange, addLabel, noneLabel }: {
  options: { id: number; display_name: string }[];
  value: number[];
  onChange: (v: number[]) => void;
  /** The list's first line: what picking does, and what shows when nobody is left. */
  addLabel?: string; noneLabel?: string;
}) {
  const { t } = useI18n();
  const chosen = options.filter((o) => value.includes(o.id));
  const left = options.filter((o) => !value.includes(o.id));
  return (
    <div className="stack" style={{ gap: 6 }}>
      {chosen.length > 0 && (
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          {chosen.map((o) => (
            <span key={o.id} className="badge badge-navy" style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
              {o.display_name}
              <button className="btn-ghost btn-sm" style={{ padding: "0 3px", lineHeight: 1 }}
                      aria-label={t("action.delete")}
                      onClick={() => onChange(value.filter((x) => x !== o.id))}>×</button>
            </span>
          ))}
        </div>
      )}
      <select value="" disabled={left.length === 0} aria-label={addLabel ?? t("squad.co_leaders_add")}
              onChange={(e) => e.target.value && onChange([...value, Number(e.target.value)])}>
        <option value="">{left.length ? (addLabel ?? t("squad.co_leaders_add")) : (noneLabel ?? t("squad.co_leaders_none"))}</option>
        {left.map((o) => <option key={o.id} value={o.id}>{o.display_name}</option>)}
      </select>
    </div>
  );
}


/** Edit a list of names (products / hardware) as removable chips + an add input. */
function TagListEditor({ value, onChange, placeholder }: {
  value: string[]; onChange: (v: string[]) => void; placeholder?: string;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const add = () => {
    const v = text.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setText("");
  };
  return (
    <div className="stack" style={{ gap: 6 }}>
      {value.length > 0 && (
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          {value.map((p) => (
            <span key={p} className="badge badge-navy" style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
              {p}
              <button className="btn-ghost btn-sm" style={{ padding: "0 3px", lineHeight: 1 }}
                      aria-label={t("action.delete")} onClick={() => onChange(value.filter((x) => x !== p))}>×</button>
            </span>
          ))}
        </div>
      )}
      <div className="inline" style={{ gap: 6 }}>
        <input style={{ flex: 1 }} value={text} placeholder={placeholder}
               onChange={(e) => setText(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }} />
        <button className="btn-secondary btn-sm" onClick={add} disabled={!text.trim()}>{t("action.add")}</button>
      </div>
    </div>
  );
}
