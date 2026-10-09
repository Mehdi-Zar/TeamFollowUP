"""The life of an OTD: replanning, declared status, cancellation, carry-over.

``initial_committed_date`` keeps the first date when the date moves (existing
OTDs start with their current one). ``declared_*`` holds a status entered by hand
for an OTD whose story happened before the tool. ``cancelled_at`` and
``cancel_reason`` mark an OTD that was dropped. ``carried_from_id`` links the copy
made on January 1st to the OTD of the previous year it carries over, and
``created_at`` tells which OTDs existed before that date. On the milestones,
``done_at`` dates the move to "done", to tell a late delivery from an on-time one.
"""
import sqlalchemy as sa
from alembic import op

revision = "0045_otd_lifecycle"
down_revision = "0044_milestone_dependencies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("otds") as b:
        b.add_column(sa.Column("initial_committed_date", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("declared_status", sa.String(length=16), nullable=True))
        b.add_column(sa.Column("declared_on", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("declared_note", sa.Text(), nullable=True))
        b.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("cancel_reason", sa.Text(), nullable=True))
        b.add_column(sa.Column("carried_from_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                               server_default=sa.func.now()))
        b.create_foreign_key("fk_otds_carried_from", "otds", ["carried_from_id"], ["id"], ondelete="SET NULL")
        b.create_index("ix_otds_carried_from_id", ["carried_from_id"])
    op.execute("UPDATE otds SET initial_committed_date = committed_date")
    with op.batch_alter_table("roadmap_items") as b:
        b.add_column(sa.Column("done_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("roadmap_items") as b:
        b.drop_column("done_at")
    with op.batch_alter_table("otds") as b:
        b.drop_index("ix_otds_carried_from_id")
        b.drop_constraint("fk_otds_carried_from", type_="foreignkey")
        for c in ("created_at", "carried_from_id", "cancel_reason", "cancelled_at", "declared_note",
                  "declared_on", "declared_status", "initial_committed_date"):
            b.drop_column(c)
