"""Offline tests for the audit-log export config + GCP keyless authentication.

No network: google-auth entry points are monkeypatched, so we assert the auth
method is *dispatched* correctly (ADC / WIF / impersonation / key) and that the
config layer stores/masks secrets and defaults to the recommended keyless method.
"""
import json

import pytest

from app import logexport, logexportconfig


# --------------------------------------------------------------------------- #
# Config layer
# --------------------------------------------------------------------------- #
def test_defaults_recommend_keyless(db):
    cfg = logexportconfig.get_log_export(db)
    assert cfg["auth_method"] == "adc"           # keyless by default
    assert cfg["destination"] == "syslog"
    assert cfg["gcp_credentials_json"] == ""      # never leaks
    assert cfg["gcp_credentials_json_set"] is False


def test_invalid_auth_method_falls_back_to_adc(db):
    logexportconfig.set_log_export(db, {"auth_method": "nonsense"})
    assert logexportconfig.get_log_export(db)["auth_method"] == "adc"


def test_key_secret_is_masked_but_kept(db):
    logexportconfig.set_log_export(db, {"auth_method": "key",
                                        "gcp_credentials_json": '{"x":1}'})
    db.commit()  # the caller (admin router) commits; mirror that here
    masked = logexportconfig.get_log_export(db)
    assert masked["gcp_credentials_json"] == ""            # masked to the client
    assert masked["gcp_credentials_json_set"] is True
    # An empty secret in a later patch must NOT wipe the stored one.
    logexportconfig.set_log_export(db, {"gcs_bucket": "b", "gcp_credentials_json": ""})
    db.commit()
    revealed = logexportconfig.get_log_export(db, reveal_secrets=True)
    assert revealed["gcp_credentials_json"] == '{"x":1}'


def test_wif_config_is_not_treated_as_secret(db):
    # The external_account config is a config file, safe to echo back.
    logexportconfig.set_log_export(db, {"auth_method": "wif",
                                        "wif_config_json": '{"type":"external_account"}'})
    db.commit()
    cfg = logexportconfig.get_log_export(db)
    assert cfg["wif_config_json"] == '{"type":"external_account"}'


# --------------------------------------------------------------------------- #
# Auth dispatch (google-auth monkeypatched - no network)
# --------------------------------------------------------------------------- #
class _FakeCreds:
    def __init__(self, universe="googleapis.com"):
        self.token = "tok-123"
        self.universe_domain = universe

    def refresh(self, request):
        self.token = "tok-refreshed"


def test_adc_dispatch(monkeypatch):
    seen = {}

    def fake_default(scopes=None):
        seen["scopes"] = scopes
        return _FakeCreds(), "proj"

    monkeypatch.setattr(logexport.google.auth, "default", fake_default)
    creds = logexport._credentials({"auth_method": "adc"}, [logexport.SCOPE_GCS])
    assert isinstance(creds, _FakeCreds)
    assert seen["scopes"] == [logexport.SCOPE_GCS]


def test_key_dispatch(monkeypatch):
    seen = {}

    def fake_from_info(info, scopes=None):
        seen["info"] = info
        seen["scopes"] = scopes
        return _FakeCreds()

    monkeypatch.setattr(logexport.service_account.Credentials,
                        "from_service_account_info", staticmethod(fake_from_info))
    cfg = {"auth_method": "key", "gcp_credentials_json": json.dumps({"client_email": "x"})}
    creds = logexport._credentials(cfg, [logexport.SCOPE_BQ])
    assert isinstance(creds, _FakeCreds)
    assert seen["info"] == {"client_email": "x"}


def test_key_missing_raises(monkeypatch):
    with pytest.raises(logexport.LogExportError):
        logexport._credentials({"auth_method": "key", "gcp_credentials_json": ""},
                               [logexport.SCOPE_GCS])


def test_wif_dispatch(monkeypatch):
    seen = {}

    def fake_load(info, scopes=None):
        seen["info"] = info
        return _FakeCreds(), "proj"

    monkeypatch.setattr(logexport.google.auth, "load_credentials_from_dict", fake_load)
    cfg = {"auth_method": "wif", "wif_config_json": json.dumps({"type": "external_account"})}
    creds = logexport._credentials(cfg, [logexport.SCOPE_GCS])
    assert isinstance(creds, _FakeCreds)
    assert seen["info"]["type"] == "external_account"


def test_wif_missing_raises():
    with pytest.raises(logexport.LogExportError):
        logexport._credentials({"auth_method": "wif", "wif_config_json": ""},
                               [logexport.SCOPE_GCS])


