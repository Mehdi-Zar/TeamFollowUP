"""Tests for the logging configuration (text vs GCP Cloud Logging JSON)."""
import json
import logging

from app.logconfig import (
    CloudLoggingFormatter,
    configure_logging,
    uvicorn_log_config,
)


def _record(level=logging.INFO, msg="hello %s", args=("world",), name="trt.test"):
    return logging.LogRecord(
        name=name, level=level, pathname="/app/x.py", lineno=42,
        msg=msg, args=args, exc_info=None, func="do_it",
    )


def test_json_formatter_shape():
    """A record renders as one JSON line with Cloud Logging's key fields."""
    line = CloudLoggingFormatter().format(_record(logging.WARNING))
    entry = json.loads(line)  # must be valid JSON
    assert entry["severity"] == "WARNING"
    assert entry["message"] == "hello world"          # args interpolated
    assert entry["logger"] == "trt.test"
    assert "T" in entry["time"]                        # ISO-8601 timestamp
    loc = entry["logging.googleapis.com/sourceLocation"]
    assert loc["file"] == "/app/x.py" and loc["line"] == "42" and loc["function"] == "do_it"


def test_json_severity_mapping():
    """Python level names map onto Cloud Logging severities."""
    for level, sev in [
        (logging.DEBUG, "DEBUG"), (logging.INFO, "INFO"),
        (logging.WARNING, "WARNING"), (logging.ERROR, "ERROR"),
        (logging.CRITICAL, "CRITICAL"),
    ]:
        entry = json.loads(CloudLoggingFormatter().format(_record(level)))
        assert entry["severity"] == sev


def test_json_formatter_includes_exception():
    """An exc_info record keeps the traceback attached to the message."""
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        rec = _record(logging.ERROR, msg="failed", args=())
        rec.exc_info = sys.exc_info()
    entry = json.loads(CloudLoggingFormatter().format(rec))
    assert entry["message"].startswith("failed\n")
    assert "ValueError: boom" in entry["message"]


def test_configure_logging_json_installs_single_stream_handler():
    """configure_logging('json') leaves exactly one JSON stdout handler on the root.

    A second, non-emitting handler (the Ops debug ring buffer) is also attached; it
    does not write to stdout, so stdout lines are still emitted exactly once.
    """
    from app.logbuffer import RingBufferHandler
    configure_logging("json", "INFO")
    root = logging.getLogger()
    try:
        streams = [h for h in root.handlers
                   if isinstance(h, logging.StreamHandler) and not isinstance(h, RingBufferHandler)]
        assert len(streams) == 1
        assert isinstance(streams[0].formatter, CloudLoggingFormatter)
        # exactly one ring buffer, never duplicated across repeated configure calls
        assert sum(isinstance(h, RingBufferHandler) for h in root.handlers) == 1
    finally:
        configure_logging("text", "INFO")  # restore for other tests


def test_uvicorn_log_config_selects_formatter():
    """uvicorn_log_config points uvicorn's loggers at the right formatter, and also
    feeds them into the ring buffer for the Ops debug panel."""
    j = uvicorn_log_config("json")
    assert j["formatters"]["default"]["()"] == "app.logconfig.CloudLoggingFormatter"
    for lg in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        assert j["loggers"][lg]["handlers"] == ["default", "ringbuffer"]
    assert j["handlers"]["ringbuffer"]["()"] == "app.logbuffer.ring_handler"

    t = uvicorn_log_config("text")
    assert "format" in t["formatters"]["default"]
