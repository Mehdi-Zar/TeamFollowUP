/**
 * Shared domain types mirroring the backend API contract (FastAPI/Pydantic
 * schemas). One place for the shapes exchanged over HTTP, so pages, hooks and
 * the API client stay type-safe and in sync with the server.
 */

// Built-in roles plus any admin-created custom persona key.
// `(string & {})` keeps the literal autocomplete while still allowing any string.
export type Role = "admin" | "tribe_leader" | "squad_leader" | "member" | (string & {});

/** Section-level access flags (persona capabilities) gating the main nav areas. */
export type Capability = "dashboard" | "roadmap" | "org" | "feed" | "reporting" | "mysquads" | "leaves";

/** One milestone (jalon) rendered inside a roadmap matrix cell. */
export interface RoadmapCellItem {
  title: string;
  status: RoadmapStatus;
  owner?: string | null;
  stage?: string | null;
  theme?: string | null;
  dependency?: string | null;
}
/** A quarter column of the roadmap matrix: completion % plus its milestones. */
export interface RoadmapMatrixQuarter { q: number; pct: number; comment?: string | null; items: RoadmapCellItem[]; }
/** A squad row of the roadmap matrix: annual % and the four quarter columns. */
export interface RoadmapMatrixSquad { squad_id: number; name: string; annual_pct: number; quarters: RoadmapMatrixQuarter[]; }
/** A tribe grouping of squad rows in the roadmap matrix. */
export interface RoadmapMatrixTribe { tribe_id: number | null; tribe_name: string; squads: RoadmapMatrixSquad[]; }
/** Top-level roadmap matrix payload for a given year and scope (tribe/all). */
export interface RoadmapMatrix { year: number; scope_name: string; tribes: RoadmapMatrixTribe[]; }

/** A persona (built-in role or custom) and the section capabilities it grants. */
export interface Persona {
  key: string;
  label: string;
  builtin: boolean;
  caps: Record<string, boolean>;
}

/** Resolved permissions for the current user: what admin surfaces they may open,
 *  which roles they can assign, and their section capabilities. */
export interface Permissions {
  role: Role;
  tribe_id: number | null;
  can_access_admin: boolean;
  admin_tabs: string[];
  assignable_roles: Role[];
  can_create_tribe: boolean;
  can_manage_users: boolean;
  can_review_access?: boolean;
  pending_access_count?: number;
  capabilities?: Record<string, boolean>;
}
/** Red/Amber/Green health used by the traffic-light UI. */
export type Rag = "green" | "amber" | "red";
/** Lifecycle status of a roadmap milestone (jalon). */
export type RoadmapStatus = "on_track" | "at_risk" | "blocked" | "done";
/** Aggregated health of a squad within a quarter (no "done" state). */
export type QuarterHealth = "on_track" | "at_risk" | "blocked";
/** KPI trend against target. */
export type Trend = "on_target" | "under_pressure" | "missed";
/** How a milestone dependency is expressed: free text, on a squad, or a tribe. */
export type DependencyKind = "text" | "squad" | "tribe";
/** Release stage of a milestone: Early Access or General Availability. */
export type ReleaseStage = "EA" | "GA";
// "product" and "transverse" ship today; any custom key is allowed (extensible).
export type SquadType = "product" | "transverse" | (string & {});
/** Delivery status of an OTD commitment. */
export type OtdStatus = "on_track" | "at_risk" | "late" | "delivered";

/** A tribe-level Initiative: the top of the reporting chain, set by the tribe
 *  leader and answered by squad objectives/milestones. */
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

