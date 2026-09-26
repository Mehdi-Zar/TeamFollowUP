from tests.conftest import login

YEAR = 2026


def test_submit_cycle_creates_immutable_snapshot(client, seeded):
    login(client, seeded["sl_a"])
    sid = seeded["squad_a"]

    jal = client.post("/api/roadmap-items", json={
        "squad_id": sid, "year": YEAR, "quarter": 2, "title": "Jalon 1", "status": "on_track",
        "theme": "Landing Zones",
    })
    assert jal.status_code == 201, jal.text

    resp = client.post(f"/api/squads/{sid}/snapshots", json={"cycle_label": "S1", "year": YEAR})
    assert resp.status_code == 201, resp.text
    snap = resp.json()
    assert snap["payload"]["roadmap_items"][0]["status"] == "on_track"

    client.put(f"/api/roadmap-items/{jal.json()['id']}", json={"status": "blocked"})

    fetched = client.get(f"/api/squads/{sid}/snapshots/{snap['id']}")
    assert fetched.json()["payload"]["roadmap_items"][0]["status"] == "on_track"
    assert client.put(f"/api/squads/{sid}/snapshots/{snap['id']}").status_code in (404, 405)


def test_snapshot_history_and_compare(client, seeded):
    login(client, seeded["sl_a"])
    sid = seeded["squad_a"]

    jal = client.post("/api/roadmap-items", json={
        "squad_id": sid, "year": YEAR, "quarter": 2, "title": "J", "status": "on_track",
        "theme": "Landing Zones",
    })
    first = client.post(f"/api/squads/{sid}/snapshots", json={"cycle_label": "C1", "year": YEAR}).json()
    client.put(f"/api/roadmap-items/{jal.json()['id']}", json={"status": "blocked"})
    second = client.post(f"/api/squads/{sid}/snapshots", json={"cycle_label": "C2", "year": YEAR}).json()

    history = client.get(f"/api/squads/{sid}/snapshots").json()
    assert len(history) == 2

    cmp = client.get(f"/api/squads/{sid}/snapshots/{second['id']}/compare").json()
    assert cmp["previous"]["id"] == first["id"]
    changes = cmp["diff"]["roadmap_items"]
    assert any(c["type"] == "changed" and "status" in c.get("fields", {}) for c in changes)


def test_quarter_progress_is_derived_from_milestones(client, seeded):
    login(client, seeded["sl_a"])
    sid = seeded["squad_a"]
    # Progress is auto-derived (share of the quarter's milestones done), not typed.
    for status in ("done", "on_track"):
        rr = client.post("/api/roadmap-items", json={
            "squad_id": sid, "year": YEAR, "quarter": 2, "title": "J", "theme": "X", "status": status})
        assert rr.status_code == 201, rr.text
    detail = client.get(f"/api/squads/{sid}?year={YEAR}").json()
    assert detail["quarter_progress"]["2"]["progress_pct"] == 50
