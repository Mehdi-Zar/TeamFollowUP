"""OIDC integration via Authlib (Authorization Code + PKCE), configured at runtime."""
import re

from authlib.integrations.starlette_client import OAuth

from . import trust

DEFAULT_SCOPES = "openid email profile"


def discovery_url(issuer: str) -> str:
    """The provider's well-known document for an issuer URL.

    Split out of :func:`get_oauth` so it can be asserted on directly: Authlib
    keeps the value it was given on a private attribute, and a test that reaches
    for a private attribute breaks on the next release for no good reason.
    """
    return (issuer or "").rstrip("/") + "/.well-known/openid-configuration"


def scope_string(raw: str | None) -> str:
    """The scope parameter to send, from whatever was typed in the config field.

    OAuth separates scopes with single spaces. The field is filled by hand, so it
    also collects commas, line breaks and the non breaking spaces a word
    processor leaves in a copied string. Any of those makes the whole list read
    as one unknown scope, and the IdP answers ``invalid_scope``, which looks
    exactly like the scopes being refused: the wrong diagnosis, on a value that
    was correct. Splitting on every plausible separator removes that trap.

    An empty result falls back to the default set rather than sending no scope at
    all, which would not even be an OIDC request.
    """
    tokens = [t for t in re.split(r"[\s,;]+", (raw or "").strip()) if t]
    return " ".join(tokens) or DEFAULT_SCOPES


def get_oauth(cfg: dict) -> OAuth:
    """Build a fresh Authlib OAuth client from the (DB) auth config.

    A new client is created per flow so runtime config changes take effect without
    a restart. The provider is discovered from the issuer's well-known document,
    and ``code_challenge_method=S256`` enforces PKCE to protect the auth-code
    exchange against interception.

    ``verify`` carries the admin-managed trust store. Authlib routes all three
    outbound fetches (discovery document, JWKS, token exchange) through this one
    client, so a single context covers the whole flow; without it an IdP issued
    by an internal authority fails at discovery with a self-signed error, and the
    only fix would be filesystem access to the container.
    """
    oauth = OAuth()
    oauth.register(
        name="oidc",
        client_id=cfg.get("oidc_client_id"),
        client_secret=cfg.get("oidc_client_secret"),
        server_metadata_url=discovery_url(cfg.get("oidc_issuer_url")),
        client_kwargs={
            "scope": scope_string(cfg.get("oidc_scopes")),
            "code_challenge_method": "S256",
            "verify": trust.context(),
        },
    )
    return oauth
