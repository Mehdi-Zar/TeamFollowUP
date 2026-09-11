"""Co-leaders: a squad led by more than one person.

A squad keeps ONE named leader (an OTD is committed on them, the report is addressed
to them) and any number of co-leaders holding exactly the same rights. Sharing an
account or moving the leader field back and forth was the alternative.

The tests that matter are the permission ones: every squad-level check goes through
one helper, so what these pin is that adding a co-leader really opens every door the
leader has, and not one more.
"""
from sqlalchemy import select

from app.models import Otd, RoadmapItem, Squad, User
from tests.conftest import login


def _add_coleader(client, squad_id: int, *user_ids: int):
    """The tribe leader names the co-leaders (structural, like the leader)."""
    return client.put(f"/api/squads/{squad_id}", json={"co_leader_user_ids": list(user_ids)})


def test_a_co_leader_is_named_by_leadership_not_by_oneself(client, db, seeded):
    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    login(client, seeded["sl_a"])
    r = _add_coleader(client, seeded["squad_a"], sl_b.id)
    assert r.status_code == 403, r.text

    login(client, seeded["tribe"])
    r = _add_coleader(client, seeded["squad_a"], sl_b.id)
    assert r.status_code == 200, r.text
    assert r.json()["co_leader_user_ids"] == [sl_b.id]


def test_a_co_leader_edits_the_squad_like_its_leader(client, db, seeded):
    """The point of the feature: the same rights, on the same squad."""
    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    squad_a = seeded["squad_a"]

    # Before: the leader of squad B is a stranger to squad A.
    login(client, seeded["sl_b"])
    assert client.put(f"/api/squads/{squad_a}", json={"description": "vu par B"}).status_code == 403
    assert client.post("/api/roadmap-items", json={
        "squad_id": squad_a, "title": "Jalon", "quarter": 1, "year": 2026,
        "theme": "Socle"}).status_code == 403

    login(client, seeded["tribe"])
    _add_coleader(client, squad_a, sl_b.id)

    # After: everything the leader could do.
    login(client, seeded["sl_b"])
    assert client.put(f"/api/squads/{squad_a}", json={"description": "vu par B"}).status_code == 200
    r = client.post("/api/roadmap-items", json={
        "squad_id": squad_a, "title": "Jalon", "quarter": 1, "year": 2026,
        "theme": "Socle"})
    assert r.status_code == 201, r.text
    detail = client.get(f"/api/squads/{squad_a}").json()
    assert detail["description"] == "vu par B"
    assert [c["id"] for c in detail["co_leaders"]] == [sl_b.id]


def test_a_co_leader_does_not_become_the_leader(client, db, seeded):
    """Identity and rights are two different things: the OTD stays on the leader."""
    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    login(client, seeded["tribe"])
    _add_coleader(client, seeded["squad_a"], sl_b.id)

    squad = db.get(Squad, seeded["squad_a"])
    db.refresh(squad)
    assert squad.leader_user_id == db.scalar(select(User.id).where(User.email == seeded["sl_a"]))
    assert [u.id for u in squad.co_leaders] == [sl_b.id]


def test_naming_a_member_co_leader_gives_them_the_role(client, db, seeded):
    """Otherwise the account is listed as a leader and refused by every check."""
    member = db.scalar(select(User).where(User.email == seeded["member"]))
    assert member.role == "member"

    login(client, seeded["tribe"])
    assert _add_coleader(client, seeded["squad_a"], member.id).status_code == 200
    db.expire_all()
    assert db.get(User, member.id).role == "squad_leader"

    login(client, seeded["member"])
    assert client.put(f"/api/squads/{seeded['squad_a']}", json={"description": "x"}).status_code == 200


def test_a_co_leader_of_another_tribe_is_refused(client, db, seeded):
    """It would open that tribe's squad through the door tribe scope closes."""
    other = db.scalar(select(User).where(User.email == seeded["tribe2"]))
    login(client, "admin@test")
    r = _add_coleader(client, seeded["squad_a"], other.id)
    assert r.status_code == 400 and "tribe" in r.json()["detail"].lower()


