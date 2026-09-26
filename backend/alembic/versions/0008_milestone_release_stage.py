"""Mandatory EA/GA release stage on milestones.

Adds roadmap_items.release_stage (EA|GA), defaulting existing rows to EA.
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_milestone_release_stage"
down_revision = "0007_milestone_dependency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roadmap_items",
        sa.Column("release_stage", sa.String(2), nullable=False, server_default="EA"),
    )


def downgrade() -> None:
    op.drop_column("roadmap_items", "release_stage")
