// The Customer Success menu (ADR 0020, docs/37): the projects a CS team delivers.
// Two tabs, like the Steerco:
//
//   Projets       the dashboard (figures and badges), then one card per project,
//                 grouped Blocked / In progress / Delivered; a card opens the
//                 project in a window of the app. The recap mail is built from here.
//   Parametrage   the CS leaders, the stages, the offers and the thresholds.
//
// A CS leader (the tribe leader by default, the designated users, the
// administrator) sees both. A reader (capability "customer_success") and a
// contributor see the projects. The server checks every call the same way.
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { Tribe } from "../types";
import { useSetPageChrome } from "../components/pageChrome";
import { EmptyState } from "../components/ui";
import CsProjects from "../components/cs/CsProjects";
import CsSettingsTab from "../components/cs/CsSettings";

type Tab = "projects" | "settings";
const TRIBE_KEY = "cs.tribe";

export default function CsPage() {
  const { t } = useI18n();
  const { customerSuccess: cs } = useAuth();
  const [params, setParams] = useSearchParams();
  const [tribes, setTribes] = useState<Tribe[]>([]);

  useEffect(() => { api.get<Tribe[]>("/api/tribes").then(setTribes).catch(() => {}); }, []);

  const tabs = useMemo(() => {
    const out: { key: Tab; label: string }[] = [];
    if (cs.read || cs.run || cs.contribute) out.push({ key: "projects", label: t("cs.tab.projects") });
    if (cs.run || cs.designate_tribe_ids.length) out.push({ key: "settings", label: t("cs.tab.settings") });
    return out;
  }, [cs, t]);
  const asked = params.get("tab") as Tab | null;
  const tab: Tab | undefined = tabs.find((x) => x.key === asked)?.key ?? tabs[0]?.key;

  const scopeIds = tab === "projects"
    ? Array.from(new Set([...cs.read_tribe_ids, ...cs.run_tribe_ids, ...cs.contribute_tribe_ids])).sort((a, b) => a - b)
    : Array.from(new Set([...cs.run_tribe_ids, ...cs.designate_tribe_ids])).sort((a, b) => a - b);
  const [tribeId, setTribeId] = useState<number | null>(() => {
    const s = Number(localStorage.getItem(TRIBE_KEY));
    return Number.isFinite(s) && s > 0 ? s : null;
  });
  const shown = tribeId !== null && scopeIds.includes(tribeId) ? tribeId : (scopeIds[0] ?? null);
  const pickTribe = (id: number) => { setTribeId(id); localStorage.setItem(TRIBE_KEY, String(id)); };
  const tribeName = (id: number) => tribes.find((x) => x.id === id)?.name ?? `#${id}`;

  useSetPageChrome({
    title: t("cs.title"),
    tabs,
    activeTab: tab,
    onTab: (k) => setParams({ tab: k }),
    actions: scopeIds.length > 1 ? (
      <select className="w-auto" aria-label={t("admin.tribe")} value={shown ?? ""}
              onChange={(e) => pickTribe(Number(e.target.value))}>
        {scopeIds.map((id) => <option key={id} value={id}>{tribeName(id)}</option>)}
      </select>
    ) : undefined,
  }, [tabs, tab, scopeIds.join(","), shown, tribes, t]);

  if (!tab) return <EmptyState message={t("cs.closed")} />;
  if (shown === null) return <EmptyState message={t("cs.no_tribe")} />;
  const runs = cs.all_tribes || cs.run_tribe_ids.includes(shown);

  return (
    <div className="stack" style={{ gap: 16 }}>
      {tab === "projects" && <CsProjects tribeId={shown} canRun={runs} />}
      {tab === "settings" && (
        <CsSettingsTab tribeId={shown} canRun={runs}
                       canDesignate={cs.all_tribes || cs.designate_tribe_ids.includes(shown)} />
      )}
    </div>
  );
}
