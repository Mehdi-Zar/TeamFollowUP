// GettingStartedPage - the personalized onboarding / "what can I do here" screen.
// It mirrors the navigation and the API's authorization model: a journey card is
// shown only when the persona holds the matching capability AND its module is on
// (fail-closed). The card order is persona-specific, and admin/steering surfaces
// are intentionally pushed to the bottom rather than being the headline.
import { Link } from "react-router-dom";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { useModule } from "../config";
import { Role } from "../types";
import { canSeeAdmin, isGlobalAdmin } from "../perms";
import { useSetPageChrome } from "../components/pageChrome";
import { EmptyState } from "../components/ui";
import {
  IconAdmin, IconCalendar, IconDashboard, IconEntry, IconFeed, IconOrg, IconReview, IconTribes,
} from "../components/icons";

/** Getting Started, from the USER's point of view. What you see is driven by your
 *  persona's *capabilities* (can()) and the enabled modules - exactly like the
 *  nav - so custom personas and admin toggles are respected, and the page shows
 *  how to USE your workspace (not how to install it). Admin setup is a small block
 *  at the bottom, not the headline. */

/** Identifiers for each journey card that can appear in the onboarding list. */
type CardKey =
  | "dashboard" | "reporting" | "roadmap" | "otd" | "mysquads" | "feed" | "org" | "leaves";

/** Card key -> icon component (includes the two admin-only keys). */
const ICON: Record<CardKey | "admin" | "tribes", (p: { size?: number }) => JSX.Element> = {
  dashboard: IconDashboard, reporting: IconEntry, roadmap: IconEntry, otd: IconReview,
  mysquads: IconTribes, feed: IconFeed, org: IconOrg, leaves: IconCalendar,
  admin: IconAdmin, tribes: IconTribes,
};

/** Card key -> in-app route the card's CTA links to. */
const ROUTE: Record<CardKey, string> = {
  dashboard: "/", reporting: "/saisie", roadmap: "/roadmap", otd: "/otd",
  mysquads: "/mes-squads", feed: "/fil", org: "/organigramme", leaves: "/conges",
};

// Priority order per persona (only cards the user is actually entitled to appear).
const ORDER: Record<Role, CardKey[]> = {
  member: ["dashboard", "feed", "org", "roadmap", "leaves"],
  squad_leader: ["reporting", "otd", "mysquads", "dashboard", "feed", "roadmap", "leaves"],
  tribe_leader: ["mysquads", "otd", "dashboard", "roadmap", "org", "feed", "leaves"],
  admin: ["dashboard", "reporting", "roadmap", "otd", "mysquads", "feed", "org", "leaves"],
};

/**
 * Renders the personalized onboarding page: a greeting header, the persona's
 * ordered journey cards, and (for admins) a separate admin/steering section.
 *
 * Access: any authenticated user; content is filtered by capability + module.
 */
