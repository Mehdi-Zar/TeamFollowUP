"""The getting-started guide's "don't show at startup" choice, on the account.

It used to live in the browser's storage only, so a browser that clears it on
close (a common corporate policy) showed the guide again at every start.
"""
import sqlalchemy as sa
from alembic import op

revision = "0046_user_hide_getting_started"
down_revision = "0045_otd_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("hide_getting_started", sa.Boolean(), nullable=False,
                                     server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("hide_getting_started")
