"""SSO callback URLs are derived from one public base URL, never hardcoded.

Covers the contract described in app/authconfig.py: an admin configures a single
public URL (or nothing at all) and the OIDC redirect URI / SAML entity ID / ACS
URL follow, including when the app sits behind a TLS-terminating proxy.
"""
from app.authconfig import (
    derive_sso_urls,
    get_auth_config,
    normalize_base_url,
    set_auth_config,
)

from .conftest import login


def test_normalize_base_url_accepts_what_people_actually_paste():
    # Trailing slash, a pasted callback path, a bare hostname: all reduce to the
    # authority, because anything else would corrupt every derived URL.
    assert normalize_base_url("https://app.example.com/") == "https://app.example.com"
    assert normalize_base_url("https://app.example.com/api/auth/oidc/callback") == "https://app.example.com"
    assert normalize_base_url("  app.example.com  ") == "https://app.example.com"
    assert normalize_base_url("HTTP://localhost:8000") == "http://localhost:8000"
    assert normalize_base_url("") == ""
    assert normalize_base_url(None) == ""


def test_derive_sso_urls_uses_the_documented_paths():
    assert derive_sso_urls("https://app.example.com") == {
        "oidc_redirect_uri": "https://app.example.com/api/auth/oidc/callback",
        "saml_sp_entity_id": "https://app.example.com/api/auth/saml/metadata",
        "saml_acs_url": "https://app.example.com/api/auth/saml/acs",
    }
    # No base URL at all: empty, never a fabricated localhost.
    assert set(derive_sso_urls("").values()) == {""}


def test_urls_default_to_the_configured_public_base_url(db):
    set_auth_config(db, {"public_base_url": "https://teamfollowup.example.com/"})
    db.commit()
    cfg = get_auth_config(db)
    assert cfg["base_url_source"] == "configured"
    assert cfg["oidc_redirect_uri"] == "https://teamfollowup.example.com/api/auth/oidc/callback"
    assert cfg["saml_acs_url"] == "https://teamfollowup.example.com/api/auth/saml/acs"


def test_urls_fall_back_to_the_request_when_nothing_is_configured(client, seeded):
    login(client, seeded["admin"])
    cfg = client.get("/api/admin/auth-config").json()
    assert cfg["base_url_source"] == "request"
    # TestClient's default base is http://testserver.
    assert cfg["oidc_redirect_uri"] == "http://testserver/api/auth/oidc/callback"


def test_proxy_headers_are_honoured(client, seeded):
    """Behind a TLS-terminating Gateway the pod speaks HTTP, but the callback URL
    must be the public HTTPS one the browser (and the IdP) actually sees.

    This is the nginx-style convention, where the proxy rewrites Host and states the
    original one in X-Forwarded-Host."""
    login(client, seeded["admin"])
    cfg = client.get("/api/admin/auth-config", headers={
        "x-forwarded-proto": "https",
        "x-forwarded-host": "teamfollowup.example.com",
    }).json()
    assert cfg["saml_sp_entity_id"] == "https://teamfollowup.example.com/api/auth/saml/metadata"


def test_google_load_balancer_shape(client, seeded):
    """GKE Gateway / Google ALBs do NOT send X-Forwarded-Host: they set
    X-Forwarded-Proto and forward the client's Host unchanged. The public URL must
    still come out as https, or every SSO callback would point at the pod's internal
    plain-HTTP address."""
    login(client, seeded["admin"])
    cfg = client.get("/api/admin/auth-config", headers={
        "host": "tribe.internal.example",
        "x-forwarded-proto": "https",
        "x-forwarded-for": "203.0.113.7, 35.191.0.1",
    }).json()
    assert cfg["base_url_effective"] == "https://tribe.internal.example"
    assert cfg["oidc_redirect_uri"] == "https://tribe.internal.example/api/auth/oidc/callback"
    assert cfg["saml_acs_url"] == "https://tribe.internal.example/api/auth/saml/acs"


