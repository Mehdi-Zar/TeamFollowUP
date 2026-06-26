// Built-in roles plus any admin-created custom persona key.
export type Role = "admin" | "tribe_leader" | "squad_leader" | "member" | (string & {});

export type Capability = "dashboard" | "roadmap" | "org" | "feed" | "reporting" | "mysquads";

export interface RoadmapCellItem {
  title: string;
  status: RoadmapStatus;
  owner?: string | null;
  stage?: string | null;
  theme?: string | null;
  dependency?: string | null;
}
export interface RoadmapMatrixQuarter { q: number; pct: number; comment?: string | null; items: RoadmapCellItem[]; }
export interface RoadmapMatrixSquad { squad_id: number; name: string; annual_pct: number; quarters: RoadmapMatrixQuarter[]; }
export interface RoadmapMatrixTribe { tribe_id: number | null; tribe_name: string; squads: RoadmapMatrixSquad[]; }
export interface RoadmapMatrix { year: number; scope_name: string; tribes: RoadmapMatrixTribe[]; }

export interface Persona {
  key: string;
  label: string;
  builtin: boolean;
  caps: Record<string, boolean>;
}

export interface Permissions {
  role: Role;
  tribe_id: number | null;
  can_access_admin: boolean;
  admin_tabs: string[];
  assignable_roles: Role[];
  can_create_tribe: boolean;
  can_manage_users: boolean;
  capabilities?: Record<string, boolean>;
}
export type Rag = "green" | "amber" | "red";
export type RoadmapStatus = "on_track" | "at_risk" | "blocked" | "done";
export type QuarterHealth = "on_track" | "at_risk" | "blocked";
export type Trend = "on_target" | "under_pressure" | "missed";
export type DependencyKind = "text" | "squad" | "tribe";
export type ReleaseStage = "EA" | "GA";
// "product" and "transverse" ship today; any custom key is allowed (extensible).
export type SquadType = "product" | "transverse" | (string & {});
export type OtdStatus = "on_track" | "at_risk" | "late" | "delivered";

export interface Initiative {
  id: number;
  tribe_id: number;
  year: number;
  title: string;
  squad_id?: number | null;
  squad_name?: string | null;
  owner?: string | null;
  deadline?: string | null;
  description?: string | null;
  display_order: number;
  is_active: boolean;
}

export interface Otd {
  id: number;
  tribe_id: number;
  year: number;
  title: string;
  description?: string | null;
  budget_ref?: string | null;
  committed_date?: string | null;
  owner_user_id?: number | null;
  display_order: number;
}

// Reporting (read) shapes returned by the report endpoints.
export interface ReportJalon {
  id: number; title: string; theme?: string | null; quarter: number; stage?: string | null;
  status: RoadmapStatus; squad_id: number; squad_name: string;
  otd_id?: number | null; otd_title?: string | null; owner?: string | null;
}
export interface ReportObjective {
  id: number; title: string; squad_id: number; squad_name: string; rag: Rag;
  status: RoadmapStatus; jalons: ReportJalon[];
}
export interface ReportInitiative {
  id: number; title: string; description?: string | null; owner_name?: string | null;
  status: RoadmapStatus; progress: number;
  counts: { total: number; done: number; blocked: number; at_risk: number };
  objectives: ReportObjective[];
}
export interface InitiativeReport {
  year: number; scope_name: string; initiatives: ReportInitiative[];
}
export interface OtdReport extends Otd {
  owner_name?: string | null;
  status: OtdStatus;
  counts: { total: number; done: number; blocked: number; at_risk: number };
  jalons: { id: number; title: string; quarter: number; stage?: string | null; status: RoadmapStatus; squad_id: number; squad_name: string }[];
}
export interface CandidateObjective { id: number; title: string; squad_id: number; squad_name: string; initiative_id?: number | null; }
export interface CandidateJalon { id: number; title: string; quarter: number; theme?: string | null; squad_id: number; squad_name: string; otd_id?: number | null; }

