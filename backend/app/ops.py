"""Operational runtime info + self-restart, for the Admin > Ops panel.

The app binds its listener (HTTP vs in-app TLS on a fixed port) at boot, so changes
like the TLS toggle only take effect on the next start. Rather than asking an admin
to shell in and run ``docker compose up -d`` / roll the pod, the Ops panel exposes a
"restart" button. In a container/orchestrated deployment the standard, safe way to
"restart from inside" is simply to exit the process and let the supervisor bring it
back: Docker (``restart: unless-stopped``) and Kubernetes (Deployment
``restartPolicy: Always``) both re-create the container automatically.

``request_restart`` therefore raises SIGTERM on our own PID after flushing the HTTP
response; uvicorn traps it, drains in-flight requests and exits cleanly, and the
orchestrator restarts us with the new configuration applied. When no supervisor is
present (a bare ``python -m app.server``) the process would just stop, so the status
reports ``auto_restart`` and the UI warns accordingly.
"""
from __future__ import annotations

import os
import platform
import signal
import socket
import threading
import time

from sqlalchemy.orm import Session

# Process start time, captured at import (module load ~= process start) for uptime.
_START = time.time()

# Surfaced in the Ops panel. Override via env at build/deploy time.
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")


def detect_orchestrator() -> str:
    """Best-effort guess at what supervises this process, which decides whether a
    self-exit results in an automatic restart.

    - "kubernetes": the injected ``KUBERNETES_SERVICE_HOST`` env is present.
    - "docker": running inside a container (``/.dockerenv`` or the ``container`` env).
    - "process": a bare process with no supervisor - exiting would NOT auto-restart.
    """
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        return "kubernetes"
    if os.path.exists("/.dockerenv") or os.environ.get("container"):
        return "docker"
    return "process"


def _git_sha() -> str | None:
    """Deployed commit, if the build/deploy injected one (several common env names)."""
    for key in ("GIT_SHA", "GIT_COMMIT", "SOURCE_COMMIT", "COMMIT_SHA", "VCS_REF"):
        v = os.environ.get(key)
        if v:
            return v[:12]
    return None


def runtime_status(db: Session) -> dict:
    """Read-only diagnostics for the Ops panel (identity, uptime, serving mode).

    Includes the TLS effective-vs-running mismatch so the panel can flag that a
    restart is needed to apply a pending change.
    """
    from . import tlsconfig  # lazy: avoids import cycle at module load

    tls = tlsconfig.status(db)
    orchestrator = detect_orchestrator()
    return {
        "version": APP_VERSION,
        "git_sha": _git_sha(),
        "hostname": socket.gethostname(),           # pod name in k8s / container id in Docker
        "pid": os.getpid(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "orchestrator": orchestrator,
        "auto_restart": orchestrator in ("kubernetes", "docker"),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_START)),
        "uptime_seconds": int(time.time() - _START),
        # TLS serving mode: effective preference vs what the live process bound at boot.
        "tls_enabled": tls.get("tls_enabled"),
        "tls_running": tls.get("tls_running"),
        "restart_pending": tls.get("tls_enabled") != tls.get("tls_running"),
    }


def request_restart(delay: float = 0.5) -> dict:
    """Schedule a graceful process restart shortly after the caller responds.

    Sends SIGTERM to our own PID after ``delay`` seconds (enough to flush the HTTP
    response); uvicorn drains and exits, and the orchestrator restarts the container.
    Set ``OPS_DISABLE_RESTART=1`` to make this a no-op (used by tests, and any
    environment where a self-restart must never fire).
    """
    orchestrator = detect_orchestrator()
    result = {
        "scheduled": False,
        "orchestrator": orchestrator,
        "auto_restart": orchestrator in ("kubernetes", "docker"),
    }
    if os.environ.get("OPS_DISABLE_RESTART") == "1":
        result["reason"] = "disabled"
        return result

    def _stop() -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Timer(max(0.0, delay), _stop).start()
    result["scheduled"] = True
    return result
