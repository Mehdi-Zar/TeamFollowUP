"""Point-in-time snapshots of the business data: take one, restore one, schedule them.

The database already had a backup sidecar (``pg_dump`` every night, see
docker-compose). It protects the machine, not the person: restoring it means a
shell, a running Postgres, and an all-or-nothing rewind of everything including
the configuration. What was missing is the thing an administrator actually asks
for before a reset, an import, or a demo: **take a copy now, and be able to put it
back from the screen**.

A snapshot is the content of the business tables, serialized to JSON and gzipped
into one row of ``data_snapshots``. Small by construction (this application counts
its rows in thousands), inside the database, so it follows the pg_dump backups and
survives a container rebuild.

What a snapshot holds is exactly what a reset can erase, minus the configuration:
:data:`app.datareset.NEVER_ERASED` is the single definition of what stays out, so a
snapshot can never carry SMTP credentials or the snapshot store itself.

Restoring is deliberately brutal and complete: the covered tables are emptied and
rewritten with the stored rows, **ids included**, inside one transaction. Keeping
the ids is what makes a restore a rewind rather than a merge, and it is why the
Postgres sequences are re-aligned afterwards, otherwise the next insert would
collide with a restored row.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, func, select
from sqlalchemy.orm import Session

from .database import Base
from .datareset import NEVER_ERASED
from .models import DataSnapshot, utcnow

# Named datasnapshots, not snapshots: routers/snapshots.py already owns that word
# for the weekly report snapshot, which is a different thing entirely.
logger = logging.getLogger("trt.datasnapshots")

# Keeping a name is not cosmetic: an administrator restoring one three weeks later
# has the date, the kind (manual/auto) and this to go on.
MAX_NAME = 120


def covered_tables() -> list:
    """The tables a snapshot carries, parents first (insert order)."""
    return [t for t in Base.metadata.sorted_tables if t.name not in NEVER_ERASED]


def _encode(value):
    """JSON-safe value, keeping enough to rebuild the Python one on restore."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _decode(column, value):
    """Back to the Python type the column expects.

    SQLite refuses an ISO string on a DateTime column, Postgres accepts it: coercing
    here keeps the restore identical on the test database and on production, which
    is the only way the tests below mean anything.
    """
    if value is None:
        return None
    kind = column.type
    if isinstance(kind, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(kind, Date) and isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(kind, Numeric) and isinstance(value, str):
        return Decimal(value)
    return value


def create(db: Session, name: str, *, kind: str = "manual", user_id: int | None = None) -> DataSnapshot:
    """Serialize the business tables into one stored, gzipped snapshot."""
    payload, counts = {}, {}
    for table in covered_tables():
        rows = [{c.name: _encode(r._mapping[c]) for c in table.columns}
                for r in db.execute(select(table)).all()]
        payload[table.name] = rows
        if rows:
            counts[table.name] = len(rows)
    blob = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    snap = DataSnapshot(
        name=(name or "").strip()[:MAX_NAME] or utcnow().strftime("%Y-%m-%d %H:%M"),
        kind=("auto" if kind == "auto" else "manual"),
        created_by_user_id=user_id,
        size_bytes=len(blob),
        row_counts=counts,
        payload=blob,
    )
    db.add(snap)
    db.flush()
    logger.info("snapshot %s (%s): %d tables, %d bytes", snap.id, snap.kind, len(counts), len(blob))
    return snap


def read_payload(snap: DataSnapshot) -> dict:
    """The stored rows, table by table."""
    return json.loads(gzip.decompress(snap.payload).decode("utf-8"))


def restore(db: Session, snap: DataSnapshot) -> dict[str, int]:
    """Put the data back exactly as it was: empty, rewrite, re-align the sequences.

    Runs in the caller's transaction. A table absent from the snapshot (added by a
    later migration) is still emptied: leaving rows that the restored state never
    knew about would be a merge, and a merge is not what "restore" means.
    """
    data = read_payload(snap)
    tables = covered_tables()
    # The snapshot store itself survives a restore and points at the accounts being
    # rewritten, so its links are cut before the wipe and put back afterwards: a
    # snapshot keeps its author whenever that account comes back with it.
    from .datareset import detach_external_refs, reattach
    saved = detach_external_refs(db, {t.name for t in tables})
    for table in reversed(tables):
        db.execute(table.delete())
    written: dict[str, int] = {}
    for table in tables:
        rows = data.get(table.name) or []
        if not rows:
            continue
        cols = {c.name: c for c in table.columns}
        prepared = [{k: _decode(cols[k], v) for k, v in row.items() if k in cols} for row in rows]
        db.execute(table.insert(), prepared)
        written[table.name] = len(prepared)
    reattach(db, saved)
    _resync_sequences(db, tables)
    logger.info("restore of snapshot %s: %s", snap.id, written)
    return written


def _resync_sequences(db: Session, tables) -> None:
    """Move each identity sequence past the restored ids (PostgreSQL only).

    Without this the next insert reuses an id a restored row already holds, and the
    restore looks fine until somebody creates a squad.
    """
    from sqlalchemy import text
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    for table in tables:
        for col in table.primary_key.columns:
            if not str(col.type).lower().startswith(("integer", "bigint")):
                continue
            db.execute(text(
                "SELECT setval(pg_get_serial_sequence(:t, :c), "
                "COALESCE((SELECT MAX(" + col.name + ") FROM " + table.name + "), 0) + 1, false)"
            ), {"t": table.name, "c": col.name})


def prune(db: Session, keep: int) -> int:
    """Drop the oldest AUTOMATIC snapshots past ``keep``. Manual ones are never
    pruned: somebody took them on purpose and only that somebody should remove them."""
    if keep <= 0:
        return 0
    rows = db.scalars(select(DataSnapshot).where(DataSnapshot.kind == "auto")
                      .order_by(DataSnapshot.created_at.desc())).all()
    doomed = rows[keep:]
    for snap in doomed:
        db.delete(snap)
    return len(doomed)


# --------------------------------------------------------------------------
# Automatic snapshots, driven by the hourly in-process scheduler
# --------------------------------------------------------------------------

SNAPSHOT_KEY = "snapshot_config"


def default_config() -> dict:
    """Off by default: taking copies of somebody's data is their decision."""
    return {"enabled": False, "interval_days": 7, "keep": 8}


def get_config(db: Session) -> dict:
    from .models import AppSetting
    cfg = default_config()
    row = db.get(AppSetting, SNAPSHOT_KEY)
    if row:
        try:
            stored = json.loads(row.value)
            cfg.update({k: v for k, v in stored.items() if k in cfg})
        except (json.JSONDecodeError, TypeError):
            pass
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["interval_days"] = max(1, int(cfg["interval_days"] or 1))
    cfg["keep"] = max(1, int(cfg["keep"] or 1))
    return cfg


def set_config(db: Session, patch: dict) -> dict:
    from .models import AppSetting
    cfg = get_config(db)
    for k in cfg:
        if k in (patch or {}):
            cfg[k] = patch[k]
    cfg = {**default_config(), **cfg}
    cfg["enabled"] = bool(cfg["enabled"])
    cfg["interval_days"] = max(1, int(cfg["interval_days"] or 1))
    cfg["keep"] = max(1, int(cfg["keep"] or 1))
    row = db.get(AppSetting, SNAPSHOT_KEY)
    payload = json.dumps(cfg)
    if row is None:
        db.add(AppSetting(key=SNAPSHOT_KEY, value=payload))
    else:
        row.value = payload
    return cfg


def run_due_snapshot(db: Session) -> dict | None:
    """Take the automatic snapshot if one is due, then prune. Called by the tick.

    Due is measured from the last automatic snapshot, not from a stored schedule:
    a restart, a clock change or a week of downtime cannot make one silently
    overdue for ever.
    """
    cfg = get_config(db)
    if not cfg["enabled"]:
        return None
    last = db.scalar(select(func.max(DataSnapshot.created_at)).where(DataSnapshot.kind == "auto"))
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=utcnow().tzinfo)
        if (utcnow() - last).total_seconds() < cfg["interval_days"] * 86400:
            return None
    snap = create(db, utcnow().strftime("Auto %Y-%m-%d %H:%M"), kind="auto")
    pruned = prune(db, cfg["keep"])
    db.commit()
    return {"id": snap.id, "pruned": pruned}
