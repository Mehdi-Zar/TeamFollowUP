"""Squad governance meetings ("comitologie").

Adds the committees table: recurring meetings a squad runs (name, purpose,
cadence, day/time/duration, participants, animator). Declared by the squad
leader, read by the tribe leader. Gated by the optional `committees` module.
"""
import sqlalchemy as sa
from alembic import op

revision = "0022_committees"
down_revision = "0021_leave_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "committees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("squads.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("frequency", sa.String(16), nullable=False, server_default="monthly"),
        sa.Column("day_of_week", sa.String(16), nullable=True),
        sa.Column("time_of_day", sa.String(5), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("participants", sa.Text(), nullable=True),
        sa.Column("animator", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_committees_squad_id", "committees", ["squad_id"])


def downgrade() -> None:
    op.drop_index("ix_committees_squad_id", table_name="committees")
    op.drop_table("committees")
