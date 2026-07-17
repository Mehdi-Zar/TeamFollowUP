"""Programmatic launcher: serve the app on a single port, in one of two modes.

Replaces the bare ``uvicorn app.main:app`` CLI so we can:
  * pick the serving mode from configuration (``TLS_ENABLED``);
  * when the app terminates TLS itself, ensure a certificate exists (self-signed
    by default) before binding, and keep a handle on the live SSLContext so admin
    cert uploads hot-reload it.

Two modes:
  * ``TLS_ENABLED=false`` (supported GKE model): serve plain HTTP on
    ``HTTP_PORT`` (default 8000); the Gateway API + ALB terminate TLS upstream.
  * ``TLS_ENABLED=true`` (default, local/standalone): terminate TLS in-process on
    ``HTTPS_PORT`` (default 8443).

HTTP->HTTPS redirection is always an infrastructure concern, never the app's.

Run with:  python -m app.server
"""
from __future__ import annotations

import logging
import os

import uvicorn

from . import tls, tlsconfig
from .config import settings
from .database import SessionLocal
from .logconfig import configure_logging, uvicorn_log_config
from .main import app

log = logging.getLogger("trt.tls")

# Internal container port (map it in docker-compose).
HTTPS_PORT = int(os.environ.get("HTTPS_PORT", "8443"))
HOST = os.environ.get("BIND_HOST", "0.0.0.0")

# HTTP keep-alive timeout (seconds). MUST stay ABOVE the fronting load
# balancer's backend idle timeout, otherwise the LB can dispatch a request on a
# pooled connection that uvicorn has just closed -> the backend RSTs it and the
# proxy surfaces "reset reason: connection termination". Google Cloud
# Application LBs (incl. the S3NS internal ALB) default to 600s, so we sit
# safely above it. Override via env if your LB uses a different idle timeout.
KEEPALIVE_TIMEOUT = int(os.environ.get("KEEPALIVE_TIMEOUT", "620"))


def main() -> None:
    """Entry point: materialize the TLS cert, then run the HTTPS uvicorn server.

    Order matters — the certificate must exist on disk before uvicorn builds its
    SSLContext. After ``load()`` we hand the live SSLContext to ``tls`` so an admin
    certificate upload can swap it in place without restarting the process.
    """
    configure_logging(settings.log_format, settings.log_level)
    log_cfg = uvicorn_log_config(settings.log_format, settings.log_level)

    # Infra-terminated TLS (the supported GKE model): serve plain HTTP and let the
    # Gateway API + ALB do TLS. No certificate is materialised. proxy_headers +
    # forwarded_allow_ips let the app trust the ALB's X-Forwarded-Proto so it still
    # sees the original request as https (correct redirect URLs, secure cookies).
    if not settings.tls_enabled:
        log.info("TLS disabled: serving plain HTTP on :%s (TLS terminated upstream by the infrastructure).",
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
        return

    # 1) Ensure a certificate exists and is written to disk (self-signed default).
    db = SessionLocal()
    try:
        st = tlsconfig.ensure_materialized(db)
    finally:
        db.close()
    log.info("TLS ready: mode=%s, subject=%s", st.get("mode"),
             (st.get("active") or {}).get("subject"))

    # 2) HTTPS server. uvicorn builds the SSLContext from these files; we grab it
    #    afterwards so certificate uploads can hot-reload it in place.
    https_cfg = uvicorn.Config(
        app,
        host=HOST,
        port=HTTPS_PORT,
        proxy_headers=True,
        forwarded_allow_ips="*",
        timeout_keep_alive=KEEPALIVE_TIMEOUT,
        ssl_certfile=tls.FULLCHAIN_PATH,
        ssl_keyfile=tls.KEY_PATH,
        log_config=log_cfg,
    )
    https_cfg.load()  # builds https_cfg.ssl
    if https_cfg.ssl is not None:
        tls.set_live_context(https_cfg.ssl)
    uvicorn.Server(https_cfg).run()


if __name__ == "__main__":
    main()
