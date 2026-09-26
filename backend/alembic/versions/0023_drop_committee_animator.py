"""Drop the unused committees.animator column.

The facilitator/animator field was dropped from the comitologie feature as
unnecessary.
"""
import sqlalchemy as sa
from alembic import op

revision = "0023_drop_committee_animator"
down_revision = "0022_committees"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("committees", "animator")


def downgrade() -> None:
    op.add_column("committees", sa.Column("animator", sa.String(255), nullable=True))
