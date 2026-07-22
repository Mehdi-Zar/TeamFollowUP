"""SQLAlchemy ORM models - the database schema of the Tribe Cockpit.

Every persisted entity lives here as a declarative model mapped onto a table.
The domain is a multi-tenant reporting tool organised around a hierarchy:

    Tribe (tenant) -> Squad (team) -> Objective -> RoadmapItem (jalon/milestone)

with cross-cutting entities layered on top: strategic Initiatives and OTD
(budget delivery commitments) at tribe level, plus KPIs, budgets, key messages,
committees, a social feed, notifications, leaves/absences, audit log and machine
API keys. Business-rule and constraint details that aren't obvious from the
column type are documented inline next to each field.
"""
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Used as the default/onupdate for timestamp columns so every stored time is
    unambiguously UTC (never a naive local time).
    """
    return datetime.now(timezone.utc)


# Global roles: admin | tribe_leader | squad_leader | member
class Tribe(Base):
    """A tenant: the top-level organisational unit that owns squads and users.

    Also holds tribe-wide leave/absence policy (approval requirement and the
    overlap warning threshold) configured by its tribe leader.
    """
    __tablename__ = "tribes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Leave/absence management, configurable per tribe (deps.can_manage_leave).
    # When approval is required, a member's request starts "pending" until a
    # squad/tribe leader approves it; otherwise it is recorded immediately.
    leaves_require_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true")
    # Warn leaders when this many people of one squad are absent on the same day.
    leaves_overlap_threshold: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False, server_default="3")

    squads: Mapped[list["Squad"]] = relationship(back_populates="tribe")


class User(Base):
    """A login account and its role, tribe membership and notification settings.

    Identity may come from SSO (``auth_subject`` links to the IdP subject) or a
    local password (``password_hash``). ``role`` and ``status`` together decide
    what the account may do and whether it may sign in at all.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Login identifier; unique + indexed because it is the natural lookup key.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Built-in role (admin|tribe_leader|squad_leader|member) or a custom persona key.
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    # Access lifecycle: pending (provisioned by SSO, awaiting validation) | active
    # (validated) | disabled (revoked). Only "active" accounts may use the app.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    # Tribe the user belongs to; NULL for admins (who are global / cross-tribe).
    tribe_id: Mapped[int | None] = mapped_column(ForeignKey("tribes.id"), nullable=True, index=True)
    # Stable IdP subject identifier for SSO logins (indexed for callback lookup).
    auth_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Emergency local admin created at first boot; protected from non-admin edits.
    is_break_glass: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Argon2 hash for local (non-SSO) login; NULL for accounts that only use SSO.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # notification preferences
    notify_tweets: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_replies: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscribe_weekly_report: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Personal report subscription: send the report every N days (0 = unsubscribed).
    report_interval_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Squads this user leads (via Squad.leader_user_id); explicit FK because
    # Squad references users more than once.
    led_squads: Mapped[list["Squad"]] = relationship(back_populates="leader", foreign_keys="Squad.leader_user_id")


