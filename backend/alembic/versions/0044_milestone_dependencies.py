"""Several dependencies per milestone.

A milestone could depend on one squad, one tribe or one free text. It now keeps a
list. The existing single dependency becomes the first entry of the list; the
``dependency_*`` columns stay, mirroring that first entry, for the frozen
submissions and the API clients that read only one.
"""
import sqlalchemy as sa
from alembic import op

revision = "0044_milestone_dependencies"
down_revision = "0043_export_studio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roadmap_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("roadmap_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("squads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tribe_id", sa.Integer(), sa.ForeignKey("tribes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("text", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_roadmap_dependencies_item_id", "roadmap_dependencies", ["item_id"])
    op.create_index("ix_roadmap_dependencies_squad_id", "roadmap_dependencies", ["squad_id"])
    op.create_index("ix_roadmap_dependencies_tribe_id", "roadmap_dependencies", ["tribe_id"])
    op.execute("""
        INSERT INTO roadmap_dependencies (item_id, position, kind, squad_id, tribe_id, text)
        SELECT id, 0, dependency_kind, dependency_squad_id, NULL, NULL FROM roadmap_items
         WHERE dependency_kind = 'squad' AND dependency_squad_id IS NOT NULL
        UNION ALL
        SELECT id, 0, dependency_kind, NULL, dependency_tribe_id, NULL FROM roadmap_items
         WHERE dependency_kind = 'tribe' AND dependency_tribe_id IS NOT NULL
        UNION ALL
        SELECT id, 0, 'text', NULL, NULL, SUBSTR(TRIM(dependencies), 1, 500) FROM roadmap_items
         WHERE (dependency_kind = 'text' OR dependency_kind IS NULL)
           AND dependencies IS NOT NULL AND TRIM(dependencies) <> ''
    """)


def downgrade() -> None:
    op.drop_index("ix_roadmap_dependencies_tribe_id", table_name="roadmap_dependencies")
    op.drop_index("ix_roadmap_dependencies_squad_id", table_name="roadmap_dependencies")
    op.drop_index("ix_roadmap_dependencies_item_id", table_name="roadmap_dependencies")
    op.drop_table("roadmap_dependencies")
