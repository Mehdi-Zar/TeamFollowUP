"""Squad members: the "reports to" link stays inside the squad and never loops,
and removing a manager does not strand the people who reported to them."""
from tests.conftest import login


def _add(client, squad_id, name, manager_id=None):
    r = client.post("/api/members", json={"squad_id": squad_id, "full_name": name, "manager_id": manager_id})
    return r


def test_manager_must_belong_to_the_same_squad(client, seeded):
    login(client, seeded["admin"])
    boss_b = _add(client, seeded["squad_b"], "Boss B").json()["id"]
    r = _add(client, seeded["squad_a"], "Alice", manager_id=boss_b)
    assert r.status_code == 422, r.text
    assert _add(client, seeded["squad_a"], "Alice", manager_id=999999).status_code == 422


def test_reporting_chain_cannot_loop(client, seeded):
    login(client, seeded["sl_a"])
    a = _add(client, seeded["squad_a"], "A").json()["id"]
    b = _add(client, seeded["squad_a"], "B", manager_id=a)
    assert b.status_code == 201, b.text
    b = b.json()["id"]
    assert client.put(f"/api/members/{a}", json={"manager_id": b}).status_code == 422
    assert client.put(f"/api/members/{a}", json={"manager_id": a}).status_code == 422
    assert client.put(f"/api/members/{b}", json={"manager_id": None}).status_code == 200


def test_deleting_a_manager_detaches_their_reports(client, seeded):
    login(client, seeded["sl_a"])
    boss = _add(client, seeded["squad_a"], "Boss").json()["id"]
    report = _add(client, seeded["squad_a"], "Report", manager_id=boss).json()["id"]
    assert client.delete(f"/api/members/{boss}").status_code == 204
    members = client.get(f"/api/squads/{seeded['squad_a']}").json()["members"]
    assert [(m["id"], m["manager_id"]) for m in members] == [(report, None)]


def test_member_name_is_required(client, seeded):
    login(client, seeded["sl_a"])
    assert _add(client, seeded["squad_a"], "").status_code == 422
    mid = _add(client, seeded["squad_a"], "Named").json()["id"]
    assert client.put(f"/api/members/{mid}", json={"full_name": None}).status_code == 422
    assert client.put(f"/api/members/{mid}", json={"full_name": "   "}).status_code == 422
    assert client.put(f"/api/members/{mid}", json={"full_name": "x" * 256}).status_code == 422


def test_squad_rename_refuses_empty_or_null(client, seeded):
    """The team window also renames the squad: an emptied field must not blank it,
    and an explicit null on a NOT NULL column is a 422, not a 500."""
    login(client, seeded["admin"])
    sid = seeded["squad_a"]
    assert client.put(f"/api/squads/{sid}", json={"name": ""}).status_code == 422
    assert client.put(f"/api/squads/{sid}", json={"name": "  "}).status_code == 422
    assert client.put(f"/api/squads/{sid}", json={"name": None}).status_code == 422
    assert client.put(f"/api/squads/{sid}", json={"kpis_enabled": None}).status_code == 422
    assert client.put(f"/api/squads/{sid}", json={"name": "Renamed"}).status_code == 200


# ---- the link to the login account, by email -----------------------------------

def test_adding_by_email_links_the_account_of_the_tribe(client, db, seeded):
    login(client, seeded["sl_a"])
    r = client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": " Member@Test "})
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["email"] == "member@test" and m["user_id"] == seeded["member_id"]
    assert m["full_name"] == "Member"                     # the account's name
    again = client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "member@test"})
    assert again.status_code == 409


def test_manual_email_with_names_links_at_first_login(client, db, seeded):
    from app.models import Member, User
    from app.security import hash_password
    login(client, seeded["sl_a"])
    r = client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "jean.dupont@test",
                                          "first_name": "Jean", "last_name": "Dupont"})
    assert r.status_code == 201, r.text
    assert r.json()["full_name"] == "Jean Dupont" and r.json()["user_id"] is None
    only_mail = client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "marie.curie@test"})
    assert only_mail.json()["full_name"] == "Marie Curie"
    assert client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "no mail"}).status_code == 422

    db.add(User(email="jean.dupont@test", display_name="J. Dupont", role="member",
                tribe_id=seeded["t1"], password_hash=hash_password("pw")))
    db.commit()
    login(client, "jean.dupont@test")
    db.expire_all()
    jean = db.get(Member, r.json()["id"])
    assert jean.user_id == db.query(User).filter_by(email="jean.dupont@test").one().id


