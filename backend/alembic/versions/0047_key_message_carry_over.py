"""Submitted key messages carry over into the next reporting, editable.

Until now a submission closed the squad's key messages and the next reporting
started with none: the documents fell back on the submitted ones, shown read
only, and the first message added made them all disappear. The submission now
copies them, open again, into the next reporting. This brings the squads that
are between two reportings to the same state: where a squad and year have no
open message, the messages of its last submission are copied as open ones.
"""
import sqlalchemy as sa
from alembic import op

revision = "0047_key_message_carry_over"
down_revision = "0046_user_hide_getting_started"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    km = sa.table("key_messages",
                  sa.column("id", sa.Integer), sa.column("squad_id", sa.Integer),
                  sa.column("year", sa.Integer), sa.column("kind", sa.String),
                  sa.column("text", sa.Text), sa.column("display_order", sa.Integer),
                  sa.column("created_at", sa.DateTime(timezone=True)),
                  sa.column("created_by_user_id", sa.Integer),
                  sa.column("snapshot_id", sa.Integer))
    rows = bind.execute(sa.select(km)).mappings().all()
    groups: dict = {}
    for r in rows:
        groups.setdefault((r["squad_id"], r["year"]), []).append(r)
    copies = []
    for msgs in groups.values():
        if any(m["snapshot_id"] is None for m in msgs):
            continue
        last = max(m["snapshot_id"] for m in msgs)
        for m in sorted((m for m in msgs if m["snapshot_id"] == last),
                        key=lambda m: (m["display_order"], m["id"])):
            copies.append({k: m[k] for k in ("squad_id", "year", "kind", "text",
                                             "display_order", "created_at",
                                             "created_by_user_id")} | {"snapshot_id": None})
    if copies:
        op.bulk_insert(km, copies)


def downgrade() -> None:
    # The copies cannot be told from messages written afterwards: nothing to undo.
    pass
