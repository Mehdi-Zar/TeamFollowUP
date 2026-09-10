"""Programmatic launcher: serve the app on a single plain-HTTP port.

Replaces the bare ``uvicorn app.main:app`` CLI so the log configuration (JSON or
text, plus a level persisted from Admin > Ops) is applied before the first line
is emitted, and so the keep-alive timeout below is set in one place.

The application never terminates TLS: an ALB, a Gateway or any reverse proxy
does it in front of the container, which then speaks HTTP on ``HTTP_PORT``
(default 8000). See ADR 0013. ``proxy_headers`` + ``forwarded_allow_ips`` make
the app trust the proxy's ``X-Forwarded-Proto`` / ``-Host``, so it still sees the
original request as https and builds correct redirect and callback URLs.
HTTP->HTTPS redirection is an infrastructure concern too, never the app's.

Run with:  python -m app.server
"""
from __future__ import annotations

import logging
import os

import uvicorn

from .config import settings
from .database import SessionLocal
from .logconfig import configure_logging, uvicorn_log_config
from .main import app

log = logging.getLogger("trt.server")

HOST = os.environ.get("BIND_HOST", "0.0.0.0")

# HTTP keep-alive timeout (seconds). MUST stay ABOVE the fronting load
# balancer's backend idle timeout, otherwise the LB can dispatch a request on a
# pooled connection that uvicorn has just closed -> the backend RSTs it and the
# proxy surfaces "reset reason: connection termination". Google Cloud
# Application LBs (incl. the S3NS internal ALB) default to 600s, so we sit
# safely above it. Override via env if your LB uses a different idle timeout.
KEEPALIVE_TIMEOUT = int(os.environ.get("KEEPALIVE_TIMEOUT", "620"))


def main() -> None:
    """Entry point: configure logging, then run the HTTP uvicorn server."""
    configure_logging(settings.log_format, settings.log_level)
    # A runtime log-level override set from Admin > Ops is persisted in the DB and
    # re-applied here so it survives restarts; otherwise the env default stands.
    from . import logbuffer
    db = SessionLocal()
    try:
        persisted = logbuffer.persisted_level(db)
    finally:
        db.close()
    effective_level = persisted or settings.log_level
    if persisted:
        logbuffer.set_live_level(persisted)
    log_cfg = uvicorn_log_config(settings.log_format, effective_level)

    log.info("Serving plain HTTP on :%s (TLS is terminated upstream by the infrastructure).",
             settings.http_port)
    http_cfg = uvicorn.Config(
        app,
        host=HOST,
        port=settings.http_port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        timeout_keep_alive=KEEPALIVE_TIMEOUT,
        log_config=log_cfg,
    )
    uvicorn.Server(http_cfg).run()


if __name__ == "__main__":
    main()