export interface User {
  id: number;
  email: string;
  display_name: string;
  role: Role;
  tribe_id?: number | null;
  is_break_glass: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
}

export interface Tribe {
  id: number;
  name: string;
  description?: string | null;
  display_order: number;
}

export interface LeaderInfo {
  id?: number | null;
  display_name?: string | null;
  email?: string | null;
}

export interface Freshness {
  last_submitted_at: string | null;
  age_days: number | null;
  is_stale: boolean;
  threshold_days: number;
  never_submitted: boolean;
}

export interface Counts {
  objectives_total: number;
  objectives_red: number;
  objectives_amber: number;
  objectives_green: number;
  roadmap_total: number;
  roadmap_done: number;
  roadmap_blocked: number;
  roadmap_at_risk: number;
  roadmap_on_track: number;
}

export interface Objective {
  id: number;
  squad_id: number;
  year: number;
  title: string;
  description?: string | null;
  target_date?: string | null;
  rag_status: Rag;
  weight: number;
  is_active: boolean;
  initiative_id?: number | null;
}

export interface RoadmapItem {
  id: number;
  squad_id: number;
  year: number;
  quarter: number;
  title: string;
  theme?: string | null;
  release_stage: ReleaseStage;
  description?: string | null;
  success_criteria?: string | null;
  user_benefit?: string | null;
  dependencies?: string | null;
  dependency_kind?: DependencyKind | null;
  dependency_squad_id?: number | null;
  dependency_tribe_id?: number | null;
  dependency_label?: string | null;
  risks?: string | null;
  owner?: string | null;
  status: RoadmapStatus;
  display_order: number;
  objective_id?: number | null;
  otd_id?: number | null;
  otd_label?: string | null;
}

export interface DependentItem {
  squad_id: number;
  squad_name: string;
  tribe_name?: string | null;
  year: number;
  quarter: number;
  title: string;
  status: RoadmapStatus;
  via: DependencyKind;
}

export interface Kpi {
  id: number;
  squad_id: number;
  name: string;
  unit?: string | null;
  target_value?: number | null;
  current_value?: number | null;
  trend_status: Trend;
  comment?: string | null;
}

export interface Member {
  id: number;
  squad_id: number;
  full_name: string;
  role_title?: string | null;
  user_id?: number | null;
  manager_id?: number | null;
  display_order: number;
}

export interface Squad {
  id: number;
  tribe_id: number;
  name: string;
  description?: string | null;
  leader_user_id?: number | null;
  display_order: number;
  kpis_enabled: boolean;
  budget_enabled?: boolean;
  squad_type?: SquadType;
  products?: string[];
  hardware?: string[];
}

export type KeyMessageKind = "success" | "alert" | "risk";

export interface KeyMessage {
  id: number;
  squad_id: number;
  year: number;
  kind: KeyMessageKind;
  text: string;
  display_order: number;
  created_at: string;
}

export type BudgetStatus = "on_track" | "at_risk" | "over";

export interface Budget {
  total?: number | null;
  spent?: number | null;
  forecast?: number | null;
  comment?: string | null;
  status: BudgetStatus;
  spent_pct?: number | null;
  forecast_pct?: number | null;
  overrun: number;
  overrun_pct: number;
  updated_at?: string | null;
}

export interface QuarterCell {
  progress_pct: number;
  comment?: string | null;
}

export interface SquadDetail extends Squad {
  leader?: LeaderInfo | null;
  year: number;
  annual_progress: number;
  freshness: Freshness;
  counts: Counts;
  quarter_progress: Record<string, QuarterCell>;
  objectives: Objective[];
  roadmap_items: RoadmapItem[];
  kpis: Kpi[];
  members: Member[];
  key_messages: KeyMessage[];
  budget?: Budget | null;
}

