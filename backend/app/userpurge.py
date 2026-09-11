"""Deleting a user: what goes with them, and what has to survive.

Nineteen columns in the schema point at ``users.id``, every one of them with
``NO ACTION``, so a bare ``db.delete(user)`` fails on the first of them that has
a row. That is not a theoretical objection: ``DELETE /api/admin/users/{id}``
returned 500 for any account that had ever logged in, because logging in writes
an audit row. The policy this module applies was already written down in three
places, and only the endpoint was not following it.

  * ``models.AuditLog``: "``user_id`` stays nullable so the trail survives
    deletion of the acting user".
  * ``docs/20`` section 5: personal records (absences, feed posts, replies,
    reactions) are erased without discussion; the audit trail is **anonymised,
    not erased**, because destroying it would destroy the evidence that the
    action happened; and the account itself should be removed through
    Administration, "which handles the detachments".
  * ``scripts/prune_users.py``, which detaches the audit rows and the squad
    leadership before deleting, exactly as intended.

Two rules, then. Rows that are the person's own go with them. Every other
reference is detached, so somebody else's record, or a fact that must stay
provable, survives without the attribution.

The owned rows are deleted **through the ORM**, one at a time, so the cascades
declared on the relationships actually run: a feed post carries its replies and
reactions, whose foreign keys have no ``ON DELETE CASCADE`` of their own. This is
the same lesson ``maintenance.purge_old_records`` records for the retention job,
where a bulk delete would fail the same way.

The detach set is derived from the schema rather than listed by hand, so a table
added later is handled without anyone remembering this file. What cannot be
derived is whether a new reference is personal, so a non-nullable one that nobody
has classified raises instead of guessing.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .database import Base

logger = logging.getLogger("trt.users")

# The person's own records: no meaning once they are gone, and listed one by one
# because "is this personal data" is a judgement, not a property of the schema.
# Mirrors docs/20 section 5, plus the two non-nullable references it does not
# mention (a notification and a report subscription are as personal as it gets).
OWNED_BY_USER: set[tuple[str, str]] = {
    ("leaves", "user_id"),
    ("feed_posts", "author_user_id"),
    ("feed_replies", "author_user_id"),
    ("feed_reactions", "user_id"),
    ("notifications", "user_id"),
    ("report_subscriptions", "user_id"),
    # Co-leading a squad is a link to the person, not a piece of the squad: once
    # the account is gone the row means nothing, and the squad keeps its leader
    # and its other co-leaders.
    ("squad_coleaders", "user_id"),
}


def _references_to_users() -> tuple[list, list]:
    """Split every column pointing at ``users.id`` into (owned, to detach).

    Raises on a non-nullable reference nobody has classified: it can neither be
    detached nor kept, so the alternative to failing here is a 500 in front of an
    administrator later.
    """
    owned, detach = [], []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if not any(fk.column.table.name == "users" and fk.column.name == "id"
                       for fk in col.foreign_keys):
                continue
            if (table.name, col.name) in OWNED_BY_USER:
                owned.append((table, col))
            elif col.nullable:
                detach.append((table, col))
            else:
                raise RuntimeError(
                    f"{table.name}.{col.name} references users.id, is NOT NULL, and is not "
                    f"listed in OWNED_BY_USER. Decide whether it is the person's own record "
                    f"(add it there) or somebody else's (make the column nullable)."
                )
    return owned, detach


def _class_for(table_name: str):
    """The mapped class for a table, so owned rows can be deleted via the ORM."""
    for mapper in Base.registry.mappers:
        if mapper.local_table is not None and mapper.local_table.name == table_name:
            return mapper.class_
    return None


def purge_user_references(db: Session, user_id: int) -> dict[str, int]:
    """Make ``user_id`` deletable: drop what is theirs, detach the rest.

    Does not delete the user and does not commit, so the caller keeps the
    transaction and can audit the deletion in the same one. Returns a per-table
    count, which is what makes the operation reportable rather than silent.
    """
    owned, detach = _references_to_users()
    counts: dict[str, int] = {}

    for table, col in owned:
        cls = _class_for(table.name)
        if cls is None:                     # unmapped table: no cascades to run
            n = db.execute(delete(table).where(col == user_id)).rowcount or 0
        else:
            # One by one through the ORM: the cascades declared on the
            # relationships (a post's replies and reactions) have no
            # ON DELETE CASCADE behind them and would fail a bulk delete.
            rows = db.scalars(select(cls).where(getattr(cls, col.name) == user_id)).all()
            for row in rows:
                db.delete(row)
            n = len(rows)
        if n:
            counts[f"{table.name}.{col.name}"] = n

    db.flush()

    for table, col in detach:
        n = db.execute(update(table).where(col == user_id).values({col.name: None})).rowcount or 0
        if n:
            counts[f"{table.name}.{col.name}(detached)"] = n

    if counts:
        logger.info("user %s: %s", user_id, counts)
    return counts
