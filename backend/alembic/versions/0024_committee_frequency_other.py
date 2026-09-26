"""Add committees.frequency_other (free-text cadence for frequency == 'other').

Also enables the new 'per_sprint' and 'other' frequency values (stored in the
existing varchar column, no schema change needed for those).
"""
import sqlalchemy as sa
from alembic import op

revision = "0024_committee_frequency_other"
down_revision = "0023_drop_committee_animator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("committees", sa.Column("frequency_other", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("committees", "frequency_other")
