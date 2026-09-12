"""Granular data reset: erase what you choose, keep the rest, from the admin UI.

There was one way to start over, ``python -m app.reset_data``: it wiped every
business table and re-seeded a hard-coded organisation nobody uses any more. It
had to be run inside the container, it asked no question, and it could not erase a
year of entries while keeping the org chart that took an afternoon to type in.

This module is the catalogue behind the screen. A **domain** is a set of tables
that mean one thing to a person ("the weekly entries", "the roadmap", "the org
structure"), plus what erasing it drags along. Dependencies are declared rather
than discovered: the FK graph knows that roadmap items die with their squad, it
does not know that an administrator who says "erase the entries" does not mean
"erase the squads".

Two rules the screen depends on:

* every domain is counted before anything is deleted, so the confirmation shows
  real numbers rather than a promise;
* erasing a domain always erases the domains that hang off it (``implies``),
  transitively, because leaving orphans would be worse than the reset itself.

What is never erased here: ``app_settings`` (SMTP, modules, SSO, the whole
configuration), ``leave_types`` (a referential, not data), and the break-glass
admin. Losing the configuration with the data would lock the administrator out of
the app they were tidying up.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import Base

logger = logging.getLogger("trt.reset")

# Never erased, whatever is selected: configuration, referentials, and the
# snapshot store (erasing your backups as part of a reset would be a trap).
NEVER_ERASED = {"app_settings", "leave_types", "data_snapshots", "alembic_version"}

# key -> (tables it owns, domains it drags along when erased)
DOMAINS: dict[str, dict] = {
    "reporting": {
        "tables": ["report_snapshots", "quarter_progress", "key_messages", "review_actions",
                   "report_baselines"],
        "implies": [],
    },
    "roadmap": {"tables": ["roadmap_items"], "implies": []},
    "objectives": {"tables": ["objectives"], "implies": ["roadmap"]},
    "initiatives": {"tables": ["initiatives", "otds"], "implies": []},
    "kpis": {"tables": ["kpis"], "implies": []},
    "budgets": {"tables": ["squad_budgets"], "implies": []},
    "steerco": {
        "tables": ["steerco_entries", "platform_contributors", "platforms"],
        "implies": [],
    },
    "committees": {"tables": ["committees"], "implies": []},
    "members": {"tables": ["members"], "implies": []},
    "org": {"tables": ["org_nodes"], "implies": []},
    "leaves": {"tables": ["leaves"], "implies": []},
    "feed": {"tables": ["feed_reactions", "feed_replies", "feed_posts"], "implies": []},
    "notifications": {"tables": ["notifications"], "implies": []},
    "audit": {"tables": ["audit_log"], "implies": []},
    "api_keys": {"tables": ["api_keys"], "implies": []},
    # The structure carries everything that hangs off a squad or a tribe, so it
    # cannot be erased alone: the implied list is the honest consequence, shown in
    # the confirmation before anything happens.
    "structure": {
        "tables": ["squad_coleaders", "squads", "tribes"],
        "implies": ["reporting", "roadmap", "objectives", "initiatives", "kpis", "budgets",
                    "steerco", "committees", "members", "org", "leaves"],
    },
    # Accounts go last: a user is referenced from everywhere, and the deletion
    # policy of app/userpurge.py is the authority on what is personal.
    "users": {"tables": ["report_subscriptions"], "implies": ["feed", "notifications", "leaves",
                                                              "api_keys"]},
}


def expand(keys) -> list[str]:
    """The domains actually erased when ``keys`` are selected, transitively.

    Returned in the catalogue's order so the confirmation screen and the deletion
    agree on what is about to happen.
    """
    wanted, queue = set(), list(keys or [])
    while queue:
        key = queue.pop()
        if key in wanted or key not in DOMAINS:
            continue
        wanted.add(key)
        queue.extend(DOMAINS[key]["implies"])
    return [k for k in DOMAINS if k in wanted]


def _table(name: str):
    return Base.metadata.tables.get(name)


def counts(db: Session) -> dict[str, dict]:
    """Row count per domain and per table, for the screen that asks before erasing.

    A domain with nothing in it is still listed: "0" is the answer to "is there
    anything left to clean up", and hiding the line would leave the question open.
    """
    out: dict[str, dict] = {}
    for key, spec in DOMAINS.items():
        per_table, total = {}, 0
        for name in spec["tables"]:
            table = _table(name)
            if table is None:
                continue
            n = db.scalar(select(func.count()).select_from(table)) or 0
            per_table[name] = n
            total += n
        out[key] = {"total": total, "tables": per_table, "implies": spec["implies"]}
    # Accounts are counted apart: the break-glass admin is never erased, so the
    # number shown must be the number that will really go.
    users = _table("users")
    if users is not None:
        bg = (settings.breakglass_email or "").lower().strip()
        n = db.scalar(select(func.count()).select_from(users).where(
            func.lower(users.c.email) != bg)) or 0
        out["users"]["tables"]["users"] = n
        out["users"]["total"] += n
    return out


def detach_external_refs(db: Session, emptied: set[str]) -> list[tuple]:
    """NULL every reference from a SURVIVING table into a table being emptied.

    Deleting the tribes while the accounts still point at them fails on the
    foreign key, and the administrator reads a database error for a choice the
    screen offered. Rather than ordering the deletions more cleverly (there is no
    order that works: the reference survives the referent on purpose), the links
    are cut first.

    A non-nullable reference from a surviving table cannot be cut, and means the
    domain graph is wrong: erasing one thing without the other would leave a row
    that cannot exist. Raising here says which pair, instead of surfacing as an
    integrity error mid-transaction.

    Returns what was cut, so a restore can put it back (see datasnapshots.restore);
    a reset has nothing to put back.
    """
    saved = []
    for table in Base.metadata.sorted_tables:
        if table.name in emptied:
            continue
        for col in table.columns:
            targets = {fk.column.table.name for fk in col.foreign_keys}
            if not targets & emptied:
                continue
            if not col.nullable:
                raise RuntimeError(
                    f"{table.name}.{col.name} pointe vers {sorted(targets & emptied)} et ne peut "
                    f"pas etre detache : les deux doivent etre effaces ensemble."
                )
            pk = list(table.primary_key.columns)
            rows = db.execute(select(*pk, col).where(col.is_not(None))).all() if pk else []
            if rows:
                saved.append((table, col, pk, [tuple(r) for r in rows]))
            db.execute(table.update().where(col.is_not(None)).values({col.name: None}))
    return saved


def reattach(db: Session, saved: list[tuple]) -> None:
    """Put back the links cut by :func:`detach_external_refs`, where they still point
    at something. After a restore the rows are usually back with the same ids, so a
    snapshot keeps its author; a row that did not come back stays detached."""
    for table, col, pk, rows in saved:
        target = next(iter(col.foreign_keys)).column
        for row in rows:
            value = row[-1]
            exists = db.scalar(select(func.count()).select_from(target.table)
                               .where(target == value))
            if not exists:
                continue
            where = [c == row[i] for i, c in enumerate(pk)]
            db.execute(table.update().where(*where).values({col.name: value}))


def erase(db: Session, keys) -> dict[str, int]:
    """Delete the selected domains (and what they imply). Returns rows per table.

    Tables are emptied in reverse dependency order so a child never outlives its
    parent, and the whole thing runs in the caller's transaction: a reset either
    happens entirely or not at all.
    """
    selected = expand(keys)
    names = {n for key in selected for n in DOMAINS[key]["tables"]}
    erase_users = "users" in selected
    users = Base.metadata.tables["users"]
    bg = (settings.breakglass_email or "").lower().strip()
    deleted: dict[str, int] = {}

    # Accounts first, one by one: app/userpurge.py is the authority on what is
    # personal (deleted) and what is somebody else's (detached), and it refuses to
    # guess about a reference nobody classified.
    if erase_users:
        from .userpurge import purge_user_references
        for uid in db.scalars(select(users.c.id).where(func.lower(users.c.email) != bg)).all():
            purge_user_references(db, uid)
        db.flush()

    detach_external_refs(db, set(names) | ({"users"} if erase_users else set()))

    for table in reversed(Base.metadata.sorted_tables):
        if table.name in NEVER_ERASED:
            continue
        if table.name == "users":
            if not erase_users:
                continue
            # Whoever else goes, the break-glass admin stays: it is the only login
            # guaranteed to work after the data it administers has gone.
            n = db.execute(table.delete().where(func.lower(table.c.email) != bg)).rowcount or 0
        elif table.name in names:
            n = db.execute(table.delete()).rowcount or 0
        else:
            continue
        if n:
            deleted[table.name] = n

    logger.info("reset: %s -> %s", selected, deleted)
    return deleted
