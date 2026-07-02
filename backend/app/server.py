"""Programmatic launcher: serve the app over HTTPS, with an optional plain-HTTP
listener that 301-redirects to HTTPS.

Replaces the bare ``uvicorn app.main:app`` CLI so we can:
  * ensure a certificate exists (self-signed by default) before binding TLS;
  * keep a handle on the live SSLContext so admin cert uploads hot-reload it;
  * run an HTTP->HTTPS redirect on a second port.

Run with:  python -m app.server
"""
from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from . import tls, tlsconfig
from .database import SessionLocal
from .main import app

log = logging.getLogger("trt.tls")

# Internal container ports (map them in docker-compose).
HTTPS_PORT = int(os.environ.get("HTTPS_PORT", "8443"))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8080"))
HOST = os.environ.get("BIND_HOST", "0.0.0.0")

# Public HTTPS port used when building redirect URLs (the host-side mapped port).
PUBLIC_HTTPS_PORT = int(os.environ.get("PUBLIC_HTTPS_PORT", str(HTTPS_PORT)))


def _make_redirect_app(public_https_port: int):
    """Minimal ASGI app: 301 every plain-HTTP request to the HTTPS origin."""

    async def redirect_app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        headers = dict(scope.get("headers") or [])
        host = headers.get(b"host", b"localhost").decode().split(":")[0]
        port_suffix = "" if public_https_port == 443 else f":{public_https_port}"
        path = scope.get("path", "/")
        qs = scope.get("query_string", b"").decode()
        location = f"https://{host}{port_suffix}{path}" + (f"?{qs}" if qs else "")
        await send({
            "type": "http.response.start",
            "status": 301,
            "headers": [(b"location", location.encode()), (b"content-length", b"0")],
        })
        await send({"type": "http.response.body", "body": b""})

    return redirect_app


async def _amain() -> None:
    # 1) Ensure a certificate exists and is written to disk (self-signed default).
    db = SessionLocal()
    try:
        st = tlsconfig.ensure_materialized(db)
        redirect_http = tlsconfig.redirect_http_enabled(db)
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
    https_server = uvicorn.Server(https_cfg)

    servers = [https_server.serve()]

    # 3) Optional HTTP -> HTTPS redirect listener.
    if redirect_http:
        http_cfg = uvicorn.Config(
            _make_redirect_app(PUBLIC_HTTPS_PORT),
            host=HOST,
            port=HTTP_PORT,
            proxy_headers=True,
            forwarded_allow_ips="*",
            log_level="warning",
        )
        http_server = uvicorn.Server(http_cfg)
        servers.append(http_server.serve())
        log.info("HTTP->HTTPS redirect on :%s -> https://<host>:%s", HTTP_PORT, PUBLIC_HTTPS_PORT)

    await asyncio.gather(*servers)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
