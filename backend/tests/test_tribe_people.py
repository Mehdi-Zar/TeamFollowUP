"""The list of people offered in the pick-or-type fields."""
from tests.conftest import login


def test_a_member_sees_the_active_people_of_their_tribe_only(client, seeded, db):
    from app.models import User
    login(client, seeded["member"])
    me = db.query(User).filter(User.email == seeded["member"]).one()
    rows = client.get("/api/tribes/people").json()
    assert rows and all(r["tribe_id"] == me.tribe_id for r in rows)
    assert {"id", "name", "email"} <= set(rows[0])


def test_an_admin_sees_every_tribe(client, seeded):
    login(client, seeded["admin"])
    tribes = {r["tribe_id"] for r in client.get("/api/tribes/people").json()}
    assert {seeded["t1"], seeded["t2"]} <= tribes


def test_it_needs_a_session(client, seeded):
    assert client.get("/api/tribes/people").status_code == 401
