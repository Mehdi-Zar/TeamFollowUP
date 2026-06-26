from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ---
    app_name: str = "Tribe Cockpit"
    secret_key: str = "change-me-in-prod-please-32chars-min-secret"
    session_cookie: str = "trt_session"
    session_max_age_seconds: int = 60 * 60 * 12  # 12h
    # Session cookie hardening - set COOKIE_SECURE=true behind TLS in production.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"  # lax | strict | none

    # --- Hardening / retention ---
    login_max_attempts: int = 10        # per IP per window (0 = disabled)
    login_window_seconds: int = 300     # 5 min
    audit_retention_days: int = 0       # 0 = keep forever
    progress_retention_days: int = 0    # 0 = keep forever

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
    oidc_enabled: bool = False
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:8080/api/auth/oidc/callback"
    oidc_scopes: str = "openid email profile"

    # --- SAML ---
    saml_enabled: bool = False
    saml_idp_metadata_url: str = ""
    saml_idp_metadata_path: str = ""
    saml_sp_entity_id: str = "http://localhost:8080/api/auth/saml/metadata"
    saml_acs_url: str = "http://localhost:8080/api/auth/saml/acs"
    saml_sp_cert: str = ""
    saml_sp_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
