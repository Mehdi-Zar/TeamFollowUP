"""Tribe initiatives, OTD delivery commitments, and squad type.

Adds the tribe-leader reporting chain Initiative -> Objective -> Milestone,
the top-management OTD (on-time delivery / budget) commitments that group
milestones, and a squad_type discriminator (product vs transverse) that drives
which export format a squad gets.
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_initiatives_otd"
down_revision = "0009_milestone_theme"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "initiatives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tribe_id", sa.Integer(), sa.ForeignKey("tribes.id"), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=False, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "otds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tribe_id", sa.Integer(), sa.ForeignKey("tribes.id"), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=False, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("budget_ref", sa.String(100), nullable=True),
        sa.Column("committed_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("squads", sa.Column("squad_type", sa.String(12), nullable=False, server_default="product"))
    op.add_column("objectives", sa.Column(
        "initiative_id", sa.Integer(),
        sa.ForeignKey("initiatives.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_objectives_initiative_id", "objectives", ["initiative_id"])
    op.add_column("roadmap_items", sa.Column(
        "objective_id", sa.Integer(),
        sa.ForeignKey("objectives.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_roadmap_items_objective_id", "roadmap_items", ["objective_id"])
    op.add_column("roadmap_items", sa.Column(
        "otd_id", sa.Integer(),
        sa.ForeignKey("otds.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_roadmap_items_otd_id", "roadmap_items", ["otd_id"])


def downgrade() -> None:
    op.drop_index("ix_roadmap_items_otd_id", table_name="roadmap_items")
    op.drop_column("roadmap_items", "otd_id")
    op.drop_index("ix_roadmap_items_objective_id", table_name="roadmap_items")
    op.drop_column("roadmap_items", "objective_id")
    op.drop_index("ix_objectives_initiative_id", table_name="objectives")
    op.drop_column("objectives", "initiative_id")
    op.drop_column("squads", "squad_type")
    op.drop_table("otds")
    op.drop_table("initiatives")
