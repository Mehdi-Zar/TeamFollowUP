"""The OIDC callback when the IdP says no.

An IdP that refuses the authorization request redirects the browser back to the
callback with ``error`` and no ``code``. Handing that to Authlib raises inside
the token exchange, so the admin doing the SSO setup reads "Internal Server
Error" for what is in fact a precise answer from the IdP (an unauthorized scope,
a redirect URI that does not match, a consent that was declined). These tests
pin that the answer reaches the screen.
"""
from app.authconfig import set_auth_config

CFG = {
    "oidc_enabled": True,
    "oidc_issuer_url": "https://idp.example/realms/tribe",
    "oidc_client_id": "teamfollowup",
    "oidc_client_secret": "s3cr3t",
    "oidc_scopes": "openid profile email",
}


def _enable_oidc(db):
    set_auth_config(db, CFG)
    db.commit()


def test_an_idp_refusal_is_reported_not_raised(db, client):
    _enable_oidc(db)
    resp = client.get("/api/auth/oidc/callback", params={
        "error": "invalid_scope",
        "error_description": "The requested scope is invalid, unknown, malformed, "
                             "or exceeds that which the client is permitted to request.",
        "state": "xyPZznfCJB28Qss68n9vVhnkIPyhlY",
    })
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "invalid_scope" in detail
    # The provider's own wording is what tells the admin which knob to turn.
    assert "exceeds that which the client is permitted to request" in detail


def test_a_refusal_without_a_description_still_names_the_error(db, client):
    _enable_oidc(db)
    resp = client.get("/api/auth/oidc/callback", params={"error": "access_denied"})
    assert resp.status_code == 400, resp.text
    assert "access_denied" in resp.json()["detail"]


def test_the_callback_stays_invisible_when_oidc_is_off(db, client):
    resp = client.get("/api/auth/oidc/callback", params={"error": "invalid_scope"})
    assert resp.status_code == 404
