"""Rattacher un jalon a un OTD depuis le jalon, avec une liste deroulante.

Le jalon porte deux liens, un par portee: ``otd_id`` vers l'engagement
management, ``squad_otd_id`` vers l'engagement de la squad. Ils se choisissaient
seulement depuis l'ecran de l'OTD; ils se choisissent maintenant aussi depuis le
jalon. Ce n'est pas un second lien: les deux ecrans ecrivent la meme colonne.

Les droits suivent ceux de l'ecran de l'OTD, avec une ouverture: le squad leader
rattache ses jalons a l'engagement management fixe sur sa squad (ou qui lui est
assigne). Un engagement management de toute la tribe reste au tribe leader, et
personne ne detache un lien qu'il n'aurait pas pu poser.
"""
from datetime import datetime, timezone

from tests.conftest import login

YEAR = datetime.now(timezone.utc).year


def _jalon(client, squad_id, **extra):
    r = client.post("/api/roadmap-items", json={"squad_id": squad_id, "year": YEAR, "quarter": 2,
                                                "title": "Livrer", "theme": "LZ", **extra})
    return r


def _otd(client, **kw):
    r = client.post("/api/otds", json={"year": YEAR, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_a_squad_leader_links_a_milestone_to_their_squad_commitment(client, seeded):
    login(client, seeded["sl_a"])
    sq_otd = _otd(client, tribe_id=seeded["t1"], title="Notre promesse", scope="squad", squad_id=seeded["squad_a"])
    r = _jalon(client, seeded["squad_a"], squad_otd_id=sq_otd)
    assert r.status_code == 201, r.text
    assert r.json()["squad_otd_id"] == sq_otd and r.json()["squad_otd_label"] == "Notre promesse"
    # The OTD screen sees the same link: one column, two views.
    otd = next(o for o in client.get(f"/api/otds?year={YEAR}").json() if o["id"] == sq_otd)
    assert [j["id"] for j in otd["jalons"]] == [r.json()["id"]]
    # Unlinking from the milestone.
    jid = r.json()["id"]
    r = client.put(f"/api/roadmap-items/{jid}", json={"squad_otd_id": None})
    assert r.status_code == 200 and r.json()["squad_otd_id"] is None


def test_management_commitments_follow_their_owner(client, seeded):
    login(client, seeded["tribe"])
    tribe_wide = _otd(client, tribe_id=seeded["t1"], title="Promesse de tribe")
    on_squad_a = _otd(client, tribe_id=seeded["t1"], title="Promesse sur A", squad_id=seeded["squad_a"])
    login(client, seeded["sl_a"])
    jid = _jalon(client, seeded["squad_a"]).json()["id"]
    # The commitment fixed on squad A: its leader says which milestone keeps it.
    r = client.put(f"/api/roadmap-items/{jid}", json={"otd_id": on_squad_a})
    assert r.status_code == 200 and r.json()["otd_label"] == "Promesse sur A"
    # The tribe-wide one stays with the tribe leader.
    r = client.put(f"/api/roadmap-items/{jid}", json={"otd_id": tribe_wide})
    assert r.status_code == 403
    # The tribe leader links it on the OTD screen; the squad leader cannot undo it...
    login(client, seeded["tribe"])
    assert client.put(f"/api/otds/{tribe_wide}/jalons", json={"jalon_ids": [jid]}).status_code == 200
    login(client, seeded["sl_a"])
    assert client.put(f"/api/roadmap-items/{jid}", json={"otd_id": None}).status_code == 403
    # ...but saving the milestone with the link unchanged is fine (the form sends it back).
    r = client.put(f"/api/roadmap-items/{jid}", json={"title": "Livrer vite", "otd_id": tribe_wide})
    assert r.status_code == 200 and r.json()["otd_id"] == tribe_wide


def test_a_link_must_fit_the_milestone(client, seeded):
    login(client, seeded["sl_a"])
    own = _otd(client, tribe_id=seeded["t1"], title="A", scope="squad", squad_id=seeded["squad_a"])
    next_year = _otd(client, tribe_id=seeded["t1"], title="A+1", scope="squad", squad_id=seeded["squad_a"],
                     **{"year": YEAR + 1})
    login(client, seeded["sl_b"])
    other = _otd(client, tribe_id=seeded["t1"], title="B", scope="squad", squad_id=seeded["squad_b"])
    login(client, seeded["sl_a"])
    jid = _jalon(client, seeded["squad_a"]).json()["id"]
    # a squad commitment in the management slot, another squad's, another year's
    assert client.put(f"/api/roadmap-items/{jid}", json={"otd_id": own}).status_code == 400
    assert client.put(f"/api/roadmap-items/{jid}", json={"squad_otd_id": other}).status_code == 400
    assert client.put(f"/api/roadmap-items/{jid}", json={"squad_otd_id": next_year}).status_code == 400
    assert client.put(f"/api/roadmap-items/{jid}", json={"squad_otd_id": 999999}).status_code == 400
    # one milestone can keep both commitments at once
    login(client, seeded["tribe"])
    mgmt = _otd(client, tribe_id=seeded["t1"], title="M", squad_id=seeded["squad_a"])
    login(client, seeded["sl_a"])
    r = client.put(f"/api/roadmap-items/{jid}", json={"otd_id": mgmt, "squad_otd_id": own})
    assert r.status_code == 200 and (r.json()["otd_id"], r.json()["squad_otd_id"]) == (mgmt, own)


def test_admin_links_any_management_commitment(client, seeded):
    login(client, seeded["admin"])
    tribe_wide = _otd(client, tribe_id=seeded["t1"], title="Promesse de tribe")
    r = _jalon(client, seeded["squad_b"], otd_id=tribe_wide)
    assert r.status_code == 201 and r.json()["otd_id"] == tribe_wide
    # not across tribes
    other_tribe = _otd(client, tribe_id=seeded["t2"], title="Ailleurs")
    assert _jalon(client, seeded["squad_b"], otd_id=other_tribe).status_code == 400
