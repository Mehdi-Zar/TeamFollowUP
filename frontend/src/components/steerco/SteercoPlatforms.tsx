// Steerco > Parametres, sections "Le modele de la tribe" and "Les plateformes".
//
// A platform is one slide. Everything that shapes a slide is set here, once: its
// rows (from the tribe's model), the squads concerned (optional: their key messages
// feed the events step), how its KPI chart is drawn, and, through the Studio, its
// layout. The month's figures are entered in "Le mois", never here.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { Squad } from "../../types";
import { ChartMode, Display, Platform, PlatformTemplate, TemplateItem } from "../../steerco";
import { ErrorBanner, Modal, Spinner, EmptyState } from "../ui";

const EMPTY: PlatformTemplate = { kpis: [], sla: [] };
const MODES: ChartMode[] = ["auto", "lines", "small_multiples", "table"];
// Past this many curves on one plot, they cannot be told apart (same rule as the server).
const LINES_MAX = 5;

/** The platforms of one tribe. */
export function PlatformList({ tribeId, onChanged }: { tribeId: number; onChanged?: () => void }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<Platform[] | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<Platform | "new" | null>(null);

  async function load() {
    setErr(null);
    try {
      const [p, s] = await Promise.all([
        api.get<Platform[]>(`/api/steerco/platforms?tribe_id=${tribeId}`),
        api.get<Squad[]>("/api/squads"),
      ]);
      setRows(p); setSquads(s.filter((x) => x.tribe_id === tribeId));
    } catch (e) { setErr(errorText(e)); setRows([]); }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setRows(null); load(); }, [tribeId]);
  const changed = async () => { await load(); onChanged?.(); };

  async function remove(p: Platform) {
    if (!window.confirm(t("platforms.delete_confirm", { name: p.name }))) return;
    try { await api.del(`/api/steerco/platforms/${p.id}`); await changed(); }
    catch (e) { setErr(errorText(e)); }
  }

  // In or out of the pack, straight from the list.
  async function setEnabled(p: Platform, on: boolean) {
    setRows((rs) => rs && rs.map((r) => (r.id === p.id ? { ...r, steerco_enabled: on } : r)));
    try { await api.put(`/api/steerco/platforms/${p.id}`, { steerco_enabled: on }); onChanged?.(); }
    catch (e) { setErr(errorText(e)); await load(); }
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="between" style={{ alignItems: "center", gap: 12 }}>
        <div className="small muted">{t("platforms.hint")}</div>
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
              <th>{t("platforms.squads")}</th>
              <th>{t("platforms.items")}</th>
              <th>{t("platforms.state")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
                <td className="strong">{p.name}</td>
                <td className="small">{p.squads.map((c) => c.name).join(", ") || "-"}</td>
                <td className="small">
                  {t("platforms.item_count", {
                    kpis: String((p.template.kpis ?? []).length),
                    sla: String((p.template.sla ?? []).length),
                  })}
                </td>
                <td>
                  <label className="switch" style={{ fontWeight: 400, fontSize: 13 }}>
                    <input type="checkbox" checked={p.steerco_enabled}
                           onChange={(e) => setEnabled(p, e.target.checked)} />
                    <span className="track"><span className="knob" /></span>
                    <span>{p.steerco_enabled ? t("platforms.on") : t("platforms.off")}</span>
                  </label>
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <button className="btn-secondary btn-sm" onClick={() => setEditing(p)}>✎ {t("action.edit")}</button>{" "}
                  {/* The slide's layout lives in the export Studio, the one layout engine. */}
                  <Link className="btn-ghost btn-sm" to={`/exports?scope=platform:${p.id}`}>{t("steerco.open_studio")}</Link>{" "}
                  <button className="btn-ghost btn-sm" onClick={() => remove(p)}>{t("action.delete")}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {editing && (
        <PlatformModal
          platform={editing === "new" ? null : editing}
          tribeId={tribeId}
          squads={squads}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); changed(); }}
        />
      )}
    </div>
  );
}

