"""OIDC integration via Authlib (Authorization Code + PKCE), configured at runtime."""
from authlib.integrations.starlette_client import OAuth


def discovery_url(issuer: str) -> str:
    """The provider's well-known document for an issuer URL.

    Split out of :func:`get_oauth` so it can be asserted on directly: Authlib
    keeps the value it was given on a private attribute, and a test that reaches
    for a private attribute breaks on the next release for no good reason.
    """
    return (issuer or "").rstrip("/") + "/.well-known/openid-configuration"


def get_oauth(cfg: dict) -> OAuth:
    """Build a fresh Authlib OAuth client from the (DB) auth config.

    A new client is created per flow so runtime config changes take effect without
    a restart. The provider is discovered from the issuer's well-known document,
    and ``code_challenge_method=S256`` enforces PKCE to protect the auth-code
    exchange against interception.
    """
    oauth = OAuth()
    oauth.register(
        name="oidc",
        client_id=cfg.get("oidc_client_id"),
        client_secret=cfg.get("oidc_client_secret"),
        server_metadata_url=discovery_url(cfg.get("oidc_issuer_url")),
        client_kwargs={"scope": cfg.get("oidc_scopes") or "openid email profile", "code_challenge_method": "S256"},
    )
    return oauth
