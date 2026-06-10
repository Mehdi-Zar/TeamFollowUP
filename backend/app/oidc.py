"""OIDC integration via Authlib (Authorization Code + PKCE), configured at runtime."""
from authlib.integrations.starlette_client import OAuth


def get_oauth(cfg: dict) -> OAuth:
    """Build a fresh OAuth client from the (DB) auth config."""
    oauth = OAuth()
    issuer = (cfg.get("oidc_issuer_url") or "").rstrip("/")
    oauth.register(
        name="oidc",
        client_id=cfg.get("oidc_client_id"),
        client_secret=cfg.get("oidc_client_secret"),
        server_metadata_url=issuer + "/.well-known/openid-configuration",
        client_kwargs={"scope": cfg.get("oidc_scopes") or "openid email profile", "code_challenge_method": "S256"},
    )
    return oauth
