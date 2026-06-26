"""Drop the progress_updates table (progress-review feature removed).

The whole progress-review notion (per-squad review notes + confidence, the
auto/weekly timeline and the COPIL review page) was removed. This drops its
storage. Forward-only in practice: the downgrade recreates the table shape but
not its data.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_drop_progress_updates"
down_revision = "0016_subscription_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("progress_updates")


def downgrade() -> None:
    op.create_table(
        "progress_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("squads.id"), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="auto"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("at_risk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("changes", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )
