"""Per-scope report baselines, to compute "what changed since your last report".

Stores a compact snapshot of each report's state at send time, keyed by scope
("global", "tribe:<id>", "sub:<id>"), diffed against the next send.
"""
import sqlalchemy as sa
from alembic import op

revision = "0025_report_baselines"
down_revision = "0024_committee_frequency_other"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_baselines",
        sa.Column("scope_key", sa.String(64), primary_key=True),
        sa.Column("signature", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("report_baselines")
