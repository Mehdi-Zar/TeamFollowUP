"""Remove the default "Télétravail" leave type.

Product decision: telework is not tracked as an absence. Only removes the seeded
default when it is unused (no leave references it), so a customer who relabelled
or used it keeps their data.
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_remove_teletravail"
down_revision = "0019_leaves"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(sa.text(
        "SELECT id FROM leave_types WHERE label = :l"), {"l": "Télétravail"}).first()
    if not row:
        return
    type_id = row[0]
    used = conn.execute(sa.text(
        "SELECT 1 FROM leaves WHERE type_id = :t LIMIT 1"), {"t": type_id}).first()
    if used:
        return  # keep referential integrity if it is already in use
    conn.execute(sa.text("DELETE FROM leave_types WHERE id = :t"), {"t": type_id})


def downgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(sa.text(
        "SELECT 1 FROM leave_types WHERE label = :l"), {"l": "Télétravail"}).first()
    if not exists:
        conn.execute(sa.text(
            "INSERT INTO leave_types (label, color, display_order, is_active) "
            "VALUES (:l, :c, :o, true)"),
            {"l": "Télétravail", "c": "#0891B2", "o": 4})