export default function GettingStartedPage() {
  const { t, role: roleLabel } = useI18n();
  const { user, effectiveRole, can } = useAuth();
  const m = useModule();
  const role = (effectiveRole ?? "member") as Role;

  useSetPageChrome({ title: t("gs.title") }, [t]);

  // A card shows only when the persona holds the capability AND the module is on -
  // the same pair the nav and the API enforce (fail-closed). OTD is role-scoped
  // (managed by tribe leader, read by the concerned squad leader).
  const visible = (k: CardKey): boolean => {
    switch (k) {
      case "dashboard": return can("dashboard") && m("dashboard");
      case "reporting": return can("reporting") && m("reporting");
      case "roadmap": return can("roadmap") && m("squad_content", "roadmap");
      case "otd": return ["admin", "tribe_leader", "squad_leader"].includes(role);
      case "mysquads": return can("mysquads");
      case "feed": return can("feed") && m("feed");
      case "org": return can("org") && m("org");
      case "leaves": return can("leaves") && m("leaves");
    }
  };

  const cards = (ORDER[role] ?? ORDER.member).filter(visible);
  const showAdmin = canSeeAdmin(role);

  return (
    <div className="stack" style={{ gap: 18, maxWidth: 860 }}>
      {/* Header: who you are + what you can do here */}
      <div className="card" style={{ background: "var(--navy)", color: "#fff" }}>
        <div className="strong" style={{ fontSize: 18 }}>
          {t("gs.hello", { name: user?.display_name || "" })}
        </div>
        <div style={{ marginTop: 4, opacity: 0.92 }}>
          <span className="badge" style={{ background: "rgba(255,255,255,.16)", color: "#fff" }}>{roleLabel(role)}</span>
          <span style={{ marginLeft: 10 }}>{t(`gs.sub.${role}` as const)}</span>
        </div>
      </div>

      {/* First steps: capability-driven journey cards */}
      {cards.length === 0 ? (
        <EmptyState message={t("gs.empty")} />
      ) : (
        <>
          <div className="small strong" style={{ textTransform: "uppercase", letterSpacing: ".04em", color: "var(--muted)" }}>
            {t("gs.firstSteps")}
          </div>
          <div className="stack" style={{ gap: 12 }}>
            {cards.map((k, i) => {
              const Icon = ICON[k];
              return (
                <div key={k} className="card" style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                  <StepIcon Icon={Icon} n={i + 1} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="strong">{t(`gs.card.${k}.title`)}</div>
                    <div className="small muted" style={{ marginTop: 2 }}>{t(`gs.card.${k}.desc`)}</div>
                    <Link to={ROUTE[k]} className="btn btn-secondary btn-sm" style={{ marginTop: 10, display: "inline-block" }}>
                      {t("gs.card.cta")} →
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Admin / steering surfaces - deliberately at the bottom, not the headline */}
      {showAdmin && (
        <>
          <div className="small strong" style={{ textTransform: "uppercase", letterSpacing: ".04em", color: "var(--muted)", marginTop: 6 }}>
            {t("gs.admin.section")}
          </div>
          <div className="stack" style={{ gap: 12 }}>
            <AdminCard Icon={ICON.admin} to="/admin" title={t("gs.card.admin.title")} desc={t("gs.card.admin.desc")} cta={t("gs.card.cta")} />
            {isGlobalAdmin(role) && (
              <AdminCard Icon={ICON.tribes} to="/tribus" title={t("gs.card.tribes.title")} desc={t("gs.card.tribes.desc")} cta={t("gs.card.cta")} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Circular icon badge for a journey card, overlaid with its 1-based step number.
 * Purely presentational.
 */
function StepIcon({ Icon, n }: { Icon: (p: { size?: number }) => JSX.Element; n: number }) {
  return (
    <div style={{
      flex: "0 0 auto", width: 40, height: 40, borderRadius: 11, background: "var(--ice-soft)",
      color: "var(--accent)", display: "inline-flex", alignItems: "center", justifyContent: "center", position: "relative",
    }}>
      <Icon size={20} />
      <span style={{
        position: "absolute", top: -6, left: -6, width: 20, height: 20, borderRadius: "50%",
        background: "var(--navy)", color: "#fff", fontSize: 11, fontWeight: 700,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
      }}>{n}</span>
    </div>
  );
}

/**
 * Card used in the admin/steering section (Admin console, Tribes). Same layout
 * as a journey card but without the numbered step, since these are not part of
 * the ordered "first steps" flow.
 */
function AdminCard({ Icon, to, title, desc, cta }: { Icon: (p: { size?: number }) => JSX.Element; to: string; title: string; desc: string; cta: string }) {
  return (
    <div className="card" style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
      <div style={{
        flex: "0 0 auto", width: 40, height: 40, borderRadius: 11, background: "var(--ice-soft)",
        color: "var(--accent)", display: "inline-flex", alignItems: "center", justifyContent: "center",
      }}>
        <Icon size={20} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="strong">{title}</div>
        <div className="small muted" style={{ marginTop: 2 }}>{desc}</div>
        <Link to={to} className="btn btn-secondary btn-sm" style={{ marginTop: 10, display: "inline-block" }}>{cta} →</Link>
      </div>
    </div>
  );
}
