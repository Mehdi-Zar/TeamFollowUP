// The Steerco menu (ADR 0018): a topic of its own, out of the weekly reporting.
// Two tabs, so that the monthly work and the settings never mix:
//
//   Le mois      the month's work, in three steps: enter, validate, send
//                (and a year view of every platform's months)
//   Parametres   every setting, in one place, with a set-up checklist: who runs
//                it, the tribe's model, the platforms, the mails, who may read
//
// A Steerco leader (the tribe leader by default, the designated users, the
// administrator) sees both. A reader (the "steerco" capability) sees "Le mois",
// read only. The server checks every call the same way.
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { Tribe } from "../types";
import { useSetPageChrome } from "../components/pageChrome";
import ExportMenu from "../components/ExportMenu";
import { EmptyState } from "../components/ui";
import SteercoMonth from "../components/steerco/SteercoMonth";
import SteercoSettings from "../components/steerco/SteercoSettings";
import { currentSteercoPeriod } from "../steerco";

type Tab = "month" | "settings";
const TRIBE_KEY = "steerco.tribe";

export default function SteercoPage() {
  const { t } = useI18n();
  const { steerco } = useAuth();
  const [params, setParams] = useSearchParams();
  const [tribes, setTribes] = useState<Tribe[]>([]);

  useEffect(() => { api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {}); }, []);

  const runIds = steerco.run_tribe_ids;
  const designateIds = steerco.designate_tribe_ids;
  const tabs = useMemo(() => {
    const out: { key: Tab; label: string }[] = [];
    if (steerco.read || steerco.run || steerco.contribute) out.push({ key: "month", label: t("steerco.tab.month") });
    if (steerco.run || designateIds.length) out.push({ key: "settings", label: t("steerco.tab.settings") });
    return out;
  }, [steerco, designateIds.length, t]);

  // Links written before the two tabs (entry, consolidation, platforms, leaders) still land.
  const OLD: Record<string, Tab> = { entry: "month", consolidation: "month", platforms: "settings", leaders: "settings" };
  const raw = params.get("tab");
  const asked = (raw && OLD[raw]) || (raw as Tab | null);
  const tab: Tab | undefined = tabs.find((x) => x.key === asked)?.key ?? tabs[0]?.key;

  // The tribes this tab works on: the ones read for the month, the ones run or
  // designated in for the settings.
  const scopeIds = tab === "month"
    ? Array.from(new Set([...steerco.read_tribe_ids, ...runIds, ...steerco.contribute_tribe_ids])).sort((a, b) => a - b)
    : Array.from(new Set([...runIds, ...designateIds])).sort((a, b) => a - b);
  const [tribeId, setTribeId] = useState<number | null>(() => {
    const s = Number(localStorage.getItem(TRIBE_KEY));
    return Number.isFinite(s) && s > 0 ? s : null;
  });
  const shownTribe = tribeId !== null && scopeIds.includes(tribeId) ? tribeId : (scopeIds[0] ?? null);
  const pickTribe = (id: number) => { setTribeId(id); localStorage.setItem(TRIBE_KEY, String(id)); };
  const tribeName = (id: number) => tribes.find((x) => x.id === id)?.name ?? `#${id}`;

  // The month's filters, lifted here so the chrome ExportMenu targets them.
  const [period, setPeriod] = useState(currentSteercoPeriod());
  const [platformId, setPlatformId] = useState("");

  useSetPageChrome({
    title: t("steerco.title"),
    tabs,
    activeTab: tab,
    onTab: (k) => setParams({ tab: k }),
    actions: (
      <>
        {scopeIds.length > 1 && (
          <select className="w-auto" aria-label={t("admin.tribe")} value={shownTribe ?? ""}
                  onChange={(e) => pickTribe(Number(e.target.value))}>
            {scopeIds.map((id) => <option key={id} value={id}>{tribeName(id)}</option>)}
          </select>
        )}
        {tab === "month" && (
          <ExportMenu docs={["steerco"]} steerco={{ period, platformId, tribeId: shownTribe ?? undefined }} />
        )}
      </>
    ),
  }, [tabs, tab, scopeIds.join(","), shownTribe, tribes, period, platformId, t]);

  if (!tab) return <EmptyState message={t("steerco.closed")} />;
  if (shownTribe === null) return <EmptyState message={t("steerco.no_tribe")} />;
  const runsShown = steerco.all_tribes || runIds.includes(shownTribe);

  return (
    <div className="stack" style={{ gap: 16 }}>
      {tab === "month" && (
        <SteercoMonth tribeId={shownTribe} canRun={runsShown} period={period} setPeriod={setPeriod}
                      platformId={platformId} setPlatformId={setPlatformId}
                      onSettings={() => setParams({ tab: "settings" })} />
      )}
      {tab === "settings" && (
        <SteercoSettings tribeId={shownTribe} canRun={runsShown}
                         canDesignate={steerco.all_tribes || designateIds.includes(shownTribe)} />
      )}
    </div>
  );
}
