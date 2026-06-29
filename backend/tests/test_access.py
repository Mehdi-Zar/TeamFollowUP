"""SSO access-approval workflow: provisioning is pending until a manager validates,
and validation scope follows the approver's role."""
from app.models import User
from app.security import hash_password
from tests.conftest import login


def _pending(db, email="newbie@test", role="member"):
    u = User(email=email, display_name="Newbie", role=role, status="pending",
             password_hash=hash_password("pw"))
    db.add(u)
    db.commit()
    return u


def test_pending_user_is_authenticated_but_denied(client, seeded, db):
    _pending(db)
    login(client, "newbie@test")
    # /me works (so the SPA can show the pending screen)...
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["status"] == "pending"
    # ...but every protected endpoint is denied with a machine-readable code.
    r = client.get("/api/dashboard")
    assert r.status_code == 403 and r.json()["detail"] == "access_pending"


def test_admin_sees_and_approves_request(client, seeded, db):
    u = _pending(db)
    login(client, seeded["admin"])
    reqs = client.get("/api/access-requests").json()
    assert any(x["email"] == "newbie@test" for x in reqs["requests"])
    assert set(reqs["roles"]) == {"admin", "tribe_leader", "squad_leader", "member"}

    ok = client.post(f"/api/access-requests/{u.id}/approve",
                     json={"role": "member", "tribe_id": seeded["t1"]})
    assert ok.status_code == 200 and ok.json()["status"] == "active"

    # The now-active user can reach the app.
    login(client, "newbie@test")
    assert client.get("/api/dashboard").status_code == 200


def test_tribe_leader_scope(client, seeded, db):
    u = _pending(db)
    login(client, seeded["tribe"])
    opts = client.get("/api/access-requests").json()
    assert set(opts["roles"]) == {"squad_leader", "member"}
    assert opts["tribe_locked"] is True
    # Cannot grant admin.
    assert client.post(f"/api/access-requests/{u.id}/approve", json={"role": "admin"}).status_code == 403
    # Can grant member into their own tribe (tribe forced to theirs).
    ok = client.post(f"/api/access-requests/{u.id}/approve", json={"role": "member"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "active" and ok.json()["tribe_id"] == seeded["t1"]


def test_squad_leader_must_place_into_own_squad(client, seeded, db):
    u = _pending(db)
    login(client, seeded["sl_a"])
    opts = client.get("/api/access-requests").json()
    assert opts["roles"] == ["member"] and opts["can_deny"] is False
    assert {s["id"] for s in opts["squads"]} == {seeded["squad_a"]}
    # No squad → rejected; someone else's squad → forbidden.
    assert client.post(f"/api/access-requests/{u.id}/approve", json={"role": "member"}).status_code == 400
    assert client.post(f"/api/access-requests/{u.id}/approve",
                       json={"role": "member", "squad_id": seeded["squad_b"]}).status_code == 403
    # Own squad → validated into that squad's tribe.
    ok = client.post(f"/api/access-requests/{u.id}/approve",
                     json={"role": "member", "squad_id": seeded["squad_a"]})
    assert ok.status_code == 200 and ok.json()["tribe_id"] == seeded["t1"]


def test_member_cannot_review(client, seeded, db):
    _pending(db)
    login(client, seeded["member"])
    assert client.get("/api/access-requests").status_code == 403


def test_deny_disables_and_blocks_login(client, seeded, db):
    u = _pending(db)
    login(client, seeded["admin"])
    assert client.post(f"/api/access-requests/{u.id}/deny").status_code == 200
    db.refresh(u)
    assert u.status == "disabled"
    # A disabled account can no longer log in.
    r = client.post("/api/auth/login", json={"email": "newbie@test", "password": "pw"})
    assert r.status_code == 403

    # Squad leaders cannot deny (gatekeeping reserved to admin / tribe leader).
    u2 = _pending(db, email="n2@test")
    login(client, seeded["sl_a"])
    assert client.post(f"/api/access-requests/{u2.id}/deny").status_code == 403
