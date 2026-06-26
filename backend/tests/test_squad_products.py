"""Squad product / hardware lists: set on create or edit, returned on the detail."""
from .conftest import login


def test_create_squad_with_products_and_hardware(seeded, client):
    login(client, seeded["tribe"])
    r = client.post("/api/squads", json={
        "name": "Edge Computing", "tribe_id": seeded["t1"],
        "products": ["Morpheus", "OneEdge", "DAP"], "hardware": ["DELL VxRAIL"]})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    d = client.get(f"/api/squads/{sid}").json()
    assert d["products"] == ["Morpheus", "OneEdge", "DAP"]
    assert d["hardware"] == ["DELL VxRAIL"]


def test_edit_products_and_hardware(seeded, client):
    login(client, seeded["tribe"])
    sa = seeded["squad_a"]
    client.put(f"/api/squads/{sa}", json={"products": ["GCP", "S3NS"], "hardware": []})
    d = client.get(f"/api/squads/{sa}").json()
    assert d["products"] == ["GCP", "S3NS"] and d["hardware"] == []


def test_squad_leader_can_edit_own_products(seeded, client):
    login(client, seeded["sl_a"])
    sa = seeded["squad_a"]
    r = client.put(f"/api/squads/{sa}", json={"products": ["Azure"]})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/squads/{sa}").json()["products"] == ["Azure"]
