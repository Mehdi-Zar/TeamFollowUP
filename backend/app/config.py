"""Application configuration.

Single source of truth for every tunable of the backend. Values are read (in
order of precedence) from environment variables, then a local ``.env`` file,
then the defaults declared below. Grouped by concern: core/session, security
hardening, database, business rules, seeding, break-glass access and the two
SSO backends (OIDC / SAML).

The settings object is built once and cached (:func:`get_settings`) so the
whole process shares one immutable configuration; import ``settings`` to use it.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated configuration loaded from the environment / ``.env``.

    Each attribute is a setting with a safe default for local development;
    production overrides them via environment variables. ``extra="ignore"`` lets
    unrelated environment variables coexist without raising a validation error.
    """

    # Load overrides from a local .env file; ignore env vars we don't declare.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ---
    app_name: str = "TeamFollowUP"
    secret_key: str = "change-me-in-prod-please-32chars-min-secret"
    session_cookie: str = "trt_session"
    session_max_age_seconds: int = 60 * 60 * 12  # 12h
    # Session cookie hardening - set COOKIE_SECURE=true behind TLS in production.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"  # lax | strict | none

    # --- Serving / TLS termination ---
    # tls_enabled=True (default, local/standalone): uvicorn terminates TLS itself
    # on HTTPS_PORT (see server.py + tls.py). tls_enabled=False: the app serves
    # plain HTTP on http_port and lets the infrastructure terminate TLS - the
    # supported GKE model (Gateway API + ALB do TLS, the pod speaks HTTP).
    tls_enabled: bool = True
    http_port: int = 8000

    # --- Public URL ---
    # The URL users type in their browser to reach the app, scheme + host (+ port
    # if non-standard), no trailing slash. Example: https://teamfollowup.example.com
    # It is NOT the port the container listens on: behind a Gateway/ALB the pod
    # speaks HTTP on :8000 while the public URL is https://... on :443.
    # Every SSO callback URL (OIDC redirect URI, SAML entity ID / ACS) is derived
    # from it, so it is the single value to set when deploying.
    # Left empty (the default), the app derives it from each incoming request
    # (X-Forwarded-Proto / X-Forwarded-Host are honoured), which is correct for
    # local dev and for any single-hostname deployment.
    public_base_url: str = ""

    # --- Logging ---
    # "text" = human-readable lines (local dev). "json" = GCP Cloud Logging
    # structured entries (severity/message/time) that the GKE logging agent parses
    # straight off stdout - set LOG_FORMAT=json in the cluster.
    log_format: str = "text"  # text | json
    log_level: str = "INFO"

    # --- Metrics (Prometheus) ---
    # /metrics exposes latency, error rate and saturation. It is enabled by
    # default because an app nobody can graph is an app nobody can operate, but
    # it describes the traffic (which routes exist, how often, how many 5xx), so
    # it must not be reachable from outside. Two ways to keep it private, and you
    # want at least one: do not route /metrics on the public gateway (see
    # docs/17), or set metrics_token and give the scraper a bearer token.
    metrics_enabled: bool = True
    metrics_token: str = ""

    # --- Hardening / retention ---
    login_max_attempts: int = 10        # per IP per window (0 = disabled)
    login_window_seconds: int = 300     # 5 min
    audit_retention_days: int = 0       # 0 = keep forever

    # --- Database ---
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "tribe"
    postgres_user: str = "tribe"
    postgres_password: str = "tribe"

    # --- Business rules ---
    staleness_threshold_days: int = 7

    # --- Seed ---
    seed_demo: bool = True

    # --- Breaking-glass ---
    breakglass_email: str = "admin@local"
    breakglass_password: str = ""  # empty -> random generated & logged at first boot

    # --- OIDC ---
    # oidc_redirect_uri is left empty on purpose: it is derived from
    # public_base_url (see authconfig.derive_sso_urls). Set it only to override
    # the derivation, e.g. when the IdP registration uses a legacy URL.
    oidc_enabled: bool = False
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_scopes: str = "openid email profile"

    # --- SAML ---
    # Same rule: entity ID and ACS URL are derived from public_base_url unless
    # explicitly set here (an entity ID already registered at the IdP, typically).
    saml_enabled: bool = False
    saml_idp_metadata_url: str = ""
    saml_idp_metadata_path: str = ""
    saml_sp_entity_id: str = ""
    saml_acs_url: str = ""
    saml_sp_cert: str = ""
    saml_sp_key: str = ""

    @property
    def database_url(self) -> str:
        """Assemble the SQLAlchemy connection URL from the postgres_* parts.

        Kept as a derived property (rather than a stored setting) so the DSN
        always stays in sync with the individual host/port/credentials fields.
        """
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton.

    Cached so configuration is parsed from the environment only once; every
    caller shares the same instance.
    """
    return Settings()


# Module-level shortcut so callers can simply `from .config import settings`.
settings = get_settings()
