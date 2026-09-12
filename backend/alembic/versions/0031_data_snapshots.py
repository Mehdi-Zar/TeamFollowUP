"""Point-in-time snapshots of the business data, taken and restored from the admin UI.

The backup sidecar dumps the database every night; it protects the machine. This
table protects the person: a copy taken from the screen before a reset or an
import, and restorable from the same screen.

The payload is gzipped JSON in one row. This application counts its rows in
thousands, so a snapshot is a few hundred kilobytes: keeping it in the database
means it follows the existing pg_dump backups instead of needing a volume of its
own.
"""
import sqlalchemy as sa
from alembic import op

revision = "0031_data_snapshots"
down_revision = "0030_squad_coleaders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_counts", sa.JSON(), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_data_snapshots_created_at"), "data_snapshots",
                    ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_data_snapshots_created_at"), table_name="data_snapshots")
    op.drop_table("data_snapshots")
