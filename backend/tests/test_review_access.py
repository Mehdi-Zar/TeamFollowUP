"""Section access is governed by persona capabilities (Admin → Personas)."""
from app.personasconfig import get_personas, set_personas
from tests.conftest import login


def _set_cap(db, role_key, cap, value):
    personas = get_personas(db)
    for p in personas:
        if p["key"] == role_key:
            p["caps"][cap] = value
    set_personas(db, personas)
    db.commit()


def test_dashboard_and_feed_capabilities_enforced(client, seeded, db):
    _set_cap(db, "member", "dashboard", False)
    login(client, seeded["member"])
    assert client.get("/api/dashboard").status_code == 403
    # feed default member=True → allowed
    assert client.get("/api/feed").status_code == 200
    _set_cap(db, "member", "feed", False)
    assert client.get("/api/feed").status_code == 403


def test_feed_capability_gates_writes_not_just_reads(client, seeded, db):
    # squad_leader can post by default (leader + feed cap). Revoke the feed cap →
    # every feed endpoint (read AND write) is denied, not just the list.
    login(client, seeded["sl_a"])
    assert client.post("/api/feed", json={"content": "hi", "kind": "info"}).status_code == 201
    _set_cap(db, "squad_leader", "feed", False)
    assert client.get("/api/feed").status_code == 403
    assert client.post("/api/feed", json={"content": "again", "kind": "info"}).status_code == 403


def test_me_permissions_exposes_capabilities(client, seeded):
    login(client, seeded["member"])
    caps = client.get("/api/auth/me/permissions").json()["capabilities"]
    assert caps["dashboard"] is True and caps["feed"] is True
