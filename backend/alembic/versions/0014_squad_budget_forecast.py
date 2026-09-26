"""Add squad_budgets.forecast (projected landing, reported by the squad leader).

The on-track / at-risk / over status is derived from forecast (falling back to
spent) versus the total envelope, so budget risk reflects where the squad will
land, not only what it has spent to date.
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_squad_budget_forecast"
down_revision = "0013_squad_budget_key_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("squad_budgets", sa.Column("forecast", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("squad_budgets", "forecast")
