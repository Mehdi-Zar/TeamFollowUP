"""Widen squads.squad_type to allow custom (longer) type keys.

The squad type is open-ended (product | transverse | future custom types); widen
the column so a new type key isn't constrained to 12 characters.
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_widen_squad_type"
down_revision = "0010_initiatives_otd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("squads", "squad_type", type_=sa.String(32),
                    existing_nullable=False, existing_server_default="product")


def downgrade() -> None:
    op.alter_column("squads", "squad_type", type_=sa.String(12),
                    existing_nullable=False, existing_server_default="product")
