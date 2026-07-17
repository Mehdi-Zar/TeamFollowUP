"""Pydantic schemas - the API's request and response contracts.

These models validate incoming JSON and shape outgoing JSON; they are the
boundary between the HTTP layer and the SQLAlchemy models in :mod:`.models`.
A consistent naming convention runs through the file:

  * ``<Entity>Create`` - body to create a row (required fields present).
  * ``<Entity>Update`` - partial edit; every field is Optional so only the
    provided keys are changed (PATCH semantics).
  * ``<Entity>Out``    - response model, usually built from an ORM object via
    ``from_attributes`` (see :class:`ORMModel`).
  * ``<Entity>In``     - a non-CRUD input payload (actions, filters, config).

The ``Literal`` aliases below centralise the small enumerations shared across
schemas so allowed values stay consistent between input and output.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# --- Shared enumerations (constrain fields to a fixed, validated value set) ---
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
    """Base for response schemas that are serialized directly from ORM objects.

    ``from_attributes=True`` lets Pydantic read values off SQLAlchemy model
    instances (attribute access) instead of requiring a dict, so routers can
    return ORM rows and have them validated/serialized automatically.
    """
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class LoginIn(BaseModel):
    """Credentials submitted to the local (password) login endpoint."""
    email: str
    password: str


class AuthConfig(BaseModel):
    """Which SSO backends are enabled, so the SPA can show the right login options."""
    oidc_enabled: bool
    saml_enabled: bool


class UserOut(ORMModel):
    """Public view of a user account returned by the API."""
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
    """A pending SSO-provisioned account awaiting an admin's validation."""
    id: int
    email: str
    display_name: str
    role: str  # role proposed at provisioning (from IdP groups), pre-validation
    auth_subject: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class AccessApproveIn(BaseModel):
    """Admin decision when validating a pending account: final role and placement."""
    role: str
    tribe_id: Optional[int] = None
    squad_id: Optional[int] = None


class UserCreate(BaseModel):
    """Fields to create a user account manually (password optional for SSO-only users)."""
    email: str
    display_name: str
    role: str = "member"
    tribe_id: Optional[int] = None
    password: Optional[str] = None


class UserUpdate(BaseModel):
    """Partial edit of a user account; only provided fields are changed."""
    display_name: Optional[str] = None
    role: Optional[str] = None
    tribe_id: Optional[int] = None
    password: Optional[str] = None


# ---------- Tribe (tenant) ----------
class TribeCreate(BaseModel):
    """Fields to create a tribe, optionally promoting a user to lead it."""
    name: str
    description: Optional[str] = None
    display_order: int = 0
    leader_user_id: Optional[int] = None  # promote this user to tribe leader of the new tribe


class TribeUpdate(BaseModel):
    """Partial edit of a tribe."""
    name: Optional[str] = None
    description: Optional[str] = None
    display_order: Optional[int] = None


class TribeOut(ORMModel):
    """Tribe as returned by the API."""
    id: int
    name: str
    description: Optional[str] = None
    display_order: int


# ---------- Objective (annual; status is auto-derived, not entered by hand) ----------
class ObjectiveCreate(BaseModel):
    """Fields to create an annual squad objective."""
    squad_id: int
    year: int
    title: str
    description: Optional[str] = None
    target_date: Optional[datetime] = None  # optional deadline
    weight: int = 1
    is_active: bool = True
    initiative_id: Optional[int] = None  # tribe initiative this objective answers


class ObjectiveUpdate(BaseModel):
    """Partial edit of an objective."""
    title: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    weight: Optional[int] = None
    is_active: Optional[bool] = None
    year: Optional[int] = None
    initiative_id: Optional[int] = None


class ObjectiveOut(ORMModel):
    """Objective as returned by the API (rag_status is server-derived)."""
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
    """Fields to create a roadmap milestone; theme and release_stage are mandatory here."""
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
    """Partial edit of a roadmap milestone (note: otd_id is managed from the OTD side)."""
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
    """Roadmap milestone as returned; includes resolved dependency/OTD display labels."""
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
    """Fields to create a tribe-level strategic initiative."""
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
    """Partial edit of an initiative."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    squad_id: Optional[int] = None
    owner: Optional[str] = None
    deadline: Optional[datetime] = None
    description: Optional[str] = None
    year: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class InitiativeOut(ORMModel):
    """Initiative as returned, with the assigned squad's name resolved for display."""
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
    """Fields to create an OTD (top-management budget delivery commitment)."""
    tribe_id: int
    year: int
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    committed_date: Optional[datetime] = None
    owner_user_id: Optional[int] = None  # the squad leader this OTD is assigned to
    display_order: int = 0


