"""Key messages belong to a reporting: each submission closes its messages.

``snapshot_id`` names the submission that carried the message (NULL while the
reporting is still being filled in). A new reporting starts with no message of
its own, and the documents keep showing the last submitted ones until it has
some. No foreign key: a data reset empties the snapshots before the messages.
Existing messages start open, as part of the reporting in progress.
"""
import sqlalchemy as sa
from alembic import op

revision = "0040_key_message_cycle"
down_revision = "0039_session_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("key_messages", sa.Column("snapshot_id", sa.Integer(), nullable=True))
    op.create_index("ix_key_messages_snapshot_id", "key_messages", ["snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_key_messages_snapshot_id", table_name="key_messages")
    op.drop_column("key_messages", "snapshot_id")
