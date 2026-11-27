// Customer Success > Parametrage: who runs it, the stages, the offers and the
// thresholds of the dashboard badges (docs/37). CS leaders change them; the
// administrator and the tribe leader designate the CS leaders.
import { useEffect, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { CsSettings, Stage } from "../../cs";
import { Chip, ErrorBanner, Spinner, Toggle } from "../ui";

export default function CsSettingsTab({ tribeId, canRun, canDesignate }: {
  tribeId: number; canRun: boolean; canDesignate: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card stack" style={{ gap: 12 }}>
        <h2 style={{ margin: 0 }}>{t("cs.leaders.title")}</h2>
        <CsLeaders tribeId={tribeId} canDesignate={canDesignate} />
      </div>
      {canRun && <CsConfig tribeId={tribeId} />}
    </div>
  );
}

type Leader = { user_id: number; display_name: string; email: string; role: string; by_default: boolean; active: boolean };
type LeadersOut = { tribe_id: number; leaders: Leader[]; can_designate: boolean; can_exclude_default: boolean };
type Person = { id: number; name: string; email: string | null; tribe_id: number | null };

function CsLeaders({ tribeId, canDesignate }: { tribeId: number; canDesignate: boolean }) {
  const { t, role } = useI18n();
  const [data, setData] = useState<LeadersOut | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [pick, setPick] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setData(null); setErr(null);
    api.get<LeadersOut>(`/api/cs/leaders?tribe_id=${tribeId}`).then(setData).catch((e) => setErr(errorText(e)));
    if (canDesignate) api.get<Person[]>("/api/tribes/people").then((ps) => setPeople(ps.filter((p) => p.tribe_id === tribeId))).catch(() => {});
  }, [tribeId, canDesignate]);

  async function run(fn: () => Promise<LeadersOut>) {
    setBusy(true); setErr(null);
    try { setData(await fn()); setPick(""); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }
  const add = (uid: number) => run(() => api.post<LeadersOut>("/api/cs/leaders", { tribe_id: tribeId, user_id: uid }));
  const remove = (l: Leader) => {
    const msg = l.by_default ? t("cs.leaders.exclude_confirm", { name: l.display_name }) : t("cs.leaders.remove_confirm", { name: l.display_name });
    if (window.confirm(msg)) run(() => api.del<LeadersOut>(`/api/cs/leaders/${l.user_id}?tribe_id=${tribeId}`));
  };

  const taken = new Set((data?.leaders ?? []).filter((l) => l.active).map((l) => l.user_id));
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="small muted">{t("cs.leaders.hint")}</div>
      {err && <ErrorBanner message={err} />}
      {data === null ? (!err && <Spinner />) : (
        <>
          <table className="table">
            <thead><tr><th>{t("cs.leaders.name")}</th><th>{t("cs.leaders.role")}</th><th>{t("cs.leaders.how")}</th><th></th></tr></thead>
            <tbody>
              {data.leaders.length === 0 && <tr><td colSpan={4} className="small muted">{t("cs.leaders.none")}</td></tr>}
              {data.leaders.map((l) => (
                <tr key={l.user_id} style={l.active ? undefined : { opacity: 0.6 }}>
                  <td className="strong">{l.display_name}</td>
                  <td className="small">{role(l.role as any)}</td>
                  <td>{l.by_default
                    ? <span className={`badge ${l.active ? "badge-navy" : "badge-grey"}`}>{l.active ? t("cs.leaders.by_default") : t("cs.leaders.excluded")}</span>
                    : <span className="badge badge-green">{t("cs.leaders.designated")}</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    {l.by_default ? (data.can_exclude_default && (l.active
                      ? <button className="btn-ghost btn-sm" disabled={busy} onClick={() => remove(l)}>{t("cs.leaders.exclude")}</button>
                      : <button className="btn-secondary btn-sm" disabled={busy} onClick={() => add(l.user_id)}>{t("cs.leaders.restore")}</button>))
                      : data.can_designate && <button className="btn-ghost btn-sm" disabled={busy} onClick={() => remove(l)}>{t("action.remove")}</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.can_designate ? (
            <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
              <select aria-label={t("cs.leaders.pick")} value={pick} onChange={(e) => setPick(e.target.value)} style={{ minWidth: 240 }}>
                <option value="">{t("cs.leaders.pick")}</option>
                {people.filter((p) => !taken.has(p.id)).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <button className="btn-sm" disabled={!pick || busy} onClick={() => add(Number(pick))}>{t("cs.leaders.add")}</button>
            </div>
          ) : <div className="small muted">{t("cs.leaders.only_tl")}</div>}
        </>
      )}
    </div>
  );
}

function CsConfig({ tribeId }: { tribeId: number }) {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<CsSettings | null>(null);
  const [offer, setOffer] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setCfg(null);
    api.get<CsSettings>(`/api/cs/settings?tribe_id=${tribeId}`).then(setCfg).catch((e) => setErr(errorText(e)));
  }, [tribeId]);

  if (err && !cfg) return <ErrorBanner message={err} />;
  if (!cfg) return <Spinner />;
  const edit = (patch: Partial<CsSettings>) => { setCfg({ ...cfg, ...patch }); setOk(false); };
  const setStage = (i: number, patch: Partial<Stage>) => edit({ stages: cfg.stages.map((s, j) => j === i ? { ...s, ...patch } : s) });
  const move = (i: number, d: number) => {
    const next = [...cfg.stages];
    const [s] = next.splice(i, 1);
    next.splice(i + d, 0, s);
    edit({ stages: next });
  };

  async function save() {
    setBusy(true); setErr(null);
    try {
      const out = await api.put<CsSettings>(`/api/cs/settings?tribe_id=${tribeId}`, {
        stages: cfg!.stages, offers: cfg!.offers, stale_days: cfg!.stale_days, access_warn_days: cfg!.access_warn_days,
      });
      setCfg(out); setOk(true);
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="card stack" style={{ gap: 16 }}>
      <h2 style={{ margin: 0 }}>{t("cs.cfg.title")}</h2>
      {err && <ErrorBanner message={err} />}

      <div className="stack" style={{ gap: 8 }}>
        <div className="strong">{t("cs.cfg.stages")}</div>
        <div className="small muted">{t("cs.cfg.stages_hint")}</div>
        <table className="table">
          <thead><tr><th>{t("cs.cfg.stage_label")}</th><th>{t("cs.cfg.color")}</th><th>{t("cs.cfg.closed")}</th><th></th></tr></thead>
          <tbody>
            {cfg.stages.map((s, i) => (
              <tr key={s.key + i}>
                <td><input value={s.label} aria-label={t("cs.cfg.stage_label")} maxLength={80} onChange={(e) => setStage(i, { label: e.target.value })} /></td>
                <td><input type="color" value={s.color} aria-label={t("cs.cfg.color")} onChange={(e) => setStage(i, { color: e.target.value.toUpperCase() })} /></td>
                <td><Toggle checked={s.closed} onChange={(v) => setStage(i, { closed: v })}><span className="sr-only">{t("cs.cfg.closed")}</span></Toggle></td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <button className="btn-ghost btn-sm" disabled={i === 0} aria-label={t("cs.cfg.up")} onClick={() => move(i, -1)}>↑</button>
                  <button className="btn-ghost btn-sm" disabled={i === cfg.stages.length - 1} aria-label={t("cs.cfg.down")} onClick={() => move(i, 1)}>↓</button>
                  <button className="btn-ghost btn-sm" disabled={cfg.stages.length <= 1}
                          onClick={() => edit({ stages: cfg.stages.filter((_, j) => j !== i) })}>{t("action.remove")}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div><button className="btn-secondary btn-sm"
                     onClick={() => edit({ stages: [...cfg.stages, { key: "", label: t("cs.cfg.new_stage"), color: "#667085", closed: false }] })}>
          {t("cs.cfg.add_stage")}</button></div>
      </div>

      <div className="stack" style={{ gap: 8 }}>
        <div className="strong">{t("cs.cfg.offers")}</div>
        <div className="small muted">{t("cs.cfg.offers_hint")}</div>
        <div className="inline" style={{ gap: 6, flexWrap: "wrap" }}>
          {cfg.offers.length === 0 && <span className="small muted">{t("cs.cfg.no_offer")}</span>}
          {cfg.offers.map((o) => <Chip key={o} on onToggle={() => edit({ offers: cfg.offers.filter((x) => x !== o) })}>{o}</Chip>)}
        </div>
        <div className="inline" style={{ gap: 8 }}>
          <input value={offer} placeholder={t("cs.cfg.offer_ph")} aria-label={t("cs.cfg.offer_ph")} maxLength={255}
                 onChange={(e) => setOffer(e.target.value)} />
          <button className="btn-secondary btn-sm" disabled={!offer.trim()}
                  onClick={() => { edit({ offers: [...cfg.offers, offer.trim()] }); setOffer(""); }}>{t("action.add")}</button>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
        <label className="stack" style={{ gap: 4 }}>
          <span className="small strong">{t("cs.cfg.stale_days")}</span>
          <input type="number" min={1} max={365} value={cfg.stale_days} onChange={(e) => edit({ stale_days: Number(e.target.value) })} />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span className="small strong">{t("cs.cfg.access_days")}</span>
          <input type="number" min={1} max={365} value={cfg.access_warn_days} onChange={(e) => edit({ access_warn_days: Number(e.target.value) })} />
        </label>
      </div>

      <div className="inline" style={{ gap: 8, justifyContent: "flex-end", alignItems: "center" }}>
        {ok && <span className="small" style={{ color: "var(--green)" }}>{t("cs.saved")}</span>}
        <button className="btn-sm" disabled={busy} onClick={save}>{t("action.save")}</button>
      </div>
    </div>
  );
}
