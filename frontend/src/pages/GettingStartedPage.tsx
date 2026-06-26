import { Link } from "react-router-dom";
import { useI18n } from "../i18n";
import { useAuth } from "../auth";
import { Role } from "../types";
import { useSetPageChrome } from "../components/pageChrome";
import {
  IconAdmin, IconDashboard, IconEntry, IconFeed, IconOrg, IconReview, IconTribes,
} from "../components/icons";

type IconKey = "tribes" | "admin" | "users" | "squads" | "org" | "report" | "review" | "dash" | "feed" | "mail" | "team";
const ICON: Record<IconKey, (p: { size?: number }) => JSX.Element> = {
  tribes: IconTribes, admin: IconAdmin, users: IconAdmin, squads: IconTribes, org: IconOrg,
  report: IconEntry, review: IconReview, dash: IconDashboard, feed: IconFeed, mail: IconReview, team: IconTribes,
};

type Step = { icon: IconKey; title: string; desc: string; to?: string; cta?: string };

const STEPS: Record<"fr" | "en", Record<Role, { hello: string; steps: Step[] }>> = {
  fr: {
    admin: {
      hello: "Vous administrez l'outil. Voici comment le mettre en place de A à Z.",
      steps: [
        { icon: "tribes", title: "Créez vos tribes", desc: "Créez chaque tribe et nommez son tribe leader au moment de la création.", to: "/tribus", cta: "Aller aux Tribes" },
        { icon: "users", title: "Créez les utilisateurs", desc: "Ajoutez les personnes et donnez-leur un rôle (tribe leader, squad leader, membre).", to: "/admin", cta: "Administration → Utilisateurs" },
        { icon: "admin", title: "Activez les services", desc: "Choisissez les modules visibles (Fil, Revue, Rapport…) et leurs options dans l'onglet Services.", to: "/admin", cta: "Administration → Services" },
        { icon: "mail", title: "Configurez l'email (SMTP)", desc: "Indispensable pour l'envoi automatique des rapports et les notifications.", to: "/admin", cta: "Administration → Email" },
        { icon: "dash", title: "Pilotez l'ensemble", desc: "Suivez l'avancement de toutes les tribes sur le tableau de bord et la revue.", to: "/", cta: "Voir le dashboard" },
      ],
    },
    tribe_leader: {
      hello: "Vous pilotez votre tribe. Cadrez vos squads, puis suivez leur avancement.",
      steps: [
        { icon: "squads", title: "Définissez vos squads", desc: "Créez vos squads et désignez un responsable (squad leader) pour chacune.", to: "/mes-squads", cta: "Aller à Mes squads" },
        { icon: "squads", title: "OTD (objectifs annuels)", desc: "Pour chaque squad : fixez les OTD (objectifs engagés de l'année).", to: "/mes-squads", cta: "Mes squads → Éditer" },
        { icon: "org", title: "Construisez l'organigramme", desc: "Organisez vos squads par domaine pour une vue claire de la tribe.", to: "/organigramme", cta: "Aller à l'Organigramme" },
        { icon: "review", title: "Animez la revue", desc: "Chaque semaine, regardez ce qui a bougé : avancement, blocages, confiance.", to: "/revue", cta: "Voir la Revue" },
        { icon: "mail", title: "Recevez le rapport", desc: "Abonnez-vous pour recevoir le rapport par email à la fréquence de votre choix.", to: "/", cta: "Dashboard → Exporter" },
      ],
    },
    squad_leader: {
      hello: "Vous dirigez une ou plusieurs squads. Tenez votre équipe et votre reporting à jour.",
      steps: [
        { icon: "team", title: "Gérez votre équipe", desc: "Ajoutez vos membres et définissez qui est rattaché à qui.", to: "/mes-squads", cta: "Aller à Ma squad" },
        { icon: "report", title: "Faites votre reporting", desc: "Renseignez vos jalons par trimestre et l'avancement.", to: "/saisie", cta: "Aller au Reporting" },
        { icon: "review", title: "Ajoutez une note de revue", desc: "Quelques lignes + un indice de confiance : c'est ce qui nourrit la revue d'équipe.", to: "/saisie", cta: "Reporting → Revue" },
        { icon: "report", title: "Soumettez votre cycle", desc: "Cliquez « Soumettre » pour figer l'état : il devient la dernière soumission.", to: "/saisie", cta: "Aller au Reporting" },
        { icon: "feed", title: "Restez connecté", desc: "Partagez infos et incidents dans le fil, suivez le dashboard de la tribe.", to: "/fil", cta: "Voir le Fil" },
      ],
    },
    member: {
      hello: "Bienvenue ! Voici l'essentiel pour suivre l'activité de la tribe.",
      steps: [
        { icon: "dash", title: "Le tableau de bord", desc: "Vue d'ensemble : statut et avancement de chaque squad.", to: "/", cta: "Voir le dashboard" },
        { icon: "feed", title: "Le fil d'actualité", desc: "Suivez les annonces et incidents, réagissez et répondez.", to: "/fil", cta: "Voir le Fil" },
        { icon: "org", title: "L'organigramme", desc: "Qui fait quoi dans la tribe - cliquez une squad pour son détail.", to: "/organigramme", cta: "Voir l'Organigramme" },
        { icon: "review", title: "Vos préférences", desc: "Choisissez vos notifications dans vos préférences.", to: "/preferences", cta: "Mes préférences" },
      ],
    },
  },
  en: {
    admin: {
      hello: "You administer the tool. Here's how to set it up end to end.",
      steps: [
        { icon: "tribes", title: "Create your tribes", desc: "Create each tribe and name its tribe leader at creation.", to: "/tribus", cta: "Go to Tribes" },
        { icon: "users", title: "Create users", desc: "Add people and give them a role (tribe leader, squad leader, member).", to: "/admin", cta: "Admin → Users" },
        { icon: "admin", title: "Enable services", desc: "Pick which modules are visible (Feed, Review, Report…) and their options.", to: "/admin", cta: "Admin → Services" },
        { icon: "mail", title: "Configure email (SMTP)", desc: "Required for automatic reports and notifications.", to: "/admin", cta: "Admin → Email" },
        { icon: "dash", title: "Steer everything", desc: "Track all tribes on the dashboard and the review.", to: "/", cta: "Open dashboard" },
      ],
    },
    tribe_leader: {
      hello: "You lead your tribe. Set up your squads, then track their progress.",
      steps: [
        { icon: "squads", title: "Define your squads", desc: "Create squads and assign a squad leader to each.", to: "/mes-squads", cta: "Go to My squads" },
        { icon: "squads", title: "OTD (annual objectives)", desc: "Per squad: set the OTD (this year's committed objectives).", to: "/mes-squads", cta: "My squads → Edit" },
        { icon: "org", title: "Build the org chart", desc: "Organise squads by domain for a clear view of the tribe.", to: "/organigramme", cta: "Go to Org chart" },
        { icon: "review", title: "Run the review", desc: "Each week, see what moved: progress, blockers, confidence.", to: "/revue", cta: "Open Review" },
        { icon: "mail", title: "Get the report", desc: "Subscribe to receive the report by email at your chosen cadence.", to: "/", cta: "Dashboard → Export" },
      ],
    },
    squad_leader: {
      hello: "You lead one or more squads. Keep your team and reporting up to date.",
      steps: [
        { icon: "team", title: "Manage your team", desc: "Add members and set who reports to whom.", to: "/mes-squads", cta: "Go to My squad" },
        { icon: "report", title: "Do your reporting", desc: "Fill in milestones per quarter and progress.", to: "/saisie", cta: "Go to Reporting" },
        { icon: "review", title: "Add a review note", desc: "A few lines + a confidence level feed the team review.", to: "/saisie", cta: "Reporting → Review" },
        { icon: "report", title: "Submit your cycle", desc: "Click 'Submit' to freeze the state as the latest submission.", to: "/saisie", cta: "Go to Reporting" },
        { icon: "feed", title: "Stay in the loop", desc: "Share news and incidents in the feed, follow the dashboard.", to: "/fil", cta: "Open Feed" },
      ],
    },
    member: {
      hello: "Welcome! Here's what you need to follow the tribe.",
      steps: [
        { icon: "dash", title: "The dashboard", desc: "Overview: status and progress of each squad.", to: "/", cta: "Open dashboard" },
        { icon: "feed", title: "The activity feed", desc: "Follow announcements and incidents, react and reply.", to: "/fil", cta: "Open Feed" },
        { icon: "org", title: "The org chart", desc: "Who does what in the tribe - click a squad for details.", to: "/organigramme", cta: "Open Org chart" },
        { icon: "review", title: "Your preferences", desc: "Choose your notifications in your preferences.", to: "/preferences", cta: "My preferences" },
      ],
    },
  },
};

