"""Reusable theme/lane on milestones.

Adds roadmap_items.theme: a short, reusable label (e.g. "Landing Zones",
"Managed Services") used to group milestones by theme in the roadmap and its
exports. Nullable so existing rows stay valid; mandatory at the API layer.
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_milestone_theme"
down_revision = "0008_milestone_release_stage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("roadmap_items", sa.Column("theme", sa.String(120), nullable=True))
    op.create_index("ix_roadmap_items_theme", "roadmap_items", ["theme"])


def downgrade() -> None:
    op.drop_index("ix_roadmap_items_theme", table_name="roadmap_items")
    op.drop_column("roadmap_items", "theme")
