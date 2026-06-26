"""Initiatives: a flat per-squad list (title / owner / squad / deadline) set by the
tribe leader, visible to everyone, and surfaced in each squad's report."""
from datetime import datetime, timezone

from tests.conftest import login

YEAR = datetime.now(timezone.utc).year


def _init(client, tribe_id, **extra):
    body = {"tribe_id": tribe_id, "year": YEAR, "title": "Init", **extra}
    r = client.post("/api/initiatives", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_initiative_flat_fields_and_squad_name(client, seeded):
    login(client, seeded["tribe"])
    out = _init(client, seeded["t1"], title="Portail unifié", squad_id=seeded["squad_a"],
                owner="Camille D.", deadline=f"{YEAR}-09-30T00:00:00Z")
    assert out["squad_id"] == seeded["squad_a"] and out["squad_name"] == "Squad A"
    assert out["owner"] == "Camille D." and out["deadline"][:10] == f"{YEAR}-09-30"
    rows = client.get(f"/api/initiatives?year={YEAR}").json()
    assert any(i["id"] == out["id"] and i["squad_name"] == "Squad A" for i in rows)


def test_initiative_squad_must_be_in_tribe(client, seeded):
    login(client, seeded["tribe"])  # tribe leader of t1
    r = client.post("/api/initiatives", json={
        "tribe_id": seeded["t1"], "year": YEAR, "title": "X", "squad_id": seeded["squad_c"]})  # squad_c in t2
    assert r.status_code == 400


def test_initiative_visible_to_member_but_not_editable(client, seeded):
    login(client, seeded["tribe"])
    _init(client, seeded["t1"], title="Visible", squad_id=seeded["squad_a"])
    # A member can READ the flat list...
    login(client, seeded["member"])
    rows = client.get(f"/api/initiatives?year={YEAR}").json()
    assert any(i["title"] == "Visible" for i in rows)
    # ...but cannot create.
    assert client.post("/api/initiatives", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "Nope"}).status_code == 403


def test_squad_leader_cannot_manage_initiatives(client, seeded):
    login(client, seeded["sl_a"])
    assert client.post("/api/initiatives", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "X"}).status_code == 403


def test_initiative_surfaces_in_squad_report(client, seeded, db):
    login(client, seeded["tribe"])
    _init(client, seeded["t1"], title="Squad A initiative", squad_id=seeded["squad_a"], owner="O1")
    from app.report import build_report_data
    data = build_report_data(db, seeded["t1"], YEAR)
    rows = [r for blk in data["tribes"] for r in blk["squads"] if r["squad_id"] == seeded["squad_a"]]
    assert rows and any(i["title"] == "Squad A initiative" for i in rows[0]["detail"]["initiatives"])


def test_initiatives_export_html_and_pptx(client, seeded):
    import pytest
    login(client, seeded["tribe"])
    _init(client, seeded["t1"], title="Exported initiative", squad_id=seeded["squad_a"], owner="Owner X")
    r = client.get(f"/api/initiatives/report.html?year={YEAR}")
    assert r.status_code == 200 and "Exported initiative" in r.text and "Owner X" in r.text
    pytest.importorskip("pptx")
    p = client.get(f"/api/initiatives/report.pptx?year={YEAR}")
    assert p.status_code == 200 and p.content[:2] == b"PK"
