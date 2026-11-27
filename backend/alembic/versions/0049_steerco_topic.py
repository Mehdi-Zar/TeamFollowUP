"""Steerco becomes a topic of its own, run by Steerco leaders (ADR 0018, 4.0.0).

* ``steerco_leaders``: who runs a tribe's Steerco, on top of their role. The tribe
  leader holds it by default without a row, so nothing is inserted here.
* ``steerco_entries`` gains its life cycle (draft / validated, reopened with a
  reason) and a version counter against concurrent saves. Every existing month
  starts as a draft: marking them validated would claim a validation nobody made.
* Templates lose their per-item owners (``owner_squad_id``): only Steerco leaders
  enter figures now. The linked squads stay, as the platform's squads concerned.
* ``squads.steerco_enabled`` goes: it only decided whether the weekly entry showed
  a Steerco step, and that step is gone.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0049_steerco_topic"
down_revision = "0048_people_named"
branch_labels = None
depends_on = None


def _strip_owners(tpl):
    if isinstance(tpl, str):
        try:
            tpl = json.loads(tpl)
        except ValueError:
            return None
    if not isinstance(tpl, dict):
        return None
    out = dict(tpl)
    out["kpis"] = [{k: v for k, v in item.items() if k != "owner_squad_id"}
                   for item in (tpl.get("kpis") or []) if isinstance(item, dict)]
    out["sla"] = [{k: v for k, v in item.items() if k != "owner_squad_id"}
                  for item in (tpl.get("sla") or []) if isinstance(item, dict)]
    out.pop("incidents", None)
    return out


def upgrade() -> None:
    op.create_table(
        "steerco_leaders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("tribe_id", sa.Integer, sa.ForeignKey("tribes.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("excluded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("user_id", "tribe_id", name="uq_steerco_leader"),
    )
    with op.batch_alter_table("steerco_entries") as b:
        b.add_column(sa.Column("status", sa.String(16), nullable=False, server_default="draft"))
        b.add_column(sa.Column("version", sa.Integer, nullable=False, server_default="1"))
        b.add_column(sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("validated_by_user_id", sa.Integer,
                               sa.ForeignKey("users.id", name="fk_steerco_validated_by"),
                               nullable=True))
        b.add_column(sa.Column("revised_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    platforms = sa.table("platforms", sa.column("id", sa.Integer), sa.column("template", sa.JSON))
    for row in bind.execute(sa.select(platforms)).mappings().all():
        tpl = _strip_owners(row["template"])
        if tpl is not None:
            bind.execute(platforms.update().where(platforms.c.id == row["id"]).values(template=tpl))

    with op.batch_alter_table("squads") as b:
        b.drop_column("steerco_enabled")


def downgrade() -> None:
    with op.batch_alter_table("squads") as b:
        b.add_column(sa.Column("steerco_enabled", sa.Boolean, nullable=False,
                               server_default=sa.false()))
    with op.batch_alter_table("steerco_entries") as b:
        b.drop_column("revised_at")
        b.drop_column("validated_by_user_id")
        b.drop_column("validated_at")
        b.drop_column("version")
        b.drop_column("status")
    op.drop_table("steerco_leaders")
