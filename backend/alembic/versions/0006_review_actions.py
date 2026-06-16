"""review actions (COPIL decisions/actions per squad)

Revision ID: 0006_review_actions
Revises: 0005_report_subscriptions
Create Date: 2026-06-16 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_review_actions"
down_revision = "0005_report_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=False, index=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("review_actions")
