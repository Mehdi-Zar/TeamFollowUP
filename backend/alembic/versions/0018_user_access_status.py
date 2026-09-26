"""Add User.status for the SSO access-approval lifecycle.

pending (provisioned by SSO, awaiting validation) | active (validated) |
disabled (revoked). Existing accounts are backfilled to "active" so nothing
breaks; only newly SSO-provisioned users start as "pending".
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_user_access_status"
down_revision = "0017_drop_progress_updates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("status", sa.String(length=20), nullable=False, server_default="active"))


def downgrade() -> None:
    op.drop_column("users", "status")
