import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useConfig } from "../config";
import { Kpi, Member, Objective, Rag, RoadmapItem, RoadmapStatus, Squad, SquadDetail, Trend, Role } from "../types";
import { Dot, FreshnessBadge, Spinner, ErrorBanner } from "../components/ui";
import { canEditSquad, canManageObjectives } from "../perms";
import { roadmapRag } from "../labels";

const ROADMAP_STATUSES: RoadmapStatus[] = ["on_track", "at_risk", "blocked", "done"];

export default function EntryPage() {
  const { user, effectiveRole, isPreview } = useAuth();
  const { t, roadmap, trend, rag, freshness } = useI18n();
  const { default_year } = useConfig();
  const role = (effectiveRole ?? "member") as Role;
  const [squads, setSquads] = useState<Squad[]>([]);
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

  if (error) return <ErrorBanner message={error} />;
  if (editable.length === 0) return <div className="card muted">{t("entry.no_squad")}</div>;

  const years = [year - 1, year, year + 1];
  const writeAllowed = squad ? canEditSquad(role, user?.id, squad) : false;
  const objAllowed = canManageObjectives(role);
  const steps = [t("entry.gs.s1"), t("entry.gs.s2"), t("entry.gs.s3"), t("entry.gs.s4")];

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="between">
        <div className="muted small">{t("entry.subtitle")}</div>
        <div className="inline">
          <select className="w-auto" value={squadId ?? ""} onChange={(e) => setSquadId(Number(e.target.value))}>
            {editable.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <div className="seg">
            {years.map((y) => (
              <button key={y} className={y === year ? "active" : ""} onClick={() => { setYear(y); setYearTouched(true); }}>{y}</button>
            ))}
          </div>
          <button onClick={() => setRecap(true)} disabled={!writeAllowed}>{t("action.submit")}</button>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 12 }}>{t("entry.gs.title")}</h3>
        <div className="steps">
          {steps.map((stp, i) => (
            <div key={i} className="step">
              <div className="step-num">{i + 1}</div>
              <div className="step-txt">{stp}</div>
            </div>
          ))}
        </div>
      </div>

      {message && <div className="banner banner-green">{message}</div>}

      {!squad ? (
        <Spinner />
      ) : (
        <>
          <div className="card between">
            <div>
              <div className="strong" style={{ fontSize: 16, color: "var(--navy)" }}>{squad.name}</div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {t("squad.squad_leader")} : <span className="strong">{squad.leader?.display_name || "—"}</span>
                {" · "}{t("entry.last_submit")} : {freshness(squad.freshness)}
              </div>
            </div>
            <FreshnessBadge freshness={squad.freshness} />
          </div>
          {!writeAllowed && <div className="banner" style={{ background: "var(--ice-soft)" }}>{t("entry.readonly")}</div>}

          <RoadmapEditor squad={squad} year={year} onChange={reload} readonly={!writeAllowed} t={t} roadmap={roadmap} />
          <ObjectivesEditor squad={squad} year={year} onChange={reload} editable={objAllowed} t={t} rag={rag} />
          <KpisEditor squad={squad} onChange={reload} readonly={!writeAllowed} t={t} trend={trend} />
          <MembersEditor squad={squad} onChange={reload} readonly={!writeAllowed} t={t} />
        </>
      )}

      {recap && squad && <SubmitRecap squad={squad} onConfirm={confirmSubmit} onCancel={() => setRecap(false)} t={t} />}
    </div>
  );
}

function SubmitRecap({ squad, onConfirm, onCancel, t }: any) {
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
          <button className="btn-secondary" onClick={onCancel}>{t("action.cancel")}</button>
          <button onClick={onConfirm}>{t("entry.submit_confirm")}</button>
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
  return { year, quarter, title: "", description: "", success_criteria: "", user_benefit: "", dependencies: "", risks: "", owner: "", status: "on_track" };
}

