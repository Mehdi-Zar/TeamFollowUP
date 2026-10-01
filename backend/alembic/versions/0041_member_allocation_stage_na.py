"""Members' time on the squad, quarters a squad is not concerned by, jalons
outside a product release.

- ``members.allocation_pct``: share of the person's time spent on the squad
  (100 = full time). Existing members start at 100.
- ``quarter_progress.not_applicable``: the squad says a quarter does not concern
  it (it started in Q3, for instance). Shown as N/A, never as 0 %.
- ``roadmap_items.release_stage`` takes two more values, ``NP`` (not a product
  release: a security committee, an audit) and ``OT`` (other, named in
  ``release_stage_other``). Neither is drawn as a tag.
"""
import sqlalchemy as sa
from alembic import op

revision = "0041_member_allocation_stage_na"
down_revision = "0040_key_message_cycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("members", sa.Column("allocation_pct", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("quarter_progress", sa.Column("not_applicable", sa.Boolean(), nullable=False,
                                                server_default=sa.false()))
    op.add_column("roadmap_items", sa.Column("release_stage_other", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("roadmap_items", "release_stage_other")
    op.drop_column("quarter_progress", "not_applicable")
    op.drop_column("members", "allocation_pct")