export interface Breakdown {
  total: number;
  on_track: number;
  at_risk: number;
  blocked: number;
  done: number;
}

export interface SquadCard {
  squad_id: number;
  name: string;
  tribe_id: number;
  tribe_name?: string | null;
  leader?: LeaderInfo | null;
  annual_progress: number;
  risk_rank: number;
  focus_quarter?: number | null;
  quarter_progress: Record<string, number>;
  quarter_breakdowns: Record<string, Breakdown>;
  blocked_count: number;
  at_risk_count: number;
  counts: Counts;
  members_count: number;
  freshness: Freshness;
}

export interface ModulesConfig {
  dashboard: { enabled: boolean };
  org: { enabled: boolean };
  reporting: { enabled: boolean };
  feed: { enabled: boolean; reactions: boolean; replies: boolean; pin: boolean; kinds: boolean };
  review: { enabled: boolean; weekly_report: boolean };
  squad_content: { enabled: boolean; objectives: boolean; roadmap: boolean; kpis: boolean };
  notifications: { enabled: boolean; inapp: boolean; email: boolean };
  exports_csv: { enabled: boolean };
  getting_started: { enabled: boolean };
}

export type ModuleKey = keyof ModulesConfig;

export interface ReviewAction {
  id: number;
  squad_id: number;
  text: string;
  owner?: string | null;
  due_date?: string | null;
  done: boolean;
  created_at?: string | null;
}

export interface PublicConfig {
  app_name: string;
  app_subtitle: string;
  default_lang: "fr" | "en";
  default_year: number;
  feed_post_scope: "leaders" | "everyone";
  feed_kinds: FeedKind[];
  smtp_enabled: boolean;
  modules: ModulesConfig;
}

export interface Notif {
  id: number;
  kind: "tweet" | "reply";
  actor_name?: string | null;
  excerpt?: string | null;
  link?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationsResponse {
  unread_count: number;
  items: Notif[];
}

export interface Preferences {
  notify_tweets: boolean;
  notify_replies: boolean;
  email_notifications: boolean;
  subscribe_weekly_report: boolean;
}

export interface DashboardSummary {
  squads_total: number;
  blocked_jalons: number;
  at_risk_jalons: number;
  squads_stale: number;
  avg_progress: number;
}

export interface DashboardOut {
  year: number;
  current_year: number;
  current_quarter: number;
  summary: DashboardSummary;
  cards: SquadCard[];
}

export interface SnapshotMeta {
  id: number;
  squad_id: number;
  submitted_by_user_id?: number | null;
  submitted_at: string;
  cycle_label: string;
}

export interface OrgNode {
  id: number;
  parent_id?: number | null;
  title: string;
  person_name?: string | null;
  squad_id?: number | null;
  squad_status?: QuarterHealth | null;
  display_order: number;
  children: OrgNode[];
}

export interface TribeOrg {
  tribe_id: number;
  tribe_name: string;
  squads_count: number;
  tree: OrgNode[];
}

export interface AuditEntry {
  id: number;
  user_id?: number | null;
  action: string;
  entity?: string | null;
  entity_id?: string | null;
  timestamp: string;
  detail?: any;
}

export interface AuthConfig {
  oidc_enabled: boolean;
  saml_enabled: boolean;
}

// ---- Feed (tweet zone) ----
export type FeedKind = "incident" | "info" | "success";
export type ReactionKind = "like" | "ack";

export interface AuthorInfo {
  id?: number | null;
  display_name?: string | null;
  role?: string | null;
}

export interface FeedReply {
  id: number;
  content: string;
  created_at: string;
  author: AuthorInfo;
}

export interface FeedPost {
  id: number;
  content: string;
  kind: FeedKind;
  squad_id?: number | null;
  squad_name?: string | null;
  is_pinned: boolean;
  created_at: string;
  author: AuthorInfo;
  replies: FeedReply[];
  reactions: Record<string, number>;
  my_reactions: string[];
}