def test_no_link_across_tribes(client, db, seeded):
    """Being someone's member hands their leaves to the squad leader: never across tribes."""
    login(client, seeded["sl_a"])
    r = client.post("/api/members", json={"squad_id": seeded["squad_a"], "email": "tribe2@test"})
    assert r.status_code == 409
    other = client.get(f"/api/members/candidates?squad_id={seeded['squad_a']}").json()
    assert "tribe2@test" not in [c["email"] for c in other]
    assert "member@test" in [c["email"] for c in other]


def test_changing_the_mood_keeps_its_comment(client, seeded):
    login(client, seeded["sl_a"])
    sid = seeded["squad_a"]
    client.put(f"/api/squads/{sid}/mood", json={"mood": "mixed", "comment": "Sprint difficile"})
    r = client.put(f"/api/squads/{sid}/mood", json={"mood": "bad"})
    assert r.status_code == 200 and r.json()["mood_comment"] == "Sprint difficile"
    r = client.put(f"/api/squads/{sid}/mood", json={"mood": None})
    assert r.json()["mood_comment"] is None


def test_pending_changes_since_the_last_submission(client, seeded):
    """The reporting says what changed since the squad last submitted, step by step."""
    from datetime import datetime, timezone
    year = datetime.now(timezone.utc).year
    login(client, seeded["sl_a"])
    sid = seeded["squad_a"]
    base = f"/api/squads/{sid}/snapshots"
    r = client.get(f"{base}/pending?year={year}").json()
    assert r["last"] is None and r["changed"]["mood"] is False
    client.put(f"/api/squads/{sid}/mood", json={"mood": "good"})
    assert client.get(f"{base}/pending?year={year}").json()["changed"]["mood"] is True
    assert client.post(base, json={"year": year}).status_code == 201
    r = client.get(f"{base}/pending?year={year}").json()
    assert r["last"] is not None and r["any"] is False
    client.put(f"/api/squads/{sid}/mood", json={"mood": "bad"})
    r = client.get(f"{base}/pending?year={year}").json()
    assert r["changed"]["mood"] is True and r["changed"]["roadmap"] is False


def test_compare_covers_what_the_reporting_submits(client, seeded):
    """Changing the mood and a key message shows in the history's comparison."""
    from datetime import datetime, timezone
    year = datetime.now(timezone.utc).year
    login(client, seeded["sl_a"])
    sid = seeded["squad_a"]
    base = f"/api/squads/{sid}/snapshots"
    client.put(f"/api/squads/{sid}/mood", json={"mood": "good"})
    assert client.post(base, json={"year": year}).status_code == 201
    client.put(f"/api/squads/{sid}/mood", json={"mood": "bad", "comment": "Rush"})
    client.post(f"/api/squads/{sid}/key-messages?year={year}", json={"kind": "risk", "text": "Retard fournisseur"})
    snap = client.post(base, json={"year": year}).json()["id"]
    diff = client.get(f"{base}/{snap}/compare").json()["diff"]
    assert diff["mood"][0]["fields"]["mood"] == {"from": "good", "to": "bad"}
    assert [c["type"] for c in diff["key_messages"]] == ["added"]
    assert "objectives" not in diff


def test_rewording_the_mood_keeps_its_date(client, seeded, db):
    from app.models import Squad
    from datetime import datetime, timezone, timedelta
    login(client, seeded["sl_a"])
    sid = seeded["squad_a"]
    client.put(f"/api/squads/{sid}/mood", json={"mood": "good"})
    sq = db.get(Squad, sid); old = datetime.now(timezone.utc) - timedelta(days=30)
    sq.mood_at = old; db.commit()
    assert client.put(f"/api/squads/{sid}/mood", json={"comment": "Rush"}).status_code == 200
    db.expire_all()
    got = db.get(Squad, sid)
    assert got.mood == "good" and got.mood_comment == "Rush"
    assert abs((got.mood_at.replace(tzinfo=timezone.utc) - old).total_seconds()) < 5