class OtdUpdate(BaseModel):
    """Partial edit of an OTD."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    committed_date: Optional[datetime] = None
    owner_user_id: Optional[int] = None
    year: Optional[int] = None
    display_order: Optional[int] = None


class OtdOut(ORMModel):
    """OTD as returned by the API."""
    id: int
    tribe_id: int
    year: int
    title: str
    description: Optional[str] = None
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
    """Upsert a squad's completion percentage (0-100) for one year/quarter."""
    year: int
    quarter: Quarter
    progress_pct: int = Field(ge=0, le=100)
    comment: Optional[str] = None


class QuarterProgressOut(ORMModel):
    """A squad's quarterly progress entry as returned."""
    id: int
    squad_id: int
    year: int
    quarter: int
    progress_pct: int
    comment: Optional[str] = None


# ---------- KPI ----------
class KpiCreate(BaseModel):
    """Fields to create a KPI on a squad."""
    squad_id: int
    name: str
    unit: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    trend_status: Trend = "on_target"
    comment: Optional[str] = None


class KpiUpdate(BaseModel):
    """Partial edit of a KPI."""
    name: Optional[str] = None
    unit: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    trend_status: Optional[Trend] = None
    comment: Optional[str] = None


class KpiOut(ORMModel):
    """KPI as returned by the API."""
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
    """Fields to declare a recurring governance meeting for a squad."""
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
    """Partial edit of a committee."""
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
    """Committee as returned by the API."""
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
    """Fields to add a person to a squad's org chart (optionally linked to a login)."""
    squad_id: int
    full_name: str
    role_title: Optional[str] = None
    user_id: Optional[int] = None
    manager_id: Optional[int] = None
    display_order: int = 0


class MemberUpdate(BaseModel):
    """Partial edit of a squad member."""
    full_name: Optional[str] = None
    role_title: Optional[str] = None
    user_id: Optional[int] = None
    manager_id: Optional[int] = None
    display_order: Optional[int] = None


class MemberOut(ORMModel):
    """Squad member as returned by the API."""
    id: int
    squad_id: int
    full_name: str
    role_title: Optional[str] = None
    user_id: Optional[int] = None
    manager_id: Optional[int] = None
    display_order: int


# ---------- Squad ----------
class SquadCreate(BaseModel):
    """Fields to create a squad. budget_enabled is intentionally not settable here
    (a tribe leader turns budget on afterwards via SquadUpdate)."""
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
    """Partial edit of a squad (incl. toggling budget tracking and moving tribe)."""
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
    """Squad summary as returned by the API (without the heavy nested report)."""
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
    """Budget figures submitted for a squad; who may set which field is role-gated
    server-side (only tribe leaders may set the total envelope)."""
    total: Optional[float] = None      # envelope - tribe leader only (ignored from a squad leader)
    spent: Optional[float] = None      # consumed to date - squad leader
    forecast: Optional[float] = None   # projected landing - squad leader
    comment: Optional[str] = None


class SquadBudgetOut(BaseModel):
    """Budget as returned, with status/percentages/overrun derived server-side."""
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
    """Fields to add a curated executive message (year comes from the route/context)."""
    kind: KeyMessageKind = "success"
    text: str
    display_order: int = 0


class KeyMessageUpdate(BaseModel):
    """Partial edit of a key message."""
    kind: Optional[KeyMessageKind] = None
    text: Optional[str] = None
    display_order: Optional[int] = None


class KeyMessageOut(ORMModel):
    """Key message as returned by the API."""
    id: int
    squad_id: int
    year: int
    kind: KeyMessageKind
    text: str
    display_order: int
    created_at: datetime


class LeaderInfo(BaseModel):
    """Minimal identity of a squad/tribe leader for display in cards and details."""
    id: Optional[int] = None
    display_name: Optional[str] = None
    email: Optional[str] = None


class SquadDetail(SquadOut):
    """Full squad report: SquadOut plus all nested content and computed roll-ups.

    ``budget`` is only populated for privileged viewers (squad leader, its tribe
    leader, admins); other viewers receive it as None.
    """
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
    """One squad's condensed status for the dashboard grid (progress + risk signals)."""
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
    """Aggregate headline figures across all squads in scope."""
    squads_total: int
    blocked_jalons: int
    at_risk_jalons: int
    squads_stale: int
    avg_progress: int


