"""Leading a squad is a job, not a persona; and every call opens on the same year."""
from sqlalchemy import select

from app.models import User
from tests.conftest import login

YEAR = 2026


def _uid(db, email):
    return db.scalar(select(User).where(User.email == email)).id


def test_a_tribe_leader_named_at_the_head_of_a_squad_fills_it_in(client, seeded, db):
    tribe_id = _uid(db, seeded["tribe"])
    sq = seeded["squad_b"]
    login(client, seeded["tribe"])
    assert client.put(f"/api/squads/{sq}", json={"leader_user_id": tribe_id}).status_code == 200

    caps = client.get("/api/auth/me/permissions").json()["capabilities"]
    assert caps["reporting"] is True
    r = client.post("/api/roadmap-items", json={
        "squad_id": sq, "title": "Jalon", "quarter": 1, "year": YEAR, "theme": "Socle"})
    assert r.status_code == 201, r.text
    # The OTD carried by that leader is accepted, whatever their role.
    r = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "OTD",
                                       "squad_id": sq, "owner_user_id": tribe_id})
    assert r.status_code == 201, r.text
    assert client.post(f"/api/squads/{sq}/snapshots", json={"year": YEAR}).status_code == 201

    # A squad they do not lead stays closed to their submission.
    assert client.post(f"/api/squads/{seeded['squad_a']}/snapshots", json={"year": YEAR}).status_code == 403


def test_the_owner_of_an_otd_must_lead_a_squad_of_the_tribe(client, seeded, db):
    login(client, seeded["tribe"])
    r = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "OTD",
                                       "owner_user_id": seeded["member_id"]})
    assert r.status_code == 400


def test_otds_stay_inside_their_tribe(client, seeded):
    login(client, seeded["tribe"])
    otd = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "OTD"}).json()["id"]
    login(client, seeded["tribe2"])
    assert otd not in [o["id"] for o in client.get(f"/api/otds?year={YEAR}").json()]


def test_a_leader_sees_the_squad_they_lead_in_another_tribe(client, seeded, db):
    sl_a = _uid(db, seeded["sl_a"])
    login(client, seeded["admin"])
    assert client.put(f"/api/squads/{seeded['squad_c']}", json={"leader_user_id": sl_a}).status_code == 200
    login(client, seeded["sl_a"])
    assert seeded["squad_c"] in [s["id"] for s in client.get("/api/squads").json()]
    assert client.get(f"/api/squads/{seeded['squad_c']}").status_code == 200
    # ... and only that one.
    login(client, seeded["sl_b"])
    assert client.get(f"/api/squads/{seeded['squad_c']}").status_code == 403


def test_the_year_left_out_is_the_instance_default_year(client, seeded):
    login(client, seeded["admin"])
    assert client.put("/api/admin/settings", json={"default_year": 2031}).status_code == 200
    assert client.get(f"/api/squads/{seeded['squad_a']}").json()["year"] == 2031
    assert client.get("/api/dashboard").json()["year"] == 2031


