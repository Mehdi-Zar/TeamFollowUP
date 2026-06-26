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
    tribe_id: Optional[int] = None
    is_break_glass: bool
    auth_subject: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


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
    last_sent_at: Optional[datetime] = None


class ReportSubscriptionIn(BaseModel):
    squad_id: Optional[int] = None  # None = dashboard (user's visibility scope)
    interval_days: int = Field(ge=0, le=90)  # 0 = unsubscribe


# ---------- Audit ----------
class AuditOut(ORMModel):
    id: int
    user_id: Optional[int] = None
    action: str
    entity: Optional[str] = None
    entity_id: Optional[str] = None
    timestamp: datetime
    detail: Optional[dict] = None


# ---------- Progress review ----------
class ProgressNoteIn(BaseModel):
    year: Optional[int] = None
    note: Optional[str] = None
    confidence: Optional[int] = Field(default=None, ge=1, le=5)


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


class ProgressPointOut(BaseModel):
    id: int
    squad_id: int
    year: int
    created_at: datetime
    kind: str
    author_name: Optional[str] = None
    note: Optional[str] = None
    confidence: Optional[int] = None
    progress_pct: int
    blocked_count: int
    at_risk_count: int
    done_count: int
    total_count: int
    changes: list = []


class ProgressReviewRow(BaseModel):
    squad_id: int
    squad_name: str
    tribe_id: Optional[int] = None
    tribe_name: Optional[str] = None
    progress_pct: int
    progress_delta: int
    blocked_count: int
    at_risk_count: int
    confidence: Optional[int] = None
    note: Optional[str] = None
    last_update_at: Optional[datetime] = None
    points_in_period: int
    changes: list = []


# ---------- Settings ----------
class SettingsOut(BaseModel):
    staleness_threshold_days: int


class SettingsUpdate(BaseModel):
    staleness_threshold_days: int = Field(ge=1, le=365)