class DashboardOut(BaseModel):
    """The full dashboard payload: the summary tiles plus one card per squad."""
    year: int
    current_year: int
    current_quarter: int
    summary: DashboardSummary
    cards: list[SquadCard]


# ---------- Snapshot ----------
class SnapshotOut(ORMModel):
    """A stored report snapshot including its frozen JSON payload."""
    id: int
    squad_id: int
    submitted_by_user_id: Optional[int] = None
    submitted_at: datetime
    cycle_label: str
    payload: dict


class SnapshotMeta(ORMModel):
    """Snapshot header without the heavy payload, for listing past submissions."""
    id: int
    squad_id: int
    submitted_by_user_id: Optional[int] = None
    submitted_at: datetime
    cycle_label: str


class SubmitCycleIn(BaseModel):
    """Request to submit a reporting cycle, freezing the current report as a snapshot."""
    cycle_label: Optional[str] = None
    year: Optional[int] = None


# ---------- Org chart (global, editable) ----------
class OrgNodeCreate(BaseModel):
    """Fields to create a node in a tribe's editable org chart."""
    tribe_id: Optional[int] = None
    parent_id: Optional[int] = None
    title: str
    person_name: Optional[str] = None
    squad_id: Optional[int] = None
    display_order: int = 0


class OrgNodeUpdate(BaseModel):
    """Partial edit of an org-chart node (incl. re-parenting via parent_id)."""
    parent_id: Optional[int] = None
    title: Optional[str] = None
    person_name: Optional[str] = None
    squad_id: Optional[int] = None
    display_order: Optional[int] = None


class OrgNodeTree(BaseModel):
    """A recursive org-chart node with its children nested underneath.

    ``squad_status`` is the derived health of the linked squad (when the node
    maps to one), surfaced so the tree can colour-code squads.
    """
    id: int
    parent_id: Optional[int] = None
    title: str
    person_name: Optional[str] = None
    squad_id: Optional[int] = None
    squad_status: Optional[QuarterHealth] = None
    display_order: int
    children: list["OrgNodeTree"] = []


class TribeOrg(BaseModel):
    """A tribe's full org chart as a forest of OrgNodeTree roots."""
    tribe_id: int
    tribe_name: str
    squads_count: int
    tree: list[OrgNodeTree]


# ---------- Feed (tweet zone) ----------
FeedKind = Literal["incident", "info", "success"]
ReactionKind = Literal["like", "ack"]


class AuthorInfo(BaseModel):
    """Minimal identity of a feed post/reply author for display."""
    id: Optional[int] = None
    display_name: Optional[str] = None
    role: Optional[str] = None


class FeedPostCreate(BaseModel):
    """Body to publish a feed post (optionally scoped to a squad)."""
    content: str = Field(min_length=1, max_length=1000)
    kind: FeedKind = "info"
    squad_id: Optional[int] = None


class FeedReplyCreate(BaseModel):
    """Body to reply to a feed post."""
    content: str = Field(min_length=1, max_length=1000)


class ReactionIn(BaseModel):
    """Body to add/toggle a reaction on a feed post."""
    kind: ReactionKind = "like"


class PinIn(BaseModel):
    """Body to pin or unpin a feed post."""
    is_pinned: bool


class FeedReplyOut(BaseModel):
    """A feed reply as returned by the API."""
    id: int
    content: str
    created_at: datetime
    author: AuthorInfo


class FeedPostOut(BaseModel):
    """A feed post as returned, with replies, reaction tallies and the caller's own reactions."""
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
    """A single in-app notification as returned by the API."""
    id: int
    kind: str
    actor_name: Optional[str] = None
    excerpt: Optional[str] = None
    link: Optional[str] = None
    is_read: bool
    created_at: datetime


class NotificationsResponse(BaseModel):
    """A page of notifications plus the unread badge count."""
    unread_count: int
    items: list[NotificationOut]


class PreferencesOut(BaseModel):
    """The user's current notification preferences."""
    notify_tweets: bool
    notify_replies: bool
    email_notifications: bool
    subscribe_weekly_report: bool


class PreferencesUpdate(BaseModel):
    """Partial update of notification preferences."""
    notify_tweets: Optional[bool] = None
    notify_replies: Optional[bool] = None
    email_notifications: Optional[bool] = None
    subscribe_weekly_report: Optional[bool] = None


