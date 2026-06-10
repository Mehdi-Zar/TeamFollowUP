from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["admin", "tribe_leader", "squad_leader", "member"]
Rag = Literal["green", "amber", "red"]
RoadmapStatus = Literal["on_track", "at_risk", "blocked", "done"]
QuarterHealth = Literal["on_track", "at_risk", "blocked"]
Trend = Literal["on_target", "under_pressure", "missed"]
Quarter = Literal[1, 2, 3, 4]


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
    role: Role
    tribe_id: Optional[int] = None
    is_break_glass: bool
    auth_subject: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class UserCreate(BaseModel):
    email: str
    display_name: str
    role: Role = "member"
    tribe_id: Optional[int] = None
    password: Optional[str] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[Role] = None
    tribe_id: Optional[int] = None
    password: Optional[str] = None


# ---------- Tribe (tenant) ----------
class TribeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    display_order: int = 0


class TribeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    display_order: Optional[int] = None


class TribeOut(ORMModel):
    id: int
    name: str
    description: Optional[str] = None
    display_order: int


# ---------- Objective (annual, set by tribe leader) ----------
class ObjectiveCreate(BaseModel):
    squad_id: int
    year: int
    title: str
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    rag_status: Rag = "green"
    weight: int = 1
    is_active: bool = True


class ObjectiveUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    rag_status: Optional[Rag] = None
    weight: Optional[int] = None
    is_active: Optional[bool] = None
    year: Optional[int] = None


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


# ---------- Roadmap item (jalon) ----------
class RoadmapItemCreate(BaseModel):
    squad_id: int
    year: int
    quarter: Quarter
    title: str
    description: Optional[str] = None
    success_criteria: Optional[str] = None
    user_benefit: Optional[str] = None
    dependencies: Optional[str] = None
    risks: Optional[str] = None
    owner: Optional[str] = None
    status: RoadmapStatus = "on_track"
    display_order: int = 0


class RoadmapItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    success_criteria: Optional[str] = None
    user_benefit: Optional[str] = None
    dependencies: Optional[str] = None
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
    description: Optional[str] = None
    success_criteria: Optional[str] = None
    user_benefit: Optional[str] = None
    dependencies: Optional[str] = None
    risks: Optional[str] = None
    owner: Optional[str] = None
    status: RoadmapStatus
    display_order: int


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


class SquadUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    leader_user_id: Optional[int] = None
    display_order: Optional[int] = None
    kpis_enabled: Optional[bool] = None
    tribe_id: Optional[int] = None


class SquadOut(ORMModel):
    id: int
    tribe_id: int
    name: str
    description: Optional[str] = None
    leader_user_id: Optional[int] = None
    display_order: int
    kpis_enabled: bool


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


class PreferencesUpdate(BaseModel):
    notify_tweets: Optional[bool] = None
    notify_replies: Optional[bool] = None
    email_notifications: Optional[bool] = None


class EmailExportIn(BaseModel):
    to: str
    year: Optional[int] = None


# ---------- Audit ----------
class AuditOut(ORMModel):
    id: int
    user_id: Optional[int] = None
    action: str
    entity: Optional[str] = None
    entity_id: Optional[str] = None
    timestamp: datetime
    detail: Optional[dict] = None


# ---------- Settings ----------
class SettingsOut(BaseModel):
    staleness_threshold_days: int


class SettingsUpdate(BaseModel):
    staleness_threshold_days: int = Field(ge=1, le=365)
