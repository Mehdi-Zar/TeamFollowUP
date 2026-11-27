// Customer Success > Responsables: who runs Customer Success in the tribe
// (docs/37). The administrator and the tribe leader designate the CS leaders.
// The stages and the thresholds of the badges keep their defaults: nothing to set.
import { useEffect, useState } from "react";
import { api, errorText } from "../../api";
import { useI18n } from "../../i18n";
import { ErrorBanner, Spinner } from "../ui";

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
                    ? <span className={`small ${l.active ? "" : "muted"}`}>{l.active ? t("cs.leaders.by_default") : t("cs.leaders.excluded")}</span>
                    : <span className="small">{t("cs.leaders.designated")}</span>}</td>
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
