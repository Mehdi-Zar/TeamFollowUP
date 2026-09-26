/**
 * The Administration tabs: their labels and the four families of the menu.
 * Shared by the admin menu (AdminPage) and the personas table, which lists
 * the same tabs in the same order so a tick reads like the menu it opens.
 */
export const TAB_LABEL: Record<string, string> = {
  tribes: "admin.tab.tribes",
  import: "admin.tab.import",
  tribe: "admin.tab.my_tribe",
  squads: "admin.tab.squads",
  platforms: "admin.tab.platforms",
  users: "admin.tab.users",
  personas: "admin.tab.personas",
  modules: "admin.tab.modules",
  moderation: "admin.tab.moderation",
  auth: "admin.tab.auth",
  api: "admin.tab.api",
  smtp: "admin.tab.smtp",
  trust: "admin.tab.trust",
  report: "admin.tab.report",
  leaves: "admin.tab.leaves",
  logs: "admin.tab.logs",
  settings: "admin.tab.settings",
  branding: "admin.tab.branding",
  data: "admin.tab.data",
  audit: "admin.tab.audit",
  ops: "admin.tab.ops",
};

// Les quatre familles du menu, dans l'ordre ou l'on se pose les questions en
// montant une installation: qui est dans l'organisation, ce que l'application
// propose, comment on s'y connecte, comment on l'entretient. Seuls les elements
// que le role peut ouvrir sont affiches.
//
// L'import ferme la premiere famille: il sert une fois, au debut, et jamais plus.
// Le mettre au milieu le faisait passer pour un reglage courant.
export const ADMIN_GROUPS: { titleKey: string; items: string[] }[] = [
  { titleKey: "admin.group.org", items: ["tribes", "tribe", "squads", "platforms", "users", "personas", "import"] },
  { titleKey: "admin.group.config", items: ["modules", "report", "leaves", "settings", "branding"] },
  { titleKey: "admin.group.access", items: ["auth", "smtp", "api", "trust"] },
  { titleKey: "admin.group.oversight", items: ["audit", "moderation", "logs", "data", "ops"] },
];