def test_a_contributor_does_the_reporting_and_nothing_else(client, seeded, db):
    member_id = seeded["member_id"]
    sq = seeded["squad_a"]
    # The squad's own leader names a contributor: a member becomes "contributor".
    login(client, seeded["sl_a"])
    r = client.put(f"/api/squads/{sq}", json={"contributor_user_ids": [member_id]})
    assert r.status_code == 200, r.text
    assert r.json()["contributor_user_ids"] == [member_id]
    detail = client.get(f"/api/squads/{sq}").json()
    assert [c["id"] for c in detail["contributors"]] == [member_id]

    login(client, seeded["member"])
    assert client.get("/api/auth/me").json()["role"] == "contributor"
    assert client.get("/api/auth/me/permissions").json()["capabilities"]["reporting"] is True
    # The reporting: milestones, key messages, mood, the squad's OTD, submission.
    assert client.post("/api/roadmap-items", json={
        "squad_id": sq, "title": "Jalon", "quarter": 1, "year": YEAR, "theme": "Socle"}).status_code == 201
    assert client.post(f"/api/squads/{sq}/key-messages?year={YEAR}",
                       json={"kind": "success", "text": "Livré"}).status_code == 201
    assert client.put(f"/api/squads/{sq}/mood", json={"mood": "good"}).status_code == 200
    assert client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "OTD squad",
                                          "scope": "squad", "squad_id": sq}).status_code == 201
    assert client.post(f"/api/squads/{sq}/snapshots", json={"year": YEAR}).status_code == 201
    # ... and not the set-up: squad fields, contributors, team, budget.
    assert client.put(f"/api/squads/{sq}", json={"description": "x"}).status_code == 403
    assert client.put(f"/api/squads/{sq}", json={"contributor_user_ids": []}).status_code == 403
    assert client.post("/api/members", json={"squad_id": sq, "full_name": "X"}).status_code == 403
    # Nor another squad's reporting.
    assert client.post("/api/roadmap-items", json={
        "squad_id": seeded["squad_b"], "title": "J", "quarter": 1, "year": YEAR, "theme": "Socle"}).status_code == 403


def test_contributors_stay_inside_the_tribe(client, seeded, db):
    tribe2 = _uid(db, seeded["tribe2"])
    login(client, seeded["sl_a"])
    assert client.put(f"/api/squads/{seeded['squad_a']}",
                      json={"contributor_user_ids": [tribe2]}).status_code == 400


def test_the_squad_detail_names_its_contributors_by_id(client, seeded):
    """The saisie recognises a contributor by these ids: without them it showed the
    squad read-only to the very person meant to fill it in."""
    login(client, seeded["sl_a"])
    client.put(f"/api/squads/{seeded['squad_a']}", json={"contributor_user_ids": [seeded["member_id"]]})
    detail = client.get(f"/api/squads/{seeded['squad_a']}").json()
    assert detail["contributor_user_ids"] == [seeded["member_id"]]


def test_a_contributor_attaches_milestones_to_the_squad_commitment(client, seeded):
    login(client, seeded["sl_a"])
    sq = seeded["squad_a"]
    client.put(f"/api/squads/{sq}", json={"contributor_user_ids": [seeded["member_id"]]})
    jid = client.post("/api/roadmap-items", json={
        "squad_id": sq, "title": "J", "quarter": 1, "year": YEAR, "theme": "Socle"}).json()["id"]
    login(client, seeded["member"])
    rows = client.get(f"/api/otds/candidate-jalons?year={YEAR}&squad_id={sq}").json()
    assert [r["id"] for r in rows] == [jid]
    # Not another squad's milestones.
    assert client.get(f"/api/otds/candidate-jalons?year={YEAR}&squad_id={seeded['squad_b']}").json() == []


def test_a_contributor_named_co_leader_becomes_squad_leader(client, seeded, db):
    sq = seeded["squad_a"]
    login(client, seeded["sl_a"])
    client.put(f"/api/squads/{sq}", json={"contributor_user_ids": [seeded["member_id"]]})
    login(client, seeded["tribe"])
    r = client.put(f"/api/squads/{sq}", json={"co_leader_user_ids": [seeded["member_id"]]}).json()
    assert r["contributor_user_ids"] == []
    login(client, seeded["member"])
    assert client.get("/api/auth/me").json()["role"] == "squad_leader"


def test_back_to_member_drops_the_squad_roles(client, seeded):
    sq = seeded["squad_a"]
    login(client, seeded["sl_a"])
    client.put(f"/api/squads/{sq}", json={"contributor_user_ids": [seeded["member_id"]]})
    login(client, seeded["admin"])
    assert client.put(f"/api/admin/users/{seeded['member_id']}", json={"role": "member"}).status_code == 200
    login(client, seeded["sl_a"])
    assert client.get(f"/api/squads/{sq}").json()["contributor_user_ids"] == []


