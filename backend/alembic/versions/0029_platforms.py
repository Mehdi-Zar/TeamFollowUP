"""Platforms: the steerco slide stops being a squad and becomes a platform.

A platform is served by one or more squads (TP-S3NS is fed by Managed Services and
TP-S3NS LZ), and the steering committee wants one slide per platform, not one per
squad. The entry therefore moves from ``squad_id`` to ``platform_id``, and the
platform carries a ``template`` saying which contributing squad owns each KPI card
and each SLA column.

Nothing is lost on the way up: every squad that reports steerco (or has ever filled
a month) becomes a platform of its own, with that squad as sole contributor and a
template where it owns everything. Grouping two squads under one platform is then a
deliberate act in the admin screen, not something a migration guesses. Existing
events are stamped with their author squad, so the per-author merge rule applies to
history as well as to new months.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0029_platforms"
down_revision = "0028_trust_store"
branch_labels = None
depends_on = None

KPI_LABELS = ["Cloud Users", "Landing Zone", "K8aaS", "DBaaS", "Software Factory"]
SWF_SUB = ["GitLab", "Artifactory", "SonarQube"]
SLA_SERVICES = ["Incidents", "Gitlab", "Artifactory", "Sonarqube"]


def _template(squad_id: int) -> str:
    return json.dumps({
        "kpis": [{"label": label, "owner_squad_id": squad_id,
                  "sub": (list(SWF_SUB) if label == "Software Factory" else [])}
                 for label in KPI_LABELS],
        "sla": [{"label": s, "owner_squad_id": squad_id} for s in SLA_SERVICES],
        "incidents": {"owner_squad_id": squad_id},
    })


def upgrade() -> None:
    op.create_table(
        "platforms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tribe_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("steerco_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("template", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["tribe_id"], ["tribes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tribe_id", "name", name="uq_platform_tribe_name"),
    )
    op.create_index(op.f("ix_platforms_tribe_id"), "platforms", ["tribe_id"], unique=False)
    op.create_table(
        "platform_contributors",
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("squad_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["squad_id"], ["squads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("platform_id", "squad_id"),
    )
    op.add_column("steerco_entries", sa.Column("platform_id", sa.Integer(), nullable=True))

    conn = op.get_bind()
    squads = conn.execute(sa.text(
        "SELECT s.id, s.tribe_id, s.name, s.display_order FROM squads s "
        " WHERE s.steerco_enabled = true "
        "    OR EXISTS (SELECT 1 FROM steerco_entries e WHERE e.squad_id = s.id) "
        " ORDER BY s.display_order, s.id")).fetchall()
    taken: set[tuple[int, str]] = set()
    for squad_id, tribe_id, name, order in squads:
        # The platform takes the squad's name. Two squads of one tribe sharing a
        # name would break the unique constraint, so the second gets a suffix
        # rather than the migration failing on somebody's data.
        candidate, n = name, 1
        while (tribe_id, candidate) in taken:
            n += 1
            candidate = f"{name} ({n})"
        taken.add((tribe_id, candidate))
        platform_id = conn.execute(sa.text(
            "INSERT INTO platforms (tribe_id, name, display_order, steerco_enabled, template) "
            "VALUES (:tribe_id, :name, :order, true, :template) RETURNING id"),
            {"tribe_id": tribe_id, "name": candidate, "order": order or 0,
             "template": _template(squad_id)}).scalar_one()
        conn.execute(sa.text(
            "INSERT INTO platform_contributors (platform_id, squad_id) VALUES (:p, :s)"),
            {"p": platform_id, "s": squad_id})
        conn.execute(sa.text(
            "UPDATE steerco_entries SET platform_id = :p WHERE squad_id = :s"),
            {"p": platform_id, "s": squad_id})

        # Stamp the author on existing events: the merge on save keeps each
        # contributor's own lines, and an unstamped line would belong to nobody
        # and could never be edited again.
        rows = conn.execute(sa.text(
            "SELECT id, data FROM steerco_entries WHERE platform_id = :p"),
            {"p": platform_id}).fetchall()
        for entry_id, data in rows:
            blob = json.loads(data) if isinstance(data, (str, bytes)) else (data or {})
            if not isinstance(blob, dict):
                continue
            changed = False
            for key in ("last_events", "next_events"):
                events = blob.get(key)
                if isinstance(events, list):
                    for event in events:
                        if isinstance(event, dict) and not event.get("squad_id"):
                            event["squad_id"] = str(squad_id)
                            changed = True
            if changed:
                conn.execute(sa.text("UPDATE steerco_entries SET data = :d WHERE id = :i"),
                             {"d": json.dumps(blob), "i": entry_id})

    op.alter_column("steerco_entries", "platform_id", nullable=False)
    op.drop_constraint("uq_steerco_squad_period", "steerco_entries", type_="unique")
    op.drop_index(op.f("ix_steerco_entries_squad_id"), table_name="steerco_entries")
    op.drop_column("steerco_entries", "squad_id")
    op.create_index(op.f("ix_steerco_entries_platform_id"), "steerco_entries",
                    ["platform_id"], unique=False)
    op.create_unique_constraint("uq_steerco_platform_period", "steerco_entries",
                                ["platform_id", "period"])
    op.create_foreign_key("fk_steerco_platform", "steerco_entries", "platforms",
                          ["platform_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    """Back to one entry per squad, keeping the first contributor's data.

    A platform fed by several squads cannot be split back into per-squad rows: its
    single row goes to its first contributor and the others lose the month. The
    grouping is what this migration adds, so undoing it necessarily undoes that.
    """
    op.add_column("steerco_entries", sa.Column("squad_id", sa.Integer(), nullable=True))
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE steerco_entries e SET squad_id = ("
        "  SELECT c.squad_id FROM platform_contributors c "
        "   WHERE c.platform_id = e.platform_id ORDER BY c.squad_id LIMIT 1)"))
    conn.execute(sa.text("DELETE FROM steerco_entries WHERE squad_id IS NULL"))
    # One row per (squad, period) again: drop what the old constraint forbids.
    conn.execute(sa.text(
        "DELETE FROM steerco_entries WHERE id NOT IN ("
        "  SELECT MIN(id) FROM steerco_entries GROUP BY squad_id, period)"))

    op.drop_constraint("fk_steerco_platform", "steerco_entries", type_="foreignkey")
    op.drop_constraint("uq_steerco_platform_period", "steerco_entries", type_="unique")
    op.drop_index(op.f("ix_steerco_entries_platform_id"), table_name="steerco_entries")
    op.drop_column("steerco_entries", "platform_id")
    op.alter_column("steerco_entries", "squad_id", nullable=False)
    op.create_index(op.f("ix_steerco_entries_squad_id"), "steerco_entries",
                    ["squad_id"], unique=False)
    op.create_unique_constraint("uq_steerco_squad_period", "steerco_entries",
                                ["squad_id", "period"])
    op.create_foreign_key("fk_steerco_squad", "steerco_entries", "squads",
                          ["squad_id"], ["id"], ondelete="CASCADE")
    op.drop_table("platform_contributors")
    op.drop_index(op.f("ix_platforms_tribe_id"), table_name="platforms")
    op.drop_table("platforms")
