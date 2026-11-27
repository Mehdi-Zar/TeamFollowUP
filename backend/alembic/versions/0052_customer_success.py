"""Customer Success: the projects a CS team delivers (ADR 0020, docs/37).

A tribe's CS leaders (the tribe leader by default, plus designated users) keep a
flat list of projects, each with a dated journal and a few points to follow.
Contributors are named project by project.

Revision ID: 0052_customer_success
Revises: 0051_steerco_contributors
"""
from alembic import op
import sqlalchemy as sa

revision = "0052_customer_success"
down_revision = "0051_steerco_contributors"
branch_labels = None
depends_on = None


def _user_fk(name: str, ondelete: str = "SET NULL", nullable: bool = True):
    return sa.Column(name, sa.Integer, sa.ForeignKey("users.id", ondelete=ondelete),
                     nullable=nullable, index=not nullable)


def upgrade() -> None:
    op.create_table(
        "cs_leaders",
        sa.Column("id", sa.Integer, primary_key=True),
        _user_fk("user_id", "CASCADE", nullable=False),
        sa.Column("tribe_id", sa.Integer, sa.ForeignKey("tribes.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("excluded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _user_fk("created_by_user_id"),
        sa.UniqueConstraint("user_id", "tribe_id", name="uq_cs_leader"),
    )
    op.create_table(
        "cs_projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tribe_id", sa.Integer, sa.ForeignKey("tribes.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("client", sa.String(255), nullable=True),
        sa.Column("requesters", sa.String(500), nullable=True),
        sa.Column("contacts", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("tags", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("stage", sa.String(40), nullable=False, server_default="request"),
        sa.Column("health", sa.String(10), nullable=True),
        sa.Column("offer", sa.String(255), nullable=True),
        sa.Column("delivery_mode", sa.String(120), nullable=True),
        sa.Column("gcp_project", sa.String(255), nullable=True),
        sa.Column("planned_delivery", sa.Date, nullable=True),
        sa.Column("actual_delivery", sa.Date, nullable=True),
        sa.Column("build_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("quote_signed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("cost_code", sa.String(255), nullable=True),
        sa.Column("consumption_billing", sa.String(20), nullable=True),
        sa.Column("consumption_cap", sa.String(255), nullable=True),
        sa.Column("users_count", sa.Integer, nullable=True),
        sa.Column("models", sa.String(500), nullable=True),
        sa.Column("data_classification", sa.String(40), nullable=True),
        sa.Column("max_duration", sa.String(120), nullable=True),
        sa.Column("access_end", sa.Date, nullable=True),
        sa.Column("milestones", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("links", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _user_fk("created_by_user_id"),
    )
    op.create_table(
        "cs_contributors",
        sa.Column("id", sa.Integer, primary_key=True),
        _user_fk("user_id", "CASCADE", nullable=False),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("cs_projects.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "project_id", name="uq_cs_contributor"),
    )
    op.create_table(
        "cs_journal",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("cs_projects.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="note"),
        sa.Column("people", sa.String(500), nullable=True),
        sa.Column("text", sa.Text, nullable=False, server_default=""),
        sa.Column("links", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("in_recap", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _user_fk("created_by_user_id"),
    )
    op.create_table(
        "cs_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("cs_projects.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="action"),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("due", sa.Date, nullable=True),
        sa.Column("opened_on", sa.Date, nullable=True),
        sa.Column("done", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("done_on", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for t in ("cs_items", "cs_journal", "cs_contributors", "cs_projects", "cs_leaders"):
        op.drop_table(t)
