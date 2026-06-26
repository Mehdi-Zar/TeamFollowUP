import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig, useModule } from "../config";
import { Kpi, Member, Objective, RoadmapItem, RoadmapStatus, Squad, SquadDetail, Tribe, Trend, Role } from "../types";
import { Dot, FreshnessBadge, Spinner, ErrorBanner, EmptyState } from "../components/ui";
import { canEditSquad, canManageObjectives } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";
import { roadmapRag } from "../labels";

const ROADMAP_STATUSES: RoadmapStatus[] = ["on_track", "at_risk", "blocked", "done"];

export default function EntryPage() {
  const { user, effectiveRole, isPreview } = useAuth();
  const { t, roadmap, trend, rag, freshness } = useI18n();
  const { default_year } = useConfig();
  const moduleOn = useModule();
  const roadmapOn = moduleOn("squad_content", "roadmap");
  const objectivesOn = moduleOn("squad_content", "objectives");
  const kpisOn = moduleOn("squad_content", "kpis");
  const role = (effectiveRole ?? "member") as Role;
  const [squads, setSquads] = useState<Squad[]>([]);
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [squadId, setSquadId] = useState<number | null>(null);
  const [year, setYear] = useState<number>(default_year);
  const [yearTouched, setYearTouched] = useState(false);
  useEffect(() => { if (!yearTouched) setYear(default_year); }, [default_year]);
  const [squad, setSquad] = useState<SquadDetail | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recap, setRecap] = useState(false);

  const canPickAll = role === "admin" || role === "tribe_leader" || isPreview;
  const editable = useMemo(() => (canPickAll ? squads : squads.filter((s) => s.leader_user_id === user?.id)), [squads, user, canPickAll]);

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
    if (squadId !== null) reload();
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

  const objAllowed = canManageObjectives(role);

  return (
    <div className="stack" style={{ gap: 18 }}>
      <ReportIntro t={t} />

      {message && <div className="banner banner-green">{message}</div>}

      {!squad ? (
        <Spinner />
      ) : (
        <>
          <div className="card between">
            <div>
              <div className="strong" style={{ fontSize: 16, color: "var(--navy)" }}>{squad.name}</div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {t("squad.squad_leader")} : <span className="strong">{squad.leader?.display_name || "-"}</span>
                {" · "}{t("entry.last_submit")} : {freshness(squad.freshness)}
              </div>
            </div>
            <FreshnessBadge freshness={squad.freshness} />
          </div>
          {!writeAllowed && <div className="banner" style={{ background: "var(--ice-soft)" }}>{t("entry.readonly")}</div>}

          {(() => {
            const secs = [
              objectivesOn && { id: "sec-obj", label: t("squad.objectives", { year }), done: squad.objectives.length > 0 },
              roadmapOn && { id: "sec-roadmap", label: t("squad.roadmap", { year }), done: squad.roadmap_items.length > 0 },
              (kpisOn && squad.kpis_enabled) && { id: "sec-kpis", label: t("squad.kpis"), done: squad.kpis.length > 0 },
            ].filter(Boolean) as Array<{ id: string; label: string; done?: boolean; optional?: boolean }>;
            if (secs.length < 2) return null;
            return (
              <nav className="section-nav" aria-label={t("entry.sections")}>
                {secs.map((s) => (
                  <button key={s.id} type="button" className="section-pill"
                          onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" })}>
                    <span className={`section-tick${s.done ? " done" : ""}${s.optional ? " opt" : ""}`}>{s.optional ? "•" : s.done ? "✓" : "○"}</span>
                    {s.label}
                  </button>
                ))}
              </nav>
            );
          })()}

          {objectivesOn && <div id="sec-obj"><ObjectivesEditor squad={squad} year={year} onChange={reload} editable={objAllowed} t={t} rag={rag} /></div>}
          {roadmapOn && <div id="sec-roadmap"><RoadmapEditor squad={squad} year={year} onChange={reload} readonly={!writeAllowed} t={t} roadmap={roadmap} squads={squads} tribes={tribes} /></div>}
          {kpisOn && squad.kpis_enabled && <div id="sec-kpis"><KpisEditor squad={squad} onChange={reload} readonly={!writeAllowed} t={t} trend={trend} /></div>}
        </>
      )}

      {recap && squad && <SubmitRecap squad={squad} onConfirm={confirmSubmit} onCancel={() => setRecap(false)} t={t} />}
    </div>
  );
}

