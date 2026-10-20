"""Signed out after a period of inactivity (Administration > General settings).

The page signs its user out after ``idle_timeout_minutes`` without activity, and
the server refuses an idle session too: the token carries the last activity
("act"), renewed by requests that are activity, never by the page's automatic
refreshes (header ``X-Background: 1``). Renewing keeps the session's issue and
expiry times: activity never stretches a session past its maximum length.
"""
import time

import jwt

from app.config import settings
from app.deps import ACTIVITY_RENEW_SECONDS, IDLE_GRACE_SECONDS
from app.generalconfig import set_general
from app.security import create_session_token, decode_session_claims
from tests.conftest import login


def _token(client):
    return client.cookies.get(settings.session_cookie)


def _age(client, seconds):
    """Rewrite the session cookie as if its last activity were ``seconds`` ago."""
    claims = jwt.decode(_token(client), settings.secret_key, algorithms=["HS256"])
    claims["act"] = int(time.time()) - seconds
    name = settings.session_cookie
    old = next(c for c in client.cookies.jar if c.name == name)
    client.cookies.delete(name)
    client.cookies.set(name, jwt.encode(claims, settings.secret_key, algorithm="HS256"),
                       domain=old.domain, path=old.path)


def test_the_setting_is_published_and_clamped(client, db, seeded):
    assert client.get("/api/config").json()["idle_timeout_minutes"] == 0
    assert set_general(db, {"idle_timeout_minutes": 99999})["idle_timeout_minutes"] == 1440
    db.commit()
    assert set_general(db, {"idle_timeout_minutes": -5})["idle_timeout_minutes"] == 0
    db.commit()
    set_general(db, {"idle_timeout_minutes": 30})
    db.commit()
    assert client.get("/api/config").json()["idle_timeout_minutes"] == 30


def test_an_idle_session_is_refused(client, db, seeded):
    set_general(db, {"idle_timeout_minutes": 30})
    db.commit()
    login(client, seeded["sl_a"])
    _age(client, 30 * 60 + IDLE_GRACE_SECONDS + 5)
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and "inactivit" in r.json()["detail"]


def test_off_means_never(client, db, seeded):
    login(client, seeded["sl_a"])
    _age(client, 10 * 3600)
    assert client.get("/api/auth/me").status_code == 200


def test_activity_renews_the_session_but_not_its_length(client, db, seeded):
    set_general(db, {"idle_timeout_minutes": 30})
    db.commit()
    login(client, seeded["sl_a"])
    first = decode_session_claims(_token(client))
    _age(client, ACTIVITY_RENEW_SECONDS + 10)
    assert client.get("/api/auth/me").status_code == 200
    renewed = decode_session_claims(_token(client))
    assert renewed["act"] >= int(time.time()) - 5
    assert (renewed["iat"], renewed["exp"]) == (first["iat"], first["exp"])


def test_automatic_refreshes_are_not_activity(client, db, seeded):
    set_general(db, {"idle_timeout_minutes": 30})
    db.commit()
    login(client, seeded["sl_a"])
    _age(client, 20 * 60)
    before = decode_session_claims(_token(client))["act"]
    assert client.get("/api/auth/me", headers={"X-Background": "1"}).status_code == 200
    assert decode_session_claims(_token(client))["act"] == before


def test_a_token_from_before_the_claim_counts_from_its_issue():
    tok = create_session_token(1)
    claims = jwt.decode(tok, settings.secret_key, algorithms=["HS256"])
    del claims["act"]
    old = jwt.encode(claims, settings.secret_key, algorithm="HS256")
    assert decode_session_claims(old)["act"] == claims["iat"]
