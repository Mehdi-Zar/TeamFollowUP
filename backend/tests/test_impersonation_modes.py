"""The admin's two simulations: "view as" (read only) and "act as".

Read only shows the app exactly as the person sees it, and the server refuses
every write of that session, whatever screen sends it. Act as writes in their
name, each change audited with the real admin. Leaving or switching the
simulation, and the routes that only compute something to look at, still pass.
"""
from sqlalchemy import select

from app.models import AuditLog, User
from tests.conftest import login


def _start(client, seeded, email, mode=None):
    login(client, seeded["admin"])
    db_user = client.get("/api/admin/users").json()
    uid = next(u["id"] for u in db_user if u["email"] == email)
    body = {"user_id": uid} | ({"mode": mode} if mode else {})
    r = client.post("/api/auth/impersonate", json=body)
    assert r.status_code == 200, r.text
    return uid


def test_read_only_sees_as_the_person_and_writes_nothing(client, seeded):
    _start(client, seeded, "sl_a@test", "read")
    perms = client.get("/api/auth/me/permissions").json()
    assert perms["impersonating"] and perms["impersonation_mode"] == "read"
    assert client.get("/api/auth/me").json()["email"] == "sl_a@test"
    # A read passes, a write is refused with a clear reason.
    assert client.get(f"/api/squads/{seeded['squad_a']}").status_code == 200
    r = client.post("/api/roadmap-items", json={"squad_id": seeded["squad_a"], "year": 2026, "quarter": 1,
                                                "title": "J", "theme": "LZ"})
    assert r.status_code == 403 and "Lecture seule" in r.json()["detail"]
    assert client.put("/api/me/preferences", json={"notify_tweets": False}).status_code == 403


def test_act_as_writes_in_their_name_audited_with_the_admin(client, db, seeded):
    _start(client, seeded, "sl_a@test", "act")
    assert client.get("/api/auth/me/permissions").json()["impersonation_mode"] == "act"
    r = client.post("/api/roadmap-items", json={"squad_id": seeded["squad_a"], "year": 2026, "quarter": 1,
                                                "title": "J", "theme": "LZ"})
    assert r.status_code == 201, r.text
    admin = db.scalar(select(User).where(User.email == "admin@test"))
    row = db.scalar(select(AuditLog).where(AuditLog.action == "roadmap.create"))
    assert row is not None and (row.detail or {}).get("impersonator_id") == admin.id


def test_switching_mode_and_leaving_pass_in_read_only(client, seeded):
    uid = _start(client, seeded, "sl_a@test", "read")
    r = client.post("/api/auth/impersonate", json={"user_id": uid, "mode": "act"})
    assert r.status_code == 200
    assert client.get("/api/auth/me/permissions").json()["impersonation_mode"] == "act"
    client.post("/api/auth/impersonate", json={"user_id": uid, "mode": "read"})
    assert client.post("/api/auth/stop-impersonation").status_code == 200
    perms = client.get("/api/auth/me/permissions").json()
    assert perms["impersonating"] is False and perms["impersonation_mode"] is None


def test_the_mode_is_recorded_and_checked(client, db, seeded):
    _start(client, seeded, "member@test", "read")
    row = db.scalar(select(AuditLog).where(AuditLog.action == "impersonate.start"))
    assert (row.detail or {}).get("mode") == "read"
    login(client, seeded["admin"])
    assert client.post("/api/auth/impersonate", json={"user_id": seeded["member_id"], "mode": "god"}).status_code == 422


def test_without_a_mode_the_route_acts_as_before(client, seeded):
    _start(client, seeded, "sl_a@test")
    assert client.get("/api/auth/me/permissions").json()["impersonation_mode"] == "act"