/** The tribe's model: the Steerco skeleton its Steerco leaders impose (KPI and
 *  their sub-metrics, SLA services). A new platform starts from it; an existing one
 *  comes back to it with "apply the tribe model". */
export function TribeModelEditor({ tribeId, onSaved }: { tribeId: number; onSaved?: () => void }) {
  const { t } = useI18n();
  const [kpis, setKpis] = useState<{ label: string; sub: string[] }[]>([]);
  const [sla, setSla] = useState<{ label: string }[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // The tribe whose model is on screen. Until the chosen tribe's model has
  // arrived, nothing may be saved: the previous tribe's items would be written
  // into it, and a late answer for the previous tribe is ignored.
  const [loadedFor, setLoadedFor] = useState<number | null>(null);
  useEffect(() => {
    setErr(null); setMsg(null); setLoadedFor(null); setKpis([]); setSla([]);
    let alive = true;
    api.get<any>(`/api/steerco/model?tribe_id=${tribeId}`)
      .then((m) => { if (!alive) return; setKpis(m.kpis ?? []); setSla(m.sla ?? []); setLoadedFor(tribeId); })
      .catch((e) => { if (alive) setErr(errorText(e)); });
    return () => { alive = false; };
  }, [tribeId]);

  async function save() {
    if (loadedFor !== tribeId) return;
    setErr(null); setMsg(null);
    try {
      const m = await api.put<any>(`/api/steerco/model?tribe_id=${tribeId}`, {
        kpis: kpis.filter((k) => k.label.trim()), sla: sla.filter((x) => x.label.trim()),
      });
      setKpis(m.kpis ?? []); setSla(m.sla ?? []);
      setMsg(t("admin.saved"));
      onSaved?.();
    } catch (e) { setErr(errorText(e)); }
  }

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="small muted">{t("platforms.model_hint")}</div>
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
        <button className="btn-sm" disabled={loadedFor !== tribeId} onClick={save}>{t("action.save")}</button>
        {msg && <span className="small" style={{ color: "var(--green)" }}>{msg}</span>}
      </div>
    </div>
  );
}

/** Create / edit one platform: identity, squads concerned, the slide's rows and how
 *  its KPI chart is drawn. */