def test_the_change_mail_setting_is_the_admins_only(client, seeded):
    login(client, seeded["tribe"])
    assert client.get("/api/admin/change-notify-config").status_code == 403
    assert client.put("/api/admin/change-notify-config", json={"enabled": True}).status_code == 403


def test_naming_a_member_leader_promotes_them(client, seeded):
    login(client, seeded["tribe"])
    r = client.put(f"/api/squads/{seeded['squad_b']}", json={"leader_user_id": seeded["member_id"]})
    assert r.status_code == 200, r.text
    login(client, seeded["member"])
    assert client.get("/api/auth/me").json()["role"] == "squad_leader"


def test_the_squad_document_names_its_co_leaders_and_contributors(client, seeded):
    sq = seeded["squad_a"]
    login(client, seeded["tribe"])
    client.put(f"/api/squads/{sq}", json={"co_leader_user_ids": [seeded["sl_b_id"]]})
    client.put(f"/api/squads/{sq}", json={"contributor_user_ids": [seeded["member_id"]]})
    html = client.get(f"/api/reports/dashboard.html?squad_id={sq}&lang=fr").text
    assert "Co-leaders : SL B" in html and "Contributeurs : Member" in html


def test_a_tribe_leader_leading_a_squad_of_another_tribe_only_leads_it(client, seeded, db):
    tribe2 = _uid(db, seeded["tribe2"])
    sq = seeded["squad_b"]  # tribe 1
    login(client, seeded["admin"])
    assert client.put(f"/api/squads/{sq}", json={"leader_user_id": tribe2}).status_code == 200
    login(client, seeded["tribe2"])
    # Leading: the reporting, its history, its document.
    assert client.get(f"/api/squads/{sq}/snapshots/pending?year={YEAR}").status_code == 200
    assert client.get(f"/api/reports/dashboard.html?squad_id={sq}").status_code == 200
    jid = client.post("/api/roadmap-items", json={
        "squad_id": sq, "title": "J", "quarter": 1, "year": YEAR, "theme": "Socle"}).json()["id"]
    rows = client.get(f"/api/otds/candidate-jalons?year={YEAR}&squad_id={sq}").json()
    assert jid in [r["id"] for r in rows]
    # Not the set-up that belongs to that tribe's leader.
    assert client.put(f"/api/squads/{sq}", json={"display_order": 9}).status_code == 403
    assert client.put(f"/api/squads/{sq}", json={"budget_enabled": True}).status_code == 403


def test_deleting_a_squad_keeps_the_management_commitment_set_on_it(client, seeded):
    login(client, seeded["tribe"])
    otd = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "Tenu par la tribe",
                                         "squad_id": seeded["squad_b"]}).json()["id"]
    assert client.delete(f"/api/squads/{seeded['squad_b']}").status_code == 204
    assert otd in [o["id"] for o in client.get(f"/api/otds?year={YEAR}").json()]


def test_the_write_guard_turns_bad_input_into_a_clear_422(client, seeded):
    login(client, seeded["sl_a"])
    base = {"squad_id": seeded["squad_a"], "quarter": 1, "year": YEAR, "theme": "Socle"}
    r = client.post("/api/roadmap-items", json={**base, "title": "x" * 600})
    assert r.status_code == 422 and "titre" in r.json()["detail"]
    r = client.post("/api/roadmap-items", json={**base, "title": "   "})
    assert r.status_code == 422
    r = client.post("/api/roadmap-items", json={**base, "title": "J", "year": 99999})
    assert r.status_code == 422


def test_the_tribe_document_lists_the_commitments_no_squad_carries(client, seeded):
    login(client, seeded["tribe"])
    client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "Engagement orphelin"})
    html = client.get(f"/api/reports/dashboard.html?year={YEAR}&lang=fr").text
    assert "Engagement orphelin" in html and "portés par aucune squad" in html
