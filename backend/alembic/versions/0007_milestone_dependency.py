"""Structured milestone dependency: squad | tribe | free text.

Adds dependency_kind + dependency_squad_id + dependency_tribe_id to roadmap_items.
The existing free-text `dependencies` column is kept (used for the "text" kind).
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_milestone_dependency"
down_revision = "0006_review_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("roadmap_items", sa.Column("dependency_kind", sa.String(10), nullable=True))
    op.add_column("roadmap_items", sa.Column("dependency_squad_id", sa.Integer, nullable=True))
    op.add_column("roadmap_items", sa.Column("dependency_tribe_id", sa.Integer, nullable=True))
    op.create_foreign_key("fk_roadmap_dep_squad", "roadmap_items", "squads",
                          ["dependency_squad_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_roadmap_dep_tribe", "roadmap_items", "tribes",
                          ["dependency_tribe_id"], ["id"], ondelete="SET NULL")
    # Backfill: existing rows with a non-empty free-text dependency become kind="text".
    op.execute(
        "UPDATE roadmap_items SET dependency_kind = 'text' "
        "WHERE dependencies IS NOT NULL AND dependencies <> ''"
    )


def downgrade() -> None:
    op.drop_constraint("fk_roadmap_dep_tribe", "roadmap_items", type_="foreignkey")
    op.drop_constraint("fk_roadmap_dep_squad", "roadmap_items", type_="foreignkey")
    op.drop_column("roadmap_items", "dependency_tribe_id")
    op.drop_column("roadmap_items", "dependency_squad_id")
    op.drop_column("roadmap_items", "dependency_kind")