class Squad(Base):
    """A team inside a tribe - the main unit that reports progress.

    Carries its own reporting configuration (KPIs on/off, budget tracking on/off,
    ``squad_type`` selecting the reporting style) and owns the bulk of the app's
    content: objectives, roadmap milestones, members, KPIs, budgets, etc. All of
    those child relationships cascade-delete so removing a squad cleans up its
    entire report.
    """
    __tablename__ = "squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    leader_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kpis_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Steerco (steering-committee) reporting is opt-in per squad and self-service:
    # the squad leader flips it on when they want to prepare their steerco input for
    # a period (recurring but at no fixed cadence, ~monthly). Off by default; when on,
    # a Steerco section appears in the reporting screen and feeds the consolidated PPTX.
    steerco_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Budget tracking is opt-in per squad: the tribe leader turns it on, then the
    # squad leader reports the figures. The amounts (SquadBudget) are visible only
    # to the squad leader, its tribe leader and admins.
    budget_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # "product" squads report via the roadmap (EA/GA milestones); "transverse"
    # squads report via initiatives + OTD. Open-ended so new types can be added.
    squad_type: Mapped[str] = mapped_column(String(32), nullable=False, default="product")
    # Product name(s) the squad owns, and optional hardware name(s). Free lists of
    # strings (set on squad create/edit, shown at the top of the squad page).
    products: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    hardware: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    tribe: Mapped["Tribe"] = relationship(back_populates="squads")
    leader: Mapped["User | None"] = relationship(back_populates="led_squads", foreign_keys=[leader_user_id])
    objectives: Mapped[list["Objective"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    roadmap_items: Mapped[list["RoadmapItem"]] = relationship(
        back_populates="squad", cascade="all, delete-orphan",
        foreign_keys="RoadmapItem.squad_id")
    quarter_progress: Mapped[list["QuarterProgress"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    kpis: Mapped[list["Kpi"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    members: Mapped[list["Member"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    snapshots: Mapped[list["ReportSnapshot"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    budgets: Mapped[list["SquadBudget"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    key_messages: Mapped[list["KeyMessage"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    committees: Mapped[list["Committee"]] = relationship(back_populates="squad", cascade="all, delete-orphan")


class Member(Base):
    """A person in a squad (org chart). Optionally linked to a login account."""
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    squad: Mapped["Squad"] = relationship(back_populates="members")
    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])


class OrgNode(Base):
    """Editable global tribe org chart (hybrid: a node may link to a squad)."""
    __tablename__ = "org_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id"), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("org_nodes.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    person_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    squad_id: Mapped[int | None] = mapped_column(ForeignKey("squads.id"), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Initiative(Base):
    """A strategic initiative set by the tribe leader and assigned to one squad.
    Shown as a flat list (initiative / owner / squad / deadline) and surfaced in
    that squad's report + dashboard. Read-only for squad leaders and members."""
    __tablename__ = "initiatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The squad the initiative is assigned to (so it shows in that squad's report).
    squad_id: Mapped[int | None] = mapped_column(
        ForeignKey("squads.id", ondelete="SET NULL"), nullable=True, index=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)  # free-text owner
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # legacy, unused
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    objectives: Mapped[list["Objective"]] = relationship(back_populates="initiative")
    squad: Mapped["Squad | None"] = relationship(foreign_keys=[squad_id])


class Otd(Base):
    """A One-Time / On-Time Delivery commitment fixed by top management to track a
    budget milestone. It groups milestones (RoadmapItem.otd_id) and carries a single
    committed date; its on-time status is derived from those milestones."""
    __tablename__ = "otds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    committed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    roadmap_items: Mapped[list["RoadmapItem"]] = relationship(back_populates="otd",
                                                              foreign_keys="RoadmapItem.otd_id")
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_user_id])


class Objective(Base):
    """An annual squad objective, optionally contributing to a tribe initiative.

    Sits in the middle of the reporting chain (Initiative -> Objective -> Jalon):
    milestones (RoadmapItem) point back to it. ``rag_status`` is a derived
    red/amber/green health, not hand-entered.
    """
    __tablename__ = "objectives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Derived health roll-up (green|amber|red), computed from milestones.
    rag_status: Mapped[str] = mapped_column(String(10), nullable=False, default="green")
    # Relative importance used to weight this objective in progress roll-ups.
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Which tribe initiative this objective contributes to (optional).
    initiative_id: Mapped[int | None] = mapped_column(
        ForeignKey("initiatives.id", ondelete="SET NULL"), nullable=True, index=True)

    squad: Mapped["Squad"] = relationship(back_populates="objectives")
    initiative: Mapped["Initiative | None"] = relationship(back_populates="objectives")
    jalons: Mapped[list["RoadmapItem"]] = relationship(
        back_populates="objective", foreign_keys="RoadmapItem.objective_id")


class RoadmapItem(Base):
    """A roadmap milestone ("jalon") planned in a given year/quarter for a squad.

    The most detailed reporting unit. It may link up to a squad Objective and to
    a top-management OTD, and may declare a structured dependency on another
    squad or tribe (or free text). ``status`` drives the at-risk/blocked signals
    surfaced on the dashboard.
    """
    __tablename__ = "roadmap_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..4
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # Reusable theme/lane (e.g. "Landing Zones", "Managed Services") used to group
    # milestones in the roadmap view and exports. Mandatory at the API layer; kept
    # nullable in the DB so pre-existing rows remain valid.
    theme: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    release_stage: Mapped[str] = mapped_column(String(2), nullable=False, default="EA")  # EA|GA
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_benefit: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-text dependency note (kept for the "text" kind and as a fallback label).
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured dependency: a dependency can target a squad, a tribe, or be free text.
    dependency_kind: Mapped[str | None] = mapped_column(String(10), nullable=True)  # text|squad|tribe
    dependency_squad_id: Mapped[int | None] = mapped_column(ForeignKey("squads.id"), nullable=True)
    dependency_tribe_id: Mapped[int | None] = mapped_column(ForeignKey("tribes.id"), nullable=True)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="on_track")  # on_track|at_risk|blocked|done
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Which squad objective this milestone answers (objective → tribe initiative).
    objective_id: Mapped[int | None] = mapped_column(
        ForeignKey("objectives.id", ondelete="SET NULL"), nullable=True, index=True)
    # Which top-management OTD (budget delivery commitment) this milestone belongs to.
    otd_id: Mapped[int | None] = mapped_column(
        ForeignKey("otds.id", ondelete="SET NULL"), nullable=True, index=True)

    squad: Mapped["Squad"] = relationship(back_populates="roadmap_items", foreign_keys=[squad_id])
    dependency_squad: Mapped["Squad | None"] = relationship(foreign_keys=[dependency_squad_id])
    dependency_tribe: Mapped["Tribe | None"] = relationship(foreign_keys=[dependency_tribe_id])
    objective: Mapped["Objective | None"] = relationship(back_populates="jalons", foreign_keys=[objective_id])
    otd: Mapped["Otd | None"] = relationship(back_populates="roadmap_items", foreign_keys=[otd_id])


class QuarterProgress(Base):
    """A squad's self-reported completion percentage for one year/quarter.

    Unique per (squad, year, quarter) - exactly one progress figure per cell of
    the quarterly grid.
    """
    __tablename__ = "quarter_progress"
    __table_args__ = (UniqueConstraint("squad_id", "year", "quarter", name="uq_quarter_progress"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    squad: Mapped["Squad"] = relationship(back_populates="quarter_progress")


class SquadBudget(Base):
    """Per-squad, per-year budget envelope. The tribe leader enables budget on the
    squad (Squad.budget_enabled); the squad leader reports `total` (allocated) and
    `spent` (consumed/forecast). On-track and overrun are derived from those two.
    Restricted to the squad leader, its tribe leader and admins."""
    __tablename__ = "squad_budgets"
    __table_args__ = (UniqueConstraint("squad_id", "year", name="uq_squad_budget"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)      # envelope, set by tribe leader
    spent: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)      # consumed to date, by squad leader
    forecast: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)   # projected landing, by squad leader
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)

    squad: Mapped["Squad"] = relationship(back_populates="budgets")


class KeyMessage(Base):
    """A hand-curated executive message for a squad/year: a success, an alert or a
    risk. Surfaced on the squad page below the roadmap to give a narrative readout."""
    __tablename__ = "key_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="success")  # success|alert|risk
    text: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    squad: Mapped["Squad"] = relationship(back_populates="key_messages")


class Committee(Base):
    """A recurring governance meeting ("comitologie") a squad runs: its name,
    purpose, cadence and logistics. Declared by the squad leader, read by the
    tribe leader for oversight. Standing (not year-scoped)."""
    __tablename__ = "committees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    # daily | weekly | biweekly | per_sprint | monthly | quarterly | yearly | on_demand | other
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    # Free-text cadence when frequency == "other".
    frequency_other: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # For recurring cadences: mon..sun (nullable). Free scheduling detail otherwise.
    day_of_week: Mapped[str | None] = mapped_column(String(16), nullable=True)
    time_of_day: Mapped[str | None] = mapped_column(String(5), nullable=True)   # "HH:MM"
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    participants: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    squad: Mapped["Squad"] = relationship(back_populates="committees")


class Kpi(Base):
    """A key performance indicator tracked by a squad (target vs current value).

    Only shown when the squad has KPIs enabled. ``trend_status`` summarises how
    the current value tracks against the target.
    """
    __tablename__ = "kpis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    trend_status: Mapped[str] = mapped_column(String(20), nullable=False, default="on_target")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    squad: Mapped["Squad"] = relationship(back_populates="kpis")


class ReportSnapshot(Base):
    """An immutable point-in-time capture of a squad's full report at submission.

    Taken when a squad submits a reporting cycle: the whole computed report is
    frozen into ``payload`` (JSON) so it can be re-read later exactly as it was,
    independent of subsequent edits. ``cycle_label`` names the cycle.
    """
    __tablename__ = "report_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # Frozen copy of the entire report at submission time (self-contained JSON).
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    cycle_label: Mapped[str] = mapped_column(String(100), nullable=False)

    squad: Mapped["Squad"] = relationship(back_populates="snapshots")


class FeedPost(Base):
    """A short message in the social feed ("tweet zone"): incident, info or success.

    Can be tribe-wide or scoped to a squad, and pinned to stay at the top. Owns
    its replies and reactions, which cascade-delete with the post.
    """
    __tablename__ = "feed_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tribe_id: Mapped[int | None] = mapped_column(ForeignKey("tribes.id"), nullable=True, index=True)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="info")  # incident|info|success
    squad_id: Mapped[int | None] = mapped_column(ForeignKey("squads.id"), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    author: Mapped["User | None"] = relationship(foreign_keys=[author_user_id])
    replies: Mapped[list["FeedReply"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    reactions: Mapped[list["FeedReaction"]] = relationship(back_populates="post", cascade="all, delete-orphan")


class FeedReply(Base):
    """A comment on a FeedPost."""
    __tablename__ = "feed_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("feed_posts.id"), nullable=False, index=True)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    post: Mapped["FeedPost"] = relationship(back_populates="replies")
    author: Mapped["User | None"] = relationship(foreign_keys=[author_user_id])


class FeedReaction(Base):
    """A user's reaction (like / ack) to a FeedPost.

    Unique per (post, user, kind) so each user registers a given reaction on a
    post at most once.
    """
    __tablename__ = "feed_reactions"
    __table_args__ = (UniqueConstraint("post_id", "user_id", "kind", name="uq_feed_reaction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("feed_posts.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="like")  # like|ack

    post: Mapped["FeedPost"] = relationship(back_populates="reactions")


class Notification(Base):
    """A per-user in-app notification (e.g. a new tweet or reply mentioning them).

    Denormalises the actor name / excerpt / link so the notification renders
    without re-joining the source entity, which may later change or be deleted.
    """
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # tweet | reply
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(String(300), nullable=True)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ReviewAction(Base):
    """A decision / action item captured during a review (COPIL), per squad."""
    __tablename__ = "review_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportSubscription(Base):
    """A user's email subscription to a report, on their own cadence.

    squad_id NULL = the dashboard report scoped to the user's visibility
    (global for admins, their tribe otherwise). squad_id set = that squad only.
    """
    __tablename__ = "report_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "squad_id", name="uq_report_sub_user_squad"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    squad_id: Mapped[int | None] = mapped_column(ForeignKey("squads.id"), nullable=True, index=True)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # legacy cadence
    # Preferred schedule: send on these weekdays (0=Mon..6=Sun) at this hour (UTC).
    weekdays: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    """A single runtime-editable setting, stored as a key/value string pair.

    Generic bag for admin-tunable values that must survive restarts and be
    changed without a redeploy (unlike the static, env-driven :mod:`.config`).
    The key is the primary key.
    """
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class ReportBaseline(Base):
    """Snapshot of a report's state at the last time it was emailed, keyed by
    scope ("global", "tribe:<id>", "sub:<id>"). Diffed against the next send to
    tell each recipient what changed since their previous report."""
    __tablename__ = "report_baselines"

    scope_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    signature: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LeaveType(Base):
    """A configurable category of absence (Congés payés, RTT, Maladie, …).

    Managed by admins (Admin → Congés). The `color` drives the pill colour in the
    team calendar; deactivating a type hides it from new declarations while keeping
    existing leaves valid."""
    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(9), nullable=False, default="#6B7280")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # When true, declaring this type prompts the user for a short free-text detail
    # (e.g. the "Autre"/"Other" type → "specify what"). Stored on Leave.detail.
    requires_detail: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false")


class Leave(Base):
    """A declared absence for one person over a date range.

    Attached to a login account (User). The *type* is visible to everyone in the
    person's tribe (admins see all); the free-text *comment* (motif) is visible
    only to the person, their squad/tribe leader and admins. Half-days are encoded
    on the range edges (start_half = starts in the afternoon, end_half = ends at
    noon)."""
    __tablename__ = "leaves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # Denormalised at creation so visibility queries stay tribe-scoped even if the
    # user later moves tribe (the leave keeps the tribe it was filed under).
    tribe_id: Mapped[int | None] = mapped_column(ForeignKey("tribes.id"), nullable=True, index=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_half: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # PM only on first day
    end_half: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)    # AM only on last day
    # Short clarification of the type (used when the type requires_detail, e.g.
    # "Autre" → "Déménagement"). Public, like the type label.
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)  # private motif
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending|approved|rejected|cancelled
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    type: Mapped["LeaveType"] = relationship(foreign_keys=[type_id])


class AuditLog(Base):
    """An append-only record of a security-relevant action for traceability.

    Captures who did what to which entity and when, with optional structured
    ``detail``. ``user_id`` stays nullable so the trail survives deletion of the
    acting user. Retention is governed by ``audit_retention_days`` in config.
    """
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ApiKey(Base):
    """A machine credential for the read-only API (Admin → API).

    Not a user: a key is a service credential owned by the organisation, so it
    survives the departure of whoever created it. The secret is shown once at
    creation and only its argon2 hash is stored - `prefix` is the non-secret
    handle used to display and look the key up.

    Scope of what it may read is the intersection of:
      * `scopes`   - which resources (see app/apikeys.py SCOPES);
      * `tribe_id` - which tribe (NULL = every tribe).
    """
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Public, non-secret handle: the "trt_ab12cd34" head of the key.
    prefix: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # NULL = all tribes; otherwise the key only ever sees that tribe.
    tribe_id: Mapped[int | None] = mapped_column(ForeignKey("tribes.id"), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tribe: Mapped["Tribe | None"] = relationship(foreign_keys=[tribe_id])
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])


class SteercoEntry(Base):
    """One squad's Steering-Committee (steerco) monthly snapshot.

    A squad has at most one entry per month (unique constraint). The one-pager
    (HTML / PPTX) is not stored: it is rebuilt on the fly from the last 12 of these
    rows, so the charts and the "last 12 months" SLA row stay in sync by construction.

    The snapshot fields live in the schemaless ``data`` JSON blob rather than in
    columns, so the input shape can evolve without a migration per field. See
    ``app/routers/steerco.py`` and ``frontend/src/steerco.ts`` for that shape.
    """
    __tablename__ = "steerco_entries"
    __table_args__ = (UniqueConstraint("squad_id", "period", name="uq_steerco_squad_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id", ondelete="CASCADE"),
                                          index=True, nullable=False)
    # Reporting month, "YYYY-MM".
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    # The month's snapshot: {"kpis": [...], "sla": {...}, "incidents": "13",
    # "last_events": [...], "next_events": [...]}.
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    squad: Mapped["Squad"] = relationship(foreign_keys=[squad_id])
    updated_by: Mapped["User | None"] = relationship(foreign_keys=[updated_by_user_id])
