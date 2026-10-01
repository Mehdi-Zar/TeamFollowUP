"""SCIM provisioning: the identity provider's own id for an account.

An identity provider that provisions accounts over SCIM (Entra ID, Okta) keeps
its own identifier for each one (``externalId``) and may look the account up by
it. Nullable: accounts created by hand or by SSO have none.
"""
import sqlalchemy as sa
from alembic import op

revision = "0042_user_scim_external_id"
down_revision = "0041_member_allocation_stage_na"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("scim_external_id", sa.String(length=255), nullable=True))
    op.create_index("ix_users_scim_external_id", "users", ["scim_external_id"])


def downgrade() -> None:
    op.drop_index("ix_users_scim_external_id", table_name="users")
    op.drop_column("users", "scim_external_id")
