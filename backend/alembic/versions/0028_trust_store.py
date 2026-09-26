"""Trusted authorities move out of the TLS blob, and the private key goes away.

The application no longer terminates TLS (ADR 0013), so the ``tls`` setting row
kept a server certificate and, worse, its **unencrypted private key**, which
followed every ``pg_dump`` into the backups. This migration rewrites the row as
the ``trust`` setting, keeping only ``cas``, the admin-managed authorities that
outbound calls verify against.

The certificate and key are dropped, not archived. Downgrading brings the
authorities back under the old key; the server material is gone for good.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0028_trust_store"
down_revision = "0027_steerco_entries"
branch_labels = None
depends_on = None

_SELECT = sa.text("SELECT value FROM app_settings WHERE key = :key")
_DELETE = sa.text("DELETE FROM app_settings WHERE key = :key")
_INSERT = sa.text("INSERT INTO app_settings (key, value) VALUES (:key, :value)")


def _move(bind, src: str, dst: str) -> None:
    """Copy the ``cas`` list from the ``src`` settings row into a fresh ``dst`` row.

    Everything else in the source blob is discarded. A missing or unreadable
    source row is not an error: it just means there is nothing to carry over.
    """
    row = bind.execute(_SELECT, {"key": src}).fetchone()
    cas = []
    if row and row[0]:
        try:
            cas = json.loads(row[0]).get("cas") or []
        except (json.JSONDecodeError, TypeError, AttributeError):
            cas = []
    bind.execute(_DELETE, {"key": src})
    bind.execute(_DELETE, {"key": dst})
    if cas:
        bind.execute(_INSERT, {"key": dst, "value": json.dumps({"cas": cas})})


def upgrade() -> None:
    _move(op.get_bind(), "tls", "trust")


def downgrade() -> None:
    _move(op.get_bind(), "trust", "tls")
