"""Initiatives become a simple per-squad list: squad, owner, deadline.

Adds initiatives.squad_id (the squad it is assigned to), owner (free text) and
deadline. The old objective/OTD wiring is left in place but no longer used.
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_initiative_squad"
down_revision = "0011_widen_squad_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("initiatives", sa.Column(
        "squad_id", sa.Integer(), sa.ForeignKey("squads.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_initiatives_squad_id", "initiatives", ["squad_id"])
    op.add_column("initiatives", sa.Column("owner", sa.String(255), nullable=True))
    op.add_column("initiatives", sa.Column("deadline", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("initiatives", "deadline")
    op.drop_column("initiatives", "owner")
    op.drop_index("ix_initiatives_squad_id", table_name="initiatives")
    op.drop_column("initiatives", "squad_id")
