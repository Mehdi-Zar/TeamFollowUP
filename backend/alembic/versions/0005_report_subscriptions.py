"""per-target report subscriptions (global or per-squad)

Revision ID: 0005_report_subscriptions
Revises: 0004_report_subscription
Create Date: 2026-06-15 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_report_subscriptions"
down_revision = "0004_report_subscription"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_subscriptions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("squad_id", sa.Integer, sa.ForeignKey("squads.id"), nullable=True, index=True),
        sa.Column("interval_days", sa.Integer, nullable=False, server_default="7"),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "squad_id", name="uq_report_sub_user_squad"),
    )
    # Migrate the user-level global subscription into a squad_id=NULL row.
    op.execute(
        "INSERT INTO report_subscriptions (user_id, squad_id, interval_days, last_sent_at, created_at) "
        "SELECT id, NULL, report_interval_days, report_last_sent_at, now() "
        "FROM users WHERE report_interval_days > 0"
    )


def downgrade() -> None:
    op.drop_table("report_subscriptions")
