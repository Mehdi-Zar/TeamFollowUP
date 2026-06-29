"""Team leave / absence management.

Adds:
- leave_types (configurable absence categories) seeded with French defaults
- leaves (one declared absence per person/date-range, with approval workflow)
- per-tribe settings on tribes (approval required, overlap alert threshold)
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_leaves"
down_revision = "0018_user_access_status"
branch_labels = None
depends_on = None


# (label, color, display_order) - mirrors leaves.DEFAULT_LEAVE_TYPES.
_DEFAULT_TYPES = [
    ("Congés payés", "#2563EB", 1),
    ("RTT", "#7C3AED", 2),
    ("Maladie", "#DC2626", 3),
    ("Télétravail", "#0891B2", 4),
    ("Formation", "#16A34A", 5),
    ("Autre", "#6B7280", 6),
]


def upgrade() -> None:
    op.add_column("tribes", sa.Column("leaves_require_approval", sa.Boolean(),
                                      nullable=False, server_default="true"))
    op.add_column("tribes", sa.Column("leaves_overlap_threshold", sa.Integer(),
                                      nullable=False, server_default="3"))

    leave_types = op.create_table(
        "leave_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=9), nullable=False, server_default="#6B7280"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.bulk_insert(leave_types, [
        {"label": lbl, "color": col, "display_order": order, "is_active": True}
        for (lbl, col, order) in _DEFAULT_TYPES
    ])

    op.create_table(
        "leaves",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tribe_id", sa.Integer(), sa.ForeignKey("tribes.id"), nullable=True),
        sa.Column("type_id", sa.Integer(), sa.ForeignKey("leave_types.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("start_half", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("end_half", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
    )
    op.create_index("ix_leaves_user_id", "leaves", ["user_id"])
    op.create_index("ix_leaves_tribe_id", "leaves", ["tribe_id"])
    op.create_index("ix_leaves_type_id", "leaves", ["type_id"])
    op.create_index("ix_leaves_start_date", "leaves", ["start_date"])
    op.create_index("ix_leaves_end_date", "leaves", ["end_date"])


def downgrade() -> None:
    op.drop_table("leaves")
    op.drop_table("leave_types")
    op.drop_column("tribes", "leaves_overlap_threshold")
    op.drop_column("tribes", "leaves_require_approval")