/** An OTD (On-Time Delivery): a dated delivery commitment the tribe leader
 *  places on a squad leader, covering a set of milestones. */
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
/** A milestone as seen in a report: enriched with its squad and OTD context. */
export interface ReportJalon {
  id: number; title: string; theme?: string | null; quarter: number; stage?: string | null;
  status: RoadmapStatus; squad_id: number; squad_name: string;
  otd_id?: number | null; otd_title?: string | null; owner?: string | null;
}
/** A squad objective in a report, with its RAG and the milestones under it. */
export interface ReportObjective {
  id: number; title: string; squad_id: number; squad_name: string; rag: Rag;
  status: RoadmapStatus; jalons: ReportJalon[];
}
/** An initiative in a report: rolled-up status/progress plus its objectives. */
export interface ReportInitiative {
  id: number; title: string; description?: string | null; owner_name?: string | null;
  status: RoadmapStatus; progress: number;
  counts: { total: number; done: number; blocked: number; at_risk: number };
  objectives: ReportObjective[];
}
/** Full initiative-centric report for a year/scope. */
export interface InitiativeReport {
  year: number; scope_name: string; initiatives: ReportInitiative[];
}
/** An OTD as seen in a report: adds owner name, delivery status, counts and the
 *  covered milestones on top of the base {@link Otd}. */
export interface OtdReport extends Otd {
  owner_name?: string | null;
  status: OtdStatus;
  counts: { total: number; done: number; blocked: number; at_risk: number };
  jalons: { id: number; title: string; quarter: number; stage?: string | null; status: RoadmapStatus; squad_id: number; squad_name: string }[];
}
/** An objective selectable when linking objectives to an initiative. */
export interface CandidateObjective { id: number; title: string; squad_id: number; squad_name: string; initiative_id?: number | null; }
/** A milestone selectable when linking milestones to an OTD. */
export interface CandidateJalon { id: number; title: string; quarter: number; theme?: string | null; squad_id: number; squad_name: string; otd_id?: number | null; }

/** Account lifecycle for SSO-provisioned users: awaiting approval, active, or revoked. */
export type AccessStatus = "pending" | "active" | "disabled";

/** An application user / account. */
export interface User {
  id: number;
  email: string;
  display_name: string;
  role: Role;
  status?: AccessStatus;
  tribe_id?: number | null;
  is_break_glass: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
}

/** A pending SSO access request awaiting a manager's approval. */
export interface AccessRequest {
  id: number;
  email: string;
  display_name: string;
  role: Role;
  auth_subject?: string | null;
  created_at?: string | null;
  last_login_at?: string | null;
}

/** Data backing the access-review screen: pending requests plus the choices
 *  (roles, squads, tribes) available to the reviewer within their scope. */
export interface AccessOptions {
  requests: AccessRequest[];
  roles: Role[];
  can_deny: boolean;
  tribe_locked: boolean;
  squads: { id: number; name: string; tribe_id: number }[];
  tribes: { id: number; name: string }[];
}

/** A tribe: the top organizational unit grouping squads. */
export interface Tribe {
  id: number;
  name: string;
  description?: string | null;
  display_order: number;
}

/** Minimal identity of a squad/tribe leader for display. */
export interface LeaderInfo {
  id?: number | null;
  display_name?: string | null;
  email?: string | null;
}

/** How recently a squad submitted its reporting, and whether it's now stale
 *  (older than the configured threshold). Drives the "data perimée" badge. */
export interface Freshness {
  last_submitted_at: string | null;
  age_days: number | null;
  is_stale: boolean;
  threshold_days: number;
  never_submitted: boolean;
}

/** Roll-up tallies of a squad's objectives (by RAG) and milestones (by status). */
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

/** A squad's annual objective; may answer a tribe initiative. */
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

/** A roadmap milestone (jalon): a quarterly deliverable with status, ownership,
 *  dependencies and links up to an objective/OTD. The main reporting unit. */
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

/** An incoming dependency: a milestone in another squad that relies on this one. */
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

/** A squad KPI with target/current values and a trend status. */
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

/** A person on a squad's team; `manager_id` builds the reporting hierarchy. */
export interface Member {
  id: number;
  squad_id: number;
  full_name: string;
  role_title?: string | null;
  user_id?: number | null;
  manager_id?: number | null;
  display_order: number;
}

