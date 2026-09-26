"""Pentest, authentication and sessions: each finding locked by a test."""
import base64
import logging

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import AuditLog, User
from app.routers import auth as auth_router

from .conftest import login


@pytest.fixture(autouse=True)
def _fresh_throttle():
    auth_router._login_failures.clear()
    auth_router._account_failures.clear()
    yield
    auth_router._login_failures.clear()
    auth_router._account_failures.clear()


def _uid(db, email):
    return db.scalar(select(User).where(User.email == email)).id


# --- SECRET_KEY / cookies at startup ---------------------------------------
def test_a_deployed_instance_refuses_the_default_secret_key(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "change-me-in-prod-please-32chars-min-secret")
    monkeypatch.setattr(settings, "public_base_url", "")
    assert settings.startup_refusals() == []            # a laptop: warning only
    monkeypatch.setattr(settings, "public_base_url", "https://tfu.example.com")
    assert settings.startup_refusals()                  # deployed: refused
    monkeypatch.setattr(settings, "allow_insecure_secret_key", True)
    assert settings.startup_refusals() == []            # explicit escape hatch
    monkeypatch.setattr(settings, "allow_insecure_secret_key", False)
    monkeypatch.setattr(settings, "secret_key", "short-key")
    assert settings.startup_refusals()
    monkeypatch.setattr(settings, "secret_key", "x" * 48)
    assert settings.startup_refusals() == []


def test_samesite_none_needs_secure_cookies(monkeypatch):
    monkeypatch.setattr(settings, "cookie_samesite", "none")
    monkeypatch.setattr(settings, "cookie_secure", False)
    assert any("SAMESITE" in r for r in settings.startup_refusals())
    monkeypatch.setattr(settings, "cookie_secure", True)
    assert not any("SAMESITE" in r for r in settings.startup_refusals())


# --- brute force ------------------------------------------------------------
def test_a_new_forwarded_address_per_guess_does_not_bypass_the_throttle(client, seeded, monkeypatch):
    monkeypatch.setattr(settings, "login_max_attempts", 5)
    codes = [client.post("/api/auth/login", json={"email": seeded["admin"], "password": "bad"},
                         headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(8)]
    assert codes[:5] == [401] * 5 and 429 in codes[5:]
    # Even the right password is throttled for that account while blocked.
    r = client.post("/api/auth/login", json={"email": seeded["admin"], "password": "pw"},
                    headers={"X-Forwarded-For": "10.9.9.9"})
    assert r.status_code == 429


def test_the_client_ip_is_the_hop_our_proxy_appended():
    class R:
        headers = {"x-forwarded-for": "6.6.6.6, 198.51.100.7"}
        client = None
    assert auth_router._client_ip(R()) == "198.51.100.7"


def test_the_tracked_failures_are_bounded(monkeypatch):
    monkeypatch.setattr(auth_router, "_MAX_TRACKED", 50)
    for i in range(500):
        auth_router._record_failure(f"ip-{i}", f"user{i}@x")
    assert len(auth_router._login_failures) <= 50 and len(auth_router._account_failures) <= 50


def test_an_unknown_email_costs_a_password_check(client, seeded, monkeypatch):
    calls = []
    monkeypatch.setattr(auth_router, "burn_verify_time", lambda pw: calls.append(pw))
    assert client.post("/api/auth/login", json={"email": "nobody@x", "password": "p"}).status_code == 401
    assert calls == ["p"]


# --- session revocation -----------------------------------------------------
def test_logout_revokes_the_token_server_side(client, seeded):
    login(client, seeded["admin"])
    cookie = client.cookies.get(settings.session_cookie)
    assert client.get("/api/admin/users").status_code == 200
    client.post("/api/auth/logout")
    client.cookies.set(settings.session_cookie, cookie)
    assert client.get("/api/admin/users").status_code == 401


def test_a_password_role_or_status_change_ends_the_sessions(client, seeded, db):
    login(client, seeded["member"])
    assert client.get("/api/auth/me").status_code == 200
    u = db.get(User, seeded["member_id"])
    u.role = "squad_leader"
    db.commit()
    assert client.get("/api/auth/me").status_code == 401
    login(client, seeded["member"])
    u = db.get(User, seeded["member_id"])
    from app.security import hash_password
    u.password_hash = hash_password("another-long-password")
    db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_a_token_from_before_session_versions_still_works_once(client, seeded):
    import jwt
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    old = jwt.encode({"sub": str(seeded["member_id"]), "iat": int(now.timestamp()),
                      "exp": int((now + timedelta(hours=1)).timestamp())}, settings.secret_key, algorithm="HS256")
    client.cookies.set(settings.session_cookie, old)
    assert client.get("/api/auth/me").status_code == 200


# --- impersonation ----------------------------------------------------------
def test_a_simulation_ends_when_its_admin_is_no_longer_an_active_admin(client, seeded, db):
    login(client, seeded["admin"])
    r = client.post("/api/auth/impersonate", json={"user_id": _uid(db, seeded["tribe"])})
    assert r.status_code == 200
    assert "Max-Age=3600" in r.headers.get("set-cookie", "")       # one hour at most
    assert client.get("/api/auth/me").json()["email"] == seeded["tribe"]
    admin = db.get(User, _uid(db, seeded["admin"]))
    admin.status = "disabled"
    db.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/stop-impersonation").status_code == 401


def test_the_audit_names_the_admin_behind_a_simulation(client, seeded, db):
    login(client, seeded["admin"])
    admin_id = _uid(db, seeded["admin"])
    client.post("/api/auth/impersonate", json={"user_id": seeded["sl_a_id"]})
    assert client.put(f"/api/squads/{seeded['squad_a']}/mood", json={"mood": "good"}).status_code == 200
    db.expire_all()
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == seeded["sl_a_id"])).all()
    assert rows and all((r.detail or {}).get("impersonator_id") == admin_id for r in rows)


