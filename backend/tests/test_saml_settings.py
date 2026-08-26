"""The SAML SP block must survive the merge with the parsed IdP metadata.

Regression test for a defect found while driving a real Keycloak IdP from a
Kubernetes bench: ``OneLogin_Saml2_IdPMetadataParser`` returns an ``sp`` hint
alongside ``idp``, and the old flat ``dict.update`` replaced our whole SP section
with it. python3-saml then refused the settings
(``sp_entityId_not_found,sp_acs_not_found``) and SAML login was impossible against
any IdP that advertises a NameIDFormat, Keycloak and PingFederate included.

``_load_idp_metadata_settings`` is stubbed, so these tests need neither network
access nor the native xmlsec stack.
"""
import pytest

from app import saml

# What Keycloak's descriptor actually parses into, trimmed to what matters here.
KEYCLOAK_PARSE = {
    "idp": {
        "entityId": "https://idp.internal.example/realms/tribe",
        "singleSignOnService": {
            "url": "https://idp.internal.example/realms/tribe/protocol/saml",
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
        },
        "x509cert": "MIIC-fake",
    },
    "sp": {"NameIDFormat": "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"},
    "security": {"authnRequestsSigned": True},
}

CFG = {
    "saml_sp_entity_id": "https://tribe.internal.example/api/auth/saml/metadata",
    "saml_acs_url": "https://tribe.internal.example/api/auth/saml/acs",
    "saml_sp_cert": "",
    "saml_sp_key": "",
}


@pytest.fixture()
def parsed(monkeypatch):
    def _set(value):
        monkeypatch.setattr(saml, "_load_idp_metadata_settings", lambda cfg: value)
    return _set


def test_sp_entity_id_and_acs_survive_the_idp_merge(parsed):
    parsed(KEYCLOAK_PARSE)
    sp = saml.build_settings(CFG)["sp"]
    assert sp["entityId"] == CFG["saml_sp_entity_id"]
    assert sp["assertionConsumerService"]["url"] == CFG["saml_acs_url"]
    assert sp["assertionConsumerService"]["binding"].endswith("HTTP-POST")


def test_our_name_id_format_wins_over_the_idp_hint(parsed):
    parsed(KEYCLOAK_PARSE)
    # We provision by email address; the IdP's "persistent" hint must not override it.
    assert saml.build_settings(CFG)["sp"]["NameIDFormat"].endswith("emailAddress")


def test_idp_block_is_taken_as_is(parsed):
    parsed(KEYCLOAK_PARSE)
    assert saml.build_settings(CFG)["idp"] == KEYCLOAK_PARSE["idp"]


def test_signed_authn_requests_need_a_key_pair(parsed):
    """Without an SP key we cannot sign, so the hint is dropped rather than
    producing settings python3-saml refuses to build."""
    parsed(KEYCLOAK_PARSE)
    assert saml.build_settings(CFG)["security"]["authnRequestsSigned"] is False


def test_signed_authn_requests_are_honoured_when_a_key_pair_exists(parsed):
    parsed(KEYCLOAK_PARSE)
    cfg = {**CFG, "saml_sp_cert": "MIIC-sp-cert", "saml_sp_key": "PRIVATE-KEY"}
    settings = saml.build_settings(cfg)
    assert settings["security"]["authnRequestsSigned"] is True
    assert settings["sp"]["x509cert"] == "MIIC-sp-cert"


def test_metadata_without_extras_still_works(parsed):
    """An IdP whose metadata yields only an idp block must keep working."""
    parsed({"idp": {"entityId": "https://idp.example"}})
    settings = saml.build_settings(CFG)
    assert settings["sp"]["entityId"] == CFG["saml_sp_entity_id"]
    assert settings["strict"] is True
