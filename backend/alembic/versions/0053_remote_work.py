"""Remote work: the usual week of each person and the changes for one day (ADR 0021).

Revision ID: 0053_remote_work
Revises: 0052_customer_success
"""
from alembic import op
import sqlalchemy as sa

revision = "0053_remote_work"
down_revision = "0052_customer_success"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remote_patterns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, unique=True, index=True),
        sa.Column("weekdays", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.create_table(
        "remote_days",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("day", sa.Date, nullable=False, index=True),
        sa.Column("location", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.UniqueConstraint("user_id", "day", name="uq_remote_day"),
    )


def downgrade() -> None:
    op.drop_table("remote_days")
    op.drop_table("remote_patterns")
