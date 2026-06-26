"""Squad budget tracking + curated key messages.

Adds squads.budget_enabled (tribe-leader opt-in), the squad_budgets table
(per-squad/year total & spent, reported by the squad leader, privileged-visible)
and the key_messages table (hand-curated success/alert/risk readouts).
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_squad_budget_key_messages"
down_revision = "0012_initiative_squad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("squads", sa.Column(
        "budget_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "squad_budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("squads.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=True),
        sa.Column("spent", sa.Numeric(14, 2), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("squad_id", "year", name="uq_squad_budget"),
    )
    op.create_index("ix_squad_budgets_squad_id", "squad_budgets", ["squad_id"])

    op.create_table(
        "key_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("squads.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="success"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_key_messages_squad_id", "key_messages", ["squad_id"])
    op.create_index("ix_key_messages_year", "key_messages", ["year"])


def downgrade() -> None:
    op.drop_index("ix_key_messages_year", table_name="key_messages")
    op.drop_index("ix_key_messages_squad_id", table_name="key_messages")
    op.drop_table("key_messages")
    op.drop_index("ix_squad_budgets_squad_id", table_name="squad_budgets")
    op.drop_table("squad_budgets")
    op.drop_column("squads", "budget_enabled")
