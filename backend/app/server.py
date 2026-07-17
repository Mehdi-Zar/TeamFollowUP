"""Programmatic launcher: serve the app over HTTPS on a single port.

Replaces the bare ``uvicorn app.main:app`` CLI so we can:
  * ensure a certificate exists (self-signed by default) before binding TLS;
  * keep a handle on the live SSLContext so admin cert uploads hot-reload it.

The app exposes exactly one port (HTTPS :8443). HTTP->HTTPS redirection is an
infrastructure concern, handled upstream (e.g. the GKE Gateway API redirect
route) - never by the app itself.

Run with:  python -m app.server
"""
from __future__ import annotations

import logging
import os

import uvicorn

from . import tls, tlsconfig
from .database import SessionLocal
from .main import app

log = logging.getLogger("trt.tls")

# Internal container port (map it in docker-compose).
HTTPS_PORT = int(os.environ.get("HTTPS_PORT", "8443"))
HOST = os.environ.get("BIND_HOST", "0.0.0.0")


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

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
        ssl_certfile=tls.FULLCHAIN_PATH,
        ssl_keyfile=tls.KEY_PATH,
    )
    https_cfg.load()  # builds https_cfg.ssl
    if https_cfg.ssl is not None:
        tls.set_live_context(https_cfg.ssl)
    uvicorn.Server(https_cfg).run()


if __name__ == "__main__":
    main()
