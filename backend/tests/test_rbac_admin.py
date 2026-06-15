"""RBAC for the role-scoped admin page: tribe leaders manage their tribe/squads/
users; squad leaders manage their squads; members have no management scope."""
from tests.conftest import login


# ---- permissions payload -------------------------------------------------------

def test_permissions_admin(client, seeded):
    login(client, seeded["admin"])
    p = client.get("/api/auth/me/permissions").json()
    assert p["can_access_admin"] is True
    assert "modules" in p["admin_tabs"] and "settings" in p["admin_tabs"]
    assert set(p["assignable_roles"]) == {"admin", "tribe_leader", "squad_leader", "member"}


def test_permissions_tribe_leader(client, seeded):
    login(client, seeded["tribe"])
    p = client.get("/api/auth/me/permissions").json()
    assert p["admin_tabs"] == ["tribe", "squads", "users"]
    assert p["assignable_roles"] == ["squad_leader", "member"]
    assert p["can_create_tribe"] is False


def test_permissions_squad_leader(client, seeded):
    login(client, seeded["sl_a"])
    p = client.get("/api/auth/me/permissions").json()
    assert p["admin_tabs"] == ["my_squads"]
    assert p["can_manage_users"] is False


def test_permissions_member_no_admin(client, seeded):
    login(client, seeded["member"])
    p = client.get("/api/auth/me/permissions").json()
    assert p["can_access_admin"] is False
    assert p["admin_tabs"] == []


# ---- tribe management ----------------------------------------------------------

def test_tribe_leader_edits_own_tribe(client, seeded):
    login(client, seeded["tribe"])  # leads t1
    assert client.put(f"/api/tribes/{seeded['t1']}", json={"description": "Notre tribu"}).status_code == 200


def test_tribe_leader_cannot_edit_other_tribe(client, seeded):
    login(client, seeded["tribe"])
    assert client.put(f"/api/tribes/{seeded['t2']}", json={"description": "x"}).status_code == 403


def test_tribe_leader_cannot_create_or_delete_tribe(client, seeded):
    login(client, seeded["tribe"])
    assert client.post("/api/tribes", json={"name": "New"}).status_code == 403
    assert client.delete(f"/api/tribes/{seeded['t1']}").status_code == 403


# ---- user management scope -----------------------------------------------------

def test_tribe_leader_lists_only_own_tribe_users(client, seeded):
    login(client, seeded["tribe"])  # t1
    users = client.get("/api/admin/users").json()
    tribe_ids = {u["tribe_id"] for u in users}
    assert tribe_ids <= {seeded["t1"]}
    assert all(u["email"] != "admin@test" for u in users)  # admin (no tribe) excluded


def test_tribe_leader_creates_member_in_own_tribe(client, seeded):
    login(client, seeded["tribe"])
    r = client.post("/api/admin/users", json={"email": "new@t1", "display_name": "New", "role": "squad_leader"})
    assert r.status_code == 201
    assert r.json()["tribe_id"] == seeded["t1"]  # forced to own tribe


def test_tribe_leader_cannot_grant_admin(client, seeded):
    login(client, seeded["tribe"])
    assert client.post("/api/admin/users", json={"email": "x@t1", "display_name": "X", "role": "admin"}).status_code == 403
    assert client.post("/api/admin/users", json={"email": "y@t1", "display_name": "Y", "role": "tribe_leader"}).status_code == 403


def test_tribe_leader_cannot_manage_other_tribe_user(client, seeded):
    login(client, seeded["tribe2"])  # t2 leader
    # member belongs to t1 → out of scope for t2 leader
    members = client.get("/api/admin/users").json()
    assert all(u["email"] != "member@test" for u in members)


def test_squad_leader_cannot_manage_users(client, seeded):
    login(client, seeded["sl_a"])
    assert client.get("/api/admin/users").status_code == 403
    assert client.post("/api/admin/users", json={"email": "z@t1", "display_name": "Z", "role": "member"}).status_code == 403


def test_member_cannot_manage_users(client, seeded):
    login(client, seeded["member"])
    assert client.get("/api/admin/users").status_code == 403


def test_admin_still_full_access(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/admin/users").status_code == 200
    assert client.post("/api/tribes", json={"name": "T3"}).status_code == 201
    r = client.post("/api/admin/users", json={"email": "tl@new", "display_name": "TL", "role": "tribe_leader", "tribe_id": seeded["t1"]})
    assert r.status_code == 201
