"""Les regles d'acces aux engagements OTD, dans leurs deux portees.

Portee ``management``: ecrite par le tribe leader (ou l'admin), visible du squad
leader dont elle embarque un jalon, invisible des autres. Portee ``squad``:
ecrite par le leader de la squad concernee, et par lui seul, y compris contre le
tribe leader, parce qu'un engagement que quelqu'un d'autre peut corriger n'est
plus l'engagement de celui qui l'a pris.
"""
from datetime import datetime, timezone

from tests.conftest import login

YEAR = datetime.now(timezone.utc).year


def _mk_jalon(client, squad_id):
    r = client.post("/api/roadmap-items", json={
        "squad_id": squad_id, "year": YEAR, "quarter": 1, "title": "J", "theme": "LZ"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ids(resp):
    return {o["id"] for o in resp.json()}


def test_otd_management_and_visibility(client, seeded):
    # Squad leader A adds a milestone on squad A.
    login(client, seeded["sl_a"])
    jid = _mk_jalon(client, seeded["squad_a"])

    # Squad leaders cannot create an OTD - management is tribe leader / admin only.
    assert client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR,
                                          "title": "nope"}).status_code == 403

    # Tribe leader creates an OTD in their tribe and attaches squad A's milestone.
    login(client, seeded["tribe"])
    r = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR, "title": "OTD-1"})
    assert r.status_code == 201, r.text
    otd_id = r.json()["id"]
    assert client.put(f"/api/otds/{otd_id}/jalons", json={"jalon_ids": [jid]}).status_code == 200

    # The concerned squad leader (A) sees it.
    login(client, seeded["sl_a"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))

    # Another squad's leader (B, same tribe) does NOT.
    login(client, seeded["sl_b"])
    assert otd_id not in _ids(client.get(f"/api/otds?year={YEAR}"))

    # A plain member sees no OTDs at all.
    login(client, seeded["member"])
    assert client.get(f"/api/otds?year={YEAR}").json() == []

    # The tribe leader (manager) sees it.
    login(client, seeded["tribe"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))

    # Admin sees it too.
    login(client, seeded["admin"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))


def test_otd_owner_must_be_squad_leader_of_the_tribe(client, seeded):
    """Assigning an owner from another tribe (or a non-squad-leader) is rejected -
    otherwise a foreign squad leader would see this tribe's OTD."""
    login(client, seeded["tribe"])  # tribe leader of t1
    # sl_b leads a squad in t1 → allowed.
    ok = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR,
                                        "title": "OK", "owner_user_id": seeded["sl_b_id"]})
    assert ok.status_code == 201, ok.text
    # A member (not a squad leader) → rejected.
    bad_role = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR,
                                              "title": "bad", "owner_user_id": seeded["member_id"]})
    assert bad_role.status_code == 400, bad_role.text
    # sl_a leads a squad in t1 but is assigned to a t2 OTD → rejected (cross-tribe).
    login(client, seeded["admin"])
    foreign_sl = client.post("/api/otds", json={"tribe_id": seeded["t2"], "year": YEAR,
                                                "title": "foreign", "owner_user_id": seeded["sl_a_id"]})
    assert foreign_sl.status_code == 400, foreign_sl.text


# ----- la portee « squad »: l'engagement que la squad prend elle-meme ------------

def _squad_otd(client, seeded, squad_id, title="Bascule 25G"):
    return client.post("/api/otds", json={
        "tribe_id": seeded["t1"], "year": YEAR, "title": title,
        "scope": "squad", "squad_id": squad_id})


def test_a_squad_leader_takes_their_own_commitment(client, seeded):
    """Ce que la demande dit: le squad leader ajoute ses propres OTD."""
    login(client, seeded["sl_a"])
    r = _squad_otd(client, seeded, seeded["squad_a"])
    assert r.status_code == 201, r.text
    otd = r.json()
    assert otd["scope"] == "squad" and otd["squad_id"] == seeded["squad_a"]

    jid = _mk_jalon(client, seeded["squad_a"])
    r = client.put(f"/api/otds/{otd['id']}/jalons", json={"jalon_ids": [jid]})
    assert r.status_code == 200, r.text
    assert [j["id"] for j in r.json()["jalons"]] == [jid]

    assert client.put(f"/api/otds/{otd['id']}",
                      json={"title": "Bascule 25G, phase 2"}).status_code == 200
    assert client.delete(f"/api/otds/{otd['id']}").status_code == 204


