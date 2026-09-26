"""Process logging setup: human-readable text or GCP Cloud Logging JSON.

Two output shapes, selected by ``settings.log_format`` (env ``LOG_FORMAT``):

* ``text`` - classic ``<time> <LEVEL> <logger>: <message>`` lines for local dev.
* ``json`` - one structured JSON object per line in the shape Google Cloud
  Logging understands. On GKE the logging agent reads container stdout, parses
  each JSON line and maps ``severity`` / ``message`` / ``time`` (plus
  ``logging.googleapis.com/sourceLocation``) onto the LogEntry, so entries land
  with the correct level and searchable fields - no sidecar needed.

``configure_logging`` wires the application's own loggers; ``uvicorn_log_config``
returns the matching ``log_config`` for uvicorn's access/error loggers, so every
line the process emits shares one format.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging

# Python level name -> Cloud Logging severity. The names line up 1:1 for the
# levels we emit; the explicit map documents that and stays correct if levels change.
_SEVERITY = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
}

# Text format shared by the plain-text formatter and uvicorn's text log_config.
TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class CloudLoggingFormatter(logging.Formatter):
    """Render a ``LogRecord`` as a single-line Cloud Logging JSON entry."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            # Cloud Logging groups by message; keep the traceback attached to it.
            message = f"{message}\n{self.formatException(record.exc_info)}"
        entry = {
            "severity": _SEVERITY.get(record.levelname, "DEFAULT"),
            "message": message,
            "time": _dt.datetime.fromtimestamp(
                record.created, _dt.timezone.utc
            ).isoformat(),
            "logger": record.name,
            "logging.googleapis.com/sourceLocation": {
                "file": record.pathname,
                "line": str(record.lineno),
                "function": record.funcName,
            },
        }
        return json.dumps(entry, ensure_ascii=False)


def _build_handler(fmt: str) -> logging.Handler:
    """A stdout StreamHandler carrying the JSON or text formatter."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        CloudLoggingFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT)
    )
    return handler


def configure_logging(fmt: str = "text", level: str | int = "INFO") -> None:
    """Install the process-wide root handler (idempotent).

    ``fmt`` is ``"json"`` (Cloud Logging) or anything else (text). Existing root
    handlers - including any left by ``logging.basicConfig`` in an imported
    module - are removed first so a single handler emits each line exactly once.
    """
    from . import logbuffer

    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(_build_handler(fmt))
    # Keep recent records in memory for the Admin > Ops debug panel.
    logbuffer.install()


def uvicorn_log_config(fmt: str = "text", level: str = "INFO") -> dict:
    """Return a uvicorn ``log_config`` dict wiring its loggers to our format.

    Keeps uvicorn's ``uvicorn`` / ``uvicorn.error`` / ``uvicorn.access`` output in
    the same shape (JSON on GKE) as the application's logs.
    """
    formatter = (
        {"()": "app.logconfig.CloudLoggingFormatter"}
        if fmt == "json"
        else {"format": TEXT_FORMAT}
    )
    # A second handler feeds uvicorn's own loggers (which don't propagate to root)
    # into the in-memory ring buffer, so the Ops debug panel sees access/error lines
    # too. dictConfig instantiates it via the factory, returning our singleton.
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": formatter},
        "handlers": {
            "default": {"class": "logging.StreamHandler", "formatter": "default"},
            "ringbuffer": {"()": "app.logbuffer.ring_handler"},
        },
        "loggers": {
            "uvicorn": {"handlers": ["default", "ringbuffer"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["default", "ringbuffer"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["default", "ringbuffer"], "level": level, "propagate": False},
        },
        "root": {"handlers": ["default", "ringbuffer"], "level": level},
    }
