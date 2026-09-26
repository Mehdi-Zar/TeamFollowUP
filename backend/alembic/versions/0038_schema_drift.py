"""Bring the migrated schema in line with the models.

The tests build their database with ``create_all`` from the models; production
builds it by running the migrations. The two had drifted apart:

- four indexes declared by the models (``index=True``) were never created, on the
  very columns the busiest screens filter on (squads, users, feed posts and org
  nodes by tribe);
- eleven creation / update timestamps are NOT NULL in the models but nullable in
  the database. Rows written before a default existed are given one first;
- the two milestone dependency foreign keys delete with SET NULL in the database
  but said nothing in the models (the models now say it too, so a future
  autogenerate does not drop the behaviour).
"""
from alembic import op

revision = "0038_schema_drift"
down_revision = "0037_squad_contributors"
branch_labels = None
depends_on = None

_INDEXES = [
    ("ix_squads_tribe_id", "squads", "tribe_id"),
    ("ix_users_tribe_id", "users", "tribe_id"),
    ("ix_feed_posts_tribe_id", "feed_posts", "tribe_id"),
    ("ix_org_nodes_tribe_id", "org_nodes", "tribe_id"),
]

_NOT_NULL = [
    ("api_keys", "created_at"),
    ("audit_log", "timestamp"),
    ("feed_posts", "created_at"),
    ("feed_replies", "created_at"),
    ("leaves", "created_at"),
    ("notifications", "created_at"),
    ("report_snapshots", "submitted_at"),
    ("report_subscriptions", "created_at"),
    ("steerco_entries", "updated_at"),
    ("tribes", "created_at"),
    ("users", "created_at"),
]


def upgrade() -> None:
    for name, table, col in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({col})")
    for table, col in _NOT_NULL:
        op.execute(f"UPDATE {table} SET {col} = now() WHERE {col} IS NULL")
        op.alter_column(table, col, nullable=False)


def downgrade() -> None:
    for table, col in _NOT_NULL:
        op.alter_column(table, col, nullable=True)
    for name, _table, _col in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
