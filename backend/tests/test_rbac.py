from tests.conftest import login

YEAR = 2026


def fresh_client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_member_is_read_only(client, seeded):
    login(client, seeded["member"])
    assert client.get("/api/dashboard").status_code == 200
    assert client.get(f"/api/squads/{seeded['squad_a']}").status_code == 200
    r = client.post("/api/roadmap-items", json={"squad_id": seeded["squad_a"], "year": YEAR, "quarter": 1, "title": "X"})
    assert r.status_code == 403


def test_squad_leader_edits_only_own_roadmap(client, seeded):
    login(client, seeded["sl_a"])
    ok = client.post("/api/roadmap-items", json={"squad_id": seeded["squad_a"], "year": YEAR, "quarter": 1, "title": "Mine"})
    assert ok.status_code == 201, ok.text
    ko = client.post("/api/roadmap-items", json={"squad_id": seeded["squad_b"], "year": YEAR, "quarter": 1, "title": "No"})
    assert ko.status_code == 403


def test_squad_leader_cannot_manage_objectives(client, seeded):
    login(client, seeded["sl_a"])
    # objectives are set by the tribe leader, even for the leader's own squad
    r = client.post("/api/objectives", json={"squad_id": seeded["squad_a"], "year": YEAR, "title": "Obj"})
    assert r.status_code == 403


def test_tribe_leader_manages_objectives_and_squads(client, seeded):
    login(client, seeded["tribe"])
    o = client.post("/api/objectives", json={"squad_id": seeded["squad_a"], "year": YEAR, "title": "Obj"})
    assert o.status_code == 201, o.text
    s = client.post("/api/squads", json={"name": "New squad"})
    assert s.status_code == 201
    n = client.post("/api/org", json={"title": "Racine"})
    assert n.status_code == 201


def test_tribe_leader_manages_users_but_not_global_config(client, seeded):
    login(client, seeded["tribe"])
    # Tribe leaders now manage users (scoped to their tribe)...
    assert client.get("/api/admin/users").status_code == 200
    # ...but global configuration stays admin-only.
    assert client.get("/api/admin/settings").status_code == 403
    assert client.get("/api/admin/modules-config").status_code == 403


def test_squad_leader_manages_own_members(client, seeded):
    login(client, seeded["sl_a"])
    ok = client.post("/api/members", json={"squad_id": seeded["squad_a"], "full_name": "Alice"})
    assert ok.status_code == 201, ok.text
    ko = client.post("/api/members", json={"squad_id": seeded["squad_b"], "full_name": "Bob"})
    assert ko.status_code == 403


def test_org_editing_requires_tribe_or_admin(client, seeded):
    login(client, seeded["sl_a"])
    assert client.post("/api/org", json={"title": "X"}).status_code == 403
    # but anyone authenticated can read the org chart
    assert client.get("/api/org").status_code == 200


def test_admin_can_do_everything(client, seeded):
    login(client, seeded["admin"])
    assert client.post("/api/objectives", json={"squad_id": seeded["squad_a"], "year": YEAR, "title": "A"}).status_code == 201
    assert client.get("/api/admin/users").status_code == 200
    assert client.post("/api/org", json={"title": "Root", "tribe_id": seeded["t1"]}).status_code == 201


def test_feed_member_can_reply_not_post(client, seeded):
    # a leader posts
    login(client, seeded["sl_a"])
    post = client.post("/api/feed", json={"content": "Incident", "kind": "incident", "squad_id": seeded["squad_a"]})
    assert post.status_code == 201, post.text
    pid = post.json()["id"]

    # member cannot post but can reply + react
    login(client, seeded["member"])
    assert client.post("/api/feed", json={"content": "x"}).status_code == 403
    assert client.post(f"/api/feed/{pid}/replies", json={"content": "ok"}).status_code == 201
    r = client.post(f"/api/feed/{pid}/reactions", json={"kind": "like"})
    assert r.status_code == 200 and r.json()["reactions"]["like"] == 1
    # toggling off
    r2 = client.post(f"/api/feed/{pid}/reactions", json={"kind": "like"})
    assert r2.json()["reactions"]["like"] == 0


def test_delete_squad_with_org_and_feed_references(client, seeded):
    login(client, seeded["admin"])
    sid = seeded["squad_a"]
    # an org node and a feed post reference the squad
    node = client.post("/api/org", json={"title": "Squad A", "squad_id": sid, "tribe_id": seeded["t1"]})
    assert node.status_code == 201
    post = client.post("/api/feed", json={"content": "incident", "kind": "incident", "squad_id": sid})
    assert post.status_code == 201
    # deletion must succeed (references detached, not blocking)
    assert client.delete(f"/api/squads/{sid}").status_code == 204
    # org node survives, detached from the squad
    tree = client.get("/api/org").json()
    assert any(n["title"] == "Squad A" and n["squad_id"] is None for n in tree)


def test_dashboard_scoped_to_own_tribe(client, seeded):
    login(client, seeded["tribe"])  # tribe leader of T1
    cards = client.get("/api/dashboard").json()["cards"]
    ids = {c["squad_id"] for c in cards}
    assert seeded["squad_a"] in ids and seeded["squad_b"] in ids
    assert seeded["squad_c"] not in ids  # other tribe hidden


def test_admin_sees_all_tribes(client, seeded):
    login(client, seeded["admin"])
    ids = {c["squad_id"] for c in client.get("/api/dashboard").json()["cards"]}
    assert seeded["squad_c"] in ids


def test_tribe_leader_cannot_touch_other_tribe(client, seeded):
    login(client, seeded["tribe"])  # T1
    # squad in T2 is out of scope
    assert client.get(f"/api/squads/{seeded['squad_c']}").status_code == 403
    assert client.post("/api/objectives", json={"squad_id": seeded["squad_c"], "year": YEAR, "title": "x"}).status_code == 403


def test_squad_leader_scoped_squads_list(client, seeded):
    login(client, seeded["sl_a"])
    ids = {s["id"] for s in client.get("/api/squads").json()}
    assert seeded["squad_c"] not in ids


def test_admin_crud_tribe_others_cannot(client, seeded):
    login(client, seeded["admin"])
    assert client.post("/api/tribes", json={"name": "New Tribe"}).status_code == 201
    assert client.get("/api/tribes/org-overview").status_code == 200
    login(client, seeded["tribe"])
    assert client.post("/api/tribes", json={"name": "X"}).status_code == 403
    assert client.get("/api/tribes/org-overview").status_code == 403


def test_feed_scoped_by_tribe(client, seeded):
    # tribe2 leader posts in T2; T1 member must not see it
    login(client, seeded["tribe2"])
    assert client.post("/api/feed", json={"content": "T2 only", "kind": "info"}).status_code == 201
    login(client, seeded["member"])  # T1
    contents = [p["content"] for p in client.get("/api/feed").json()]
    assert "T2 only" not in contents


def test_unauthenticated_rejected(client, seeded):
    assert fresh_client().get("/api/dashboard").status_code == 401