def test_a_configured_url_ignores_request_headers(client, seeded):
    """Why the manifests set PUBLIC_BASE_URL: once configured, the SSO URLs are
    deterministic and cannot be steered by whatever Host a caller sends."""
    login(client, seeded["admin"])
    client.put("/api/admin/auth-config", json={"public_base_url": "https://tribe.internal.example"})
    cfg = client.get("/api/admin/auth-config", headers={
        "host": "evil.example",
        "x-forwarded-host": "evil.example",
        "x-forwarded-proto": "https",
    }).json()
    assert cfg["base_url_source"] == "configured"
    assert cfg["oidc_redirect_uri"] == "https://tribe.internal.example/api/auth/oidc/callback"


def test_saving_a_derived_url_does_not_freeze_it(client, seeded):
    """The admin UI round-trips the URLs it displays; that must not turn them into
    overrides, otherwise changing the public URL later would leave them stale."""
    login(client, seeded["admin"])
    cfg = client.get("/api/admin/auth-config").json()
    assert client.put("/api/admin/auth-config", json=cfg).status_code == 200

    # Now point the app at a real hostname: every URL must follow.
    saved = client.put("/api/admin/auth-config", json={"public_base_url": "https://prod.example.com"}).json()
    assert saved["oidc_redirect_uri"] == "https://prod.example.com/api/auth/oidc/callback"
    assert saved["saml_acs_url"] == "https://prod.example.com/api/auth/saml/acs"


def test_saving_the_page_does_not_freeze_the_environment_url(client, seeded, monkeypatch):
    """Regression: saving anything in Admin > Authentication used to persist the
    deployment's PUBLIC_BASE_URL into the database, after which changing the env
    var in the manifest had no effect at all. Found on the Kubernetes bench."""
    from app import authconfig

    monkeypatch.setattr(authconfig.settings, "public_base_url", "https://from-env.example")
    login(client, seeded["admin"])
    # An admin toggles something unrelated and saves the page.
    saved = client.put("/api/admin/auth-config", json=client.get("/api/admin/auth-config").json()).json()
    assert saved["base_url_effective"] == "https://from-env.example"

    # Ops now redeploys with a different public URL: it must take effect.
    monkeypatch.setattr(authconfig.settings, "public_base_url", "https://redeployed.example")
    cfg = client.get("/api/admin/auth-config").json()
    assert cfg["base_url_effective"] == "https://redeployed.example"
    assert cfg["oidc_redirect_uri"] == "https://redeployed.example/api/auth/oidc/callback"


def test_an_admin_url_still_overrides_the_environment(client, seeded, monkeypatch):
    """The flip side: a URL an admin really typed must outlive a redeploy."""
    from app import authconfig

    monkeypatch.setattr(authconfig.settings, "public_base_url", "https://from-env.example")
    login(client, seeded["admin"])
    client.put("/api/admin/auth-config", json={"public_base_url": "https://chosen.example"})
    monkeypatch.setattr(authconfig.settings, "public_base_url", "https://redeployed.example")
    cfg = client.get("/api/admin/auth-config").json()
    assert cfg["base_url_source"] == "configured"
    assert cfg["base_url_effective"] == "https://chosen.example"


def test_an_explicit_override_wins_and_survives(client, seeded):
    login(client, seeded["admin"])
    saved = client.put("/api/admin/auth-config", json={
        "public_base_url": "https://prod.example.com",
        "oidc_redirect_uri": "https://legacy.example.com/sso/cb",
    }).json()
    assert saved["oidc_redirect_uri"] == "https://legacy.example.com/sso/cb"
    # The SAML pair keeps following the base URL.
    assert saved["saml_acs_url"] == "https://prod.example.com/api/auth/saml/acs"
    assert client.get("/api/admin/auth-config").json()["oidc_redirect_uri"] == "https://legacy.example.com/sso/cb"
