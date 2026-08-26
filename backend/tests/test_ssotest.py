"""The "test the connection to the IdP" button must be able to say no.

A check that is green whatever the configuration is worse than no check at all, so
these tests pin the failure paths as much as the happy one. Outbound HTTP is
stubbed: the point is the diagnosis logic, not the network.
"""
import pytest

from app import ssotest

DISCOVERY = {
    "issuer": "https://idp.example/realms/tribe",
    "authorization_endpoint": "https://idp.example/realms/tribe/auth",
    "token_endpoint": "https://idp.example/realms/tribe/token",
    "jwks_uri": "https://idp.example/realms/tribe/certs",
    "code_challenge_methods_supported": ["S256"],
}

CFG = {
    "oidc_issuer_url": "https://idp.example/realms/tribe",
    "oidc_client_id": "teamfollowup",
    "oidc_client_secret": "s3cr3t",
    "oidc_redirect_uri": "https://app.example/api/auth/oidc/callback",
}


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class FakeClient:
    """Minimal stand-in for httpx.Client driven by a routing table."""

    def __init__(self, gets, post):
        self._gets, self._post = gets, post

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, **kw):
        for fragment, resp in self._gets.items():
            if fragment in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return FakeResponse(404, {})

    def post(self, url, **kw):
        if isinstance(self._post, Exception):
            raise self._post
        return self._post


@pytest.fixture()
def httpx_stub(monkeypatch):
    def _install(gets, post=None):
        import httpx
        monkeypatch.setattr(httpx, "Client", lambda **kw: FakeClient(gets, post))
    return _install


def labels(result, level):
    return [c["label"] for c in result["checks"] if c["level"] == level]


def test_a_complete_configuration_passes(httpx_stub):
    httpx_stub(
        {".well-known": FakeResponse(200, DISCOVERY), "certs": FakeResponse(200, {"keys": [{"kid": "a"}, {"kid": "b"}]})},
        FakeResponse(400, {"error": "invalid_grant"}),   # credentials OK, fake code rejected
    )
    result = ssotest.test_oidc(CFG)
    assert result["ok"], labels(result, "error")
    assert "Identifiants du client" not in labels(result, "error")


def test_wrong_client_secret_is_reported(httpx_stub):
    """The probe must distinguish bad credentials from a disabled grant. Keycloak
    answers invalid_client with a 401 when the secret is wrong."""
    httpx_stub(
        {".well-known": FakeResponse(200, DISCOVERY), "certs": FakeResponse(200, {"keys": [{"kid": "a"}]})},
        FakeResponse(401, {"error": "invalid_client"}),
    )
    result = ssotest.test_oidc(CFG)
    assert not result["ok"]
    assert "Identifiants du client" in labels(result, "error")


def test_unreachable_issuer_is_reported(httpx_stub):
    httpx_stub({".well-known": ConnectionRefusedError("Connection refused")})
    result = ssotest.test_oidc(CFG)
    assert not result["ok"]
    assert "Document de découverte" in labels(result, "error")


def test_issuer_mismatch_is_reported(httpx_stub):
    """A discovery document that announces a different issuer breaks token
    validation later, so it must fail here rather than at someone's login."""
    httpx_stub(
        {".well-known": FakeResponse(200, {**DISCOVERY, "issuer": "https://elsewhere.example"}),
         "certs": FakeResponse(200, {"keys": [{"kid": "a"}]})},
        FakeResponse(400, {"error": "invalid_grant"}),
    )
    result = ssotest.test_oidc(CFG)
    assert not result["ok"]
    assert "Émetteur annoncé cohérent" in labels(result, "error")


def test_missing_pkce_is_a_warning_not_a_failure(httpx_stub):
    """Several IdPs support S256 without advertising it, so this informs rather
    than blocks."""
    doc = {k: v for k, v in DISCOVERY.items() if k != "code_challenge_methods_supported"}
    httpx_stub(
        {".well-known": FakeResponse(200, doc), "certs": FakeResponse(200, {"keys": [{"kid": "a"}]})},
        FakeResponse(400, {"error": "invalid_grant"}),
    )
    result = ssotest.test_oidc(CFG)
    assert result["ok"]
    assert "PKCE S256 annoncé" in labels(result, "warn")


def test_no_issuer_fails_immediately(httpx_stub):
    result = ssotest.test_oidc({**CFG, "oidc_issuer_url": ""})
    assert not result["ok"]
    assert result["checks"][0]["label"] == "URL de l'émetteur (issuer)"


def test_saml_without_metadata_source_fails(monkeypatch):
    from app import saml
    monkeypatch.setattr(saml, "saml_available", lambda: True)
    result = ssotest.test_saml({"saml_idp_metadata_url": "", "saml_idp_metadata_path": ""})
    assert not result["ok"]
    assert "Source des métadonnées IdP" in labels(result, "error")


def test_saml_reports_unreadable_metadata(monkeypatch):
    from app import saml
    monkeypatch.setattr(saml, "saml_available", lambda: True)

    def boom(cfg):
        raise OSError("HTTP Error 404: Not Found")

    monkeypatch.setattr(saml, "_load_idp_metadata_settings", boom)
    result = ssotest.test_saml({"saml_idp_metadata_url": "https://idp.example/descriptor"})
    assert not result["ok"]
    assert "Métadonnées IdP lues" in labels(result, "error")
