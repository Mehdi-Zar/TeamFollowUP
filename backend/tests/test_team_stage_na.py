"""Time on the squad, role list, jalons outside a product release, quarters a
squad is not concerned by."""
from .conftest import login

YEAR = 2026


def test_member_allocation_defaults_to_full_time_and_is_bounded(seeded, client):
    sa = seeded["squad_a"]
    login(client, seeded["sl_a"])
    r = client.post("/api/members", json={"squad_id": sa, "full_name": "Alice", "role_title": "DevOps"})
    assert r.status_code == 201, r.text
    assert r.json()["allocation_pct"] == 100
    mid = r.json()["id"]
    assert client.put(f"/api/members/{mid}", json={"allocation_pct": 50}).json()["allocation_pct"] == 50
    assert client.put(f"/api/members/{mid}", json={"allocation_pct": 150}).status_code == 422
    r = client.post("/api/members", json={"squad_id": sa, "full_name": "Bob", "allocation_pct": 20})
    assert r.json()["allocation_pct"] == 20
    members = {m["full_name"]: m for m in client.get(f"/api/squads/{sa}?year={YEAR}").json()["members"]}
    assert members["Alice"]["allocation_pct"] == 50 and members["Bob"]["allocation_pct"] == 20


def test_role_list_is_set_by_the_admin_and_published(seeded, client):
    assert "Tech lead" in client.get("/api/config").json()["member_roles"]
    login(client, seeded["admin"])
    r = client.put("/api/admin/settings", json={"member_roles": [" Tech lead ", "tech lead", "", "Architecte", "SecOps"]})
    assert r.status_code == 200, r.text
    assert r.json()["member_roles"] == ["Tech lead", "Architecte", "SecOps"]
    assert client.get("/api/config").json()["member_roles"] == ["Tech lead", "Architecte", "SecOps"]
    # Emptied, the list falls back to the defaults rather than offering nothing.
    assert "DevOps" in client.put("/api/admin/settings", json={"member_roles": []}).json()["member_roles"]


def _jalon(client, sa, **kw):
    return client.post("/api/roadmap-items", json={
        "squad_id": sa, "year": YEAR, "quarter": 2, "title": "Comite securite", "theme": "Securite", **kw})


def test_stage_outside_a_product_release_draws_no_tag(seeded, client):
    sa = seeded["squad_a"]
    login(client, seeded["sl_a"])
    assert _jalon(client, sa, release_stage="NP").status_code == 201
    # "Other" must be named.
    assert _jalon(client, sa, release_stage="OT").status_code == 422
    r = _jalon(client, sa, release_stage="OT", release_stage_other="Audit ISO", title="Audit")
    assert r.status_code == 201, r.text
    assert r.json()["release_stage_other"] == "Audit ISO"
    # Back to GA, the free name goes.
    r = client.put(f"/api/roadmap-items/{r.json()['id']}", json={"release_stage": "GA"})
    assert r.json()["release_stage_other"] is None

    login(client, seeded["tribe"])
    html = client.get(f"/api/reports/dashboard.html?squad_id={sa}&year={YEAR}").text
    assert "Comite securite" in html
    assert "<em>NP</em>" not in html and "(NP)" not in html


def test_quarter_not_concerned_is_na_and_refused_when_it_has_jalons(seeded, client):
    sa = seeded["squad_a"]
    login(client, seeded["sl_a"])
    url = f"/api/squads/{sa}/quarter-progress"
    # N/A belongs to the roadmap: available while the comment section is off.
    r = client.put(url, json={"year": YEAR, "quarter": 1, "not_applicable": True})
    assert r.status_code == 200, r.text
    assert client.put(url, json={"year": YEAR, "quarter": 1, "comment": "x"}).status_code == 404
    login(client, seeded["admin"])
    client.put("/api/admin/modules-config", json={"squad_content": {"quarter_progress": True}})
    login(client, seeded["sl_a"])
    # A comment saved later keeps the flag.
    assert client.put(url, json={"year": YEAR, "quarter": 1, "comment": "Squad creee en avril"}).status_code == 200
    cell = client.get(f"/api/squads/{sa}?year={YEAR}").json()["quarter_progress"]["1"]
    assert cell["not_applicable"] is True and cell["comment"] == "Squad creee en avril"

    assert _jalon(client, sa, quarter=3, release_stage="GA").status_code == 201
    assert client.put(url, json={"year": YEAR, "quarter": 3, "not_applicable": True}).status_code == 409

    login(client, seeded["tribe"])
    html = client.get(f"/api/reports/dashboard.html?squad_id={sa}&year={YEAR}").text
    assert "non concerné" in html
