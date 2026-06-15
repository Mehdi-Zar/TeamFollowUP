export type Role = "admin" | "tribe_leader" | "squad_leader" | "member";
export type Rag = "green" | "amber" | "red";
export type RoadmapStatus = "on_track" | "at_risk" | "blocked" | "done";
export type QuarterHealth = "on_track" | "at_risk" | "blocked";
export type Trend = "on_target" | "under_pressure" | "missed";

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
}

export interface RoadmapItem {
  id: number;
  squad_id: number;
  year: number;
  quarter: number;
  title: string;
  description?: string | null;
  success_criteria?: string | null;
  user_benefit?: string | null;
  dependencies?: string | null;
  risks?: string | null;
  owner?: string | null;
  status: RoadmapStatus;
  display_order: number;
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
  review: { enabled: boolean; notes: boolean; weekly_report: boolean };
  squad_content: { enabled: boolean; objectives: boolean; roadmap: boolean; kpis: boolean };
  notifications: { enabled: boolean; inapp: boolean; email: boolean };
  exports_csv: { enabled: boolean };
}

export type ModuleKey = keyof ModulesConfig;

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

// ---------- Progress review ----------
export interface ProgressChange {
  kind: string;
  label: string;
  from?: string | number | null;
  to?: string | number | null;
}

export type ProgressKind = "auto" | "weekly" | "review";

export interface ProgressPoint {
  id: number;
  squad_id: number;
  year: number;
  created_at: string;
  kind: ProgressKind;
  author_name?: string | null;
  note?: string | null;
  confidence?: number | null;
  progress_pct: number;
  blocked_count: number;
  at_risk_count: number;
  done_count: number;
  total_count: number;
  changes: ProgressChange[];
}

export interface ProgressReviewRow {
  squad_id: number;
  squad_name: string;
  tribe_id?: number | null;
  tribe_name?: string | null;
  progress_pct: number;
  progress_delta: number;
  blocked_count: number;
  at_risk_count: number;
  confidence?: number | null;
  note?: string | null;
  last_update_at?: string | null;
  points_in_period: number;
  changes: ProgressChange[];
}
