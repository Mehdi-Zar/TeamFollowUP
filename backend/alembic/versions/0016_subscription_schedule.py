"""Per-user report subscription: choose weekdays + hour (recurrence), replacing
the simple every-N-days interval. The interval column is kept for back-compat.
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_subscription_schedule"
down_revision = "0015_squad_products_hardware"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_subscriptions", sa.Column("weekdays", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("report_subscriptions", sa.Column("hour", sa.Integer(), nullable=False, server_default="8"))


def downgrade() -> None:
    op.drop_column("report_subscriptions", "hour")
    op.drop_column("report_subscriptions", "weekdays")
