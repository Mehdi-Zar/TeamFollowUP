"""Customer Success, simpler: a project keeps only what is followed (docs/37).

Drops the offer, the tags, the other contacts, the per-stage milestones, the
models, the data classification, the maximum duration, the delivery mode, the
GCP project, the number of users and the consumption billing. What remains of
the money is the amount (``build_amount``), the cost code and where its billing
stands (``billing``: todo, invoiced or paid), which replaces ``quote_signed``: a
signed quote reads as paid, an amount without one as invoiced, nothing as todo.
The leader corrects by hand what this guess gets wrong.

Revision ID: 0054_cs_simplify
Revises: 0053_remote_work
"""
from alembic import op
import sqlalchemy as sa

revision = "0054_cs_simplify"
down_revision = "0053_remote_work"
branch_labels = None
depends_on = None

_DROPPED = ("offer", "tags", "contacts", "milestones", "models", "data_classification",
            "max_duration", "delivery_mode", "gcp_project", "users_count",
            "consumption_billing", "consumption_cap")


def upgrade() -> None:
    with op.batch_alter_table("cs_projects") as b:
        for col in _DROPPED:
            b.drop_column(col)
        b.add_column(sa.Column("billing", sa.String(20), nullable=False, server_default="todo"))
    op.execute("UPDATE cs_projects SET billing = CASE WHEN quote_signed THEN 'paid' "
               "WHEN build_amount IS NOT NULL THEN 'invoiced' ELSE 'todo' END")
    with op.batch_alter_table("cs_projects") as b:
        b.drop_column("quote_signed")


def downgrade() -> None:
    with op.batch_alter_table("cs_projects") as b:
        b.add_column(sa.Column("quote_signed", sa.Boolean, nullable=False, server_default=sa.false()))
    op.execute("UPDATE cs_projects SET quote_signed = (billing = 'paid')")
    with op.batch_alter_table("cs_projects") as b:
        b.drop_column("billing")
        b.add_column(sa.Column("offer", sa.String(255), nullable=True))
        b.add_column(sa.Column("tags", sa.JSON, nullable=False, server_default="[]"))
        b.add_column(sa.Column("contacts", sa.JSON, nullable=False, server_default="[]"))
        b.add_column(sa.Column("milestones", sa.JSON, nullable=False, server_default="{}"))
        b.add_column(sa.Column("models", sa.String(500), nullable=True))
        b.add_column(sa.Column("data_classification", sa.String(40), nullable=True))
        b.add_column(sa.Column("max_duration", sa.String(120), nullable=True))
        b.add_column(sa.Column("delivery_mode", sa.String(120), nullable=True))
        b.add_column(sa.Column("gcp_project", sa.String(255), nullable=True))
        b.add_column(sa.Column("users_count", sa.Integer, nullable=True))
        b.add_column(sa.Column("consumption_billing", sa.String(20), nullable=True))
        b.add_column(sa.Column("consumption_cap", sa.String(255), nullable=True))