/** A squad: the delivery unit within a tribe, with its leader and feature flags. */
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

/** Category of a hand-curated key message shown on a squad. */
export type KeyMessageKind = "success" | "alert" | "risk";

/** A short, manually curated highlight/alert/risk on a squad for a given year. */
export interface KeyMessage {
  id: number;
  squad_id: number;
  year: number;
  kind: KeyMessageKind;
  text: string;
  display_order: number;
  created_at: string;
}

/** How often a committee meets (`other` = free text in `frequency_other`). */
export type CommitteeFrequency =
  | "daily" | "weekly" | "biweekly" | "per_sprint" | "monthly" | "quarterly" | "yearly" | "on_demand" | "other";
export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

/** A recurring committee/ceremony owned by a squad (cadence, day, participants). */
export interface Committee {
  id: number;
  squad_id: number;
  name: string;
  objective?: string | null;
  frequency: CommitteeFrequency;
  frequency_other?: string | null;
  day_of_week?: Weekday | null;
  time_of_day?: string | null;
  duration_minutes?: number | null;
  participants?: string | null;
  is_active: boolean;
  display_order: number;
}

/** Budget health derived from spend/forecast vs. the total envelope. */
export type BudgetStatus = "on_track" | "at_risk" | "over";

/** A squad's budget: envelope, spend-to-date, forecast and derived overrun.
 *  The `*_pct`/overrun fields are computed server-side for display. */
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

/** Per-quarter progress cell (percentage + optional comment). */
export interface QuarterCell {
  progress_pct: number;
  comment?: string | null;
}

/** Full squad payload for the detail page: base squad plus all its nested
 *  content (objectives, roadmap, KPIs, members, messages, committees, budget). */
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
  committees: Committee[];
  budget?: Budget | null;
}

/** Milestone counts by status for a quarter, used in dashboard breakdowns. */
export interface Breakdown {
  total: number;
  on_track: number;
  at_risk: number;
  blocked: number;
  done: number;
}

/** Compact squad summary shown as a card on the dashboard, with risk ranking
 *  (worst-first ordering) and per-quarter progress. */
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

/** The enable/disable map for every feature module and its sub-features,
 *  toggled by admins to show/hide UI and gate routes. */
export interface ModulesConfig {
  dashboard: { enabled: boolean };
  org: { enabled: boolean };
  reporting: { enabled: boolean };
  feed: { enabled: boolean; reactions: boolean; replies: boolean; pin: boolean; kinds: boolean };
  review: { enabled: boolean; weekly_report: boolean };
  squad_content: { enabled: boolean; objectives: boolean; roadmap: boolean; kpis: boolean };
  committees: { enabled: boolean };
  notifications: { enabled: boolean; inapp: boolean; email: boolean };
  getting_started: { enabled: boolean };
  leaves: { enabled: boolean; overlap_alert: boolean };
}

/** Any valid top-level module name (keys of {@link ModulesConfig}). */
export type ModuleKey = keyof ModulesConfig;

// ---- Leaves / absences ----
/** Approval lifecycle of a leave request. */
export type LeaveStatus = "pending" | "approved" | "rejected" | "cancelled";

/** A configurable leave/absence type (label, colour, whether detail is required). */
export interface LeaveType {
  id: number;
  label: string;
  color: string;
  display_order: number;
  is_active: boolean;
  requires_detail: boolean;
}

/** A single leave/absence entry, including half-day flags, computed `days`,
 *  and decision metadata plus per-viewer `can_edit`/`can_decide` permissions. */
