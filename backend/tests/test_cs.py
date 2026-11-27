"""Customer Success projects (ADR 0020, docs/37): who may do what, the computed
facts (blocker, next action, last contact, badges) and the recap mail."""
from datetime import date, timedelta

from app.models import CsLeader, User
from tests.conftest import login


def _enable(client):
    login(client, "admin@test")
    r = client.put("/api/admin/modules-config", json={"customer_success": {"enabled": True}})
    assert r.status_code == 200, r.text


def _project(client, tid, **kw):
    r = client.post("/api/cs/projects", json={"tribe_id": tid, "title": "Gemini + Antigravity",
                                              "client": "Entité A", **kw})
    assert r.status_code == 201, r.text
    return r.json()


# ---- module and access ---------------------------------------------------------

def test_module_is_off_by_default(client, seeded):
    login(client, "admin@test")
    assert client.get("/api/cs/projects", params={"tribe_id": seeded["t1"]}).status_code == 404


def test_tribe_leader_runs_by_default_and_member_sees_nothing(client, seeded):
    _enable(client)
    login(client, "tribe@test")
    p = _project(client, seeded["t1"])
    assert p["can_run"] and p["stage"] == "request"
    me = client.get("/api/auth/me/permissions").json()["customer_success"]
    assert me["run"] and me["run_tribe_ids"] == [seeded["t1"]]
    login(client, "member@test")
    assert client.get("/api/cs/projects", params={"tribe_id": seeded["t1"]}).status_code == 403
    assert client.get(f"/api/cs/projects/{p['id']}").status_code == 404
    # The other tribe's leader does not run tribe 1.
    login(client, "tribe2@test")
    r = client.post("/api/cs/projects", json={"tribe_id": seeded["t1"], "title": "x"})
    assert r.status_code == 403


def test_designated_leader_runs_and_cannot_designate(client, seeded, db):
    _enable(client)
    login(client, "tribe@test")
    r = client.post("/api/cs/leaders", json={"tribe_id": seeded["t1"], "user_id": seeded["member_id"]})
    assert r.status_code == 201, r.text
    login(client, "member@test")
    _project(client, seeded["t1"])
    r = client.post("/api/cs/leaders", json={"tribe_id": seeded["t1"], "user_id": seeded["sl_a_id"]})
    assert r.status_code == 403


def test_only_admin_withdraws_the_tribe_leader_default(client, seeded, db):
    _enable(client)
    tl = db.query(User).filter(User.email == "tribe@test").one()
    login(client, "tribe@test")
    assert client.delete(f"/api/cs/leaders/{tl.id}", params={"tribe_id": seeded["t1"]}).status_code == 403
    login(client, "admin@test")
    r = client.delete(f"/api/cs/leaders/{tl.id}", params={"tribe_id": seeded["t1"]})
    assert r.status_code == 200
    assert db.query(CsLeader).filter(CsLeader.user_id == tl.id).one().excluded
    login(client, "tribe@test")
    r = client.post("/api/cs/projects", json={"tribe_id": seeded["t1"], "title": "x"})
    assert r.status_code == 403


def test_reader_capability_reads_without_writing(client, seeded):
    _enable(client)
    personas = client.get("/api/admin/personas").json()["personas"]
    for p in personas:
        if p["key"] == "member":
            p["caps"]["customer_success"] = True
    assert client.put("/api/admin/personas", json={"personas": personas}).status_code == 200
    login(client, "tribe@test")
    p = _project(client, seeded["t1"])
    login(client, "member@test")
    rows = client.get("/api/cs/projects", params={"tribe_id": seeded["t1"]}).json()
    assert [r["id"] for r in rows] == [p["id"]] and rows[0]["can_edit"] is False
    assert client.put(f"/api/cs/projects/{p['id']}", json={"title": "y"}).status_code == 403


def test_contributor_sees_and_fills_only_their_project(client, seeded):
    _enable(client)
    login(client, "tribe@test")
    mine = _project(client, seeded["t1"], contributor_user_ids=[seeded["sl_a_id"]])
    other = _project(client, seeded["t1"], title="Autre")
    login(client, "sl_a@test")
    rows = client.get("/api/cs/projects", params={"tribe_id": seeded["t1"]}).json()
    assert [r["id"] for r in rows] == [mine["id"]]
    assert client.get(f"/api/cs/projects/{other['id']}").status_code == 404
    assert client.put(f"/api/cs/projects/{mine['id']}", json={"health": "red"}).status_code == 200
    assert client.post(f"/api/cs/projects/{mine['id']}/journal",
                       json={"kind": "note", "text": "ok"}).status_code == 201
    # Contributors cannot change who contributes, delete, or touch the settings.
    assert client.put(f"/api/cs/projects/{mine['id']}",
                      json={"contributor_user_ids": []}).status_code == 403
    assert client.delete(f"/api/cs/projects/{mine['id']}").status_code == 403
    assert client.put("/api/cs/settings", params={"tribe_id": seeded["t1"]},
                      json={"stale_days": 3}).status_code == 403
    assert client.get("/api/cs/settings", params={"tribe_id": seeded["t1"]}).status_code == 200


