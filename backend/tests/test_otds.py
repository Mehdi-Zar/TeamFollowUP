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

    # And so does every other squad leader of the tribe. Un engagement management
    # est ce que la tribe promet: le cacher a ceux qui le tiennent n'a jamais
    # protege personne, et un leader qui ne voit pas l'engagement pose sur sa squad
    # ne peut ni le tenir ni le contester. Il le lit sans l'ecrire, ce que pinne
    # test_the_tribe_leader_reads_a_squad_commitment_but_does_not_write_it en
    # miroir, et ci-dessous pour ce sens-ci.
    login(client, seeded["sl_b"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))
    assert client.put(f"/api/otds/{otd_id}", json={"title": "detourne"}).status_code == 403
    assert client.delete(f"/api/otds/{otd_id}").status_code == 403

    # A plain member of the tribe reads it too (the exported documents already
    # show it to them), but cannot write it.
    login(client, seeded["member"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))
    assert client.put(f"/api/otds/{otd_id}", json={"title": "detourne"}).status_code == 403

    # The tribe leader (manager) sees it.
    login(client, seeded["tribe"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))

    # Admin sees it too.
    login(client, seeded["admin"])
    assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}"))


def test_a_squad_leader_reads_the_tribe_commitments_before_anyone_attaches_a_jalon(client, seeded):
    """L'engagement management se lit des qu'il existe, pas quand on veut bien.

    Il n'etait visible d'un squad leader qu'assigne nommement a lui, ou une fois
    un de ses jalons rattache. Or seul le tribe leader rattache: le leader ne
    voyait donc pas l'engagement pose sur sa squad tant qu'un autre n'avait pas
    agi, et rien ne le lui signalait. Un engagement qu'on ignore ne peut pas etre
    tenu, et celui qui change de titulaire restait visible du seul ancien.

    La frontiere reste la tribe, elle: un leader d'une autre tribe n'en voit rien.
    """
    login(client, seeded["tribe"])
    r = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR,
                                       "title": "Sans titulaire ni jalon"})
    assert r.status_code == 201, r.text
    otd_id = r.json()["id"]

    # Aucun owner, aucun jalon: les deux leaders de la tribe le lisent quand meme.
    for who in ("sl_a", "sl_b"):
        login(client, seeded[who])
        assert otd_id in _ids(client.get(f"/api/otds?year={YEAR}")), who

    # Une squad d'une autre tribe n'a pas a le connaitre: squad_c est dans t2, et
    # son leader est le membre promu ci-dessous pour n'avoir que ce lien-la.
    login(client, seeded["admin"])
    assert client.put(f"/api/squads/{seeded['squad_c']}",
                      json={"leader_user_id": seeded["member_id"]}).status_code == 200
    assert client.put(f"/api/admin/users/{seeded['member_id']}",
                      json={"role": "squad_leader", "tribe_id": seeded["t2"]}).status_code == 200
    login(client, seeded["member"])
    assert otd_id not in _ids(client.get(f"/api/otds?year={YEAR}"))


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


def test_the_squad_payload_counts_its_own_commitments(client, seeded):
    """La page de saisie rappelle avant l'envoi ce qui est vide, et l'engagement
    en fait desormais partie: elle a donc besoin du compte.

    Il ne compte que la portee « squad ». Un engagement du management pose sur la
    squad n'est pas un engagement qu'elle a pris: le lui compter dirait « c'est
    fait » sur la seule ligne qui lui demande de s'engager elle-meme.
    """
    login(client, seeded["sl_a"])
    detail = lambda: client.get(f"/api/squads/{seeded['squad_a']}?year={YEAR}").json()
    assert detail()["otd_count"] == 0

    assert _squad_otd(client, seeded, seeded["squad_a"]).status_code == 201
    assert detail()["otd_count"] == 1

    # Celui du management ne compte pas, meme rattache a un jalon de la squad.
    jid = _mk_jalon(client, seeded["squad_a"])
    login(client, seeded["tribe"])
    mgmt = client.post("/api/otds", json={"tribe_id": seeded["t1"], "year": YEAR,
                                          "title": "Pose par le management"}).json()
    assert client.put(f"/api/otds/{mgmt['id']}/jalons",
                      json={"jalon_ids": [jid]}).status_code == 200
    login(client, seeded["sl_a"])
    assert detail()["otd_count"] == 1

    # Ni celui d'une autre annee: la liste de controle porte sur le cycle en cours.
    assert client.post("/api/otds", json={
        "tribe_id": seeded["t1"], "year": YEAR + 1, "title": "L'an prochain",
        "scope": "squad", "squad_id": seeded["squad_a"]}).status_code == 201
    assert detail()["otd_count"] == 1


def test_deleting_a_squad_takes_its_commitments_with_it(client, db, seeded):
    """Un engagement de squad ne survit pas a sa squad.

    La cle etrangere le promet depuis la migration (ON DELETE CASCADE), et c'est
    la base qui doit le faire. Le jour ou le modele a appris ce lien pour compter
    les engagements d'une squad, SQLAlchemy aurait pu s'en meler et vider
    `squad_id` avant la suppression: l'engagement serait reste, sans portee ni
    proprietaire, invisible de tous et compte par personne.
    """
    from app.models import Otd
    login(client, seeded["sl_a"])
    otd_id = _squad_otd(client, seeded, seeded["squad_a"]).json()["id"]

    login(client, seeded["tribe"])
    assert client.delete(f"/api/squads/{seeded['squad_a']}").status_code == 204
    db.expire_all()
    assert db.get(Otd, otd_id) is None


def test_at_most_two_commitments_fall_due_in_a_month(client, seeded):
    """Management ones per tribe, a squad's own per squad; moving one into a full
    month is refused too."""
    login(client, seeded["tribe"])
    base = {"tribe_id": seeded["t1"], "year": YEAR}
    june = f"{YEAR}-06-15T00:00:00Z"
    for i in (1, 2):
        assert client.post("/api/otds", json={**base, "title": f"J{i}", "committed_date": june}).status_code == 201
    third = client.post("/api/otds", json={**base, "title": "J3", "committed_date": f"{YEAR}-06-30T00:00:00Z"})
    assert third.status_code == 409, third.text
    july = client.post("/api/otds", json={**base, "title": "Jul", "committed_date": f"{YEAR}-07-01T00:00:00Z"})
    assert july.status_code == 201
    assert client.put(f"/api/otds/{july.json()['id']}", json={"committed_date": june}).status_code == 409

    login(client, seeded["sl_a"])
    own = {**base, "scope": "squad", "squad_id": seeded["squad_a"], "committed_date": june}
    assert client.post("/api/otds", json={**own, "title": "S1"}).status_code == 201   # its own quota
