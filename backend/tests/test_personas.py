"""Personas & permissions admin: capability matrix, custom personas, assignment."""
from tests.conftest import login


def test_get_personas_returns_builtins_and_catalog(client, seeded):
    login(client, seeded["admin"])
    out = client.get("/api/admin/personas").json()
    assert out["capabilities"] == ["dashboard", "roadmap", "org", "feed", "reporting", "mysquads", "leaves"]
    keys = [p["key"] for p in out["personas"]]
    assert keys[:4] == ["admin", "tribe_leader", "squad_leader", "member"]
    assert all(p["builtin"] for p in out["personas"])


def test_personas_admin_only(client, seeded):
    login(client, seeded["tribe"])
    assert client.get("/api/admin/personas").status_code == 403


def test_roadmap_matrix_endpoint(client, seeded, db):
    login(client, seeded["member"])  # member has the roadmap capability by default
    r = client.get("/api/roadmap/matrix")
    assert r.status_code == 200
    body = r.json()
    assert "tribes" in body and body["year"]
    # Revoke the roadmap capability for members → access denied.
    from app.personasconfig import get_personas, set_personas
    personas = get_personas(db)
    for p in personas:
        if p["key"] == "member":
            p["caps"]["roadmap"] = False
    set_personas(db, personas); db.commit()
    assert client.get("/api/roadmap/matrix").status_code == 403


def test_create_custom_persona_and_assign(client, seeded, db):
    login(client, seeded["admin"])
    personas = client.get("/api/admin/personas").json()["personas"]
    personas.append({"key": "Auditeur Externe", "label": "Auditeur Externe", "builtin": False,
                     "caps": {"dashboard": True, "org": True, "feed": False,
                              "reporting": False, "mysquads": False}})
    saved = client.put("/api/admin/personas", json={"personas": personas}).json()["personas"]
    custom = [p for p in saved if not p["builtin"]]
    assert len(custom) == 1
    key = custom[0]["key"]
    assert key == "auditeur_externe"  # slugified
    assert custom[0]["caps"]["dashboard"] is True and custom[0]["caps"]["feed"] is False

    # The custom persona is now assignable to a user.
    u = client.post("/api/admin/users", json={
        "email": "aud@test", "display_name": "Aud", "role": key, "tribe_id": seeded["t1"]})
    assert u.status_code == 201, u.text
    assert u.json()["role"] == key

    # That user can reach the dashboard (capability granted) but not the feed.
    from app.models import User
    from app.security import hash_password
    from sqlalchemy import select
    usr = db.scalar(select(User).where(User.email == "aud@test"))
    usr.password_hash = hash_password("pw")
    db.commit()
    login(client, "aud@test")
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/feed").status_code == 403


def test_deleting_persona_reassigns_users_to_member(client, seeded, db):
    login(client, seeded["admin"])
    personas = client.get("/api/admin/personas").json()["personas"]
    personas.append({"key": "temp", "label": "Temp", "builtin": False,
                     "caps": {c: True for c in
                              ["dashboard", "org", "feed", "reporting", "mysquads"]}})
    client.put("/api/admin/personas", json={"personas": personas})
    client.post("/api/admin/users", json={
        "email": "temp@test", "display_name": "T", "role": "temp", "tribe_id": seeded["t1"]})

    # Remove the custom persona → its user falls back to 'member'.
    builtins = [p for p in client.get("/api/admin/personas").json()["personas"] if p["builtin"]]
    client.put("/api/admin/personas", json={"personas": builtins})
    from app.models import User
    from sqlalchemy import select
    assert db.scalar(select(User).where(User.email == "temp@test")).role == "member"


def test_which_capabilities_are_enforced_server_side_matches_the_documentation():
    """The capability matrix is only as strong as the guards behind it.

    docs/05 used to state that all seven capabilities are enforced by
    ``require_capability``. Six are. ``mysquads`` is navigation only, and on
    purpose: the screen it opens drives ``PUT /api/squads/{id}``, which also
    carries the budget toggle on the squad page and the Steerco toggle on the
    entry page, so gating that route on the capability would break unrelated
    features for a persona that merely has the menu entry hidden. The actions are
    guarded by role and ownership instead.

    This test is the reason the documentation can be trusted: adding or removing
    an enforcement point fails here, so the claim has to be updated with the code.
    """
    import re
    from pathlib import Path

    from app.personasconfig import CAPABILITIES

    routers = Path(__file__).resolve().parent.parent / "app" / "routers"
    enforced = set()
    for src in routers.rglob("*.py"):
        enforced |= set(re.findall(r'require_capability\(\s*["\'](\w+)["\']', src.read_text(encoding="utf-8")))

    assert enforced <= set(CAPABILITIES), f"unknown capability guarded: {enforced - set(CAPABILITIES)}"
    assert sorted(set(CAPABILITIES) - enforced) == ["mysquads"], (
        "The set of capabilities enforced server-side changed. Update "
        "docs/05-security.md (layer 2) and docs/01-product-overview.md to match, "
        "then adjust this test."
    )
