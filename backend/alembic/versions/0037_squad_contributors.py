"""Contributors: people who do a squad's reporting without leading it.

A contributor fills in and submits the squad's weekly reporting (milestones, OTD,
key messages, mood, KPI values, progress, Steerco figures), and nothing else: the
squad's set-up (team, budget, committees, co-leaders) stays with its leadership.
Named per squad by its tribe leader or by its own leader.

No data to migrate: the table starts empty.
"""
import sqlalchemy as sa
from alembic import op

revision = "0037_squad_contributors"
down_revision = "0036_member_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "squad_contributors",
        sa.Column("squad_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["squad_id"], ["squads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("squad_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("squad_contributors")
