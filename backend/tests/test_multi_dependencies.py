"""Un jalon peut dependre de plusieurs tribes, plusieurs squads, et de textes libres.

La liste remplace la dependance unique; les champs ``dependency_*`` gardent la
premiere, pour les saisies figees et les clients qui n'en lisent qu'une.
"""
from datetime import datetime, timezone

from app import report as report_mod
from tests.conftest import login

YEAR = datetime.now(timezone.utc).year


def _item(client, squad_id, deps, **extra):
    r = client.post("/api/roadmap-items", json={"squad_id": squad_id, "year": YEAR, "quarter": 2, "title": "Bascule",
                                                "theme": "LZ", "dependency_list": deps, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_a_milestone_waits_on_several_tribes_squads_and_texts(client, db, seeded):
    login(client, seeded["admin"])
    out = _item(client, seeded["squad_a"], [
        {"kind": "tribe", "tribe_id": seeded["t2"]},
        {"kind": "tribe", "tribe_id": seeded["t1"]},
        {"kind": "squad", "squad_id": seeded["squad_c"]},
        {"kind": "text", "text": "Fournisseur reseau"},
        {"kind": "tribe", "tribe_id": seeded["t2"]},          # duplicate, dropped
        {"kind": "squad", "squad_id": seeded["squad_a"]},     # itself, dropped
    ])
    assert [d["kind"] for d in out["dependency_list"]] == ["tribe", "tribe", "squad", "text"]
    assert [d["label"] for d in out["dependency_list"]] == ["Tribe Two", "Tribe One", "Squad C", "Fournisseur reseau"]
    # the first one is mirrored in the single fields
    assert out["dependency_kind"] == "tribe" and out["dependency_tribe_id"] == seeded["t2"]
    assert out["dependency_label"] == "Tribe Two, Tribe One, Squad C, Fournisseur reseau"

    # the dependencies document lists it under each target
    data = report_mod.build_dependencies_data(db, None, YEAR)
    labels = {g["target_label"] for g in data["groups"] if any(i["jalon"] == "Bascule" for i in g["items"])}
    assert labels == {"Tribe Two", "Tribe One", "Squad C", "Fournisseur reseau"}

    # each targeted squad sees it among the milestones that wait on it
    inc_c = client.get(f"/api/squads/{seeded['squad_c']}/dependents").json()
    assert [d["title"] for d in inc_c] == ["Bascule"] and inc_c[0]["via"] == "squad"
    inc_b = client.get(f"/api/squads/{seeded['squad_b']}/dependents").json()
    assert [d["title"] for d in inc_b] == ["Bascule"] and inc_b[0]["via"] == "tribe"


def test_editing_the_list_and_the_older_single_fields(client, db, seeded):
    login(client, seeded["admin"])
    jid = _item(client, seeded["squad_a"], [{"kind": "tribe", "tribe_id": seeded["t2"]},
                                            {"kind": "squad", "squad_id": seeded["squad_b"]}])["id"]
    r = client.put(f"/api/roadmap-items/{jid}", json={"dependency_list": [{"kind": "text", "text": "Achats"}]})
    assert [d["label"] for d in r.json()["dependency_list"]] == ["Achats"]
    assert r.json()["dependency_kind"] == "text" and r.json()["dependencies"] == "Achats"
    # an older client setting one dependency gets a one-entry list
    r = client.put(f"/api/roadmap-items/{jid}", json={"dependency_kind": "squad", "dependency_squad_id": seeded["squad_b"]})
    assert [d["label"] for d in r.json()["dependency_list"]] == ["Squad B"]
    r = client.put(f"/api/roadmap-items/{jid}", json={"dependency_list": []})
    assert r.json()["dependency_list"] == [] and r.json()["dependency_kind"] is None
    r = client.put(f"/api/roadmap-items/{jid}", json={"dependency_list": [{"kind": "tribe", "tribe_id": 99999}]})
    assert r.status_code == 400


def test_a_deleted_tribe_stays_a_dependency_by_its_name(client, db, seeded):
    login(client, seeded["admin"])
    jid = _item(client, seeded["squad_a"], [{"kind": "squad", "squad_id": seeded["squad_b"]},
                                            {"kind": "tribe", "tribe_id": seeded["t2"]}])["id"]
    from app.models import RoadmapDependency, RoadmapItem
    from sqlalchemy import select
    tribe2 = seeded["t2"]
    # Squad C belongs to Tribe Two: move it so the tribe can be deleted.
    from app.models import Squad
    db.get(Squad, seeded["squad_c"]).tribe_id = seeded["t1"]
    db.commit()
    r = client.delete(f"/api/tribes/{tribe2}")
    assert r.status_code in (200, 204), r.text
    db.expire_all()
    deps = db.scalars(select(RoadmapDependency).where(RoadmapDependency.item_id == jid)
                      .order_by(RoadmapDependency.position)).all()
    assert [(d.kind, d.text) for d in deps][1] == ("text", "Tribe Two")
    assert db.get(RoadmapItem, jid).deps[0].squad_id == seeded["squad_b"]