function RoadmapEditor({ squad, year, onChange, readonly, t, roadmap }: any) {
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
    <Card title={t("squad.roadmap", { year })} hint={t("entry.roadmap_hint")}>
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
        <JalonModal jalon={editing} members={squad.members} onSave={save} onCancel={() => setEditing(null)} t={t} roadmap={roadmap} />
      )}
    </Card>
  );
}

function QuarterEditor({ squad, year, quarter, onChange, readonly, t, onAdd, onEdit }: any) {
  const cell = squad.quarter_progress[String(quarter)];
  const [pct, setPct] = useState<number>(cell?.progress_pct ?? 0);
  const items = squad.roadmap_items.filter((r: RoadmapItem) => r.quarter === quarter);

  useEffect(() => {
    setPct(squad.quarter_progress[String(quarter)]?.progress_pct ?? 0);
  }, [squad, quarter]);

  async function saveProgress(value: number) {
    await api.put(`/api/squads/${squad.id}/quarter-progress`, { year, quarter, progress_pct: value });
    onChange();
  }

  return (
    <div className="quarter-block">
      <div className="between">
        <h4>Q{quarter}</h4>
        <span className="small muted">{pct}%</span>
      </div>
      <input type="range" min={0} max={100} step={5} value={pct} disabled={readonly}
             onChange={(e) => setPct(Number(e.target.value))} onMouseUp={() => saveProgress(pct)} onTouchEnd={() => saveProgress(pct)} style={{ padding: 0 }} />
      <div style={{ marginTop: 8 }}>
        {items.map((r: RoadmapItem) => (
          <div key={r.id} className="item-row" style={{ cursor: readonly ? "default" : "pointer" }} onClick={() => !readonly && onEdit(r)}>
            <Dot status={roadmapRag(r.status)} />
            <span className="grow small">{r.title}</span>
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

function JalonModal({ jalon, members, onSave, onCancel, t, roadmap }: any) {
  const [f, setF] = useState<Partial<RoadmapItem>>(jalon);
  const set = (k: string, v: any) => setF((p) => ({ ...p, [k]: v }));
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
        <h3>{f.id ? t("jalon.edit") : t("jalon.new")} — Q{f.quarter}</h3>
        <div className="stack" style={{ gap: 10, marginTop: 10 }}>
          {field(t("jalon.title") + " *", "title")}
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
              <label>{t("jalon.owner")}</label>
              <input list="jalon-owners" placeholder={t("jalon.owner_ph")} value={f.owner ?? ""} onChange={(e) => set("owner", e.target.value)} />
              <datalist id="jalon-owners">
                {members.map((m: Member) => <option key={m.id} value={m.full_name} />)}
              </datalist>
            </div>
          </div>
          {field(t("jalon.desc"), "description", true)}
          {field(t("jalon.success"), "success_criteria", true)}
          {field(t("jalon.benefit"), "user_benefit", true)}
          {field(t("jalon.deps"), "dependencies", true)}
          {field(t("jalon.risks"), "risks", true)}
        </div>
        <div className="inline" style={{ justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
          <button className="btn-secondary" onClick={onCancel}>{t("action.cancel")}</button>
          <button onClick={() => onSave(f)} disabled={!f.title?.trim()}>{t("action.save")}</button>
        </div>
      </div>
    </div>
  );
}

function ObjectivesEditor({ squad, year, onChange, editable, t, rag }: any) {
  const [title, setTitle] = useState("");
  async function add() {
    if (!title.trim()) return;
    await api.post("/api/objectives", { squad_id: squad.id, year, title: title.trim(), rag_status: "green" });
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
        <div key={o.id} className="item-row">
          {editable ? (
            <input className="grow" defaultValue={o.title} onBlur={(e) => e.target.value !== o.title && update(o, { title: e.target.value })} />
          ) : (
            <span className="grow">{o.title}</span>
          )}
          <select className="w-auto" style={{ maxWidth: 150 }} value={o.rag_status} disabled={!editable} onChange={(e) => update(o, { rag_status: e.target.value as Rag })}>
            {(["green", "amber", "red"] as Rag[]).map((r) => (<option key={r} value={r}>{rag(r)}</option>))}
          </select>
          {editable && <button className="btn-danger btn-sm" onClick={() => remove(o)}>✕</button>}
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
  async function toggleKpis(enabled: boolean) {
    await api.put(`/api/squads/${squad.id}`, { kpis_enabled: enabled });
    onChange();
  }
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
  const toggle = (
    <label className="switch">
      <input type="checkbox" checked={squad.kpis_enabled} disabled={readonly} onChange={(e) => toggleKpis(e.target.checked)} />
      <span className="track"><span className="knob" /></span>
      <span className="small">{t("entry.kpi_toggle")}</span>
    </label>
  );
  return (
    <Card title={t("squad.kpis")} hint={squad.kpis_enabled ? t("entry.kpi_hint") : undefined} action={toggle}>
      {!squad.kpis_enabled ? (
        <div className="small muted">{t("entry.kpi_off")}</div>
      ) : (
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
              {!readonly && <button className="btn-danger btn-sm" onClick={() => remove(k)}>✕</button>}
            </div>
          ))}
          {!readonly && (
            <div className="inline" style={{ marginTop: 8 }}>
              <input placeholder={t("entry.new_kpi")} value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} />
              <button className="btn-secondary btn-sm" onClick={add}>{t("action.add")}</button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function MembersEditor({ squad, onChange, readonly, t }: any) {
  const [name, setName] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [managerId, setManagerId] = useState("");
  async function add() {
    if (!name.trim()) return;
    await api.post("/api/members", { squad_id: squad.id, full_name: name.trim(), role_title: roleTitle.trim() || null, manager_id: managerId ? Number(managerId) : null });
    setName(""); setRoleTitle(""); setManagerId("");
    onChange();
  }
  async function update(m: Member, patch: Partial<Member>) {
    await api.put(`/api/members/${m.id}`, patch);
    onChange();
  }
  async function remove(m: Member) {
    await api.del(`/api/members/${m.id}`);
    onChange();
  }
  return (
    <Card title={t("squad.team")} hint={t("entry.team_hint")}>
      {squad.members.map((m: Member) => (
        <div key={m.id} className="item-row" style={{ flexWrap: "wrap" }}>
          {readonly ? <span className="grow">{m.full_name}</span> : (
            <input className="grow" defaultValue={m.full_name} onBlur={(e) => e.target.value !== m.full_name && update(m, { full_name: e.target.value })} />
          )}
          {readonly ? <span className="small muted">{m.role_title || "—"}</span> : (
            <input className="w-auto" style={{ maxWidth: 160 }} placeholder={t("entry.member_role")} defaultValue={m.role_title ?? ""} onBlur={(e) => e.target.value !== (m.role_title ?? "") && update(m, { role_title: e.target.value || null })} />
          )}
          {!readonly && (
            <select className="w-auto" style={{ maxWidth: 180 }} value={m.manager_id ?? ""} onChange={(e) => update(m, { manager_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">{t("entry.member_manager")}: —</option>
              {squad.members.filter((o: Member) => o.id !== m.id).map((o: Member) => (
                <option key={o.id} value={o.id}>{t("entry.member_manager")}: {o.full_name}</option>
              ))}
            </select>
          )}
          {!readonly && <button className="btn-danger btn-sm" onClick={() => remove(m)}>✕</button>}
        </div>
      ))}
      {!readonly && (
        <div className="inline" style={{ marginTop: 8, flexWrap: "wrap" }}>
          <input placeholder={t("entry.member_name")} value={name} onChange={(e) => setName(e.target.value)} />
          <input placeholder={t("entry.member_role")} value={roleTitle} onChange={(e) => setRoleTitle(e.target.value)} />
          <select className="w-auto" value={managerId} onChange={(e) => setManagerId(e.target.value)}>
            <option value="">{t("entry.member_manager")}: —</option>
            {squad.members.map((o: Member) => (<option key={o.id} value={o.id}>{o.full_name}</option>))}
          </select>
          <button className="btn-secondary btn-sm" onClick={add}>{t("action.add")}</button>
        </div>
      )}
    </Card>
  );
}
