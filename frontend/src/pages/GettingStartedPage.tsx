// GettingStartedPage - the personalized "what can I do here" guide.
// It mirrors the navigation and the API's authorization model: a step shows only
// when the persona holds the matching capability AND its module is on
// (fail-closed). The order is persona-specific, and Administration comes last.
//
// The guide opens as a window when the app starts (Layout), with a "don't show
// at startup" box, and again from the "?" button of the top bar. This page only
// keeps the same guide reachable by its address.
// React 19 removed the GLOBAL JSX namespace from @types/react; it is exported
// from the module instead. Type-only import, so it costs nothing at runtime.
import type { JSX } from "react";
import { useNavigate } from "react-router-dom";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { useModule } from "../config";
import { Role } from "../types";
import { isGlobalAdmin } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";
import { EmptyState } from "../components/ui";
import {
  IconAdmin, IconCalendar, IconDashboard, IconEntry, IconFeed, IconOrg, IconRoadmap, IconTribes,
} from "../components/icons";

/** Identifiers for each step that can appear in the guide. */
type CardKey =
  | "dashboard" | "reporting" | "roadmap" | "mysquads" | "feed" | "org" | "leaves";

/** Step -> icon component (includes the two admin-only keys). */
const ICON: Record<CardKey | "admin" | "tribes", (p: { size?: number }) => JSX.Element> = {
  dashboard: IconDashboard, reporting: IconEntry, roadmap: IconRoadmap,
  mysquads: IconTribes, feed: IconFeed, org: IconOrg, leaves: IconCalendar,
  admin: IconAdmin, tribes: IconTribes,
};

/** Step -> in-app route. The OTD step depends on who looks (see `route`). */
const ROUTE: Record<CardKey, string> = {
  dashboard: "/", reporting: "/saisie", roadmap: "/roadmap",
  mysquads: "/mes-squads", feed: "/fil", org: "/organigramme", leaves: "/conges",
};

// Order per persona. It only sorts: the tiles shown are every section the
// profile opens (capability and module), custom personas included.
const ALL_CARDS: CardKey[] = ["dashboard", "reporting", "mysquads", "roadmap", "org", "feed", "leaves"];
const ORDER: Record<string, CardKey[]> = {
  member: ["dashboard", "feed", "org", "roadmap", "leaves"],
  squad_leader: ["reporting", "mysquads", "dashboard", "feed", "roadmap", "org", "leaves"],
  contributor: ["reporting", "dashboard", "feed", "roadmap", "org", "leaves"],
  tribe_leader: ["mysquads", "dashboard", "roadmap", "org", "feed", "leaves"],
  admin: ["dashboard", "reporting", "roadmap", "mysquads", "feed", "org", "leaves"],
};
const KNOWN_ROLES = new Set(Object.keys(ORDER));

/**
 * The guide itself: a one-line greeting, then the persona's steps as tiles, each
 * one opening its screen. `onGo` runs before navigating (the window closes).
 */
export function GettingStartedGuide({ onGo }: { onGo?: () => void }) {
  const { t, role: roleLabel } = useI18n();
  const { user, effectiveRole, can, adminTabs } = useAuth();
  const m = useModule();
  const navigate = useNavigate();
  const role = (effectiveRole ?? "member") as Role;

  const visible = (k: CardKey): boolean => {
    switch (k) {
      case "dashboard": return can("dashboard") && m("dashboard");
      case "reporting": return can("reporting") && m("reporting");
      case "roadmap": return can("roadmap") && m("squad_content", "roadmap");
      case "mysquads": return can("mysquads");
      case "feed": return can("feed") && m("feed");
      case "org": return can("org") && m("org");
      case "leaves": return can("leaves") && m("leaves");
    }
  };
  const route = (k: CardKey) => ROUTE[k];
  const order = ORDER[role] ?? ALL_CARDS;
  const cards = [...order, ...ALL_CARDS.filter((k) => !order.includes(k))].filter(visible);
  const go = (to: string) => { onGo?.(); navigate(to); };

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div>
        <div className="strong" style={{ fontSize: 16 }}>{t("gs.hello", { name: user?.display_name || "" })}</div>
        <div className="small muted" style={{ marginTop: 2 }}>
          <span className="badge badge-navy" style={{ marginRight: 8 }}>{roleLabel(role)}</span>
          {t(KNOWN_ROLES.has(role) ? `gs.sub.${role}` : "gs.sub.custom")}
        </div>
      </div>

      {cards.length === 0 ? (
        <EmptyState message={t("gs.empty")} />
      ) : (
        <div className="gs-grid">
          {cards.map((k, i) => (
            <Tile key={k} Icon={ICON[k]} n={i + 1} title={t(`gs.card.${k}.title`)}
                  desc={t(`gs.card.${k}.desc`)} onClick={() => go(route(k))} />
          ))}
        </div>
      )}

      {/* Administration last: it is where one sets things up, not where one works. */}
      {adminTabs.length > 0 && (
        <>
          <div className="gs-section">{t("gs.admin.section")}</div>
          <div className="gs-grid">
            <Tile Icon={ICON.admin} title={t("gs.card.admin.title")} desc={t("gs.card.admin.desc")} onClick={() => go("/admin")} />
            {isGlobalAdmin(role) && (
              <Tile Icon={ICON.tribes} title={t("gs.card.tribes.title")} desc={t("gs.card.tribes.desc")} onClick={() => go("/admin?section=tribes")} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

/** The guide as a page, for its address (/prise-en-main) and the command palette. */
export default function GettingStartedPage() {
  const { t } = useI18n();
  useSetPageChrome({ title: t("gs.title") }, [t]);
  return (
    <div className="card" style={{ maxWidth: 860 }}>
      <GettingStartedGuide />
    </div>
  );
}

/** One step: the whole tile is the button, its number in the icon's corner. */
function Tile({ Icon, n, title, desc, onClick }: {
  Icon: (p: { size?: number }) => JSX.Element; n?: number; title: string; desc: string; onClick: () => void;
}) {
  return (
    <button type="button" className="gs-tile" onClick={onClick}>
      <span className="gs-tile-icon">
        <Icon size={18} />
        {n !== undefined && <span className="gs-tile-n">{n}</span>}
      </span>
      <span className="gs-tile-text">
        <span className="strong">{title}</span>
        <span className="small muted">{desc}</span>
      </span>
    </button>
  );
}