def test_contributor_must_belong_to_the_tribe(client, seeded, db):
    _enable(client)
    other = db.query(User).filter(User.email == "tribe2@test").one()
    login(client, "tribe@test")
    r = client.post("/api/cs/projects", json={"tribe_id": seeded["t1"], "title": "x",
                                              "contributor_user_ids": [other.id]})
    assert r.status_code == 400


# ---- the card and the computed facts --------------------------------------------

def test_card_fields_round_trip_and_validation(client, seeded):
    _enable(client)
    p = _project(client, seeded["t1"], offer="Offre IA", build_amount="7 000", quote_signed=True,
                 consumption_billing="uncapped", users_count=23, data_classification="C2",
                 access_end="2027-01-19", tags=["IA", "ia", "Pilote"],
                 contacts=[{"name": "Personne A", "role": "Sponsor"}, {"name": ""}],
                 links=[{"label": "Devis", "url": "https://example.test/devis"}],
                 milestones={"proposal": {"planned": "2026-09-24", "actual": "2026-09-24"},
                             "unknown": {"planned": "2026-01-01"}})
    assert p["build_amount"] == 7000.0 and p["users_count"] == 23
    assert p["tags"] == ["IA", "Pilote"] and len(p["contacts"]) == 1
    assert list(p["milestones"]) == ["proposal"]
    pid = p["id"]
    assert client.put(f"/api/cs/projects/{pid}", json={"stage": "nope"}).status_code == 400
    assert client.put(f"/api/cs/projects/{pid}", json={"health": "pink"}).status_code == 400
    assert client.put(f"/api/cs/projects/{pid}", json={"access_end": "19/01/2027"}).status_code == 400
    r = client.put(f"/api/cs/projects/{pid}", json={"links": [{"url": "javascript:alert(1)"}]})
    assert r.status_code == 400
    assert client.put(f"/api/cs/projects/{pid}", json={"title": " "}).status_code == 400


def test_blocker_next_action_last_contact(client, seeded):
    _enable(client)
    p = _project(client, seeded["t1"])
    pid = p["id"]
    today = date.today()
    client.post(f"/api/cs/projects/{pid}/journal",
                json={"kind": "decision", "date": (today - timedelta(days=40)).isoformat(),
                      "people": "Personne B", "text": "OK pour 3 mois"})
    client.post(f"/api/cs/projects/{pid}/items",
                json={"kind": "blocker", "label": "Dérogation sécurité", "owner": "RSSI",
                      "opened_on": (today - timedelta(days=14)).isoformat()})
    client.post(f"/api/cs/projects/{pid}/items",
                json={"kind": "action", "label": "Relancer", "due": (today + timedelta(days=5)).isoformat()})
    late = client.post(f"/api/cs/projects/{pid}/items",
                       json={"kind": "action", "label": "Envoyer le devis",
                             "due": (today - timedelta(days=1)).isoformat()}).json()
    got = client.get(f"/api/cs/projects/{pid}").json()
    assert got["blocked"] and got["blocker"]["label"] == "Dérogation sécurité"
    assert got["blocker"]["days"] == 14
    assert got["next_action"]["label"] == "Envoyer le devis" and got["next_action"]["overdue"]
    assert got["last_contact"] == (today - timedelta(days=40)).isoformat()
    assert got["stale"] and got["overdue_items"] == 1
    # The decision is in the recap by default, a note would not be.
    assert got["journal"][0]["in_recap"] is True
    client.put(f"/api/cs/items/{late['id']}", json={"done": True})
    got = client.get(f"/api/cs/projects/{pid}").json()
    assert got["next_action"]["label"] == "Relancer" and got["overdue_items"] == 0
    dash = client.get("/api/cs/dashboard", params={"tribe_id": seeded["t1"]}).json()
    assert dash["open"] == 1 and dash["blocked"] == 1 and dash["stale"] == 1


