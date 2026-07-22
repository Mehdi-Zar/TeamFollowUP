"""Steerco: per-squad opt-in flag + one steering-committee entry per period.

Adds ``squads.steerco_enabled`` (self-service opt-in, off by default) and the
``steerco_entries`` table. Concrete form fields are not columns - they live in the
schemaless ``data`` JSON blob, so the input shape can evolve without a migration per
field. Unique on (squad_id, period).
"""
import sqlalchemy as sa
from alembic import op

revision = "0027_steerco_entries"
down_revision = "0026_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "squads",
        sa.Column("steerco_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "steerco_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("squad_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["squad_id"], ["squads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("squad_id", "period", name="uq_steerco_squad_period"),
    )
    op.create_index(op.f("ix_steerco_entries_squad_id"), "steerco_entries", ["squad_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_steerco_entries_squad_id"), table_name="steerco_entries")
    op.drop_table("steerco_entries")
