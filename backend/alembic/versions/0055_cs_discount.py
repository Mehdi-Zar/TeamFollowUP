"""Customer Success: a discount on the price, no more access end date (docs/37).

``discount_value`` with ``discount_kind`` (``pct``: a percentage of the price,
``amount``: euros excl. VAT). The net price, what the billing figures count, is
computed, never stored. ``access_end`` (and its "access ends soon" badge) is
dropped: nobody followed it.

Revision ID: 0055_cs_discount
Revises: 0054_cs_simplify
"""
from alembic import op
import sqlalchemy as sa

revision = "0055_cs_discount"
down_revision = "0054_cs_simplify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cs_projects") as b:
        b.add_column(sa.Column("discount_value", sa.Numeric(12, 2), nullable=True))
        b.add_column(sa.Column("discount_kind", sa.String(10), nullable=False, server_default="pct"))
        b.drop_column("access_end")


def downgrade() -> None:
    with op.batch_alter_table("cs_projects") as b:
        b.add_column(sa.Column("access_end", sa.Date(), nullable=True))
        b.drop_column("discount_kind")
        b.drop_column("discount_value")