class EmailExportIn(BaseModel):
    """Request to email a one-off report export to an address."""
    to: str
    year: Optional[int] = None


class ReportSubscriptionOut(BaseModel):
    """A user's report email subscription and its schedule, as returned."""
    squad_id: Optional[int] = None
    squad_name: Optional[str] = None
    interval_days: int
    weekdays: list[int] = []
    hour: int = 8
    last_sent_at: Optional[datetime] = None


class ReportSubscriptionIn(BaseModel):
    """Create/update a report subscription; empty weekdays unsubscribes."""
    squad_id: Optional[int] = None  # None = dashboard (user's visibility scope)
    interval_days: int = Field(default=0, ge=0, le=90)  # legacy; 0 = ignore
    weekdays: Optional[list[int]] = None   # 0=Mon..6=Sun; empty/None = unsubscribe
    hour: Optional[int] = None             # 0..23 (UTC)


# ---------- Audit ----------
class AuditOut(ORMModel):
    """An audit-log entry as returned by the API."""
    id: int
    user_id: Optional[int] = None
    action: str
    entity: Optional[str] = None
    entity_id: Optional[str] = None
    timestamp: datetime
    detail: Optional[dict] = None


# ---------- Review actions ----------
class ReviewActionOut(ORMModel):
    """A review/COPIL action item as returned by the API."""
    id: int
    squad_id: int
    text: str
    owner: Optional[str] = None
    due_date: Optional[datetime] = None
    done: bool
    created_at: Optional[datetime] = None


class ReviewActionCreate(BaseModel):
    """Fields to record a new review action item."""
    text: str
    owner: Optional[str] = None
    due_date: Optional[datetime] = None


class ReviewActionUpdate(BaseModel):
    """Partial edit of a review action (incl. marking it done)."""
    text: Optional[str] = None
    owner: Optional[str] = None
    due_date: Optional[datetime] = None
    done: Optional[bool] = None


# ---------- Settings ----------
class SettingsOut(BaseModel):
    """Editable application settings exposed to the admin UI."""
    staleness_threshold_days: int


class SettingsUpdate(BaseModel):
    """Update of application settings (bounded to sane ranges)."""
    staleness_threshold_days: int = Field(ge=1, le=365)


# ---------- Leaves / absences ----------
from datetime import date as _date  # local alias; date types for leave ranges

LeaveStatus = Literal["pending", "approved", "rejected", "cancelled"]


class LeaveTypeOut(ORMModel):
    """A configurable absence category as returned by the API."""
    id: int
    label: str
    color: str
    display_order: int
    is_active: bool
    requires_detail: bool = False


class LeaveTypeIn(BaseModel):
    """Create/update body for an absence category (admin-managed)."""
    label: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#6B7280", max_length=9)
    display_order: int = 0
    is_active: bool = True
    requires_detail: bool = False


class LeaveIn(BaseModel):
    """Body to declare an absence over a date range (half-days on the edges)."""
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
    """Partial edit of a declared absence."""
    type_id: Optional[int] = None
    start_date: Optional[_date] = None
    end_date: Optional[_date] = None
    start_half: Optional[bool] = None
    end_half: Optional[bool] = None
    detail: Optional[str] = Field(default=None, max_length=200)
    comment: Optional[str] = None


class LeaveDecisionIn(BaseModel):
    """A leader's approve/reject decision on a pending leave request."""
    action: Literal["approve", "reject"]
    comment: Optional[str] = None


class LeaveOut(BaseModel):
    """A declared absence as returned, with resolved type/label, computed day
    count and per-viewer permission flags (can_edit / can_decide). The private
    ``comment`` is null when the viewer is not allowed to see the motif."""
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
    """A tribe's current leave policy (approval requirement + overlap threshold)."""
    tribe_id: int
    tribe_name: str
    require_approval: bool
    overlap_threshold: int


class LeaveConfigIn(BaseModel):
    """Update of a tribe's leave policy (tribe leader / admin)."""
    require_approval: Optional[bool] = None
    overlap_threshold: Optional[int] = Field(default=None, ge=1, le=99)


class LeaveOverlapDay(BaseModel):
    """A day where a squad's simultaneous absences reach/exceed the warning threshold."""
    squad_id: int
    squad_name: str
    day: _date
    count: int
    names: list[str]
