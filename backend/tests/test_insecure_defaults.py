"""Which shipped defaults the Ops screen reports, and how loudly.

The startup guard already logs these. A log line is read once, by whoever
happened to deploy, and never again - which is why the same facts now reach the
Ops screen. These tests pin what counts as a problem and when it counts as a
critical one, because a security notice that fires on every developer laptop is a
security notice everybody learns to ignore.
"""
import pytest

from app.config import settings
from app.ops import insecure_defaults


@pytest.fixture()
def secure(monkeypatch):
    """A correctly configured deployment: nothing should be reported."""
    monkeypatch.setattr(settings, "secret_key", "a-real-secret-key-of-sufficient-length-32")
    monkeypatch.setattr(settings, "postgres_password", "a-real-password")
    monkeypatch.setattr(settings, "public_base_url", "https://teamfollowup.example.com")
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "metrics_enabled", True)
    monkeypatch.setattr(settings, "metrics_token", "a-real-token")
    monkeypatch.setattr(settings, "breakglass_password", "a-real-admin-password")


def _keys(items):
    return {i["key"] for i in items}


def _severity(items, key):
    return next(i["severity"] for i in items if i["key"] == key)


def test_a_properly_configured_deployment_reports_nothing(secure):
    assert insecure_defaults() == []


def test_the_default_secret_key_is_reported(secure, monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "change-me-in-prod-please-32chars-min-secret")
    items = insecure_defaults()
    assert "SECRET_KEY" in _keys(items)
    assert _severity(items, "SECRET_KEY") == "critical"


def test_the_default_database_password_is_reported(secure, monkeypatch):
    monkeypatch.setattr(settings, "postgres_password", "tribe")
    assert "POSTGRES_PASSWORD" in _keys(insecure_defaults())


def test_the_example_breakglass_password_is_reported(secure, monkeypatch):
    monkeypatch.setattr(settings, "breakglass_password", "changeme-admin")
    assert "BREAKGLASS_PASSWORD" in _keys(insecure_defaults())


def test_an_insecure_cookie_is_reported_only_once_there_is_a_public_url(secure, monkeypatch):
    """On a laptop the app is served over plain HTTP; a Secure cookie would not arrive."""
    monkeypatch.setattr(settings, "cookie_secure", False)
    assert "COOKIE_SECURE" in _keys(insecure_defaults())

    monkeypatch.setattr(settings, "public_base_url", "")
    assert "COOKIE_SECURE" not in _keys(insecure_defaults())


def test_open_metrics_are_reported_only_on_a_deployment(secure, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "")
    assert "METRICS_TOKEN" in _keys(insecure_defaults())

    monkeypatch.setattr(settings, "public_base_url", "")
    assert "METRICS_TOKEN" not in _keys(insecure_defaults())


def test_severity_drops_to_a_warning_on_what_looks_like_a_laptop(secure, monkeypatch):
    """PUBLIC_BASE_URL is the honest signal: nobody fills it in locally."""
    monkeypatch.setattr(settings, "public_base_url", "")
    monkeypatch.setattr(settings, "secret_key", "change-me-in-prod-please-32chars-min-secret")
    assert _severity(insecure_defaults(), "SECRET_KEY") == "warning"


def test_the_runtime_endpoint_carries_the_list(client, seeded):
    from tests.conftest import login
    login(client, "admin@test")
    body = client.get("/api/admin/runtime").json()
    assert "insecure_defaults" in body
    assert isinstance(body["insecure_defaults"], list)


def test_the_list_is_admin_only(client, seeded):
    from tests.conftest import login
    login(client, "member@test")
    assert client.get("/api/admin/runtime").status_code == 403
