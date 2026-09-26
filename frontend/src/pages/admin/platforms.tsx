// Admin > Platforms and Steerco: the one place where the Steerco is managed. The
// tribe leader sets the tribe's model (the skeleton every platform starts from),
// declares the platforms, says which squads feed each one, assigns every figure of
// a slide to one of them, and imports a filled workbook. The monthly figures are
// entered in Reporting, by the squads; the result reads in the dashboard.
//
// A platform is one slide. It can be fed by several squads (a platform may be fed by
// two squads or more), and the assignment below is what lets those
// squad leaders fill the same slide without overwriting each other: one item, one
// owner, no merge. An item left unassigned is nobody's job, so the panel counts them
// and says so rather than letting a column stay silently empty every month.
import { useEffect, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { useModule } from "../../config";
import { useAuth } from "../../auth";
import { Squad, Tribe } from "../../types";
import { ImportSteercoAdmin } from "./imports";
import { Platform, PlatformTemplate, TemplateItem } from "../../steerco";
import { ErrorBanner, Modal, Spinner, EmptyState } from "../../components/ui";

const EMPTY: PlatformTemplate = { kpis: [], sla: [], incidents: { owner_squad_id: null } };

/** Admin > Platforms. Tribe leader and admin: they own the committee's slides. */
export function PlatformsAdmin() {
  const { t } = useI18n();
  // The whole feature lives behind the steerco module: without it the endpoints
  // answer 404, so say why rather than render a panel that cannot load.
  const steercoOn = useModule()("steerco");
  const [rows, setRows] = useState<Platform[] | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<Platform | "new" | null>(null);

  async function load() {
    setErr(null);
    try {
      const [p, s] = await Promise.all([
        api.get<Platform[]>("/api/steerco/platforms"),
        api.get<Squad[]>("/api/squads"),
      ]);
      setRows(p); setSquads(s);
    } catch (e) { setErr(errorText(e)); setRows([]); }
  }
  useEffect(() => { if (steercoOn) load(); }, [steercoOn]);

  async function remove(p: Platform) {
    if (!window.confirm(t("platforms.delete_confirm", { name: p.name }))) return;
    try { await api.del(`/api/steerco/platforms/${p.id}`); await load(); }
    catch (e) { setErr(errorText(e)); }
  }

  const unassigned = (p: Platform) =>
    (p.template.kpis ?? []).filter((k) => !k.owner_squad_id).length
    + (p.template.sla ?? []).filter((x) => !x.owner_squad_id).length
    + (p.template.incidents?.owner_squad_id ? 0 : 1);

  if (!steercoOn) {
    return (
      <div className="card stack" style={{ gap: 6 }}>
        <h2 style={{ margin: 0 }}>{t("platforms.title")}</h2>
        <div className="small muted">{t("platforms.module_off")}</div>
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 16 }}>
    <TribeModelEditor />
    <div className="card stack" style={{ gap: 12 }}>
      <div className="between" style={{ alignItems: "center" }}>
        <div className="stack" style={{ gap: 2 }}>
          <h2 style={{ margin: 0 }}>{t("platforms.list_title")}</h2>
          <div className="small muted">{t("platforms.hint")}</div>
        </div>
        <button className="btn-sm" onClick={() => setEditing("new")}>+ {t("platforms.new")}</button>
      </div>

      {err && <ErrorBanner message={err} />}

      {rows === null ? <Spinner /> : rows.length === 0 ? (
        <EmptyState message={t("platforms.empty")} />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("platforms.name")}</th>
              <th>{t("platforms.contributors")}</th>
              <th>{t("platforms.items")}</th>
              <th>{t("platforms.state")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
                <td className="strong">{p.name}</td>
                <td className="small">{p.contributors.map((c) => c.name).join(", ") || "-"}</td>
                <td className="small">
                  {t("platforms.item_count", {
                    kpis: String((p.template.kpis ?? []).length),
                    sla: String((p.template.sla ?? []).length),
                  })}
                  {unassigned(p) > 0 && (
                    <span className="badge badge-orange" style={{ marginLeft: 6 }}>
                      {t("platforms.unassigned", { n: unassigned(p) })}
                    </span>
                  )}
                </td>
                <td>
                  <span className={`badge ${p.steerco_enabled ? "badge-green" : "badge-grey"}`}>
                    {p.steerco_enabled ? t("platforms.on") : t("platforms.off")}
                  </span>
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  {p.can_manage && (
                    <>
                      <button className="btn-secondary btn-sm" onClick={() => setEditing(p)}>✎ {t("action.edit")}</button>{" "}
                      <button className="btn-ghost btn-sm" onClick={() => remove(p)}>{t("action.delete")}</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {editing && (
        <PlatformModal
          platform={editing === "new" ? null : editing}
          squads={squads}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
    {/* A filled workbook, imported into a platform of the tribe (bulk). */}
    <ImportSteercoAdmin />
    </div>
  );
}

/** The tribe's model: the Steerco skeleton its tribe leader imposes (KPI and their
 *  sub-metrics, SLA services). A new platform starts from it; an existing one comes
 *  back to it with "apply the tribe model". The admin, who has no tribe, picks one. */
function TribeModelEditor() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tribes, setTribes] = useState<Tribe[]>([]);
  const [tribeId, setTribeId] = useState<number | null>(isAdmin ? null : user?.tribe_id ?? null);
  const [kpis, setKpis] = useState<{ label: string; sub: string[] }[]>([]);
  const [sla, setSla] = useState<{ label: string }[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    api.get<Tribe[]>("/api/tribes").then((ts) => { setTribes(ts); if (ts.length) setTribeId(ts[0].id); }).catch(() => {});
  }, [isAdmin]);
  useEffect(() => {
    if (tribeId === null) return;
    setErr(null); setMsg(null);
    api.get<any>(`/api/steerco/model?tribe_id=${tribeId}`)
      .then((m) => { setKpis(m.kpis ?? []); setSla(m.sla ?? []); })
      .catch((e) => setErr(errorText(e)));
  }, [tribeId]);

  async function save() {
    setErr(null); setMsg(null);
    try {
      const m = await api.put<any>(`/api/steerco/model?tribe_id=${tribeId}`, {
        kpis: kpis.filter((k) => k.label.trim()), sla: sla.filter((x) => x.label.trim()),
      });
      setKpis(m.kpis ?? []); setSla(m.sla ?? []);
      setMsg(t("admin.saved"));
    } catch (e) { setErr(errorText(e)); }
  }

  return (
    <div className="card stack" style={{ gap: 10 }}>
      <div className="between" style={{ alignItems: "center", gap: 12 }}>
        <div className="stack" style={{ gap: 2 }}>
          <h2 style={{ margin: 0 }}>{t("platforms.model_title")}</h2>
          <div className="small muted">{t("platforms.model_hint")}</div>
        </div>
        {isAdmin && (
          <select className="w-auto" aria-label={t("admin.tribe")} value={tribeId ?? ""}
                  onChange={(e) => setTribeId(Number(e.target.value))}>
            {tribes.map((tr) => <option key={tr.id} value={tr.id}>{tr.name}</option>)}
          </select>
        )}
      </div>
      {err && <ErrorBanner message={err} />}
      <div className="row" style={{ gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div className="stack" style={{ gap: 4, flex: 2, minWidth: 280 }}>
          <div className="between" style={{ alignItems: "center" }}>
            <span className="small strong">{t("platforms.kpis")}</span>
            <button type="button" className="btn-secondary btn-sm" onClick={() => setKpis([...kpis, { label: "", sub: [] }])}>+ {t("platforms.add_item")}</button>
          </div>
          {kpis.map((k, i) => (
            <div key={i} className="inline" style={{ gap: 6 }}>
              <input aria-label={t("platforms.item_label")} value={k.label} style={{ flex: 1 }}
                     onChange={(e) => setKpis(kpis.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
              <input aria-label={t("platforms.sub_metrics")} placeholder={t("platforms.sub_metrics")} style={{ flex: 1 }}
                     value={(k.sub ?? []).join(", ")}
                     onChange={(e) => setKpis(kpis.map((x, j) => (j === i ? { ...x, sub: e.target.value.split(",").map((v) => v.trim()).filter(Boolean) } : x)))} />
              <button type="button" className="icon-del" aria-label={t("action.delete")} onClick={() => setKpis(kpis.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
        </div>
        <div className="stack" style={{ gap: 4, flex: 1, minWidth: 200 }}>
          <div className="between" style={{ alignItems: "center" }}>
            <span className="small strong">{t("platforms.sla")}</span>
            <button type="button" className="btn-secondary btn-sm" onClick={() => setSla([...sla, { label: "" }])}>+ {t("platforms.add_item")}</button>
          </div>
          {sla.map((x, i) => (
            <div key={i} className="inline" style={{ gap: 6 }}>
              <input aria-label={t("platforms.item_label")} value={x.label} style={{ flex: 1 }}
                     onChange={(e) => setSla(sla.map((y, j) => (j === i ? { label: e.target.value } : y)))} />
              <button type="button" className="icon-del" aria-label={t("action.delete")} onClick={() => setSla(sla.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
        </div>
      </div>
      <div className="inline" style={{ gap: 10 }}>
        <button className="btn-sm" disabled={tribeId === null} onClick={save}>{t("action.save")}</button>
        {msg && <span className="small" style={{ color: "var(--green)" }}>{msg}</span>}
      </div>
    </div>
  );
}

/** Create / edit one platform: identity, contributors, and the slide's item owners. */
function PlatformModal({ platform, squads, onClose, onSaved }:
  { platform: Platform | null; squads: Squad[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(platform?.name ?? "");
  const [description, setDescription] = useState(platform?.description ?? "");
  const [enabled, setEnabled] = useState(platform?.steerco_enabled ?? true);
  const [contributors, setContributors] = useState<number[]>(platform?.contributors.map((c) => c.id) ?? []);
  const [tpl, setTpl] = useState<PlatformTemplate>(platform?.template ?? EMPTY);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const contributorSquads = squads.filter((s) => contributors.includes(s.id));
  // An owner that is no longer a contributor is dropped by the server anyway; showing
  // it as unassigned here keeps the form honest about what will be saved.
  const ownerOf = (id: number | null) => (id && contributors.includes(id) ? id : null);

  function toggleContributor(id: number) {
    setContributors((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  }

  function setItem(kind: "kpis" | "sla", i: number, patch: Partial<TemplateItem>) {
    setTpl((x) => ({ ...x, [kind]: (x[kind] ?? []).map((it, j) => (j === i ? { ...it, ...patch } : it)) }));
  }
  function addItem(kind: "kpis" | "sla") {
    setTpl((x) => ({ ...x, [kind]: [...(x[kind] ?? []), { label: "", owner_squad_id: contributors[0] ?? null }] }));
  }
  function removeItem(kind: "kpis" | "sla", i: number) {
    setTpl((x) => ({ ...x, [kind]: (x[kind] ?? []).filter((_, j) => j !== i) }));
  }

  async function save() {
    setBusy(true); setErr(null);
    const body: any = { name, description, steerco_enabled: enabled, contributor_ids: contributors };
    // A new platform starts from the tribe's model (server side); its skeleton is
    // adjusted afterwards, here, like any other platform.
    if (platform) body.template = {
      kpis: (tpl.kpis ?? []).filter((k) => k.label.trim()),
      sla: (tpl.sla ?? []).filter((x) => x.label.trim()),
      incidents: { owner_squad_id: ownerOf(tpl.incidents?.owner_squad_id ?? null) },
    };
    try {
      if (platform) await api.put(`/api/steerco/platforms/${platform.id}`, body);
      else await api.post("/api/steerco/platforms", body);
      onSaved();
    } catch (e) {
      setErr(errorText(e));
      setBusy(false);
    }
  }

  // Bring this platform back to the tribe's model: items that stay keep their owner
  // and their figures, the others go.
  async function applyModel() {
    if (!platform) return;
    setErr(null);
    try {
      const out = await api.post<Platform>(`/api/steerco/platforms/${platform.id}/apply-model`, {});
      setTpl(out.template);
    } catch (e) { setErr(errorText(e)); }
  }

  const OwnerSelect = ({ value, onChange }: { value: number | null; onChange: (v: number | null) => void }) => (
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">{t("platforms.owner_none")}</option>
      {contributorSquads.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select>
  );

  return (
    <Modal
      width={860}
      title={platform ? t("platforms.edit_title", { name: platform.name }) : t("platforms.new_title")}
      onClose={onClose}
      footer={
        <div className="between" style={{ width: "100%", alignItems: "center" }}>
          <span className="small" style={{ color: "var(--red)" }}>{err ?? ""}</span>
          <div className="inline" style={{ gap: 8 }}>
            <button className="btn-secondary btn-sm" onClick={onClose}>{t("action.cancel")}</button>
            <button className="btn-sm" disabled={busy || !name.trim()} onClick={save}>
              {busy ? t("common.saving") : t("action.save")}
            </button>
          </div>
        </div>
      }
    >
      <div className="stack" style={{ gap: 16 }}>
        <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <label htmlFor="pf-name">{t("platforms.name")}</label>
            <input id="pf-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Cloud Platform" />
          </div>
          <div style={{ flex: 2, minWidth: 220 }}>
            <label htmlFor="pf-desc">{t("platforms.description")}</label>
            <input id="pf-desc" value={description ?? ""} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <label className="switch" style={{ alignSelf: "flex-end" }}>
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            <span className="track"><span className="knob" /></span>
            <span className="small">{t("platforms.in_deck")}</span>
          </label>
        </div>

        <div className="stack" style={{ gap: 6 }}>
          <div className="strong">{t("platforms.contributors")}</div>
          <div className="small muted">{t("platforms.contributors_hint")}</div>
          <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
            {squads.map((s) => (
              <label key={s.id} className="inline small" style={{ gap: 4 }}>
                <input type="checkbox" checked={contributors.includes(s.id)} onChange={() => toggleContributor(s.id)} />
                {s.name}
              </label>
            ))}
          </div>
        </div>

        {!platform ? (
          <div className="banner small">{t("platforms.new_from_model")}</div>
        ) : (
        <div className="stack" style={{ gap: 6 }}>
          <div className="between" style={{ alignItems: "center" }}>
            <div className="strong">{t("platforms.slide")}</div>
            <button type="button" className="btn-secondary btn-sm" onClick={applyModel}>{t("platforms.apply_model")}</button>
          </div>
          <div className="small muted">{t("platforms.slide_hint")}</div>

          {(["kpis", "sla"] as const).map((kind) => (
            <div key={kind} className="stack" style={{ gap: 4 }}>
              <div className="between" style={{ alignItems: "center" }}>
                <span className="small strong">{t(`platforms.${kind}`)}</span>
                <button type="button" className="btn-secondary btn-sm" onClick={() => addItem(kind)}>
                  + {t("platforms.add_item")}
                </button>
              </div>
              <table className="table" style={{ fontSize: 13 }}>
                <thead>
                  <tr>
                    <th>{t("platforms.item_label")}</th>
                    {kind === "kpis" && <th>{t("platforms.sub_metrics")}</th>}
                    <th style={{ width: 220 }}>{t("platforms.owner")}</th>
                    <th style={{ width: 40 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {(tpl[kind] ?? []).length === 0 && (
                    <tr><td colSpan={kind === "kpis" ? 4 : 3} className="small muted">{t("platforms.no_item")}</td></tr>
                  )}
                  {(tpl[kind] ?? []).map((item, i) => (
                    <tr key={i}>
                      <td><input value={item.label} onChange={(e) => setItem(kind, i, { label: e.target.value })} /></td>
                      {kind === "kpis" && (
                        <td>
                          <input value={(item.sub ?? []).join(", ")} placeholder="GitLab, Artifactory"
                                 onChange={(e) => setItem(kind, i, { sub: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
                        </td>
                      )}
                      <td><OwnerSelect value={ownerOf(item.owner_squad_id)} onChange={(v) => setItem(kind, i, { owner_squad_id: v })} /></td>
                      <td>
                        <button type="button" className="icon-del" aria-label={t("action.delete")}
                                onClick={() => removeItem(kind, i)}>✕</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          <div className="inline" style={{ gap: 10, alignItems: "center" }}>
            <span className="small strong">{t("platforms.incidents")}</span>
            <OwnerSelect value={ownerOf(tpl.incidents?.owner_squad_id ?? null)}
                         onChange={(v) => setTpl((x) => ({ ...x, incidents: { owner_squad_id: v } }))} />
          </div>
        </div>
        )}
      </div>
    </Modal>
  );
}