def test_removing_a_co_leader_closes_the_door_again(client, db, seeded):
    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    login(client, seeded["tribe"])
    _add_coleader(client, seeded["squad_a"], sl_b.id)
    _add_coleader(client, seeded["squad_a"])          # empty list = nobody

    login(client, seeded["sl_b"])
    assert client.put(f"/api/squads/{seeded['squad_a']}", json={"description": "x"}).status_code == 403


def test_a_co_leader_sees_the_squad_s_otd(client, db, seeded):
    """OTD visibility keys on the squads a person leads, co-led ones included."""
    sl_a = db.scalar(select(User).where(User.email == seeded["sl_a"]))
    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    db.add(Otd(tribe_id=seeded["t1"], year=2026, title="Livrer la LZ", owner_user_id=sl_a.id))
    db.commit()

    login(client, seeded["sl_b"])
    assert [o["title"] for o in client.get("/api/otds?year=2026").json()] == []

    login(client, seeded["tribe"])
    _add_coleader(client, seeded["squad_a"], sl_b.id)

    # Still not visible: the OTD is committed on the leader, not on the squad. It
    # shows once a milestone of the co-led squad belongs to it.
    login(client, seeded["sl_b"])
    assert [o["title"] for o in client.get("/api/otds?year=2026").json()] == []

    otd = db.scalar(select(Otd).where(Otd.title == "Livrer la LZ"))
    db.add(RoadmapItem(squad_id=seeded["squad_a"], year=2026, quarter=1,
                       title="Jalon", otd_id=otd.id))
    db.commit()
    login(client, seeded["sl_b"])
    assert [o["title"] for o in client.get("/api/otds?year=2026").json()] == ["Livrer la LZ"]


def test_a_co_leader_reports_the_squad_s_steerco(client, db, seeded):
    """Steerco ownership is per contributing squad, so co-leading is enough."""
    from tests.test_steerco import _enable, _platform

    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    _enable(client)
    pid = _platform(db, seeded, squads=("squad_a",))

    login(client, seeded["sl_b"])
    assert client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                      json={"kpis": [{"label": "Cloud Users", "value": "1"}]}).status_code == 403

    login(client, seeded["tribe"])
    _add_coleader(client, seeded["squad_a"], sl_b.id)

    login(client, seeded["sl_b"])
    r = client.put(f"/api/steerco/platform/{pid}?period=2026-07",
                   json={"kpis": [{"label": "Cloud Users", "value": "1"}]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["kpis"][0]["value"] == "1"


def test_the_squad_list_carries_the_co_leaders(client, db, seeded):
    """The screens read the list from the ORM property, not from a hand-built payload."""
    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    login(client, seeded["tribe"])
    _add_coleader(client, seeded["squad_a"], sl_b.id)

    rows = {s["id"]: s for s in client.get("/api/squads").json()}
    assert rows[seeded["squad_a"]]["co_leader_user_ids"] == [sl_b.id]
    assert rows[seeded["squad_b"]]["co_leader_user_ids"] == []


def test_deleting_a_co_leader_account_leaves_the_squad_standing(client, db, seeded):
    """A co-leadership is a link to the person, not a piece of the squad.

    The purge policy refuses to guess about a new non-nullable reference to users,
    which is how this one got classified rather than surfacing as a 500 in front of
    an administrator deleting an account.
    """
    sl_b = db.scalar(select(User).where(User.email == seeded["sl_b"]))
    login(client, seeded["tribe"])
    _add_coleader(client, seeded["squad_a"], sl_b.id)

    login(client, "admin@test")
    r = client.delete(f"/api/admin/users/{sl_b.id}")
    assert r.status_code in (200, 204), r.text

    db.expire_all()
    squad = db.get(Squad, seeded["squad_a"])
    assert squad is not None and squad.co_leaders == []
    assert squad.leader_user_id is not None          # its own leader is untouched
