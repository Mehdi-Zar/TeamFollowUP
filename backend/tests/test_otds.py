"""OTD (dedicated `otds` entity) access rules - goal #4:
managed by the tribe leader (or admin); visible ONLY by the squad leader of a
squad the OTD groups a milestone from; invisible to everyone else."""
from datetime import datetime, timezone

from tests.conftest import login

YEAR = datetime.now(timezone.utc).year


def _mk_jalon(client, squad_id):
    r = client.post("/api/roadmap-items", json={
        "squad_id": squad_id, "year": YEAR, "quarter": 1, "title": "J", "theme": "LZ"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ids(resp):
    return {o["id"] for o in resp.json()}


def test_otd_management_and_visibility(client, seeded):
    # Squad leader A adds a milestone on squad A.
    login(client, seeded["sl_a"])
    jid = _mk_jalon(client, seeded["squad_a"])

    # Squad leaders cannot create an OTD - management is tribe leader / admin only.
    assert client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR,
                                          "title": "nope"}).status_code == 403

    # Tribe leader creates an OTD in their tribe and attaches squad A's milestone.
    login(client, seeded["tribe"])
    r = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "OTD-1"})
    assert r.status_code == 201, r.text
    otd_id = r.json()["id"]
    assert client.put(f"/api/otds/{otd_id}/jalons", json={"jalon_ids": [jid]}).status_code == 200

    # The concerned squad leader (A) sees it.
    login(client, seeded["sl_a"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))

    # Another squad's leader (B, same tribe) does NOT.
    login(client, seeded["sl_b"])
    assert otd_id not in _ids(client.get(f"/api/otds?year={YEAR}"))

    # A plain member sees no OTDs at all.
    login(client, seeded["member"])
    assert client.get(f"/api/otds?year={YEAR}").json() == []

    # The tribe leader (manager) sees it.
    login(client, seeded["tribe"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))

    # Admin sees it too.
    login(client, seeded["admin"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))


def test_otd_owner_must_be_squad_leader_of_the_tribe(client, seeded):
    """Assigning an owner from another tribe (or a non-squad-leader) is rejected -
    otherwise a foreign squad leader would see this tribe's OTD."""
    login(client, seeded["tribe"])  # tribe leader of t1
    # sl_b leads a squad in t1 → allowed.
    ok = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR,
                                        "title": "OK", "owner_user_id": seeded["sl_b_id"]})
    assert ok.status_code == 201, ok.text
    # A member (not a squad leader) → rejected.
    bad_role = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR,
                                              "title": "bad", "owner_user_id": seeded["member_id"]})
    assert bad_role.status_code == 400, bad_role.text
    # sl_a leads a squad in t1 but is assigned to a t2 OTD → rejected (cross-tribe).
    login(client, seeded["admin"])
    foreign_sl = client.post("/api/otds", json={"tribe_id": seeded["t2"], "year": YEAR,
                                                "title": "foreign", "owner_user_id": seeded["sl_a_id"]})
    assert foreign_sl.status_code == 400, foreign_sl.text
