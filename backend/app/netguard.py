"""Outbound requests the admin configures (IdP discovery, JWKS, metadata): only
http(s), and never the link-local range where cloud metadata services answer
(169.254.169.254 hands out the instance's credentials). Checked on every
request, redirects included.

Loopback and private addresses stay allowed: a local or in-cluster IdP is a
normal setup (the SSO bench runs Keycloak on localhost).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

_BLOCKED = [ipaddress.ip_network("169.254.0.0/16"), ipaddress.ip_network("fe80::/10"),
            ipaddress.ip_network("0.0.0.0/32"), ipaddress.ip_network("::/128")]


class BlockedURL(ValueError):
    """The URL points somewhere the app must not fetch."""


def check_outbound_url(url: str) -> None:
    """Raise BlockedURL unless ``url`` is http(s) to a host outside the blocked
    ranges (the host is resolved: a name pointing at the metadata IP is refused)."""
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BlockedURL(f"URL refusée (http ou https attendu) : {url}")
    host = parts.hostname
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
        addrs = {i[4][0] for i in infos}
    except socket.gaierror:
        return  # unresolvable: the request itself will fail with a clear error
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%", 1)[0])
        if any(ip in net for net in _BLOCKED):
            raise BlockedURL(f"URL refusée (adresse réservée) : {url}")


def guarded_client(**kwargs):
    """An httpx.Client that checks every outgoing request, redirects included."""
    import httpx

    def _hook(request):
        check_outbound_url(str(request.url))

    hooks = kwargs.pop("event_hooks", {}) or {}
    hooks.setdefault("request", []).append(_hook)
    return httpx.Client(event_hooks=hooks, **kwargs)