function SubmitRecap({ squad, onConfirm, onCancel, t }: any) {
  const [busy, setBusy] = useState(false);
  const hasJalons = squad.roadmap_items.length > 0;
  const hasProgress = [1, 2, 3, 4].some((q: number) => (squad.quarter_progress[String(q)]?.progress_pct ?? 0) > 0);
  const hasKpis = !squad.kpis_enabled || squad.kpis.length > 0;
  const hasMembers = squad.members.length > 0;
  const items: Array<[boolean, string]> = [
    [hasJalons, t("entry.check.jalons")],
    [hasProgress, t("entry.check.progress")],
    [hasKpis, t("entry.check.kpis")],
    [hasMembers, t("entry.check.members")],
  ];
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{t("entry.submit_recap")}</h3>
        <div className="stack" style={{ margin: "12px 0" }}>
          {items.map(([ok, label], i) => (
            <div key={i} className="inline">
              <span className={`badge ${ok ? "badge-green" : "badge-grey"}`}>{ok ? "✓" : "○"}</span>
              <span className="small">{label}</span>
            </div>
          ))}
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

function Card({ title, hint, action, children }: any) {
  return (
    <div className="card">
      <div className="between">
        <h2 style={{ marginBottom: hint ? 2 : 12 }}>{title}</h2>
        {action}
      </div>
      {hint && <div className="small muted" style={{ marginBottom: 10 }}>{hint}</div>}
      {children}
    </div>
  );
}

function emptyJalon(year: number, quarter: number): Partial<RoadmapItem> {
  return { year, quarter, title: "", theme: "", release_stage: "EA", description: "", success_criteria: "", user_benefit: "", dependencies: "", dependency_kind: null, dependency_squad_id: null, dependency_tribe_id: null, risks: "", owner: "", status: "on_track", objective_id: null };
}

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
        <span className="small muted" title={t("entry.progress_auto")}>{pct}% · {done}/{total}</span>
      </div>
      <div style={{ height: 8, background: "var(--line)", borderRadius: 6, overflow: "hidden", marginBottom: 4 }} aria-label={`${pct}%`}>
        <div style={{ width: `${pct}%`, height: "100%", background: "var(--navy)" }} />
      </div>
      <div style={{ marginTop: 8 }}>
        {items.map((r: RoadmapItem) => (
          <div key={r.id} className="item-row" style={{ cursor: readonly ? "default" : "pointer" }} onClick={() => !readonly && onEdit(r)}>
            <Dot status={roadmapRag(r.status)} />
            <span className="grow small">
              {r.theme ? <span className="strong" style={{ color: "#002060" }}>{r.theme} · </span> : null}
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

function KpisEditor({ squad, onChange, readonly, t, trend }: any) {
  const [name, setName] = useState("");
  const trends: Trend[] = ["on_target", "under_pressure", "missed"];
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
};

function ReportIntro({ t }: { t: any }) {
  const flow = [
    { key: "s1", icon: FLOW_ICONS.target, color: "#1E2761" },
    { key: "s2", icon: FLOW_ICONS.flag, color: "#175CD3" },
    { key: "s3", icon: FLOW_ICONS.check, color: "#027A48" },
    { key: "s4", icon: FLOW_ICONS.send, color: "#B54708" },
  ];
  return (
    <div className="report-intro">
      <div className="report-hero">
        <div className="report-hero-badge">{FLOW_ICONS.target}</div>
        <div>
          <div className="report-hero-title">{t("entry.purpose_title")}</div>
          <div className="report-hero-text">{t("entry.purpose")}</div>
        </div>
      </div>
      <div className="report-flow">
        {flow.map((s, i) => (
          <div key={s.key} className="flow-step">
            <span className="flow-ico" style={{ background: s.color }}>{s.icon}</span>
            <span className="flow-num">{i + 1}</span>
            <div className="flow-body">
              <div className="flow-title">{t(`entry.flow.${s.key}_t`)}</div>
              <div className="flow-desc">{t(`entry.flow.${s.key}_d`)}</div>
            </div>
            {i < flow.length - 1 && <span className="flow-chevron" aria-hidden>›</span>}
          </div>
        ))}
      </div>
      <div className="report-auto"><span className="report-auto-spark">⚡</span>{t("entry.flow.auto")}</div>
    </div>
  );
}
