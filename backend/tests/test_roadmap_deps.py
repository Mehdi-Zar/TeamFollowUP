"""Structured milestone dependencies (squad | tribe | free text) + cross-reference,
and the auto-derived objective status."""
from datetime import datetime, timezone

from app import status as st
from tests.conftest import login

YEAR = datetime.now(timezone.utc).year


def _mk_item(client, squad_id, **extra):
    body = {"squad_id": squad_id, "year": YEAR, "quarter": 1, "title": "J",
            "theme": "Landing Zones", **extra}
    r = client.post("/api/roadmap-items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_theme_is_required(client, seeded):
    login(client, seeded["admin"])
    # Theme is mandatory: a milestone without one is rejected.
    r = client.post("/api/roadmap-items", json={
        "squad_id": seeded["squad_a"], "year": YEAR, "quarter": 1, "title": "No theme"})
    assert r.status_code == 422
    # Provided theme round-trips and is offered for reuse via the themes endpoint.
    out = _mk_item(client, seeded["squad_a"], title="J", theme="Managed Services")
    assert out["theme"] == "Managed Services"
    themes = client.get("/api/roadmap-items/themes").json()
    assert "Managed Services" in themes


def test_release_stage_roundtrip_and_default(client, seeded):
    login(client, seeded["admin"])
    # Default is EA when not provided.
    out = _mk_item(client, seeded["squad_a"], title="J1")
    assert out["release_stage"] == "EA"
    # GA is accepted and round-trips.
    ga = _mk_item(client, seeded["squad_a"], title="J2", release_stage="GA")
    assert ga["release_stage"] == "GA"
    # Editable via PUT.
    upd = client.put(f"/api/roadmap-items/{out['id']}", json={"release_stage": "GA"})
    assert upd.status_code == 200 and upd.json()["release_stage"] == "GA"


def test_release_stage_in_roadmap_export(client, seeded):
    login(client, seeded["admin"])
    _mk_item(client, seeded["squad_a"], title="Catalog GKE", release_stage="GA")
    r = client.get(f"/api/squads/{seeded['squad_a']}/roadmap.html")
    assert r.status_code == 200
    # The stage is rendered as a colour-coded GA label (gold EA / green GA).
    assert "Catalog GKE" in r.text and 'class="rm-ga">GA</span>' in r.text


def test_text_dependency_roundtrip(client, seeded):
    login(client, seeded["admin"])
    out = _mk_item(client, seeded["squad_a"], dependencies="some external thing", dependency_kind="text")
    assert out["dependency_kind"] == "text"
    assert out["dependency_label"] == "some external thing"
    assert out["dependency_squad_id"] is None and out["dependency_tribe_id"] is None


def test_squad_dependency_resolves_label_and_clears_others(client, seeded):
    login(client, seeded["admin"])
    out = _mk_item(client, seeded["squad_a"], dependency_kind="squad",
                   dependency_squad_id=seeded["squad_b"], dependency_tribe_id=seeded["t2"],
                   dependencies="ignored")
    assert out["dependency_kind"] == "squad"
    assert out["dependency_squad_id"] == seeded["squad_b"]
    assert out["dependency_label"] == "Squad B"
    # the non-matching reference is cleared by normalization
    assert out["dependency_tribe_id"] is None


def test_tribe_dependency_resolves_tribe_name(client, seeded):
    login(client, seeded["admin"])
    out = _mk_item(client, seeded["squad_a"], dependency_kind="tribe", dependency_tribe_id=seeded["t2"])
    assert out["dependency_label"] == "Tribe Two"
    assert out["dependency_squad_id"] is None


def test_incoming_dependents_endpoint(client, seeded):
    login(client, seeded["admin"])
    # Squad A's milestone depends on Squad B → Squad B should see it as incoming.
    _mk_item(client, seeded["squad_a"], title="A→B", dependency_kind="squad",
             dependency_squad_id=seeded["squad_b"], status="blocked")
    # Squad C (tribe 2) depends on tribe 1 → Squad A (tribe 1) sees it via tribe.
    _mk_item(client, seeded["squad_c"], title="C→T1", dependency_kind="tribe",
             dependency_tribe_id=seeded["t1"])

    # Squad B (tribe 1): the direct A→B dependency, plus the tribe-1 dependency C→T1.
    dep_b = {d["title"]: d for d in client.get(f"/api/squads/{seeded['squad_b']}/dependents?year={YEAR}").json()}
    assert dep_b["A→B"]["via"] == "squad" and dep_b["A→B"]["squad_name"] == "Squad A"
    assert dep_b["C→T1"]["via"] == "tribe"

    # Squad A (tribe 1): sees the tribe-1 dependency, but NOT A→B (which targets B).
    dep_a = {d["title"]: d for d in client.get(f"/api/squads/{seeded['squad_a']}/dependents?year={YEAR}").json()}
    assert dep_a.get("C→T1", {}).get("via") == "tribe"
    assert "A→B" not in dep_a


def test_squad_roadmap_pptx_export(client, seeded):
    import pytest
    pytest.importorskip("pptx")
    login(client, seeded["sl_a"])  # squad leader can export their squad's roadmap
    r = client.get(f"/api/squads/{seeded['squad_a']}/roadmap.pptx")
    assert r.status_code == 200
    assert "presentationml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"
    # Out-of-scope squad (other tribe) is forbidden.
    assert client.get(f"/api/squads/{seeded['squad_c']}/roadmap.pptx").status_code == 403


def test_squad_roadmap_html_export(client, seeded):
    login(client, seeded["sl_a"])
    r = client.get(f"/api/squads/{seeded['squad_a']}/roadmap.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Squad A" in r.text
    assert client.get(f"/api/squads/{seeded['squad_c']}/roadmap.html").status_code == 403


def test_objective_status_is_derived_not_stored(client, seeded, db):
    login(client, seeded["admin"])
    # Create an objective with a deadline already in the past → must be red despite
    # never setting a status by hand (the field is gone from the API).
    r = client.post("/api/objectives", json={
        "squad_id": seeded["squad_a"], "year": YEAR, "title": "O",
        "target_date": f"{YEAR}-01-01T00:00:00Z",
    })
    assert r.status_code == 201, r.text
    assert r.json()["rag_status"] == "red"  # past deadline, no progress

    # Sending a rag_status is simply ignored (not a settable field anymore).
    oid = r.json()["id"]
    upd = client.put(f"/api/objectives/{oid}", json={"rag_status": "green"})
    assert upd.status_code == 200
    assert upd.json()["rag_status"] == "red"