# --- SSO --------------------------------------------------------------------
_CFG = {"require_approval": True, "allowed_email_domains": "", "role_mappings": []}


def test_an_unverified_email_never_links_to_an_existing_account(db, seeded):
    with pytest.raises(Exception) as exc:
        auth_router._provision(db, subject="attacker", email=seeded["admin"], name="x", groups=None,
                               cfg=_CFG, source="oidc", email_verified=False)
    assert getattr(exc.value, "status_code", None) == 403
    assert db.get(User, _uid(db, seeded["admin"])).auth_subject is None


def test_the_break_glass_account_is_never_reached_by_sso(db, seeded):
    with pytest.raises(Exception) as exc:
        auth_router._provision(db, subject="s1", email=seeded["admin"], name="x", groups=None,
                               cfg=_CFG, source="oidc", email_verified=True)
    assert getattr(exc.value, "status_code", None) == 403


def test_an_account_bound_to_an_identity_is_not_moved_by_an_email_match(db, seeded):
    u = db.get(User, seeded["member_id"])
    u.auth_subject = "legit-subject"
    db.commit()
    with pytest.raises(Exception) as exc:
        auth_router._provision(db, subject="other-subject", email=seeded["member"], name="x", groups=None,
                               cfg=_CFG, source="oidc", email_verified=True)
    assert getattr(exc.value, "status_code", None) == 403


def test_first_linking_of_an_existing_account_honours_the_domain_list(db, seeded, monkeypatch):
    monkeypatch.setattr(auth_router, "email_domain_allowed", lambda cfg, email: False)
    with pytest.raises(Exception) as exc:
        auth_router._provision(db, subject="s-new", email=seeded["member"], name="x", groups=None,
                               cfg=_CFG, source="oidc", email_verified=True)
    assert getattr(exc.value, "status_code", None) == 403


