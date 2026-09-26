"""Prometheus metrics: what the app exposes about itself.

Until now the only operational signals were logs and the audit trail, which
answer "what happened" but never "is it happening more than usual". This module
adds the missing half: counters and histograms scraped over HTTP, so latency,
error rate, saturation and the scheduler's health can be graphed and alerted on
(see ``ops/prometheus/`` for a ready-made scrape config and alert rules).

Three design points worth knowing before adding a metric here:

* **The route label is the route TEMPLATE**, never the raw path. ``/api/squads/12``
  and ``/api/squads/13`` must both be ``/api/squads/{squad_id}``, otherwise every
  identifier in the system becomes a distinct time series and the scrape target
  eventually takes Prometheus down with it. Starlette fills ``scope["route"]``
  during routing, so the label can only be read *after* the request is handled;
  requests that matched nothing are collapsed into ``unmatched`` for the same
  reason.
* **Scraping must not touch the database.** A scrape happens every 15 seconds
  forever; anything it queries becomes a permanent load floor. The gauges below
  are read from process state only, and the pool collector reads counters the
  pool already keeps in memory.
* **The endpoint is not public.** It exposes the shape of the traffic (which
  routes exist, how often they are called, how many 5xx), which is not something
  to hand to the internet. See :func:`metrics_response`.
"""
from __future__ import annotations

import hmac
import time

from prometheus_client import (CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge, Histogram,
                               generate_latest)
from prometheus_client.core import GaugeMetricFamily
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import settings

# Path the metrics themselves are served on: excluded from instrumentation so the
# scraper does not show up as the busiest client of the app.
METRICS_PATH = "/metrics"

# Buckets tuned for this app rather than the library default: most endpoints are
# small JSON reads (tens of ms), while the PPTX/HTML exports legitimately take
# seconds. The default buckets stop at 10s and would hide an export going bad.
_LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

http_requests_total = Counter(
    "teamfollowup_http_requests_total",
    "HTTP requests handled, by route template, method and status class.",
    ["method", "route", "status"],
)
http_request_duration_seconds = Histogram(
    "teamfollowup_http_request_duration_seconds",
    "Time to handle an HTTP request, in seconds.",
    ["method", "route"],
    buckets=_LATENCY_BUCKETS,
)
http_requests_in_flight = Gauge(
    "teamfollowup_http_requests_in_flight",
    "HTTP requests currently being handled.",
)
logins_total = Counter(
    "teamfollowup_logins_total",
    "Local password login attempts, by outcome (success, failure, throttled).",
    ["outcome"],
)
scheduler_runs_total = Counter(
    "teamfollowup_scheduler_runs_total",
    "Weekly-report scheduler ticks, by outcome (ok, skipped_not_leader, error).",
    ["outcome"],
)
scheduler_last_success_timestamp = Gauge(
    "teamfollowup_scheduler_last_success_timestamp_seconds",
    "Unix time of the last scheduler tick that completed without error. "
    "0 means it has not completed one since this process started.",
)
build_info = Gauge(
    "teamfollowup_build_info",
    "Always 1. The labels carry the version, so a deploy is visible as a change "
    "of series rather than a jump in a value.",
    ["version", "app_name"],
)


class _PoolCollector:
    """Expose the SQLAlchemy connection pool without querying anything.

    Saturation of the pool is the failure mode that turns a slow query into a
    site-wide outage: every request then waits for a connection, and the symptom
    (everything is slow) says nothing about the cause. The pool keeps these
    counters in memory, so reading them costs nothing.
    """

    def collect(self):
        try:
            from .database import engine
            pool = engine.pool
            out = []

            def gauge(name, doc, value):
                g = GaugeMetricFamily(name, doc)
                g.add_metric([], float(value))
                out.append(g)

            # size() is the configured steady-state size, NOT the number of
            # connections currently held. Reporting the latter as "size" would
            # make a saturation ratio look healthy exactly when it is not.
            if hasattr(pool, "size"):
                gauge("teamfollowup_db_pool_capacity",
                      "Configured steady-state size of the connection pool.", pool.size())
            gauge("teamfollowup_db_pool_in_use",
                  "Connections checked out of the pool right now.", pool.checkedout())
            if hasattr(pool, "checkedin"):
                gauge("teamfollowup_db_pool_available",
                      "Connections sitting idle in the pool, ready to be handed out.",
                      pool.checkedin())
            if hasattr(pool, "overflow"):
                # Positive means the pool ran out and is opening extra connections:
                # the clearest single signal that the database is the bottleneck.
                gauge("teamfollowup_db_pool_overflow",
                      "Connections opened beyond the configured size "
                      "(negative = that much headroom left).", pool.overflow())
            return out
        except Exception:
            # A metrics endpoint must never be the reason a page fails to load,
            # and pool internals differ between backends (SQLite in tests).
            return []


_pool_collector_registered = False


def init_metrics() -> None:
    """Register the collectors that need the app to exist. Idempotent.

    Idempotence matters because the test suite builds the app more than once in a
    process, and prometheus_client raises on a duplicate registration.
    """
    global _pool_collector_registered
    build_info.labels(version=_app_version(), app_name=settings.app_name).set(1)
    if not _pool_collector_registered:
        REGISTRY.register(_PoolCollector())
        _pool_collector_registered = True


def _app_version() -> str:
    from .ops import APP_VERSION
    return APP_VERSION


def _route_label(scope: Scope) -> str:
    """The matched route template, or ``unmatched`` - never the raw path."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    if not path:
        return "unmatched"
    return str(path)


class MetricsMiddleware:
    """Pure-ASGI timing middleware.

    Deliberately not a ``BaseHTTPMiddleware``: that class buffers the response
    through a queue, which breaks (or at best silently changes) the streaming of
    the PPTX/HTML exports and the static file responses. Here nothing touches the
    body - only the start-of-response message is observed, for its status code.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == METRICS_PATH:
            await self.app(scope, receive, send)
            return

        status_holder = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = int(message["status"])
            await send(message)

        method = scope.get("method", "GET")
        started = time.perf_counter()
        http_requests_in_flight.inc()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # An unhandled exception still produced a 500 for the client, so it
            # must be counted as one before the error propagates.
            status_holder["code"] = 500
            raise
        finally:
            http_requests_in_flight.dec()
            route = _route_label(scope)
            elapsed = time.perf_counter() - started
            http_request_duration_seconds.labels(method=method, route=route).observe(elapsed)
            http_requests_total.labels(method=method, route=route,
                                       status=str(status_holder["code"])).inc()


def metrics_authorized(authorization: str | None) -> bool:
    """Whether a scrape carrying this Authorization header may read the metrics.

    With ``METRICS_TOKEN`` empty the endpoint is open, which is the right default
    for a cluster-internal scrape and the wrong one for anything reachable from
    outside: the deployment guide says to keep ``/metrics`` off the public route,
    and the app logs a warning at boot when it looks like production. Set the
    token and the scraper must present it as a bearer, which every Prometheus
    supports (``authorization.credentials`` in the scrape config).
    """
    token = (settings.metrics_token or "").strip()
    if not token:
        return True
    if not authorization:
        return False
    scheme, _, presented = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(presented.strip(), token)


def render() -> tuple[bytes, str]:
    """The exposition payload and its content type."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