function PlatformModal({ platform, tribeId, squads, onClose, onSaved }:
  { platform: Platform | null; tribeId: number; squads: Squad[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(platform?.name ?? "");
  const [description, setDescription] = useState(platform?.description ?? "");
  const [enabled, setEnabled] = useState(platform?.steerco_enabled ?? true);
  const [linked, setLinked] = useState<number[]>(platform?.squads.map((c) => c.id) ?? []);
  const [tpl, setTpl] = useState<PlatformTemplate>(platform?.template ?? EMPTY);
  const saved: Display = platform?.template?.display ?? { kpi_chart: "auto", chart_kpis: [] };
  const [mode, setMode] = useState<ChartMode>(saved.kpi_chart);
  const [picked, setPicked] = useState<string[]>(saved.chart_kpis);   // empty: every KPI
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const toggleSquad = (id: number) =>
    setLinked((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  function setItem(kind: "kpis" | "sla", i: number, patch: Partial<TemplateItem>) {
    setTpl((x) => ({ ...x, [kind]: (x[kind] ?? []).map((it, j) => (j === i ? { ...it, ...patch } : it)) }));
  }
  const addItem = (kind: "kpis" | "sla") => setTpl((x) => ({ ...x, [kind]: [...(x[kind] ?? []), { label: "" }] }));
  const removeItem = (kind: "kpis" | "sla", i: number) =>
    setTpl((x) => ({ ...x, [kind]: (x[kind] ?? []).filter((_, j) => j !== i) }));

  const labels = (tpl.kpis ?? []).map((k) => k.label).filter((l) => l.trim());
  const shown = picked.length ? picked.filter((k) => labels.includes(k)) : labels;
  const toggleKpi = (k: string) => {
    const base = picked.length ? picked : labels;
    const next = base.includes(k) ? base.filter((x) => x !== k) : labels.filter((x) => x === k || base.includes(x));
    // Every KPI ticked is "all": the list stays empty, and a KPI added later is in.
    setPicked(next.length === labels.length ? [] : next);
  };

  async function save() {
    setBusy(true); setErr(null);
    const body: any = { name, description, steerco_enabled: enabled, squad_ids: linked, tribe_id: tribeId };
    // A new platform starts from the tribe's model (server side); its skeleton is
    // adjusted afterwards, here, like any other platform.
    if (platform) body.template = {
      kpis: (tpl.kpis ?? []).filter((k) => k.label.trim()),
      sla: (tpl.sla ?? []).filter((x) => x.label.trim()),
    };
    try {
      if (platform) {
        await api.put(`/api/steerco/platforms/${platform.id}`, body);
        if (mode !== saved.kpi_chart || JSON.stringify(picked) !== JSON.stringify(saved.chart_kpis))
          await api.put(`/api/steerco/platforms/${platform.id}/display`, { kpi_chart: mode, chart_kpis: picked });
      } else await api.post("/api/steerco/platforms", body);
      onSaved();
    } catch (e) {
      setErr(errorText(e));
      setBusy(false);
    }
  }

  // Bring this platform back to the tribe's model: items that stay keep their
  // figures, the others go.
  async function applyModel() {
    if (!platform) return;
    setErr(null);
    try {
      const out = await api.post<Platform>(`/api/steerco/platforms/${platform.id}/apply-model`, {});
      setTpl(out.template);
    } catch (e) { setErr(errorText(e)); }
  }

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
          <div className="strong">{t("platforms.squads")}</div>
          <div className="small muted">{t("platforms.squads_hint")}</div>
          <div className="inline" style={{ gap: 10, flexWrap: "wrap" }}>
            {squads.length === 0 && <span className="small muted">{t("platforms.no_squad")}</span>}
            {squads.map((s) => (
              <label key={s.id} className="inline small" style={{ gap: 4 }}>
                <input type="checkbox" checked={linked.includes(s.id)} onChange={() => toggleSquad(s.id)} />
                {s.name}
              </label>
            ))}
          </div>
        </div>

        {!platform ? (
          <div className="banner small">{t("platforms.new_from_model")}</div>
        ) : (
          <>
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
                        <th style={{ width: 40 }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {(tpl[kind] ?? []).length === 0 && (
                        <tr><td colSpan={kind === "kpis" ? 3 : 2} className="small muted">{t("platforms.no_item")}</td></tr>
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
            </div>

            {/* How the KPI chart is drawn: a setting of the slide, kept for every export. */}
            <div className="stack" style={{ gap: 6 }}>
              <div className="strong">{t("steerco.render_title")}</div>
              <div role="radiogroup" aria-label={t("steerco.render_title")} className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
                {MODES.map((m) => (
                  <button key={m} type="button" role="radio" aria-checked={mode === m}
                          className={mode === m ? "btn-sm" : "btn-secondary btn-sm"} onClick={() => setMode(m)}>
                    {t(`steerco.render_${m}`)}
                  </button>
                ))}
              </div>
              <div className="small muted">{t(`steerco.render_${mode}_hint`, { n: LINES_MAX })}</div>
              {labels.length > 0 && (
                <>
                  <div className="small muted">{t("steerco.render_kpis", { n: shown.length, total: labels.length })}</div>
                  <div className="inline" style={{ gap: 12, flexWrap: "wrap" }}>
                    {labels.map((k) => (
                      <label key={k} className="inline small" style={{ gap: 4, cursor: "pointer" }}>
                        <input type="checkbox" checked={shown.includes(k)} onChange={() => toggleKpi(k)} /> {k}
                      </label>
                    ))}
                  </div>
                  {mode === "lines" && shown.length > LINES_MAX && (
                    <div className="small" style={{ color: "var(--orange)" }}>{t("steerco.render_too_many", { n: shown.length })}</div>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