export interface Leave {
  id: number;
  user_id: number;
  user_name: string;
  tribe_id?: number | null;
  type_id: number;
  type_label: string;
  type_color: string;
  type_requires_detail?: boolean;
  detail?: string | null;
  start_date: string;  // ISO date
  end_date: string;    // ISO date
  start_half: boolean;
  end_half: boolean;
  days: number;
  status: LeaveStatus;
  comment?: string | null;
  created_at?: string | null;
  decided_by_name?: string | null;
  decided_at?: string | null;
  decision_comment?: string | null;
  can_edit: boolean;
  can_decide: boolean;
}

/** Per-tribe leave settings: whether approval is required and the overlap
 *  alert threshold (max people off the same day before warning). */
export interface LeaveConfig {
  tribe_id: number;
  tribe_name: string;
  require_approval: boolean;
  overlap_threshold: number;
}

/** A day flagged by the overlap alert: who is off and how many, per squad. */
export interface LeaveOverlapDay {
  squad_id: number;
  squad_name: string;
  day: string;
  count: number;
  names: string[];
}

/** An action item captured during a squad review. */
export interface ReviewAction {
  id: number;
  squad_id: number;
  text: string;
  owner?: string | null;
  due_date?: string | null;
  done: boolean;
  created_at?: string | null;
}

/** Public (unauthenticated-safe) app configuration: branding, defaults, feed
 *  rules and the module map. Fetched into the config context. */
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

/** A single in-app notification (new feed post or a reply to the user). */
export interface Notif {
  id: number;
  kind: "tweet" | "reply";
  actor_name?: string | null;
  excerpt?: string | null;
  link?: string | null;
  is_read: boolean;
  created_at: string;
}

/** The notifications feed plus the unread badge count. */
export interface NotificationsResponse {
  unread_count: number;
  items: Notif[];
}

/** The current user's notification/subscription preferences. */
export interface Preferences {
  notify_tweets: boolean;
  notify_replies: boolean;
  email_notifications: boolean;
  subscribe_weekly_report: boolean;
}

/** Top-line dashboard KPIs across the visible scope. */
export interface DashboardSummary {
  squads_total: number;
  blocked_jalons: number;
  at_risk_jalons: number;
  squads_stale: number;
  avg_progress: number;
}

/** Full dashboard payload: summary KPIs plus one card per squad, for `year`. */
export interface DashboardOut {
  year: number;
  current_year: number;
  current_quarter: number;
  summary: DashboardSummary;
  cards: SquadCard[];
}

/** Metadata of an immutable reporting snapshot created on submission. */
export interface SnapshotMeta {
  id: number;
  squad_id: number;
  submitted_by_user_id?: number | null;
  submitted_at: string;
  cycle_label: string;
}

/** A node in the org chart tree: a squad or a person/role, with children. */
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

/** A tribe's org chart: metadata plus the root-level nodes of its tree. */
export interface TribeOrg {
  tribe_id: number;
  tribe_name: string;
  squads_count: number;
  tree: OrgNode[];
}

/** One audit-log entry (who did what to which entity, when). */
export interface AuditEntry {
  id: number;
  user_id?: number | null;
  action: string;
  entity?: string | null;
  entity_id?: string | null;
  timestamp: string;
  detail?: any;
}

/** Which SSO methods are enabled, so the login page shows the right buttons. */
export interface AuthConfig {
  oidc_enabled: boolean;
  saml_enabled: boolean;
}

// ---- Feed (tweet zone) ----
/** Category of a feed post. */
export type FeedKind = "incident" | "info" | "success";
/** The reactions a user can leave on a feed post. */
export type ReactionKind = "like" | "ack";

/** Minimal author identity attached to feed posts and replies. */
export interface AuthorInfo {
  id?: number | null;
  display_name?: string | null;
  role?: string | null;
}

/** A reply under a feed post. */
export interface FeedReply {
  id: number;
  content: string;
  created_at: string;
  author: AuthorInfo;
}

/** A feed (tweet zone) post: content, optional squad tag, replies, and reaction
 *  counts plus the current user's own reactions (`my_reactions`). */
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

