"""The Authlib surface the OIDC login depends on.

The real OIDC exchange is covered end to end by the Kubernetes bench
(docs/16), which needs a cluster and an IdP. What is NOT covered anywhere is the
cheap failure: a dependency bump quietly renaming or moving the two methods the
login calls, which no unit test would notice and which only breaks in production
the first time somebody clicks "Sign in".

These tests are that guard. They build nothing over the network.
"""
from app.oidc import discovery_url, get_oauth

CFG = {
    "oidc_issuer_url": "https://idp.example/realms/tribe/",   # trailing slash on purpose
    "oidc_client_id": "teamfollowup",
    "oidc_client_secret": "s3cret",
    "oidc_scopes": "openid email profile",
}


def test_client_builds_from_the_runtime_config():
    client = get_oauth(CFG).oidc
    assert client is not None
    assert client.client_id == "teamfollowup"


def test_the_two_methods_the_login_calls_still_exist():
    """auth.py calls exactly these. A rename in Authlib must fail here, not live."""
    client = get_oauth(CFG).oidc
    assert callable(getattr(client, "authorize_redirect", None))
    assert callable(getattr(client, "authorize_access_token", None))


def test_discovery_url_is_derived_from_the_issuer_without_a_double_slash():
    expected = "https://idp.example/realms/tribe/.well-known/openid-configuration"
    assert discovery_url("https://idp.example/realms/tribe/") == expected
    assert discovery_url("https://idp.example/realms/tribe") == expected
    assert discovery_url("") == "/.well-known/openid-configuration"


def test_pkce_is_requested():
    """S256 is what protects the code exchange against interception; it is not optional."""
    client = get_oauth(CFG).oidc
    assert client.client_kwargs.get("code_challenge_method") == "S256"


def test_scopes_fall_back_to_the_openid_minimum():
    client = get_oauth({**CFG, "oidc_scopes": ""}).oidc
    assert client.client_kwargs["scope"] == "openid email profile"


def test_scopes_survive_the_separators_people_actually_type():
    """A scope list is space separated. The config field collects worse than that.

    Commas, a line break, or the non breaking space a word processor leaves in a
    pasted string all glue the list into a single unknown scope, and the IdP
    then answers invalid_scope: the error names the scopes while the fault is in
    the separator.
    """
    from app.oidc import DEFAULT_SCOPES, scope_string

    assert scope_string("openid profile email") == "openid profile email"
    assert scope_string("openid,profile,email") == "openid profile email"
    assert scope_string("openid, profile,  email") == "openid profile email"
    assert scope_string("openid\nprofile\temail") == "openid profile email"
    assert scope_string("  openid  profile email  ") == "openid profile email"
    # A scope with punctuation in it (Thales hub) must come out untouched.
    assert scope_string("openid,oxs:pub:groups") == "openid oxs:pub:groups"
    # Nothing usable falls back rather than sending an OIDC request without openid.
    assert scope_string("") == DEFAULT_SCOPES
    assert scope_string(None) == DEFAULT_SCOPES
    assert scope_string(" , ; ") == DEFAULT_SCOPES


def test_the_client_sends_the_normalized_scope():
    client = get_oauth({**CFG, "oidc_scopes": "openid,profile,email"}).oidc
    assert client.client_kwargs["scope"] == "openid profile email"