def test_a_squad_leader_cannot_commit_for_another_squad(client, seeded):
    """La portee protege aussi les voisins: on ne s'engage pas sur leur travail."""
    login(client, seeded["sl_a"])
    assert _squad_otd(client, seeded, seeded["squad_b"]).status_code == 403

    # Ni y rattacher un jalon qui n'est pas de sa squad.
    own = _squad_otd(client, seeded, seeded["squad_a"]).json()
    login(client, seeded["sl_b"])
    other = _mk_jalon(client, seeded["squad_b"])
    login(client, seeded["sl_a"])
    r = client.put(f"/api/otds/{own['id']}/jalons", json={"jalon_ids": [other]})
    assert r.status_code == 400, r.text


def test_the_tribe_leader_reads_a_squad_commitment_but_does_not_write_it(client, seeded):
    """Il le voit dans ses rapports, il ne le corrige pas: sinon l'engagement
    cesse d'etre celui de la squad, ce que la portee sert justement a dire."""
    login(client, seeded["sl_a"])
    otd = _squad_otd(client, seeded, seeded["squad_a"]).json()

    login(client, seeded["tribe"])
    assert otd["id"] in _ids(client.get(f"/api/otds?year={YEAR}"))
    assert client.put(f"/api/otds/{otd['id']}", json={"title": "Autre chose"}).status_code == 403
    assert client.delete(f"/api/otds/{otd['id']}").status_code == 403


def test_the_scope_cannot_be_changed_after_the_fact(client, seeded):
    """Sinon un squad leader se donnerait un droit d'ecriture sur un objet du
    tribe leader en rebaptisant le sien."""
    login(client, seeded["sl_a"])
    otd = _squad_otd(client, seeded, seeded["squad_a"]).json()
    r = client.put(f"/api/otds/{otd['id']}", json={"scope": "management", "squad_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["scope"] == "squad" and r.json()["squad_id"] == seeded["squad_a"]


def test_the_two_links_do_not_undo_each_other(client, seeded):
    """Un jalon tient souvent les deux engagements. Avec un lien unique, le
    dernier qui rattache defaisait le travail de l'autre sans le lui dire."""
    login(client, seeded["sl_a"])
    jid = _mk_jalon(client, seeded["squad_a"])
    own = _squad_otd(client, seeded, seeded["squad_a"]).json()
    assert client.put(f"/api/otds/{own['id']}/jalons",
                      json={"jalon_ids": [jid]}).status_code == 200

    login(client, seeded["tribe"])
    mgmt = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR,
                                          "title": "Engagement du management"}).json()
    assert client.put(f"/api/otds/{mgmt['id']}/jalons",
                      json={"jalon_ids": [jid]}).status_code == 200

    by_id = {o["id"]: o for o in client.get(f"/api/otds?year={YEAR}").json()}
    assert [j["id"] for j in by_id[mgmt["id"]]["jalons"]] == [jid]
    assert [j["id"] for j in by_id[own["id"]]["jalons"]] == [jid], (
        "le rattachement du management a defait celui de la squad")


def test_a_squad_leader_only_sees_their_own_candidate_jalons(client, seeded):
    """Pour choisir ce qu'il engage, il lui faut la liste, bornee a ses squads."""
    login(client, seeded["sl_b"])
    other = _mk_jalon(client, seeded["squad_b"])
    login(client, seeded["sl_a"])
    mine = _mk_jalon(client, seeded["squad_a"])

    cands = client.get(f"/api/otds/candidate-jalons?year={YEAR}").json()
    ids = {c["id"] for c in cands}
    assert mine in ids and other not in ids
    assert all("squad_otd_id" in c for c in cands)
