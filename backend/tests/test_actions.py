from tests.conftest import login


def test_squad_leader_crud_actions(client, seeded):
    sid = seeded["squad_a"]
    login(client, seeded["sl_a"])  # leads squad A
    r = client.post(f"/api/squads/{sid}/actions", json={"text": "Débloquer l'API", "owner": "Léo", "due_date": "2026-07-01"})
    assert r.status_code == 201
    aid = r.json()["id"]
    assert r.json()["done"] is False and r.json()["owner"] == "Léo"

    lst = client.get(f"/api/squads/{sid}/actions").json()
    assert any(a["id"] == aid for a in lst)

    assert client.put(f"/api/actions/{aid}", json={"done": True}).json()["done"] is True
    assert client.delete(f"/api/actions/{aid}").status_code == 204


def test_member_can_read_not_write(client, seeded):
    sid = seeded["squad_a"]
    login(client, seeded["sl_a"])
    client.post(f"/api/squads/{sid}/actions", json={"text": "x"})
    login(client, seeded["member"])  # same tribe → can read
    assert client.get(f"/api/squads/{sid}/actions").status_code == 200
    assert client.post(f"/api/squads/{sid}/actions", json={"text": "y"}).status_code == 403


def test_squad_leader_cannot_act_on_other_squad(client, seeded):
    login(client, seeded["sl_a"])  # leads squad A, not squad B
    assert client.post(f"/api/squads/{seeded['squad_b']}/actions", json={"text": "z"}).status_code == 403


def test_actions_gated_by_review_module(client, seeded):
    login(client, seeded["admin"])
    client.put("/api/admin/modules-config", json={"review": {"enabled": False}})
    assert client.get(f"/api/squads/{seeded['squad_a']}/actions").status_code == 404
