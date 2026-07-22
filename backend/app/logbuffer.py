"""In-memory ring buffer of recent log records, for the Admin > Ops debug panel.

In a container/Kubernetes deployment the process logs to stdout, which the
orchestrator captures - unreadable from inside the app. To let an admin *see* and
*download* recent logs (and flip the level to DEBUG to reproduce an issue) without
shelling into the pod, we keep the last N records in a bounded, thread-safe deque
via a logging handler attached to the root and uvicorn loggers.

The handler accepts everything (level DEBUG); what actually reaches it is gated by
the emitting logger's level, so raising the level to DEBUG at runtime
(``set_live_level``) is what surfaces debug lines. The chosen level can be persisted
(``persist_level``) so it survives a restart.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from threading import Lock

# How many recent records to retain. ~2000 lines is plenty to debug an incident
# while staying small in memory (a few MB at most).
CAPACITY = 2000

# Levels offered in the UI, low -> high. CRITICAL is included for completeness.
LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_LEVEL_NO = {name: getattr(logging, name) for name in LEVELS}

# DB key under which the runtime level override is persisted (AppSetting).
_DB_KEY = "log_level"

_buffer: deque[dict] = deque(maxlen=CAPACITY)
_lock = Lock()
_exc_formatter = logging.Formatter()


class RingBufferHandler(logging.Handler):
    """A logging handler that appends each record to the module ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                message = f"{message}\n{_exc_formatter.formatException(record.exc_info)}"
            entry = {
                "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
            with _lock:
                _buffer.append(entry)
        except Exception:  # never let logging raise
            self.handleError(record)


_handler: RingBufferHandler | None = None


def ring_handler() -> RingBufferHandler:
    """Return the singleton handler (used both directly and as a dictConfig factory
    from ``uvicorn_log_config`` so uvicorn's own loggers feed the same buffer)."""
    global _handler
    if _handler is None:
        _handler = RingBufferHandler()
        _handler.setLevel(logging.DEBUG)  # capture everything the loggers let through
    return _handler


def install() -> RingBufferHandler:
    """Attach the ring handler to the root logger (idempotent)."""
    h = ring_handler()
    root = logging.getLogger()
    if h not in root.handlers:
        root.addHandler(h)
    return h


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def records(limit: int = 500, min_level: str | None = None) -> list[dict]:
    """Most recent records (oldest first), optionally filtered to ``min_level`` and up."""
    with _lock:
        items = list(_buffer)
    if min_level:
        threshold = _LEVEL_NO.get(min_level.upper(), logging.NOTSET)
        items = [e for e in items if _LEVEL_NO.get(e["level"], logging.INFO) >= threshold]
    if limit and limit > 0:
        items = items[-limit:]
    return items


def as_text(items: list[dict]) -> str:
    """Render records as aligned, human-readable log lines."""
    return "".join(
        f"{e['time']} {e['level']:<8} {e['logger']}: {e['message']}\n" for e in items
    )


def as_ndjson(items: list[dict]) -> str:
    """Render records as newline-delimited JSON (one object per line)."""
    return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in items)


def stats() -> dict:
    """Buffer size + capacity, for the UI header."""
    with _lock:
        return {"count": len(_buffer), "capacity": CAPACITY}


# --------------------------------------------------------------------------- #
# Level control (live + persisted)
# --------------------------------------------------------------------------- #
def current_level() -> str:
    """The effective root logger level name."""
    return logging.getLevelName(logging.getLogger().level)


def set_live_level(level: str) -> str:
    """Set the root + uvicorn logger levels immediately. Returns the applied name."""
    name = (level or "").upper()
    if name not in _LEVEL_NO:
        raise ValueError(f"Niveau de log invalide: {level}")
    logging.getLogger().setLevel(name)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).setLevel(name)
    return current_level()


def clear() -> None:
    """Empty the buffer (handy: clear, reproduce the issue, then read/download)."""
    with _lock:
        _buffer.clear()


def persisted_level(db) -> str | None:
    """The admin-set level override stored in the DB, if any (applied at boot)."""
    from .models import AppSetting
    row = db.get(AppSetting, _DB_KEY)
    return row.value if row else None


def persist_level(db, level: str) -> None:
    """Persist the level override so it is re-applied on the next server start."""
    from .models import AppSetting
    name = (level or "").upper()
    if name not in _LEVEL_NO:
        raise ValueError(f"Niveau de log invalide: {level}")
    row = db.get(AppSetting, _DB_KEY)
    if row is None:
        db.add(AppSetting(key=_DB_KEY, value=name))
    else:
        row.value = name
    db.commit()
