"""A non-admin account without a tribe sees nothing, not every tribe.

None means "all tribes" to the read helpers. Such an account exists: created
without a tribe, or left behind when its tribe is deleted. It used to be scoped
like an admin."""
from app.models import User
from app.security import hash_password
from tests.conftest import login


def _tribeless(db, role="member"):
    u = User(email=f"{role}-none@test", display_name="Nobody", role=role,
             tribe_id=None, password_hash=hash_password("pw"))
    db.add(u)
    db.commit()
    return u.email


def test_tribeless_member_sees_no_squad_nor_initiative(client, db, seeded):
    login(client, _tribeless(db))
    assert client.get("/api/squads").json() == []
    r = client.get("/api/initiatives")
    assert r.status_code in (200, 404), r.text
    if r.status_code == 200:
        assert r.json() == []
    r = client.get("/api/dashboard")
    assert r.status_code == 200, r.text
    assert "Squad C" not in r.text and "Squad A" not in r.text


def test_tribeless_tribe_leader_lists_no_user(client, db, seeded):
    login(client, _tribeless(db, "tribe_leader"))
    r = client.get("/api/admin/users")
    # Without a tribe there is no tribe to manage: refused, or at worst empty.
    assert r.status_code == 403 or [u["email"] for u in r.json()] == [], r.text
