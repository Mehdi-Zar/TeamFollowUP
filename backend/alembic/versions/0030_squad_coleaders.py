"""Co-leaders: a squad can be led by more than one person.

``squads.leader_user_id`` stays as the squad's named leader (the person an OTD is
committed on, the one the report addresses). Co-leaders hold exactly the same rights
over the squad without disputing that identity, which is what holidays, a squad
piloted by two people, or a handover in progress actually need. Adding one used to
mean sharing an account or moving the leader field back and forth.

No data to migrate: the table starts empty and every existing squad keeps its single
leader.
"""
import sqlalchemy as sa
from alembic import op

revision = "0030_squad_coleaders"
down_revision = "0029_platforms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "squad_coleaders",
        sa.Column("squad_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["squad_id"], ["squads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("squad_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("squad_coleaders")
