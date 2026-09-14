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


def _jalon(client, squad_id, title, quarter=1):
    """Un jalon appartient a sa squad: seuls son leader et un admin l'ecrivent."""
    r = client.post("/api/roadmap-items", json={
        "squad_id": squad_id, "year": YEAR, "quarter": quarter, "title": title,
        "theme": "Socle", "release_stage": "GA", "status": "on_track"})
    assert r.status_code == 201, r.text
    return r.json()


def test_an_initiative_carries_the_jalons_that_serve_it(client, seeded):
    """La ligne d'une initiative dans la frise, ce sont ces jalons la.

    Le lien passait par l'objectif annuel, et aucun ecran ne posait le maillon
    « cet objectif sert telle initiative » : chaque frise montrait des lignes
    d'initiative vides et une ligne anonyme portant tous les jalons. Il se pose
    maintenant du cote de l'initiative, comme celui d'un engagement."""
    login(client, seeded["admin"])
    sq = seeded["squad_a"]
    init = _init(client, seeded["t1"], title="Portail unifié", squad_id=sq)
    a = _jalon(client, sq, "Cache des dépendances", 1)
    b = _jalon(client, sq, "Build incrémental", 3)

    cands = client.get(f"/api/initiatives/candidate-jalons?squad_id={sq}&year={YEAR}").json()
    assert {c["id"] for c in cands} >= {a["id"], b["id"]}
    assert all(c["initiative_id"] is None for c in cands)

    r = client.put(f"/api/initiatives/{init['id']}/jalons", json={"jalon_ids": [a["id"], b["id"]]})
    assert r.status_code == 200, r.text
    cands = client.get(f"/api/initiatives/candidate-jalons?squad_id={sq}&year={YEAR}").json()
    assert {c["id"] for c in cands if c["initiative_id"] == init["id"]} == {a["id"], b["id"]}

    # Poser un ensemble plus petit libere ce qui en sort, sans supprimer le jalon.
    client.put(f"/api/initiatives/{init['id']}/jalons", json={"jalon_ids": [a["id"]]})
    cands = {c["id"]: c for c in
             client.get(f"/api/initiatives/candidate-jalons?squad_id={sq}&year={YEAR}").json()}
    assert cands[a["id"]]["initiative_id"] == init["id"]
    assert cands[b["id"]]["initiative_id"] is None


def test_the_timeline_hangs_those_jalons_under_that_initiative(client, seeded, db):
    """Le seul but du lien: que la frise cesse d'afficher une ligne vide et une
    ligne anonyme."""
    from app import report as report_mod
    from app.models import User
    from sqlalchemy import select

    login(client, seeded["admin"])
    sq = seeded["squad_a"]
    init = _init(client, seeded["t1"], title="Portail unifié", squad_id=sq)
    served = _jalon(client, sq, "Cache des dépendances", 1)
    _jalon(client, sq, "Nettoyage des images", 2)          # ne sert rien
    client.put(f"/api/initiatives/{init['id']}/jalons", json={"jalon_ids": [served["id"]]})

    viewer = db.scalar(select(User).where(User.email == seeded["admin"]))
    det = report_mod.build_report_data(db, None, YEAR, 7, lang="fr", viewer=viewer,
                                       squad_id=sq)["tribes"][0]["squads"][0]["detail"]
    rows = report_mod.timeline_rows(det, "fr")
    named = next(r for r in rows if r["title"] == "Portail unifié")
    assert [it["title"] for it in named["items"]] == ["Cache des dépendances"]
    orphans = next(r for r in rows if r["key"] == "none")
    assert [it["title"] for it in orphans["items"]] == ["Nettoyage des images"]


def test_only_a_tribe_leader_or_admin_sets_that_link(client, seeded):
    """Un squad leader ecrit ses jalons, pas ce qu'ils servent: l'arbitrage entre
    initiatives appartient a la tribu."""
    login(client, seeded["admin"])
    init = _init(client, seeded["t1"], squad_id=seeded["squad_a"])
    j = _jalon(client, seeded["squad_a"], "Un jalon")

    login(client, seeded["sl_a"])
    r = client.put(f"/api/initiatives/{init['id']}/jalons", json={"jalon_ids": [j["id"]]})
    assert r.status_code == 403, r.text
