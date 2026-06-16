from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
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
    return datetime.now(timezone.utc)


# Global roles: admin | tribe_leader | squad_leader | member
class Tribe(Base):
    __tablename__ = "tribes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    squads: Mapped[list["Squad"]] = relationship(back_populates="tribe")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    tribe_id: Mapped[int | None] = mapped_column(ForeignKey("tribes.id"), nullable=True, index=True)
    auth_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_break_glass: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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

    led_squads: Mapped[list["Squad"]] = relationship(back_populates="leader", foreign_keys="Squad.leader_user_id")


class Squad(Base):
    __tablename__ = "squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    leader_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kpis_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tribe: Mapped["Tribe"] = relationship(back_populates="squads")
    leader: Mapped["User | None"] = relationship(back_populates="led_squads", foreign_keys=[leader_user_id])
    objectives: Mapped[list["Objective"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    roadmap_items: Mapped[list["RoadmapItem"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    quarter_progress: Mapped[list["QuarterProgress"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    kpis: Mapped[list["Kpi"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    members: Mapped[list["Member"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    snapshots: Mapped[list["ReportSnapshot"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    progress_updates: Mapped[list["ProgressUpdate"]] = relationship(back_populates="squad", cascade="all, delete-orphan")


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


class Objective(Base):
    __tablename__ = "objectives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rag_status: Mapped[str] = mapped_column(String(10), nullable=False, default="green")
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    squad: Mapped["Squad"] = relationship(back_populates="objectives")


class RoadmapItem(Base):
    __tablename__ = "roadmap_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..4
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_benefit: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="on_track")  # on_track|at_risk|blocked|done
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    squad: Mapped["Squad"] = relationship(back_populates="roadmap_items")


class QuarterProgress(Base):
    __tablename__ = "quarter_progress"
    __table_args__ = (UniqueConstraint("squad_id", "year", "quarter", name="uq_quarter_progress"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    squad: Mapped["Squad"] = relationship(back_populates="quarter_progress")


class Kpi(Base):
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
    __tablename__ = "report_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    cycle_label: Mapped[str] = mapped_column(String(100), nullable=False)

    squad: Mapped["Squad"] = relationship(back_populates="snapshots")


class ProgressUpdate(Base):
    """A point in a squad's progress-review timeline.

    Created automatically on each meaningful update (kind="auto", coalesced),
    on a weekly cadence (kind="weekly"), or when a leader writes a review note
    (kind="review"). Stores the metrics of the moment (for the evolution curve),
    a light state snapshot + computed changes (for the deltas), an optional free
    review note and a confidence indicator.
    """
    __tablename__ = "progress_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..5

    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    at_risk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    squad: Mapped["Squad"] = relationship(back_populates="progress_updates")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])


class FeedPost(Base):
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
    __tablename__ = "feed_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("feed_posts.id"), nullable=False, index=True)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    post: Mapped["FeedPost"] = relationship(back_populates="replies")
    author: Mapped["User | None"] = relationship(foreign_keys=[author_user_id])


class FeedReaction(Base):
    __tablename__ = "feed_reactions"
    __table_args__ = (UniqueConstraint("post_id", "user_id", "kind", name="uq_feed_reaction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("feed_posts.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="like")  # like|ack

    post: Mapped["FeedPost"] = relationship(back_populates="reactions")


class Notification(Base):
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
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