def test_delivered_projects_are_not_stale_and_access_badge(client, seeded):
    _enable(client)
    soon = (date.today() + timedelta(days=10)).isoformat()
    p = _project(client, seeded["t1"], stage="delivered", access_end=soon,
                 actual_delivery=date.today().isoformat(), build_amount=7000, quote_signed=True)
    assert p["closed"] and not p["stale"] and p["access_soon"]
    dash = client.get("/api/cs/dashboard", params={"tribe_id": seeded["t1"]}).json()
    assert dash["open"] == 0 and dash["delivered_year"] == 1 and dash["access_soon"] == 1
    assert dash["build_signed"] == 7000.0


# ---- settings -----------------------------------------------------------------

def test_stages_are_editable_but_a_used_one_stays(client, seeded):
    _enable(client)
    tid = seeded["t1"]
    _project(client, tid)  # stage "request"
    cfg = client.get("/api/cs/settings", params={"tribe_id": tid}).json()
    stages = cfg["stages"]
    renamed = [dict(s, label="Nouvelle demande") if s["key"] == "request" else s for s in stages]
    r = client.put("/api/cs/settings", params={"tribe_id": tid}, json={"stages": renamed, "offers": ["A", "a", "B"]})
    assert r.status_code == 200 and r.json()["stages"][0]["label"] == "Nouvelle demande"
    assert r.json()["offers"] == ["A", "B"]
    r = client.put("/api/cs/settings", params={"tribe_id": tid},
                   json={"stages": [s for s in stages if s["key"] != "request"]})
    assert r.status_code == 409
    assert client.put("/api/cs/settings", params={"tribe_id": tid}, json={"stages": []}).status_code == 400


# ---- the recap ----------------------------------------------------------------

def test_recap_is_the_mail_and_escapes(client, seeded):
    _enable(client)
    tid = seeded["t1"]
    client.put("/api/cs/settings", params={"tribe_id": tid},
               json={"recap_intro": "Bonjour,\n\nRécap des sujets <IA>."})
    p = _project(client, tid, requesters="Personne A", gcp_project="prj-demo",
                 build_amount=7000, quote_signed=True)
    client.post(f"/api/cs/projects/{p['id']}/journal",
                json={"kind": "proposal", "date": "2026-09-24", "text": "7 000 € HT <b>build</b>"})
    client.post(f"/api/cs/projects/{p['id']}/journal",
                json={"kind": "note", "date": "2026-09-25", "text": "petite relance"})
    client.post(f"/api/cs/projects/{p['id']}/items", json={"kind": "blocker", "label": "Dérogation"})
    html = client.get("/api/cs/recap.html", params={"tribe_id": tid}).text
    assert "En résumé" in html and "prj-demo" in html and "En attente : Dérogation" in html
    assert "&lt;b&gt;build&lt;/b&gt;" in html and "<b>build</b>" not in html
    assert "&lt;IA&gt;" in html
    assert "petite relance" not in html  # a note is not in the recap by default
    assert "Proposition (24/09)" in html
    assert "Nouveau" not in html  # never marked: nothing reads "new"
    assert chr(0x2014) not in html and chr(0xB7) not in html
    # Mark it sent: what is added next reads "Nouveau".
    assert client.post("/api/cs/recap/mark", params={"tribe_id": tid}).status_code == 200
    client.post(f"/api/cs/projects/{p['id']}/journal", json={"kind": "decision", "text": "GO"})
    html = client.get("/api/cs/recap.html", params={"tribe_id": tid}).text
    assert html.count("Nouveau") == 1
    en = client.get("/api/cs/recap.html", params={"tribe_id": tid, "lang": "en"}).text
    assert "Summary" in en and "Waiting for: Dérogation" in en


def test_recap_filters(client, seeded):
    _enable(client)
    tid = seeded["t1"]
    a = _project(client, tid, title="Alpha", offer="Offre IA")
    _project(client, tid, title="Beta", offer="Autre")
    html = client.get("/api/cs/recap.html", params={"tribe_id": tid, "offer": "Offre IA"}).text
    assert "Alpha" in html and "Beta" not in html
    html = client.get("/api/cs/recap.html", params={"tribe_id": tid, "projects": str(a["id"])}).text
    assert "Alpha" in html and "Beta" not in html


def test_deleting_a_user_keeps_projects(client, seeded, db):
    _enable(client)
    login(client, "tribe@test")
    r = client.post("/api/cs/leaders", json={"tribe_id": seeded["t1"], "user_id": seeded["member_id"]})
    assert r.status_code == 201
    p = _project(client, seeded["t1"], contributor_user_ids=[seeded["member_id"]])
    login(client, "admin@test")
    r = client.delete(f"/api/admin/users/{seeded['member_id']}")
    assert r.status_code in (200, 204), r.text
    got = client.get(f"/api/cs/projects/{p['id']}").json()
    assert got["contributors"] == []
