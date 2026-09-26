"""Session version: logging out, or changing a password, a role or a status,
ends the account's existing sessions.

Every session token carries the account's version; a token with an older one is
refused. Existing accounts start at 0, and a token issued before this migration
(no version in it) reads as 0: current sessions survive the upgrade once.
"""
import sqlalchemy as sa
from alembic import op

revision = "0039_session_version"
down_revision = "0038_schema_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "session_version")
