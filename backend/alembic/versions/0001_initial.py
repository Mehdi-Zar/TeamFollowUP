"""initial schema (v2: squads + quarterly roadmap)

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tribes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("tribe_id", sa.Integer, sa.ForeignKey("tribes.id"), nullable=True),
        sa.Column("auth_subject", sa.String(255), nullable=True),
        sa.Column("is_break_glass", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("notify_tweets", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notify_replies", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("email_notifications", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_auth_subject", "users", ["auth_subject"])

    op.create_table(
        "squads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tribe_id", sa.Integer, sa.ForeignKey("tribes.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("leader_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("kpis_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "members",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role_title", sa.String(255), nullable=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("manager_id", sa.Integer, sa.ForeignKey("members.id"), nullable=True),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_members_squad_id", "members", ["squad_id"])

    op.create_table(
        "org_nodes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tribe_id", sa.Integer, sa.ForeignKey("tribes.id"), nullable=False),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("org_nodes.id"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("person_name", sa.String(255), nullable=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=True),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "objectives",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rag_status", sa.String(10), nullable=False, server_default="green"),
        sa.Column("weight", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_objectives_squad_id", "objectives", ["squad_id"])
    op.create_index("ix_objectives_year", "objectives", ["year"])

    op.create_table(
        "roadmap_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("quarter", sa.Integer, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("success_criteria", sa.Text, nullable=True),
        sa.Column("user_benefit", sa.Text, nullable=True),
        sa.Column("dependencies", sa.Text, nullable=True),
        sa.Column("risks", sa.Text, nullable=True),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="on_track"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_roadmap_items_squad_id", "roadmap_items", ["squad_id"])
    op.create_index("ix_roadmap_items_year", "roadmap_items", ["year"])

    op.create_table(
        "quarter_progress",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("quarter", sa.Integer, nullable=False),
        sa.Column("progress_pct", sa.Integer, nullable=False, server_default="0"),
        sa.Column("comment", sa.Text, nullable=True),
        sa.UniqueConstraint("squad_id", "year", "quarter", name="uq_quarter_progress"),
    )
    op.create_index("ix_quarter_progress_squad_id", "quarter_progress", ["squad_id"])

    op.create_table(
        "kpis",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("target_value", sa.Numeric, nullable=True),
        sa.Column("current_value", sa.Numeric, nullable=True),
        sa.Column("trend_status", sa.String(20), nullable=False, server_default="on_target"),
        sa.Column("comment", sa.Text, nullable=True),
    )
    op.create_index("ix_kpis_squad_id", "kpis", ["squad_id"])

    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=False),
        sa.Column("submitted_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("cycle_label", sa.String(100), nullable=False),
    )
    op.create_index("ix_report_snapshots_squad_id", "report_snapshots", ["squad_id"])
    op.create_index("ix_report_snapshots_submitted_at", "report_snapshots", ["submitted_at"])

    op.create_table(
        "feed_posts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tribe_id", sa.Integer, sa.ForeignKey("tribes.id"), nullable=True),
        sa.Column("author_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("content", sa.String(1000), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="info"),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=True),
        sa.Column("is_pinned", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_feed_posts_created_at", "feed_posts", ["created_at"])

    op.create_table(
        "feed_replies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("post_id", sa.Integer, sa.ForeignKey("feed_posts.id"), nullable=False),
        sa.Column("author_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("content", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_feed_replies_post_id", "feed_replies", ["post_id"])

    op.create_table(
        "feed_reactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("post_id", sa.Integer, sa.ForeignKey("feed_posts.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="like"),
        sa.UniqueConstraint("post_id", "user_id", "kind", name="uq_feed_reaction"),
    )
    op.create_index("ix_feed_reactions_post_id", "feed_reactions", ["post_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("actor_name", sa.String(255), nullable=True),
        sa.Column("excerpt", sa.String(300), nullable=True),
        sa.Column("link", sa.String(300), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.String(100), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.JSON, nullable=True),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("notifications")
    op.drop_table("app_settings")
    op.drop_table("feed_reactions")
    op.drop_table("feed_replies")
    op.drop_table("feed_posts")
    op.drop_table("report_snapshots")
    op.drop_table("kpis")
    op.drop_table("quarter_progress")
    op.drop_table("roadmap_items")
    op.drop_table("objectives")
    op.drop_table("org_nodes")
    op.drop_table("members")
    op.drop_table("squads")
    op.drop_table("users")
    op.drop_table("tribes")
