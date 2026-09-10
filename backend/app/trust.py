"""Outbound TLS trust: what the application accepts when it *calls* something.

The application does not serve TLS at all: an infrastructure component terminates
it in front of the container (ADR 0013). It still *calls* an internal IdP, an
internal SMTP relay and a log sink, and those endpoints are routinely issued by a
private authority no public trust store knows about. This module is what makes
them reachable.

The CA store administrators fill from Administration is materialised here into a
bundle (the public roots plus the imported authorities) that every outbound call
verifies against:

  * explicitly through :func:`context`, wherever we build the client ourselves
    (OIDC, SAML metadata, SMTP, the SSO connectivity test);
  * implicitly through ``SSL_CERT_FILE``, for libraries whose HTTP client we do
    not build (google-auth in ``logexport``).

Nothing here can disable verification. Importing the authority is the supported
way to reach a privately issued endpoint; switching verification off is not.
"""
from __future__ import annotations

import logging
import os
import ssl
import threading

import certifi

log = logging.getLogger("trt.tls")

# The trust source in effect *before* we take over, captured once at import time.
# A bundle supplied at deploy time (SSL_CERT_FILE baked into the image, or the
# Kubernetes bench appending to certifi) therefore composes with the admin store
# instead of being silently replaced by it, and repeated applies never chain.
BASE_CA_FILE = os.environ.get("SSL_CERT_FILE") or certifi.where()

# A scratch file under CERT_DIR: the database is the source of truth, this is only
# what the SSL layer reads. Module-level so tests can point it somewhere temporary.
_CERT_DIR = os.environ.get("CERT_DIR") or os.path.join(os.path.dirname(__file__), "..", "certs")
BUNDLE_PATH = os.path.abspath(os.path.join(_CERT_DIR, "trust_bundle.pem"))

_lock = threading.Lock()
_context: ssl.SSLContext | None = None


def _cafile() -> str:
    """The file outbound verification reads: the merged bundle once it has been
    written, the base store until then (tests, or before the boot hook runs)."""
    return BUNDLE_PATH if os.path.exists(BUNDLE_PATH) else BASE_CA_FILE


def context() -> ssl.SSLContext:
    """Verification context for outbound TLS, cached until the store changes.

    A bundle that cannot be loaded falls back to the base store rather than
    breaking every outbound call: the SSO test then reports the real failure
    against the IdP instead of the whole app losing its ability to talk out.
    """
    global _context
    with _lock:
        if _context is None:
            cafile = _cafile()
            try:
                _context = ssl.create_default_context(cafile=cafile)
            except Exception as exc:
                log.error("Trust bundle %s is unusable (%s); falling back to %s.",
                          cafile, exc, BASE_CA_FILE)
                _context = ssl.create_default_context(cafile=BASE_CA_FILE)
        return _context


def apply(ca_pems: list[str]) -> str:
    """Merge the admin CA store into the base trust store and make it effective.

    Writes the bundle, points ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE`` at it for
    third-party clients, and drops the cached context. Takes effect immediately,
    without a restart: the next outbound call rebuilds its context from the new
    bundle. Returns the bundle path.
    """
    global _context
    extra = [p.strip() for p in ca_pems if p and p.strip()]
    with open(BASE_CA_FILE, "r", encoding="utf-8") as fh:
        parts = [fh.read().strip()]
    parts.extend(extra)
    os.makedirs(os.path.dirname(BUNDLE_PATH), exist_ok=True)
    with open(BUNDLE_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")
    # Libraries we do not hand a context to read these at connection time, so the
    # value only has to be set before the call, not before the process starts.
    os.environ["SSL_CERT_FILE"] = BUNDLE_PATH
    os.environ["REQUESTS_CA_BUNDLE"] = BUNDLE_PATH
    with _lock:
        _context = None
    log.info("Outbound trust bundle written to %s (%d added authority/ies).",
             BUNDLE_PATH, len(extra))
    return BUNDLE_PATH
