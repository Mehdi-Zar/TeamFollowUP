"""personal report subscription (interval in days)

Revision ID: 0004_report_subscription
Revises: 0003_weekly_report
Create Date: 2026-06-15 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_report_subscription"
down_revision = "0003_weekly_report"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("report_interval_days", sa.Integer(), nullable=False,
                                     server_default="0"))
    op.add_column("users", sa.Column("report_last_sent_at", sa.DateTime(timezone=True), nullable=True))
    # Migrate the old boolean opt-in to a weekly (7-day) personal subscription.
    op.execute("UPDATE users SET report_interval_days = 7 WHERE subscribe_weekly_report = true")


def downgrade() -> None:
    op.drop_column("users", "report_last_sent_at")
    op.drop_column("users", "report_interval_days")
