"""Platforms and Steerco, managed in one place: the tribe leader imposes a model,
each platform starts from it and can be adjusted, figures follow their labels when
the skeleton changes, and the whole tribe reads the dashboard."""
from tests.conftest import login
from tests.test_steerco import _enable, _platform


def _model(kpis, sla):
    return {"kpis": [{"label": k, "sub": []} for k in kpis], "sla": [{"label": s} for s in sla]}


def test_a_new_platform_starts_from_the_tribe_model(client, seeded):
    _enable(client)
    login(client, seeded["tribe"])
    r = client.put("/api/steerco/model", json=_model(["Users", "Cost"], ["Portal"]))
    assert r.status_code == 200, r.text
    p = client.post("/api/steerco/platforms", json={"name": "Data", "contributor_ids": [seeded["squad_a"]]})
    assert p.status_code == 201, p.text
    tpl = p.json()["template"]
    assert [k["label"] for k in tpl["kpis"]] == ["Users", "Cost"]
    assert [s["label"] for s in tpl["sla"]] == ["Portal"]
    assert all(k["owner_squad_id"] == seeded["squad_a"] for k in tpl["kpis"])   # sole contributor
    # A squad leader does not impose the model.
    login(client, seeded["sl_a"])
    assert client.put("/api/steerco/model", json=_model(["X"], [])).status_code == 403


def test_figures_follow_their_label_when_the_skeleton_changes(client, db, seeded):
    """Removing an item used to shift the figures of the next ones at the next save."""
    from app.models import SteercoEntry
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["sl_a"])
    data = client.get(f"/api/steerco/platform/{pid}?period=2026-07").json()["data"]
    for i, k in enumerate(data["kpis"]):
        k["value"] = str(100 + i)            # Cloud Users=100, Landing Zone=101, K8aaS=102...
    assert client.put(f"/api/steerco/platform/{pid}?period=2026-07", json=data).status_code == 200
    login(client, seeded["tribe"])
    p = next(x for x in client.get("/api/steerco/platforms").json() if x["id"] == pid)
    tpl = p["template"]
    tpl["kpis"] = [k for k in tpl["kpis"] if k["label"] != "Landing Zone"]      # drop the 2nd
    assert client.put(f"/api/steerco/platforms/{pid}", json={"template": tpl}).status_code == 200
    db.expire_all()
    stored = db.query(SteercoEntry).filter_by(platform_id=pid, period="2026-07").one().data
    values = {k["label"]: k["value"] for k in stored["kpis"]}
    assert values["Cloud Users"] == "100" and values["K8aaS"] == "102" and "Landing Zone" not in values


def test_apply_the_tribe_model_keeps_owners_and_figures(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["tribe"])
    client.put("/api/steerco/model", json=_model(["K8aaS", "New KPI"], ["Gitlab"]))
    r = client.post(f"/api/steerco/platforms/{pid}/apply-model")
    assert r.status_code == 200, r.text
    tpl = r.json()["template"]
    assert [k["label"] for k in tpl["kpis"]] == ["K8aaS", "New KPI"]
    assert tpl["kpis"][0]["owner_squad_id"] == seeded["squad_a"]


def test_the_whole_tribe_reads_the_dashboard(client, db, seeded):
    _enable(client)
    pid = _platform(db, seeded)
    login(client, seeded["member"])
    r = client.get("/api/steerco/entries?period=2026-07")
    assert r.status_code == 200 and [e["platform_id"] for e in r.json()] == [pid]
    assert client.get(f"/api/steerco/onepager.html?platform_id={pid}&period=2026-07").status_code == 200
    login(client, seeded["tribe2"])                      # another tribe: not theirs
    assert client.get("/api/steerco/entries?period=2026-07").json() == []
