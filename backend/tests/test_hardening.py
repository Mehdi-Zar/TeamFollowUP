"""Login rate-limiting and data-retention purge."""
from datetime import timedelta

from app.config import settings
from app.maintenance import purge_old_records
from app.models import AuditLog, utcnow
from app.routers.auth import _login_failures
from tests.conftest import login


def test_login_throttle_blocks_after_max_failures(client, seeded):
    _login_failures.clear()
    for _ in range(settings.login_max_attempts):
        assert client.post("/api/auth/login", json={"email": "nope@x", "password": "bad"}).status_code == 401
    # next attempt is throttled
    assert client.post("/api/auth/login", json={"email": "nope@x", "password": "bad"}).status_code == 429
    _login_failures.clear()  # don't leak throttle state into other tests


def test_successful_login_resets_throttle(client, seeded):
    _login_failures.clear()
    for _ in range(settings.login_max_attempts - 1):
        client.post("/api/auth/login", json={"email": "nope@x", "password": "bad"})
    login(client, seeded["admin"])  # success clears the counter
    # we can fail again without being immediately throttled
    assert client.post("/api/auth/login", json={"email": "nope@x", "password": "bad"}).status_code == 401
    _login_failures.clear()


def test_audit_retention_purge(db, seeded, monkeypatch):
    db.add(AuditLog(action="old", timestamp=utcnow() - timedelta(days=400)))
    db.add(AuditLog(action="recent", timestamp=utcnow()))
    db.commit()
    monkeypatch.setattr(settings, "audit_retention_days", 30)
    out = purge_old_records(db)
    assert out.get("audit", 0) >= 1
    from sqlalchemy import select
    remaining = {a.action for a in db.scalars(select(AuditLog)).all()}
    assert "old" not in remaining and "recent" in remaining


def test_retention_disabled_by_default(db, seeded):
    db.add(AuditLog(action="keep", timestamp=utcnow() - timedelta(days=9999)))
    db.commit()
    assert purge_old_records(db) == {}  # 0 retention = keep forever
