from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["admin", "tribe_leader", "squad_leader", "member"]
Rag = Literal["green", "amber", "red"]
RoadmapStatus = Literal["on_track", "at_risk", "blocked", "done"]
DependencyKind = Literal["text", "squad", "tribe"]
ReleaseStage = Literal["EA", "GA"]  # Early Access | General Availability
QuarterHealth = Literal["on_track", "at_risk", "blocked"]
Trend = Literal["on_target", "under_pressure", "missed"]
Quarter = Literal[1, 2, 3, 4]
# Open-ended: "product" (roadmap) and "transverse" (initiatives/OTD) ship today, but
# any custom type key is accepted so new squad types can be added without a schema change.
SquadType = str
OtdStatus = Literal["on_track", "at_risk", "late", "delivered"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class LoginIn(BaseModel):
    email: str
    password: str


class AuthConfig(BaseModel):
    oidc_enabled: bool
    saml_enabled: bool


class UserOut(ORMModel):
    id: int
    email: str
    display_name: str
    role: str  # built-in role or custom persona key
    status: str = "active"  # pending | active | disabled
    tribe_id: Optional[int] = None
    is_break_glass: bool
    auth_subject: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


# ---------- Access approval (SSO provisioning) ----------
class AccessRequestOut(ORMModel):
    id: int
    email: str
    display_name: str
    role: str  # role proposed at provisioning (from IdP groups), pre-validation
    auth_subject: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class AccessApproveIn(BaseModel):
    role: str
    tribe_id: Optional[int] = None
    squad_id: Optional[int] = None


class UserCreate(BaseModel):
    email: str
    display_name: str
    role: str = "member"
    tribe_id: Optional[int] = None
    password: Optional[str] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    tribe_id: Optional[int] = None
    password: Optional[str] = None


# ---------- Tribe (tenant) ----------
class TribeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    display_order: int = 0
    leader_user_id: Optional[int] = None  # promote this user to tribe leader of the new tribe


class TribeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    display_order: Optional[int] = None


class TribeOut(ORMModel):
    id: int
    name: str
    description: Optional[str] = None
    display_order: int


# ---------- Objective (annual; status is auto-derived, not entered by hand) ----------
class ObjectiveCreate(BaseModel):
    squad_id: int
    year: int
    title: str
    description: Optional[str] = None
    target_date: Optional[datetime] = None  # optional deadline
    weight: int = 1
    is_active: bool = True
    initiative_id: Optional[int] = None  # tribe initiative this objective answers


class ObjectiveUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    weight: Optional[int] = None
    is_active: Optional[bool] = None
    year: Optional[int] = None
    initiative_id: Optional[int] = None


class ObjectiveOut(ORMModel):
    id: int
    squad_id: int
    year: int
    title: str
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    rag_status: Rag
    weight: int
    is_active: bool
    initiative_id: Optional[int] = None


# ---------- Roadmap item (jalon) ----------
class RoadmapItemCreate(BaseModel):
    squad_id: int
    year: int
    quarter: Quarter
    title: str
    theme: str = Field(min_length=1, max_length=120)  # mandatory, reusable grouping
    release_stage: ReleaseStage = "EA"  # mandatory EA/GA stage
    description: Optional[str] = None
    success_criteria: Optional[str] = None
    user_benefit: Optional[str] = None
    dependencies: Optional[str] = None
    dependency_kind: Optional[DependencyKind] = None
    dependency_squad_id: Optional[int] = None
    dependency_tribe_id: Optional[int] = None
    risks: Optional[str] = None
    owner: Optional[str] = None
    status: RoadmapStatus = "on_track"
    display_order: int = 0
    objective_id: Optional[int] = None  # squad objective this milestone answers


class RoadmapItemUpdate(BaseModel):
    title: Optional[str] = None
    theme: Optional[str] = Field(default=None, min_length=1, max_length=120)
    objective_id: Optional[int] = None
    release_stage: Optional[ReleaseStage] = None
    description: Optional[str] = None
    success_criteria: Optional[str] = None
    user_benefit: Optional[str] = None
    dependencies: Optional[str] = None
    dependency_kind: Optional[DependencyKind] = None
    dependency_squad_id: Optional[int] = None
    dependency_tribe_id: Optional[int] = None
    risks: Optional[str] = None
    owner: Optional[str] = None
    year: Optional[int] = None
    quarter: Optional[Quarter] = None
    status: Optional[RoadmapStatus] = None
    display_order: Optional[int] = None


class RoadmapItemOut(ORMModel):
    id: int
    squad_id: int
    year: int
    quarter: int
    title: str
    theme: Optional[str] = None
    release_stage: ReleaseStage
    description: Optional[str] = None
    success_criteria: Optional[str] = None
    user_benefit: Optional[str] = None
    dependencies: Optional[str] = None
    dependency_kind: Optional[DependencyKind] = None
    dependency_squad_id: Optional[int] = None
    dependency_tribe_id: Optional[int] = None
    dependency_label: Optional[str] = None  # resolved display label (squad/tribe name or free text)
    risks: Optional[str] = None
    owner: Optional[str] = None
    status: RoadmapStatus
    display_order: int
    objective_id: Optional[int] = None
    otd_id: Optional[int] = None  # set only from the OTD side (tribe/admin)
    otd_label: Optional[str] = None  # resolved OTD title


# ---------- Initiative (tribe-level) & OTD ----------
class InitiativeCreate(BaseModel):
    tribe_id: int
    year: int
    title: str = Field(min_length=1, max_length=300)
    squad_id: Optional[int] = None
    owner: Optional[str] = None
    deadline: Optional[datetime] = None
    description: Optional[str] = None
    display_order: int = 0
    is_active: bool = True


class InitiativeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    squad_id: Optional[int] = None
    owner: Optional[str] = None
    deadline: Optional[datetime] = None
    description: Optional[str] = None
    year: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class InitiativeOut(ORMModel):
    id: int
    tribe_id: int
    year: int
    title: str
    squad_id: Optional[int] = None
    squad_name: Optional[str] = None
    owner: Optional[str] = None
    deadline: Optional[datetime] = None
    description: Optional[str] = None
    display_order: int
    is_active: bool


class OtdCreate(BaseModel):
    tribe_id: int
    year: int
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    budget_ref: Optional[str] = None
    committed_date: Optional[datetime] = None
    owner_user_id: Optional[int] = None
    display_order: int = 0


class OtdUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    budget_ref: Optional[str] = None
    committed_date: Optional[datetime] = None
    owner_user_id: Optional[int] = None
    year: Optional[int] = None
    display_order: Optional[int] = None


class OtdOut(ORMModel):
    id: int
    tribe_id: int
    year: int
    title: str
    description: Optional[str] = None
    budget_ref: Optional[str] = None
    committed_date: Optional[datetime] = None
    owner_user_id: Optional[int] = None
    display_order: int


class OtdMembers(BaseModel):
    """Set of milestone ids that make up an OTD (tribe/admin manages membership)."""
    jalon_ids: list[int] = []


class DependentItemOut(BaseModel):
    """A milestone in another squad that depends on the squad being viewed."""
    squad_id: int
    squad_name: str
    tribe_name: Optional[str] = None
    year: int
    quarter: int
    title: str
    status: RoadmapStatus
    via: DependencyKind  # 'squad' = direct, 'tribe' = via this squad's tribe


# ---------- Quarter progress ----------
class QuarterProgressIn(BaseModel):
    year: int
    quarter: Quarter
    progress_pct: int = Field(ge=0, le=100)
    comment: Optional[str] = None


class QuarterProgressOut(ORMModel):
    id: int
    squad_id: int
    year: int
    quarter: int
    progress_pct: int
    comment: Optional[str] = None


# ---------- KPI ----------
class KpiCreate(BaseModel):
    squad_id: int
    name: str
    unit: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    trend_status: Trend = "on_target"
    comment: Optional[str] = None


class KpiUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    trend_status: Optional[Trend] = None
    comment: Optional[str] = None


class KpiOut(ORMModel):
    id: int
    squad_id: int
    name: str
    unit: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    trend_status: Trend
    comment: Optional[str] = None


# ---------- Committee (governance / comitologie) ----------
CommitteeFrequency = Literal["daily", "weekly", "biweekly", "per_sprint", "monthly", "quarterly", "yearly", "on_demand", "other"]
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class CommitteeCreate(BaseModel):
    squad_id: int
    name: str
    objective: Optional[str] = None
    frequency: CommitteeFrequency = "monthly"
    frequency_other: Optional[str] = None
    day_of_week: Optional[Weekday] = None
    time_of_day: Optional[str] = None
    duration_minutes: Optional[int] = None
    participants: Optional[str] = None
    is_active: bool = True
    display_order: int = 0


class CommitteeUpdate(BaseModel):
    name: Optional[str] = None
    objective: Optional[str] = None
    frequency: Optional[CommitteeFrequency] = None
    frequency_other: Optional[str] = None
    day_of_week: Optional[Weekday] = None
    time_of_day: Optional[str] = None
    duration_minutes: Optional[int] = None
    participants: Optional[str] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class CommitteeOut(ORMModel):
    id: int
    squad_id: int
    name: str
    objective: Optional[str] = None
    frequency: CommitteeFrequency
    frequency_other: Optional[str] = None
    day_of_week: Optional[Weekday] = None
    time_of_day: Optional[str] = None
    duration_minutes: Optional[int] = None
    participants: Optional[str] = None
    is_active: bool
    display_order: int


# ---------- Member (person in a squad) ----------
class MemberCreate(BaseModel):
    squad_id: int
    full_name: str
    role_title: Optional[str] = None
    user_id: Optional[int] = None
    manager_id: Optional[int] = None
    display_order: int = 0


class MemberUpdate(BaseModel):
    full_name: Optional[str] = None
    role_title: Optional[str] = None
    user_id: Optional[int] = None
    manager_id: Optional[int] = None
    display_order: Optional[int] = None


class MemberOut(ORMModel):
    id: int
    squad_id: int
    full_name: str
    role_title: Optional[str] = None
    user_id: Optional[int] = None
    manager_id: Optional[int] = None
    display_order: int


# ---------- Squad ----------
class SquadCreate(BaseModel):
    tribe_id: Optional[int] = None  # required for admin; tribe leaders use their own tribe
    name: str
    description: Optional[str] = None
    leader_user_id: Optional[int] = None
    display_order: int = 0
    kpis_enabled: bool = True
    squad_type: SquadType = "product"
    products: list[str] = []
    hardware: list[str] = []


class SquadUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    leader_user_id: Optional[int] = None
    display_order: Optional[int] = None
    kpis_enabled: Optional[bool] = None
    budget_enabled: Optional[bool] = None
    tribe_id: Optional[int] = None
    squad_type: Optional[SquadType] = None
    products: Optional[list[str]] = None
    hardware: Optional[list[str]] = None


class SquadOut(ORMModel):
    id: int
    tribe_id: int
    name: str
    description: Optional[str] = None
    leader_user_id: Optional[int] = None
    display_order: int
    kpis_enabled: bool
    budget_enabled: bool = False
    squad_type: SquadType = "product"
    products: list[str] = []
    hardware: list[str] = []


# ---------- Budget (split entry, privileged-visible) ----------
BudgetStatus = Literal["on_track", "at_risk", "over"]


class SquadBudgetIn(BaseModel):
    total: Optional[float] = None      # envelope - tribe leader only (ignored from a squad leader)
    spent: Optional[float] = None      # consumed to date - squad leader
    forecast: Optional[float] = None   # projected landing - squad leader
    comment: Optional[str] = None


class SquadBudgetOut(BaseModel):
    total: Optional[float] = None
    spent: Optional[float] = None
    forecast: Optional[float] = None
    comment: Optional[str] = None
    status: BudgetStatus = "on_track"   # derived from forecast (else spent) vs total
    spent_pct: Optional[int] = None     # spent as % of total
    forecast_pct: Optional[int] = None  # forecast as % of total
    overrun: float = 0.0               # max(0, reference - total)
    overrun_pct: int = 0               # overrun as % of total
    updated_at: Optional[datetime] = None


# ---------- Key messages (curated success / alert / risk) ----------
KeyMessageKind = Literal["success", "alert", "risk"]


class KeyMessageCreate(BaseModel):
    kind: KeyMessageKind = "success"
    text: str
    display_order: int = 0


class KeyMessageUpdate(BaseModel):
    kind: Optional[KeyMessageKind] = None
    text: Optional[str] = None
    display_order: Optional[int] = None


class KeyMessageOut(ORMModel):
    id: int
    squad_id: int
    year: int
    kind: KeyMessageKind
    text: str
    display_order: int
    created_at: datetime


class LeaderInfo(BaseModel):
    id: Optional[int] = None
    display_name: Optional[str] = None
    email: Optional[str] = None


class SquadDetail(SquadOut):
    leader: Optional[LeaderInfo] = None
    year: int
    annual_progress: int
    freshness: dict
    counts: dict
    quarter_progress: dict
    objectives: list[ObjectiveOut]
    roadmap_items: list[RoadmapItemOut]
    kpis: list[KpiOut]
    members: list[MemberOut]
    key_messages: list[KeyMessageOut] = []
    committees: list[CommitteeOut] = []
    budget: Optional[SquadBudgetOut] = None   # only populated for privileged viewers


# ---------- Dashboard ----------
class SquadCard(BaseModel):
    squad_id: int
    name: str
    tribe_id: int
    tribe_name: Optional[str] = None
    leader: Optional[LeaderInfo] = None
    annual_progress: int
    risk_rank: int                 # derived from blocked/at-risk counts (for sorting)
    focus_quarter: Optional[int] = None
    quarter_progress: dict         # {"1": pct, ...}
    quarter_breakdowns: dict       # {"1": {total,on_track,at_risk,blocked,done}, ...}
    blocked_count: int             # over the year
    at_risk_count: int             # over the year
    counts: dict
    members_count: int
    freshness: dict


class DashboardSummary(BaseModel):
    squads_total: int
    blocked_jalons: int
    at_risk_jalons: int
    squads_stale: int
    avg_progress: int


class DashboardOut(BaseModel):
    year: int
    current_year: int
    current_quarter: int
    summary: DashboardSummary
    cards: list[SquadCard]


# ---------- Snapshot ----------
class SnapshotOut(ORMModel):
    id: int
    squad_id: int
    submitted_by_user_id: Optional[int] = None
    submitted_at: datetime
    cycle_label: str
    payload: dict


class SnapshotMeta(ORMModel):
    id: int
    squad_id: int
    submitted_by_user_id: Optional[int] = None
    submitted_at: datetime
    cycle_label: str


class SubmitCycleIn(BaseModel):
    cycle_label: Optional[str] = None
    year: Optional[int] = None


# ---------- Org chart (global, editable) ----------
class OrgNodeCreate(BaseModel):
    tribe_id: Optional[int] = None
    parent_id: Optional[int] = None
    title: str
    person_name: Optional[str] = None
    squad_id: Optional[int] = None
    display_order: int = 0


class OrgNodeUpdate(BaseModel):
    parent_id: Optional[int] = None
    title: Optional[str] = None
    person_name: Optional[str] = None
    squad_id: Optional[int] = None
    display_order: Optional[int] = None


class OrgNodeTree(BaseModel):
    id: int
    parent_id: Optional[int] = None
    title: str
    person_name: Optional[str] = None
    squad_id: Optional[int] = None
    squad_status: Optional[QuarterHealth] = None
    display_order: int
    children: list["OrgNodeTree"] = []


class TribeOrg(BaseModel):
    tribe_id: int
    tribe_name: str
    squads_count: int
    tree: list[OrgNodeTree]


# ---------- Feed (tweet zone) ----------
FeedKind = Literal["incident", "info", "success"]
ReactionKind = Literal["like", "ack"]


class AuthorInfo(BaseModel):
    id: Optional[int] = None
    display_name: Optional[str] = None
    role: Optional[str] = None


class FeedPostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    kind: FeedKind = "info"
    squad_id: Optional[int] = None


class FeedReplyCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class ReactionIn(BaseModel):
    kind: ReactionKind = "like"


class PinIn(BaseModel):
    is_pinned: bool


class FeedReplyOut(BaseModel):
    id: int
    content: str
    created_at: datetime
    author: AuthorInfo


class FeedPostOut(BaseModel):
    id: int
    content: str
    kind: FeedKind
    squad_id: Optional[int] = None
    squad_name: Optional[str] = None
    is_pinned: bool
    created_at: datetime
    author: AuthorInfo
    replies: list[FeedReplyOut]
    reactions: dict           # {"like": n, "ack": n}
    my_reactions: list[str]


# ---------- Notifications & preferences ----------
class NotificationOut(ORMModel):
    id: int
    kind: str
    actor_name: Optional[str] = None
    excerpt: Optional[str] = None
    link: Optional[str] = None
    is_read: bool
    created_at: datetime


class NotificationsResponse(BaseModel):
    unread_count: int
    items: list[NotificationOut]


class PreferencesOut(BaseModel):
    notify_tweets: bool
    notify_replies: bool
    email_notifications: bool
    subscribe_weekly_report: bool


class PreferencesUpdate(BaseModel):
    notify_tweets: Optional[bool] = None
    notify_replies: Optional[bool] = None
    email_notifications: Optional[bool] = None
    subscribe_weekly_report: Optional[bool] = None


class EmailExportIn(BaseModel):
    to: str
    year: Optional[int] = None


class ReportSubscriptionOut(BaseModel):
    squad_id: Optional[int] = None
    squad_name: Optional[str] = None
    interval_days: int
    weekdays: list[int] = []
    hour: int = 8
    last_sent_at: Optional[datetime] = None


class ReportSubscriptionIn(BaseModel):
    squad_id: Optional[int] = None  # None = dashboard (user's visibility scope)
    interval_days: int = Field(default=0, ge=0, le=90)  # legacy; 0 = ignore
    weekdays: Optional[list[int]] = None   # 0=Mon..6=Sun; empty/None = unsubscribe
    hour: Optional[int] = None             # 0..23 (UTC)


# ---------- Audit ----------
class AuditOut(ORMModel):
    id: int
    user_id: Optional[int] = None
    action: str
    entity: Optional[str] = None
    entity_id: Optional[str] = None
    timestamp: datetime
    detail: Optional[dict] = None


# ---------- Review actions ----------
class ReviewActionOut(ORMModel):
    id: int
    squad_id: int
    text: str
    owner: Optional[str] = None
    due_date: Optional[datetime] = None
    done: bool
    created_at: Optional[datetime] = None


class ReviewActionCreate(BaseModel):
    text: str
    owner: Optional[str] = None
    due_date: Optional[datetime] = None


class ReviewActionUpdate(BaseModel):
    text: Optional[str] = None
    owner: Optional[str] = None
    due_date: Optional[datetime] = None
    done: Optional[bool] = None


# ---------- Settings ----------
class SettingsOut(BaseModel):
    staleness_threshold_days: int


class SettingsUpdate(BaseModel):
    staleness_threshold_days: int = Field(ge=1, le=365)


# ---------- Leaves / absences ----------
from datetime import date as _date  # local alias; date types for leave ranges

LeaveStatus = Literal["pending", "approved", "rejected", "cancelled"]


class LeaveTypeOut(ORMModel):
    id: int
    label: str
    color: str
    display_order: int
    is_active: bool
    requires_detail: bool = False


class LeaveTypeIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#6B7280", max_length=9)
    display_order: int = 0
    is_active: bool = True
    requires_detail: bool = False


class LeaveIn(BaseModel):
    type_id: int
    start_date: _date
    end_date: _date
    start_half: bool = False
    end_half: bool = False
    detail: Optional[str] = Field(default=None, max_length=200)
    comment: Optional[str] = None
    # Leaders may file on behalf of another person in their scope; omit for self.
    user_id: Optional[int] = None


class LeaveUpdate(BaseModel):
    type_id: Optional[int] = None
    start_date: Optional[_date] = None
    end_date: Optional[_date] = None
    start_half: Optional[bool] = None
    end_half: Optional[bool] = None
    detail: Optional[str] = Field(default=None, max_length=200)
    comment: Optional[str] = None


class LeaveDecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    comment: Optional[str] = None


class LeaveOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    tribe_id: Optional[int] = None
    type_id: int
    type_label: str
    type_color: str
    type_requires_detail: bool = False
    start_date: _date
    end_date: _date
    start_half: bool
    end_half: bool
    days: float
    status: LeaveStatus
    detail: Optional[str] = None  # public clarification of the type (e.g. "Déménagement")
    comment: Optional[str] = None  # private motif; null when the viewer may not see it
    created_at: Optional[datetime] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_comment: Optional[str] = None
    can_edit: bool = False
    can_decide: bool = False


class LeaveConfigOut(BaseModel):
    tribe_id: int
    tribe_name: str
    require_approval: bool
    overlap_threshold: int


class LeaveConfigIn(BaseModel):
    require_approval: Optional[bool] = None
    overlap_threshold: Optional[int] = Field(default=None, ge=1, le=99)


class LeaveOverlapDay(BaseModel):
    squad_id: int
    squad_name: str
    day: _date
    count: int
    names: list[str]