def test_impersonation_wraps_adc(monkeypatch):
    captured = {}

    monkeypatch.setattr(logexport.google.auth, "default",
                        lambda scopes=None: (_FakeCreds(), "proj"))

    def fake_impersonated(source_credentials, target_principal, target_scopes,
                          lifetime=3600, iam_endpoint_override=None):
        captured.update(target=target_principal, scopes=target_scopes,
                        override=iam_endpoint_override)
        return _FakeCreds()

    monkeypatch.setattr(logexport.impersonated_credentials, "Credentials", fake_impersonated)
    cfg = {"auth_method": "impersonation",
           "impersonate_service_account": "svc@proj.iam.gserviceaccount.com"}
    logexport._credentials(cfg, [logexport.SCOPE_GCS])
    assert captured["target"] == "svc@proj.iam.gserviceaccount.com"
    assert captured["scopes"] == [logexport.SCOPE_GCS]
    assert captured["override"] is None        # default universe -> no override


def test_impersonation_uses_universe_override_for_s3ns(monkeypatch):
    captured = {}
    monkeypatch.setattr(logexport.google.auth, "default",
                        lambda scopes=None: (_FakeCreds(universe="s3nsapis.fr"), "proj"))

    def fake_impersonated(source_credentials, target_principal, target_scopes,
                          lifetime=3600, iam_endpoint_override=None):
        captured["override"] = iam_endpoint_override
        return _FakeCreds(universe="s3nsapis.fr")

    monkeypatch.setattr(logexport.impersonated_credentials, "Credentials", fake_impersonated)
    cfg = {"auth_method": "impersonation", "universe_domain": "s3nsapis.fr",
           "impersonate_service_account": "svc@p.iam.gserviceaccount.com"}
    logexport._credentials(cfg, [logexport.SCOPE_BQ])
    assert captured["override"] == (
        "https://iamcredentials.s3nsapis.fr"
        "/v1/projects/-/serviceAccounts/{}:generateAccessToken")


def test_impersonation_missing_target_raises(monkeypatch):
    monkeypatch.setattr(logexport.google.auth, "default",
                        lambda scopes=None: (_FakeCreds(), "proj"))
    with pytest.raises(logexport.LogExportError):
        logexport._credentials({"auth_method": "impersonation"}, [logexport.SCOPE_GCS])


def test_adc_missing_credentials_gives_helpful_error(monkeypatch):
    def boom(scopes=None):
        raise logexport.DefaultCredentialsError("no creds")

    monkeypatch.setattr(logexport.google.auth, "default", boom)
    with pytest.raises(logexport.LogExportError) as ei:
        logexport._credentials({"auth_method": "adc"}, [logexport.SCOPE_GCS])
    assert "Workload Identity" in str(ei.value)


# --------------------------------------------------------------------------- #
# Token + universe resolution
# --------------------------------------------------------------------------- #
def test_token_and_universe_explicit_wins(monkeypatch):
    monkeypatch.setattr(logexport, "_credentials", lambda cfg, scopes: _FakeCreds(universe="googleapis.com"))
    token, universe = logexport._token_and_universe({"universe_domain": "s3nsapis.fr"}, logexport.SCOPE_GCS)
    assert token == "tok-refreshed"
    assert universe == "s3nsapis.fr"       # explicit config beats the creds' own


def test_token_and_universe_from_creds(monkeypatch):
    monkeypatch.setattr(logexport, "_credentials", lambda cfg, scopes: _FakeCreds(universe="s3nsapis.fr"))
    _, universe = logexport._token_and_universe({}, logexport.SCOPE_BQ)
    assert universe == "s3nsapis.fr"


# --------------------------------------------------------------------------- #
# httpx transport adapter
# --------------------------------------------------------------------------- #
def test_httpx_auth_adapter_maps_response(monkeypatch):
    class _Resp:
        status_code = 200
        headers = {"content-type": "application/json"}
        content = b'{"ok":true}'

    monkeypatch.setattr(logexport.httpx, "request", lambda *a, **k: _Resp())
    r = logexport._HttpxAuthRequest()("https://oauth2.googleapis.com/token", method="POST")
    assert r.status == 200
    assert r.data == b'{"ok":true}'
    assert r.headers["content-type"] == "application/json"


# --------------------------------------------------------------------------- #
# Serialization is unchanged and destination dispatch still routes
# --------------------------------------------------------------------------- #
def test_export_empty_is_noop():
    ok, msg = logexport.export_entries({"destination": "gcs"}, [])
    assert ok is True


def test_gcs_requires_bucket(monkeypatch):
    ok, msg = logexport.export_entries({"destination": "gcs", "gcs_bucket": ""},
                                       [logexport.sample_entry()])
    assert ok is False
    assert "bucket" in msg.lower()
