"""weekly report subscription flag on users

Revision ID: 0003_weekly_report
Revises: 0002_progress_updates
Create Date: 2026-06-15 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_weekly_report"
down_revision = "0002_progress_updates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("subscribe_weekly_report", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "subscribe_weekly_report")