export default function GettingStartedPage() {
  const { t, lang, role: roleLabel } = useI18n();
  const { user, effectiveRole } = useAuth();
  const role = (effectiveRole ?? "member") as Role;
  const data = STEPS[lang === "en" ? "en" : "fr"][role];

  useSetPageChrome({ title: t("gs.title") }, [t]);

  return (
    <div className="stack" style={{ gap: 18, maxWidth: 820 }}>
      <div className="card" style={{ background: "var(--navy)", color: "#fff" }}>
        <div className="strong" style={{ fontSize: 18 }}>
          {t("gs.hello", { name: user?.display_name || "" })}
        </div>
        <div style={{ marginTop: 4, opacity: 0.9 }}>
          <span className="badge" style={{ background: "rgba(255,255,255,.16)", color: "#fff" }}>{roleLabel(role)}</span>
          <span style={{ marginLeft: 10 }}>{data.hello}</span>
        </div>
      </div>

      <div className="stack" style={{ gap: 12 }}>
        {data.steps.map((s, i) => {
          const Icon = ICON[s.icon];
          return (
            <div key={i} className="card" style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
              <div style={{
                flex: "0 0 auto", width: 40, height: 40, borderRadius: 11, background: "var(--ice-soft)",
                color: "var(--accent)", display: "inline-flex", alignItems: "center", justifyContent: "center", position: "relative",
              }}>
                <Icon size={20} />
                <span style={{
                  position: "absolute", top: -6, left: -6, width: 20, height: 20, borderRadius: "50%",
                  background: "var(--navy)", color: "#fff", fontSize: 11, fontWeight: 700,
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                }}>{i + 1}</span>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="strong">{s.title}</div>
                <div className="small muted" style={{ marginTop: 2 }}>{s.desc}</div>
                {s.to && (
                  <Link to={s.to} className="btn btn-secondary btn-sm" style={{ marginTop: 10, display: "inline-block" }}>
                    {s.cta} →
                  </Link>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
