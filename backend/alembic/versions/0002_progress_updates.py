"""progress review timeline (progress_updates)

Revision ID: 0002_progress_updates
Revises: 0001_initial
Create Date: 2026-06-10 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_progress_updates"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "progress_updates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=False, index=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("confidence", sa.Integer, nullable=True),
        sa.Column("progress_pct", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("at_risk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("done_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("state", sa.JSON, nullable=True),
        sa.Column("changes", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("progress_updates")
