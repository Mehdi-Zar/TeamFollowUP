"""Add squad.products and squad.hardware (lists of names).

Each squad owns one or more products and, optionally, one or more hardware
items. Stored as JSON arrays of strings and shown at the top of the squad page.
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_squad_products_hardware"
down_revision = "0014_squad_budget_forecast"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("squads", sa.Column("products", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("squads", sa.Column("hardware", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("squads", "hardware")
    op.drop_column("squads", "products")