def test_a_role_changed_by_sso_groups_is_audited(db, seeded, monkeypatch):
    monkeypatch.setattr(auth_router, "role_from_groups", lambda cfg, groups: "tribe_leader")
    auth_router._provision(db, subject=None, email=seeded["member"], name="x", groups=["g"],
                           cfg=_CFG, source="oidc", email_verified=True)
    db.flush()
    row = db.scalar(select(AuditLog).where(AuditLog.action == "user.role.sso"))
    assert row is not None and row.detail["from"] == "member" and row.detail["to"] == "tribe_leader"


# --- SAML -------------------------------------------------------------------
def test_saml_accepts_one_answer_per_request_once(db):
    from app import saml
    saml.remember_request(db, "ONELOGIN_abc")
    assert saml.consume_request(db, "ONELOGIN_abc") is True
    assert saml.consume_request(db, "ONELOGIN_abc") is False          # replay
    assert saml.consume_request(db, "ONELOGIN_never_sent") is False   # unsolicited
    assert saml.remember_assertion(db, "A1", None) is True
    assert saml.remember_assertion(db, "A1", None) is False           # same assertion twice


def test_saml_reads_in_response_to_without_dtds():
    from app import saml
    ok = base64.b64encode(b'<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
                          b'InResponseTo="ONELOGIN_x"/>').decode()
    assert saml.in_response_to(ok) == "ONELOGIN_x"
    evil = base64.b64encode(b'<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                            b'<r InResponseTo="&x;"/>').decode()
    assert saml.in_response_to(evil) is None
    assert saml.in_response_to(None) is None


def test_saml_acs_refuses_an_unsolicited_response(client, monkeypatch):
    monkeypatch.setattr(auth_router, "get_auth_config", lambda db, request=None: {"saml_enabled": True})
    resp = base64.b64encode(b'<r InResponseTo="ONELOGIN_forged"/>').decode()
    assert client.post("/api/auth/saml/acs", data={"SAMLResponse": resp}).status_code == 401


def test_idp_metadata_is_never_fetched_from_the_metadata_address():
    from app import saml
    from app.netguard import BlockedURL
    with pytest.raises(BlockedURL):
        saml._fetch_idp_metadata("http://169.254.169.254/latest/meta-data/")


# --- CSRF -------------------------------------------------------------------
def test_a_cross_site_state_change_is_refused(client, seeded):
    login(client, seeded["member"])
    for headers in ({"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"},
                    {"Origin": "https://evil.example"}, {"Origin": "null"}):
        r = client.put("/api/auth/me/preferences", json={}, headers=headers)
        assert r.status_code == 403, headers
    r = client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"})
    assert r.status_code == 200


# --- secrets in logs / passwords -------------------------------------------
def test_the_generated_break_glass_password_never_enters_the_logs(db, monkeypatch, capsys, caplog):
    from app import bootstrap
    monkeypatch.setattr(settings, "breakglass_password", "")
    monkeypatch.setattr(settings, "breakglass_email", "rescue@local")
    with caplog.at_level(logging.DEBUG):
        bootstrap.ensure_breakglass(db)
    printed = capsys.readouterr().err
    pw = printed.split("NOTEZ-LE) : ")[1].split("\n")[0].strip()
    assert pw and all(pw not in r.getMessage() for r in caplog.records)


def test_the_secret_link_token_is_hidden_in_the_access_log():
    from app.logconfig import RedactQueryFilter
    rec = logging.LogRecord("uvicorn.access", 20, "", 0, "%s %s %s %s %s",
                            ("1.2.3.4", "GET", "/api/auth/config?k=SECRET&x=1", "1.1", 200), None)
    RedactQueryFilter().filter(rec)
    assert "SECRET" not in rec.getMessage()


def test_passwords_shorter_than_twelve_are_refused():
    from app.security import validate_password
    with pytest.raises(Exception):
        validate_password("short-pw")
    validate_password("a-long-enough-password")
