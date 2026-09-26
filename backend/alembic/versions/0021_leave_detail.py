"""Optional "specify" detail on a leave, driven by a per-type flag.

leave_types.requires_detail: when true, declaring the type prompts the user for a
short free-text detail (stored on leaves.detail). Seeded true for the default
"Autre"/"Other" type so users can say what the "other" absence is.
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_leave_detail"
down_revision = "0020_remove_teletravail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leave_types", sa.Column("requires_detail", sa.Boolean(),
                                           nullable=False, server_default="false"))
    op.add_column("leaves", sa.Column("detail", sa.String(length=200), nullable=True))
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE leave_types SET requires_detail = true WHERE label IN ('Autre', 'Other')"))


def downgrade() -> None:
    op.drop_column("leaves", "detail")
    op.drop_column("leave_types", "requires_detail")
