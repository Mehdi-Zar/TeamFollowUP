/**
 * MySquadsPage - "manage my squads", persona-aware.
 *
 * The page splits by role at the top level:
 *  - squad_leader -> SquadLeaderSquads: manage the TEAM (members) of the squads
 *    they lead.
 *  - tribe_leader / admin -> TribeLeaderSquads: manage squads (create/edit),
 *    KPIs on/off, the OTD (annual commitment) and the budget envelope.
 * Server-side permissions remain authoritative; the split here is only UX.
 */
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { Budget, CandidateInitiativeJalon, Initiative, Member, Objective, Squad, SquadDetail, Tribe, User } from "../types";
import { ErrorBanner, Spinner, Dot, Modal, EmptyState, PickItem } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";
import { useModule } from "../config";
import { OtdPanel } from "../components/OtdPanel";

const RAGS: Array<"green" | "amber" | "red"> = ["green", "amber", "red"];

/** Persona-aware: squad leaders manage their squad's team; tribe leaders/admins
 *  manage KPIs + annual objectives. */
export default function MySquadsPage() {
  const { user } = useAuth();
  if (user?.role === "squad_leader") return <SquadLeaderSquads />;
  return <TribeLeaderSquads />;
}

/** Tribe-leader / admin view: KPIs on/off + annual objectives per squad. */
function TribeLeaderSquads() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [squads, setSquads] = useState<Squad[] | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  async function load() {
    try {
      setSquads(await api.get<Squad[]>("/api/squads"));
      setUsers(await api.get<User[]>("/api/admin/users"));
      const tr = await api.get<Tribe[]>("/api/tribes");
      // A tribe leader can only create squads in their own tribe; admins in any.
      setTribes(isAdmin ? tr : tr.filter((x) => x.id === user?.tribe_id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  }
  useEffect(() => { load(); }, []);

  // Users eligible to be a squad's "responsible" (leader) in the dropdowns.
  const leaders = users.filter((u) => ["squad_leader", "tribe_leader", "admin"].includes(u.role));

  useSetPageChrome(
    { title: t("mysquads.title"), actions: <button className="btn btn-sm" onClick={() => setCreating(true)}>+ {t("mysquads.new")}</button> },
    [t]
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
          <SquadCard key={s.id} squadId={s.id} leaders={leaders} tribes={tribes} isAdmin={isAdmin}
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
 * Tribe-leader/admin squad summary card: name, leader, KPI/budget status badges,
 * and an Edit button that opens the multi-step EditSquadModal. Loads its own
 * SquadDetail so badges reflect the latest state.
 */
function SquadCard({ squadId, leaders, tribes, isAdmin, onChanged, onError }: {
  squadId: number; leaders: User[]; tribes: Tribe[]; isAdmin: boolean;
  onChanged: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const [d, setD] = useState<SquadDetail | null>(null);
  const [edit, setEdit] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    try { setD(await api.get<SquadDetail>(`/api/squads/${squadId}`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  useEffect(() => { load(); }, [squadId]);
  const kpisOn = useModule()("squad_content", "kpis");
  const steercoOn = useModule()("steerco");
  if (!d) return <div className="card spinner">{t("common.loading")}</div>;

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div className="strong" style={{ fontSize: 16 }}>{d.name}</div>
        <button className="btn-secondary btn-sm" onClick={() => setEdit(true)}>✎ {t("action.edit")}</button>
      </div>

      <div className="small muted">{t("squad.squad_leader")} : <span className="strong">{d.leader?.display_name || "-"}</span></div>

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
          leaders={leaders}
          tribes={tribes}
          isAdmin={isAdmin}
          onClose={() => { setEdit(false); load(); onChanged(); }}
          onError={onError}
        />
      )}
    </div>
  );
}

/**
 * L'editeur d'une squad, en quatre etapes:
 *   1. Infos       qui est cette squad (nom, tribu, responsable, co-responsables,
 *                  type, description, ordre, produits, materiel)
 *   2. Options     ce qu'elle suit (KPI, budget, plateformes steerco)
 *   3. OTD         ce sur quoi elle s'engage pour l'annee
 *   4. Budget      les montants, quand le suivi est actif
 *
 * Chaque champ enregistre tout de suite (PUT) puis recharge le detail: un
 * formulaire a bouton « enregistrer » unique laisserait croire qu'on peut
 * abandonner ses modifications, ce qui n'est pas vrai des panneaux enfants (OTD,
 * budget) qui ecrivent deja au fil de l'eau. Le pied de page propose la
 * suppression de la squad, confirmee.
 */
function EditSquadModal({ detail, leaders, tribes, isAdmin, onClose, onError }: {
  detail: SquadDetail; leaders: User[]; tribes: Tribe[]; isAdmin: boolean;
  onClose: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const kpisOn = useModule()("squad_content", "kpis");
  const steercoOn = useModule()("steerco");
  const [d, setD] = useState<SquadDetail>(detail);
  const [step, setStep] = useState(0);

  async function reload() {
    try { setD(await api.get<SquadDetail>(`/api/squads/${detail.id}`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  async function run(fn: () => Promise<any>) {
    try { await fn(); await reload(); } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  const patch = (p: any) => run(() => api.put(`/api/squads/${d.id}`, p));

  const steps = [
    t("mysquads.step.infos"),
    t("mysquads.step.options"),
    t("mysquads.step.otd"),
    t("mysquads.step.budget"),
  ];
  const last = steps.length - 1;

  return (
    <Modal
      width={680}
      title={`${t("action.edit")} - ${d.name}`}
      onClose={onClose}
      footer={
        <div className="between" style={{ width: "100%", alignItems: "center" }}>
          <button className="btn-danger btn-sm" onClick={() => { if (confirm(t("mysquads.del_confirm"))) run(async () => { await api.del(`/api/squads/${d.id}`); onClose(); }); }}>
            {t("action.delete")}
          </button>
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-secondary btn-sm" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>‹ {t("common.prev")}</button>
            {step < last
              ? <button className="btn-sm" onClick={() => setStep((s) => Math.min(last, s + 1))}>{t("common.next")} ›</button>
              : <button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}
          </div>
        </div>
      }
    >
      {/* Step chips: shows where you are and lets you jump. */}
      <div className="inline" style={{ gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {steps.map((label, i) => (
          <button key={i} onClick={() => setStep(i)}
            className={`badge ${i === step ? "badge-navy" : "badge-grey"}`}
            style={{ cursor: "pointer", border: 0 }}>
            {i + 1}. {label}
          </button>
        ))}
      </div>

      {/* Etape 1 - Infos */}
      {step === 0 && (
        <div className="stack" style={{ gap: 14 }}>
          <div className="row" style={{ gap: 12 }}>
            <div style={{ flex: 1, minWidth: 180 }}>
              <label>{t("admin.name")}</label>
              <input defaultValue={d.name} onBlur={(e) => e.target.value !== d.name && patch({ name: e.target.value })} />
            </div>
            <div style={{ flex: 1, minWidth: 160 }}>
              <label>{t("admin.responsible")}</label>
              <select value={d.leader_user_id ?? ""} onChange={(e) => patch({ leader_user_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">-</option>
                {leaders.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
              </select>
            </div>
          </div>

          {/* Co-responsables: les memes droits sur cette squad, sans disputer a
              qui elle appartient. */}
          <div className="row" style={{ gap: 12 }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label>{t("squad.co_leaders")}</label>
              <div className="small muted" style={{ marginBottom: 4 }}>{t("squad.co_leaders_hint")}</div>
              <PeoplePicker options={leaders.filter((u) => u.id !== d.leader_user_id)}
                            value={d.co_leader_user_ids ?? []}
                            onChange={(v) => patch({ co_leader_user_ids: v })} />
            </div>
          </div>

          <div className="row" style={{ gap: 12 }}>
            {/* Deplacer une squad de tribu est une decision d'administrateur: un
                tribe leader ne voit pas les autres tribus. */}
            {isAdmin && (
              <div style={{ flex: 1, minWidth: 160 }}>
                <label>{t("admin.tribe")}</label>
                <select value={d.tribe_id} onChange={(e) => patch({ tribe_id: Number(e.target.value) })}>
                  {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
                </select>
              </div>
            )}
            <div style={{ width: 120 }}>
              <label>{t("admin.order")}</label>
              <input type="number" defaultValue={d.display_order}
                     onBlur={(e) => Number(e.target.value) !== d.display_order && patch({ display_order: Number(e.target.value) })} />
            </div>
          </div>

          <div>
            <label>{t("admin.description")}</label>
            <textarea rows={2} defaultValue={d.description ?? ""}
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
        </div>
      )}

      {/* Etape 2 - Options: ce que cette squad suit */}
      {step === 1 && (
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
          {steercoOn
            ? <SteercoMembership squad={d} onChange={reload} onError={onError} />
            : <div className="small muted">{t("mysquads.module_off", { name: t("steerco.tab") })}</div>}
          <SquadObjectives squad={d} onChange={reload} onError={onError} />
        </div>
      )}

      {/* Etape 3 - OTD: exactement ce que la frise exportee montre, dans son
          ordre. En haut de la frise, les engagements dates. En dessous, une ligne
          par initiative portant les jalons qui la servent. */}
      {step === 2 && (
        <div className="stack" style={{ gap: 16 }}>
          <OtdPanel squad={d} canManage onChange={reload} />
          <SquadInitiatives squad={d} onChange={reload} onError={onError} />
        </div>
      )}

      {/* Etape 4 - Budget: les montants, quand le suivi est actif */}
      {step === 3 && (
        <div className="stack" style={{ gap: 6 }}>
          <div className="small strong">{t("budget.title")}</div>
          <BudgetEditor
            squadId={d.id} year={d.year}
            enabled={!!d.budget_enabled} budget={d.budget}
            canToggle onToggle={(v) => patch({ budget_enabled: v })}
            onError={onError}
          />
        </div>
      )}
    </Modal>
  );
}


/**
 * Le rattachement steerco d'une squad, vu depuis la squad.
 *
 * Il n'y a pas d'interrupteur « steerco » sur une squad, et c'est voulu: l'etat
 * est deduit des plateformes qu'elle alimente (backend/app/platforms.py,
 * sync_squad_flags). Un interrupteur poserait la question deux fois et les deux
 * reponses finiraient par differer. Ce panneau agit donc la ou la decision se
 * prend, sur la liste des contributrices de chaque plateforme, et affiche l'etat
 * qui en decoule.
 */
function SteercoMembership({ squad, onChange, onError }: {
  squad: SquadDetail; onChange: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const [platforms, setPlatforms] = useState<PlatformRow[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try { setPlatforms(await api.get<PlatformRow[]>("/api/steerco/platforms")); }
    catch { setPlatforms([]); }
  }
  useEffect(() => { load(); }, [squad.id]);

  async function toggle(p: PlatformRow, on: boolean) {
    setBusy(true);
    try {
      const ids = p.contributors.map((c) => c.id);
      await api.put(`/api/steerco/platforms/${p.id}`, {
        contributor_ids: on ? [...ids, squad.id] : ids.filter((x) => x !== squad.id),
      });
      await load();
      onChange();
    } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
    finally { setBusy(false); }
  }

  if (platforms === null) return <div className="small muted">{t("common.loading")}</div>;

  const mine = platforms.filter((p) => p.contributors.some((c) => c.id === squad.id));
  const others = platforms.filter((p) => !p.contributors.some((c) => c.id === squad.id));

  // Eteindre le steerco pour cette squad, c'est la retirer de toutes les
  // plateformes qu'elle alimente: il n'y a pas d'autre facon de le rendre faux,
  // puisque l'etat est deduit d'elles.
  async function turnOff() {
    setBusy(true);
    try {
      for (const p of platforms!.filter((x) => x.contributors.some((c) => c.id === squad.id))) {
        await api.put(`/api/steerco/platforms/${p.id}`, {
          contributor_ids: p.contributors.map((c) => c.id).filter((x) => x !== squad.id),
        });
      }
      await load();
      onChange();
    } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
    finally { setBusy(false); }
  }

  return (
    <div className="stack" style={{ gap: 6 }}>
      <label className="switch">
        <input type="checkbox" checked={!!squad.steerco_enabled} disabled={busy || !squad.steerco_enabled}
               onChange={(e) => { if (!e.target.checked) turnOff(); }} />
        <span className="track"><span className="knob" /></span>
        <span className="small">{t("mysquads.steerco_enabled")}</span>
      </label>
      <div className="small muted">{t("mysquads.steerco_hint")}</div>
      {platforms.length === 0 && <div className="small muted">{t("mysquads.steerco_none")}</div>}
      {mine.length > 0 && (
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          {mine.map((p) => (
            <span key={p.id} className="badge badge-navy" style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
              {p.name}
              <button className="btn-ghost btn-sm" style={{ padding: "0 3px", lineHeight: 1 }}
                      aria-label={t("action.delete")} disabled={busy}
                      onClick={() => toggle(p, false)}>×</button>
            </span>
          ))}
        </div>
      )}
      {others.length > 0 && (
        <select value="" disabled={busy}
                onChange={(e) => { const p = others.find((x) => String(x.id) === e.target.value); if (p) toggle(p, true); }}>
          <option value="">{t("mysquads.steerco_add")}</option>
          {others.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      )}
      <div className="small muted">
        {squad.steerco_enabled ? t("mysquads.steerco_on") : t("mysquads.steerco_off")}
      </div>
    </div>
  );
}


/** Les OTD de l'annee, ecrits ici parce que c'est ici qu'ils se decident.
 *
 *  Ils vivaient dans l'ecran de saisie, ou seuls un tribe leader ou un admin
 *  pouvaient les ecrire, alors qu'un tribe leader n'a pas acces a cet ecran: en
 *  pratique un admin etait le seul a pouvoir en creer un. L'ecran « Mes squads »
 *  annoncait deja les porter, il les porte. */
function SquadObjectives({ squad, onChange, onError }:
  { squad: SquadDetail; onChange: () => void; onError: (m: string) => void }) {
  const { t, rag } = useI18n();
  const [title, setTitle] = useState("");

  async function run(fn: () => Promise<unknown>) {
    try { await fn(); onChange(); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  const add = () => title.trim() && run(async () => {
    await api.post("/api/objectives", { squad_id: squad.id, year: squad.year, title: title.trim() });
    setTitle("");
  });
  const update = (o: Objective, patch: Partial<Objective>) =>
    run(() => api.put(`/api/objectives/${o.id}`, patch));
  const remove = (o: Objective) => run(() => api.del(`/api/objectives/${o.id}`));

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="small strong">{t("squad.objectives", { year: squad.year })}</div>
      {squad.objectives.length === 0 && <div className="small muted">{t("squad.no_obj")}</div>}
      {squad.objectives.map((o) => (
        <div key={o.id} className="item-row" style={{ gap: 8 }}>
          {/* Le statut se deduit de l'avancement des jalons: il se montre, il ne
              se choisit pas. */}
          <span className="inline" style={{ gap: 6 }} title={t("mysquads.obj_status_auto")}>
            <Dot status={o.rag_status} />
          </span>
          <input className="grow" defaultValue={o.title}
                 onBlur={(e) => e.target.value !== o.title && update(o, { title: e.target.value })} />
          <span className="small muted" style={{ minWidth: 60 }}>{rag(o.rag_status)}</span>
          <input type="date" className="w-auto" style={{ maxWidth: 150 }}
                 title={t("mysquads.obj_deadline")}
                 value={o.target_date ? o.target_date.slice(0, 10) : ""}
                 onChange={(e) => update(o, { target_date: (e.target.value || null) as any })} />
          <button className="btn-danger btn-sm" onClick={() => remove(o)}
                  aria-label={`${t("action.delete")} - ${o.title}`}>✕</button>
        </div>
      ))}
      <div className="inline" style={{ marginTop: 8 }}>
        <input placeholder={t("mysquads.obj_new")} value={title}
               onChange={(e) => setTitle(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && add()} />
        <button className="btn-secondary btn-sm" onClick={add}>{t("action.add")}</button>
      </div>
    </div>
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

  async function load() {
    try { setAll(await api.get<Initiative[]>(`/api/initiatives?year=${squad.year}`)); }
    catch { setAll([]); }
  }
  useEffect(() => { load(); }, [squad.id, squad.year]);

  async function assign(init: Initiative, mine: boolean) {
    setBusy(true);
    try {
      await api.put(`/api/initiatives/${init.id}`, { squad_id: mine ? squad.id : null });
      await load();
    } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
    finally { setBusy(false); }
  }

  if (all === null) return <div className="small muted">{t("common.loading")}</div>;
  const mine = all.filter((i) => i.squad_id === squad.id);
  // Celles qui restent a prendre: libres, ou portees par une autre squad (le
  // cacher laisserait croire qu'elles n'existent pas).
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
                    onClick={() => assign(i, false)}>✕</button>
          </div>
        );
      })}
      {others.length > 0 && (
        <select value="" disabled={busy}
                onChange={(e) => { const i = others.find((x) => String(x.id) === e.target.value); if (i) assign(i, true); }}>
          <option value="">{t("mysquads.initiatives_add")}</option>
          {others.map((i) => (
            <option key={i.id} value={i.id}>
              {i.title}{i.squad_name ? ` (${i.squad_name})` : ""}
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
      setErr(e instanceof ApiError ? e.message : "Erreur");
    } finally { setBusy(false); }
  }

  return (
    <Modal width={560} title={initiative.title} onClose={onClose}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>{t("action.cancel")}</button>
        <button onClick={save} disabled={busy}>{busy ? "…" : t("action.save")}</button>
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
type PlatformRow = { id: number; name: string; contributors: { id: number; name: string }[] };


/**
 * New-squad modal. Admins must pick a tribe; a tribe leader is pinned to their
 * own tribe (`defaultTribeId`, tribe field hidden). Optional leader and
 * products/hardware tags. Calls onCreated on success so the list reloads.
 */
function CreateSquadModal({ isAdmin, tribes, leaders, defaultTribeId, onClose, onCreated, onError }: {
  isAdmin: boolean; tribes: Tribe[]; leaders: User[]; defaultTribeId: number | null;
  onClose: () => void; onCreated: () => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
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
    } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
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

/** Squad-leader view: manage the team (members) of the squads they lead. */
function SquadLeaderSquads() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [squads, setSquads] = useState<Squad[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const all = await api.get<Squad[]>("/api/squads");
      setSquads(all.filter((s) => s.leader_user_id === user?.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  }
  useEffect(() => { load(); }, []);
  useSetPageChrome({ title: t("mysquad.title") }, [t]);

  if (error && !squads) return <ErrorBanner message={error} />;
  if (!squads) return <Spinner />;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {error && <ErrorBanner message={error} />}
      <div className="muted small">{t("mysquad.intro")}</div>
      {squads.length === 0 && <div className="card muted">{t("mysquad.empty")}</div>}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
        {squads.map((s) => <SLSquadCard key={s.id} squadId={s.id} onError={setError} />)}
      </div>
    </div>
  );
}

/**
 * Squad-leader squad card: shows the team preview (first 5 members) and a
 * "manage team" button opening TeamModal. Used only in the squad-leader view.
 */
function SLSquadCard({ squadId, onError }: { squadId: number; onError: (m: string) => void }) {
  const { t } = useI18n();
  const steercoOn = useModule()("steerco");
  const [d, setD] = useState<SquadDetail | null>(null);
  const [open, setOpen] = useState(false);

  async function load() {
    try { setD(await api.get<SquadDetail>(`/api/squads/${squadId}`)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  useEffect(() => { load(); }, [squadId]);
  if (!d) return <div className="card spinner">{t("common.loading")}</div>;

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div className="strong" style={{ fontSize: 16 }}>{d.name}</div>
        <button className="btn-secondary btn-sm" onClick={() => setOpen(true)}>✎ {t("mysquad.manage_team")}</button>
      </div>
      {steercoOn && d.steerco_enabled && (
        <div className="small muted">{t("steerco.contributes")}</div>
      )}
      <span className="badge badge-navy">{t("squad.team_collapsed_hint", { n: d.members.length }).split(" - ")[0]}</span>
      {d.members.length === 0 && <div className="small muted">{t("squad.no_members")}</div>}
      <div className="stack" style={{ gap: 4 }}>
        {d.members.slice(0, 5).map((m) => (
          <div key={m.id} className="inline small" style={{ gap: 6 }}>
            <span className="strong">{m.full_name}</span>
            {m.role_title && <span className="muted">, {m.role_title}</span>}
          </div>
        ))}
        {d.members.length > 5 && <div className="small muted">+{d.members.length - 5}…</div>}
      </div>

      {open && <TeamModal detail={d} onClose={() => { setOpen(false); load(); }} onError={onError} />}
    </div>
  );
}

/**
 * Squad-leader team manager (modal): rename the squad, report budget (read-only
 * envelope), and CRUD the members incl. their "reports to" manager. Every input
 * saves on blur/change via run() and reloads members. `managerOptions` excludes
 * the member itself so nobody can report to themselves.
 */
function TeamModal({ detail, onClose, onError }: { detail: SquadDetail; onClose: () => void; onError: (m: string) => void }) {
  const { t } = useI18n();
  const [members, setMembers] = useState<Member[]>(detail.members);
  const [name, setName] = useState(detail.name);
  const [add, setAdd] = useState({ full_name: "", role_title: "" });

  async function reload() {
    try {
      const sd = await api.get<SquadDetail>(`/api/squads/${detail.id}`);
      setMembers(sd.members);
    } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  async function run(fn: () => Promise<any>) {
    try { await fn(); await reload(); } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  }
  const managerOptions = (mid: number) => members.filter((m) => m.id !== mid);

  return (
    <Modal
      title={`${t("mysquad.manage_team")} - ${detail.name}`}
      onClose={onClose}
      footer={<button className="btn-sm" onClick={onClose}>{t("action.close")}</button>}
    >
      <div className="stack" style={{ gap: 14 }}>
        <div>
          <label>{t("admin.squad")}</label>
          <input defaultValue={name} onBlur={(e) => { if (e.target.value !== name) { setName(e.target.value); run(() => api.put(`/api/squads/${detail.id}`, { name: e.target.value })); } }} />
        </div>

        <div className="stack" style={{ gap: 6, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <div className="small strong">{t("budget.title")}</div>
          <BudgetEditor
            squadId={detail.id} year={detail.year}
            enabled={!!detail.budget_enabled} budget={detail.budget}
            canToggle={false} onToggle={() => {}}
            onError={onError}
          />
        </div>

        <div>
          <div className="small muted" style={{ marginBottom: 6 }}>{t("admin.members")} ({members.length})</div>
          {members.length === 0 && <div className="small muted">{t("squad.no_members")}</div>}
          <div className="stack" style={{ gap: 8 }}>
            {members.map((m) => (
              <div key={m.id} className="row" style={{ gap: 8, alignItems: "flex-end" }}>
                <div style={{ flex: 1, minWidth: 120 }}>
                  <label className="small muted">{t("admin.member_name")}</label>
                  <input defaultValue={m.full_name} onBlur={(e) => e.target.value !== m.full_name && run(() => api.put(`/api/members/${m.id}`, { full_name: e.target.value }))} />
                </div>
                <div style={{ flex: 1, minWidth: 110 }}>
                  <label className="small muted">{t("admin.member_role")}</label>
                  <input defaultValue={m.role_title ?? ""} onBlur={(e) => e.target.value !== (m.role_title ?? "") && run(() => api.put(`/api/members/${m.id}`, { role_title: e.target.value }))} />
                </div>
                <div style={{ width: 130 }}>
                  <label className="small muted">{t("mysquad.reports_to")}</label>
                  <select className="w-auto" value={m.manager_id ?? ""} onChange={(e) => run(() => api.put(`/api/members/${m.id}`, { manager_id: e.target.value ? Number(e.target.value) : null }))}>
                    <option value="">-</option>
                    {managerOptions(m.id).map((mm) => <option key={mm.id} value={mm.id}>{mm.full_name}</option>)}
                  </select>
                </div>
                <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => run(() => api.del(`/api/members/${m.id}`))}>✕</button>
              </div>
            ))}
          </div>

          <div className="row" style={{ gap: 8, alignItems: "flex-end", marginTop: 10, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <div style={{ flex: 1, minWidth: 120 }}>
              <label className="small">{t("mysquad.add_member")}</label>
              <input placeholder={t("admin.member_name")} value={add.full_name} onChange={(e) => setAdd({ ...add, full_name: e.target.value })} />
            </div>
            <div style={{ flex: 1, minWidth: 110 }}>
              <input placeholder={t("admin.member_role")} value={add.role_title} onChange={(e) => setAdd({ ...add, role_title: e.target.value })} />
            </div>
            <button className="btn-sm" disabled={!add.full_name.trim()}
                    onClick={() => run(async () => { await api.post("/api/members", { squad_id: detail.id, full_name: add.full_name.trim(), role_title: add.role_title.trim() || null }); setAdd({ full_name: "", role_title: "" }); })}>
              {t("admin.add")}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

/** Budget management, reusable in Manage-my-squads. Tribe leaders/admins can
 *  toggle tracking on/off (canToggle); the squad leader fills total/spent.
 *  Saves on blur and keeps its own readout from the API response. */
const BUDGET_BADGE: Record<string, string> = { on_track: "badge-green", at_risk: "badge-orange", over: "badge-red" };

function BudgetEditor({ squadId, year, enabled, budget, canToggle, onToggle, onError }: {
  squadId: number; year: number; enabled: boolean; budget?: Budget | null;
  canToggle: boolean; onToggle: (v: boolean) => void; onError: (m: string) => void;
}) {
  const { t } = useI18n();
  const [b, setB] = useState<Budget | null | undefined>(budget);
  const [total, setTotal] = useState(budget?.total != null ? String(budget.total) : "");
  const [spent, setSpent] = useState(budget?.spent != null ? String(budget.spent) : "");
  const [forecast, setForecast] = useState(budget?.forecast != null ? String(budget.forecast) : "");
  const [comment, setComment] = useState(budget?.comment ?? "");
  const fmt = (n?: number | null) => (n == null ? "-" : `${n.toLocaleString()} €`);

  // canToggle == tribe leader / admin: they own the envelope (total). A squad
  // leader only reports spent / forecast / comment, and sees total read-only.
  const save = async () => {
    try {
      const res = await api.put<Budget>(`/api/squads/${squadId}/budget?year=${year}`, {
        total: total === "" ? null : Number(total),   // ignored server-side unless tribe/admin
        spent: spent === "" ? null : Number(spent),
        forecast: forecast === "" ? null : Number(forecast),
        comment: comment.trim() || null,
      });
      setB(res);
    } catch (e) { onError(e instanceof ApiError ? e.message : "Erreur"); }
  };

  return (
    <div className="stack" style={{ gap: 8 }}>
      {canToggle && (
        <label className="switch">
          <input type="checkbox" checked={enabled} onChange={(e) => onToggle(e.target.checked)} />
          <span className="track"><span className="knob" /></span>
          <span className="small">{t("budget.enable_label")}</span>
        </label>
      )}
      {enabled ? (
        <>
          <div className="small muted">{t("budget.hint")}</div>
          <div className="row" style={{ gap: 8 }}>
            <div style={{ flex: 1, minWidth: 100 }}>
              <label className="small muted">{t("budget.total")}</label>
              {canToggle
                ? <input type="number" value={total} onChange={(e) => setTotal(e.target.value)} onBlur={save} />
                : <input type="number" value={total} disabled title={t("budget.total_locked")} />}
            </div>
            <div style={{ flex: 1, minWidth: 100 }}>
              <label className="small muted" title={t("budget.spent_hint")}>{t("budget.spent")}</label>
              <input type="number" value={spent} onChange={(e) => setSpent(e.target.value)} onBlur={save} />
            </div>
            <div style={{ flex: 1, minWidth: 100 }}>
              <label className="small muted" title={t("budget.forecast_hint")}>{t("budget.forecast")}</label>
              <input type="number" value={forecast} onChange={(e) => setForecast(e.target.value)} onBlur={save} />
            </div>
          </div>
          <label className="small muted">{t("budget.comment")}
            <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} onBlur={save} />
          </label>
          {b && (b.total != null && (b.spent != null || b.forecast != null)) && (
            <span className={`badge ${BUDGET_BADGE[b.status] ?? "badge-grey"}`}>
              {t(`budget.status.${b.status}`)}
              {b.status === "over" && ` ${t("budget.overrun_val", { amount: fmt(b.overrun), pct: b.overrun_pct })}`}
            </span>
          )}
        </>
      ) : (
        !canToggle && <div className="small muted">{t("budget.disabled")}</div>
      )}
    </div>
  );
}

/** Choisir des personnes dans une liste deroulante, et les garder en vue.
 *
 *  Meme forme que TagListEditor juste en dessous, qui fait cela pour du texte
 *  libre: les choix restent affiches au-dessus, la liste ne propose que ce qui
 *  n'a pas encore ete pris. Choisir dans une liste est deja un geste explicite,
 *  il n'y a donc pas de bouton « ajouter » a valider derriere. */
function PeoplePicker({ options, value, onChange }: {
  options: { id: number; display_name: string }[];
  value: number[];
  onChange: (v: number[]) => void;
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
      <select value="" disabled={left.length === 0}
              onChange={(e) => e.target.value && onChange([...value, Number(e.target.value)])}>
        <option value="">{left.length ? t("squad.co_leaders_add") : t("squad.co_leaders_none")}</option>
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
