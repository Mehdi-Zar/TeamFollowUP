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
    assert p["admin_tabs"] == ["tribe", "users"]
    assert p["assignable_roles"] == ["squad_leader", "member"]
    assert p["can_create_tribe"] is False


def test_permissions_squad_leader(client, seeded):
    login(client, seeded["sl_a"])
    p = client.get("/api/auth/me/permissions").json()
    # Squad leaders manage their squad on the dedicated "my squad" page, not in admin.
    assert p["admin_tabs"] == []
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


GLOBAL_CONFIG_GETS = [
    "/api/admin/smtp-config",
    "/api/admin/auth-config",
    "/api/admin/settings",
    "/api/admin/modules-config",
    "/api/admin/report-config",
    "/api/admin/log-export-config",
]


def test_non_admins_cannot_read_global_config(client, seeded):
    for who in (seeded["tribe"], seeded["sl_a"], seeded["member"]):
        login(client, who)
        for ep in GLOBAL_CONFIG_GETS:
            assert client.get(ep).status_code == 403, f"{who} could GET {ep}"


def test_non_admins_cannot_write_smtp_or_modules(client, seeded):
    for who in (seeded["tribe"], seeded["sl_a"]):
        login(client, who)
        assert client.put("/api/admin/smtp-config", json={"enabled": True}).status_code == 403
        assert client.post("/api/admin/smtp-config/test", json={}).status_code == 403
        assert client.put("/api/admin/modules-config", json={"feed": {"enabled": False}}).status_code == 403
        assert client.put("/api/admin/settings", json={"app_name": "Hack"}).status_code == 403
        assert client.put("/api/admin/report-config", json={"enabled": True}).status_code == 403


def test_create_tribe_with_leader(client, seeded):
    login(client, seeded["admin"])
    # promote the existing member to tribe leader of a brand-new tribe
    member = next(u for u in client.get("/api/admin/users").json() if u["email"] == "member@test")
    r = client.post("/api/tribes", json={"name": "Nouvelle", "leader_user_id": member["id"]})
    assert r.status_code == 201
    new_tribe_id = r.json()["id"]
    updated = next(u for u in client.get("/api/admin/users").json() if u["id"] == member["id"])
    assert updated["role"] == "tribe_leader" and updated["tribe_id"] == new_tribe_id


def test_kpis_toggle_is_tribe_leader_only(client, seeded):
    sid = seeded["squad_a"]
    # squad leader cannot flip kpis_enabled (structural / tribe-leader decision)
    login(client, seeded["sl_a"])
    assert client.put(f"/api/squads/{sid}", json={"kpis_enabled": False}).status_code == 403
    # tribe leader of that tribe can
    login(client, seeded["tribe"])
    assert client.put(f"/api/squads/{sid}", json={"kpis_enabled": False}).status_code == 200


def test_impersonation_full_simulation(client, seeded):
    login(client, seeded["admin"])
    tl = next(u for u in client.get("/api/admin/users").json() if u["email"] == "tribe@test")

    # Start viewing as the tribe leader → session truly becomes them.
    r = client.post("/api/auth/impersonate", json={"user_id": tl["id"]})
    assert r.status_code == 200 and r.json()["email"] == "tribe@test"
    me = client.get("/api/auth/me").json()
    assert me["role"] == "tribe_leader" and me["tribe_id"] == seeded["t1"]

    perms = client.get("/api/auth/me/permissions").json()
    assert perms["impersonating"] is True
    assert perms["admin_tabs"] == ["tribe", "users"]  # tribe-leader tabs
    # And global config is now genuinely forbidden (acting as the tribe leader).
    assert client.get("/api/admin/smtp-config").status_code == 403

    # Stop → back to admin with full access.
    back = client.post("/api/auth/stop-impersonation")
    assert back.status_code == 200 and back.json()["email"] == "admin@test"
    assert client.get("/api/admin/smtp-config").status_code == 200


def test_non_admin_cannot_impersonate(client, seeded):
    login(client, seeded["tribe"])
    assert client.post("/api/auth/impersonate", json={"user_id": 1}).status_code == 403


def test_stop_without_impersonation_fails(client, seeded):
    login(client, seeded["admin"])
    assert client.post("/api/auth/stop-impersonation").status_code == 400


def test_review_restricted_to_configured_roles_scoped(client, seeded):
    # The review tab is gated by the persona 'review' capability (default: tribe_leader).
    # A member lacks it → 403.
    login(client, seeded["member"])  # tribe 1
    assert client.get("/api/progress/review").status_code == 403
    # A tribe leader is allowed, scoped to their own tribe.
    login(client, seeded["tribe"])  # tribe 1
    r = client.get("/api/progress/review")
    assert r.status_code == 200
    assert all(row["tribe_id"] == seeded["t1"] for row in r.json())


def test_admin_still_full_access(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/admin/users").status_code == 200
    assert client.post("/api/tribes", json={"name": "T3"}).status_code == 201
    r = client.post("/api/admin/users", json={"email": "tl@new", "display_name": "TL", "role": "tribe_leader", "tribe_id": seeded["t1"]})
    assert r.status_code == 201
