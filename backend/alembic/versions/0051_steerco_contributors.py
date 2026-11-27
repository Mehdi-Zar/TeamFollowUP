"""Steerco contributors: people who fill in a platform's figures (ADR 0019).

A Steerco leader names them platform by platform. They enter the month of the
platforms they hold, and nothing else: validation and sending stay with the Steerco
leaders.

Revision ID: 0051_steerco_contributors
Revises: 0050_report_diffusions
"""
from alembic import op
import sqlalchemy as sa

revision = "0051_steerco_contributors"
down_revision = "0050_report_diffusions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "steerco_contributors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("platform_id", sa.Integer, sa.ForeignKey("platforms.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("user_id", "platform_id", name="uq_steerco_contributor"),
    )


def downgrade() -> None:
    op.drop_table("steerco_contributors")
