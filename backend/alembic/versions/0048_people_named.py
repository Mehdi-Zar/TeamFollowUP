"""Every account and org-chart line shows a name, never an address.

When the identity provider (OIDC, SAML), the SCIM directory or the import sent
no name, the email was stored as the account's name, and the screens showed
some people by name and others by address. New accounts now get a name read
from the email (« jean.dupont@... » gives « Jean Dupont ») until the provider
sends the real one; this brings the existing rows to the same state.
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0048_people_named"
down_revision = "0047_key_message_carry_over"
branch_labels = None
depends_on = None


def _name_from_email(email: str) -> str:
    local = email.split("@", 1)[0]
    parts = [p for p in re.split(r"[._\-+]+", local) if p]
    return " ".join(p.capitalize() for p in parts) or email


def upgrade() -> None:
    bind = op.get_bind()
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("email", sa.String),
                     sa.column("display_name", sa.String))
    for r in bind.execute(sa.select(users)).mappings().all():
        cur = (r["display_name"] or "").strip()
        if (not cur or "@" in cur) and (r["email"] or cur):
            bind.execute(users.update().where(users.c.id == r["id"])
                         .values(display_name=_name_from_email(r["email"] or cur)[:255]))
    members = sa.table("members", sa.column("id", sa.Integer), sa.column("email", sa.String),
                       sa.column("full_name", sa.String))
    for r in bind.execute(sa.select(members)).mappings().all():
        cur = (r["full_name"] or "").strip()
        if "@" in cur:
            bind.execute(members.update().where(members.c.id == r["id"])
                         .values(full_name=_name_from_email(cur)[:255]))


def downgrade() -> None:
    # The addresses stay on the rows (email column): nothing is lost, nothing to undo.
    pass
