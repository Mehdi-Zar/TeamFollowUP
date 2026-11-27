"""Scheduled reports become diffusions.

* ``report_sends``: the history of each diffusion (when, how triggered, how many
  mails, which were refused). The diffusions themselves live in ``app_settings``
  and are converted from the earlier schedules by reportconfig.ensure_diffusions
  on first use, which also renames their "what's new" baselines.
* The "report" Administration tab can now be given to a persona: a tribe leader
  sets up the diffusions of their own tribe. It could not be ticked before, so no
  admin ever chose to leave it out: the stored tribe leader persona gets it.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0050_report_diffusions"
down_revision = "0049_steerco_topic"
branch_labels = None
depends_on = None


def _personas(bind):
    settings = sa.table("app_settings", sa.column("key", sa.String), sa.column("value", sa.Text))
    row = bind.execute(sa.select(settings.c.value).where(settings.c.key == "personas")).first()
    return settings, row


def upgrade() -> None:
    op.create_table(
        "report_sends",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("diffusion_id", sa.Integer, nullable=False, index=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("sent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("attempted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("recipients", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed", sa.JSON, nullable=True),
        sa.Column("missing", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    bind = op.get_bind()
    settings, row = _personas(bind)
    if row is None:
        return
    try:
        personas = json.loads(row[0])
    except (TypeError, ValueError):
        return
    changed = False
    for p in personas if isinstance(personas, list) else []:
        if isinstance(p, dict) and p.get("key") == "tribe_leader":
            tabs = p.get("admin_tabs") or []
            if "report" not in tabs:
                p["admin_tabs"] = [*tabs, "report"]
                changed = True
    if changed:
        bind.execute(settings.update().where(settings.c.key == "personas")
                     .values(value=json.dumps(personas)))


def downgrade() -> None:
    op.drop_table("report_sends")
