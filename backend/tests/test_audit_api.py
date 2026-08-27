"""Audit-log read API: pagination, filters, and who is allowed to read it.

The screen exists to answer a question about the past ("who disabled this
account", "what happened on the 12th"), so the filters and the total matter more
than the raw listing. The access test is the important one: the audit trail names
who did what, and it is admin-only for that reason.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AuditLog, User
from tests.conftest import login


def _admin(db, seeded) -> User:
    """The seeded fixture hands back emails; the audit API works on ids."""
    return db.scalar(select(User).where(User.email == seeded["admin"]))


def _seed_entries(db, admin_id: int, count: int = 60):
    base = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    for i in range(count):
        db.add(AuditLog(
            user_id=admin_id if i % 2 == 0 else None,
            action="user.update" if i % 3 else "login.local",
            entity="user" if i % 3 else None,
            entity_id=str(100 + i) if i % 3 else None,
            timestamp=base + timedelta(minutes=i),
            detail={"i": i},
        ))
    db.commit()


def test_requires_admin(client, seeded):
    for email in ("tribe@test", "sl_a@test", "member@test"):
        login(client, email)
        assert client.get("/api/audit-log").status_code == 403


def test_returns_a_page_and_the_total(client, seeded, db):
    admin = _admin(db, seeded)
    _seed_entries(db, admin.id, count=60)
    login(client, "admin@test")

    r = client.get("/api/audit-log", params={"limit": 20})
    assert r.status_code == 200
    page = r.json()
    assert len(page["items"]) == 20
    assert page["limit"] == 20 and page["offset"] == 0
    # The login that just happened is audited too, so total is at least the seed.
    assert page["total"] >= 60


def test_newest_first_and_offset_walks_backwards_in_time(client, seeded, db):
    _seed_entries(db, _admin(db, seeded).id, count=30)
    login(client, "admin@test")

    first = client.get("/api/audit-log", params={"limit": 5}).json()["items"]
    second = client.get("/api/audit-log", params={"limit": 5, "offset": 5}).json()["items"]

    assert [e["id"] for e in first] != [e["id"] for e in second]
    assert first[0]["timestamp"] >= first[-1]["timestamp"]
    assert first[-1]["timestamp"] >= second[0]["timestamp"]


def test_pages_do_not_overlap_or_skip(client, seeded, db):
    _seed_entries(db, _admin(db, seeded).id, count=25)
    login(client, "admin@test")

    seen, offset = [], 0
    while True:
        page = client.get("/api/audit-log", params={"limit": 10, "offset": offset}).json()
        seen.extend(e["id"] for e in page["items"])
        offset += 10
        if offset >= page["total"]:
            break
    assert len(seen) == len(set(seen)), "an entry was returned on two pages"


def test_action_filter_is_a_case_insensitive_substring(client, seeded, db):
    _seed_entries(db, _admin(db, seeded).id, count=30)
    login(client, "admin@test")

    page = client.get("/api/audit-log", params={"action": "USER.UP"}).json()
    assert page["total"] > 0
    assert all("user.update" in e["action"] for e in page["items"])


def test_entity_filter_is_exact(client, seeded, db):
    _seed_entries(db, _admin(db, seeded).id, count=30)
    login(client, "admin@test")

    page = client.get("/api/audit-log", params={"entity": "user"}).json()
    assert page["total"] > 0
    assert all(e["entity"] == "user" for e in page["items"])
    assert client.get("/api/audit-log", params={"entity": "use"}).json()["total"] == 0


def test_date_range_filters(client, seeded, db):
    _seed_entries(db, _admin(db, seeded).id, count=60)  # one per minute from 12:00
    login(client, "admin@test")

    page = client.get("/api/audit-log", params={
        "since": "2026-03-01T12:10:00Z", "until": "2026-03-01T12:19:00Z", "limit": 500,
    }).json()
    assert page["total"] == 10
    for e in page["items"]:
        assert "2026-03-01T12:1" in e["timestamp"]


def test_user_filter(client, seeded, db):
    admin = _admin(db, seeded)
    _seed_entries(db, admin.id, count=20)
    login(client, "admin@test")

    page = client.get("/api/audit-log", params={"user_id": admin.id, "limit": 500}).json()
    assert page["total"] > 0
    assert all(e["user_id"] == admin.id for e in page["items"])


def test_acting_user_is_resolved_and_survives_deletion(client, seeded, db):
    """The FK is nullable so the trail outlives its authors; the join must cope."""
    admin = _admin(db, seeded)
    db.add(AuditLog(user_id=admin.id, action="user.update", entity="user", entity_id="1"))
    db.add(AuditLog(user_id=None, action="user.provisioned.oidc", entity="user", entity_id="2"))
    db.commit()
    login(client, "admin@test")

    items = client.get("/api/audit-log", params={"limit": 500}).json()["items"]
    with_user = [e for e in items if e["user_id"] == admin.id]
    orphan = [e for e in items if e["action"] == "user.provisioned.oidc"]
    assert with_user and with_user[0]["user_email"] == admin.email
    assert with_user[0]["user_name"] == admin.display_name
    assert orphan and orphan[0]["user_email"] is None


def test_limit_is_bounded(client, seeded):
    login(client, "admin@test")
    assert client.get("/api/audit-log", params={"limit": 10_000}).status_code == 422
    assert client.get("/api/audit-log", params={"limit": 0}).status_code == 422
    assert client.get("/api/audit-log", params={"offset": -1}).status_code == 422
