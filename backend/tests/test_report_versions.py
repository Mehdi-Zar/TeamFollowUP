"""Les versions d'un document: le dashboard, la roadmap et le rapport d'une date passee.

Une saisie figee existait deja, mais ne se lisait qu'une soumission a la fois,
dans l'historique d'une squad. La question posee apres coup n'est pas celle-la:
c'est « montre-moi le dashboard tel qu'il etait le 12 », et la seule reponse
possible etait de restaurer une sauvegarde de toute la base.

Ce qui se teste ici n'est pas la mise en page d'une version mais ce qu'elle
promet: qu'elle ne bouge plus quand la donnee bouge, qu'elle dise qu'elle est
datee, qu'elle nomme les squads qui n'avaient rien soumis plutot que de les
remplacer par leur etat du jour, et qu'elle n'ouvre a personne ce qu'il n'a pas
le droit de voir aujourd'hui.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app import report as report_mod
from app.models import Otd, ReportSnapshot, RoadmapItem, Squad, User
from app.reportasof import freeze_report_data, list_versions
from tests.conftest import login

YEAR = 2026


def _utc(month: int, day: int) -> dt.datetime:
    return dt.datetime(YEAR, month, day, tzinfo=dt.timezone.utc)


def _viewer(db, seeded):
    return db.scalar(select(User).where(User.email == seeded["admin"]))


def _submit(client, squad_id: int, label: str | None = None):
    r = client.post(f"/api/squads/{squad_id}/snapshots",
                    json={"year": YEAR, "cycle_label": label})
    assert r.status_code == 201, r.text
    return r.json()


def _data(db, seeded, viewer, as_of=None):
    data = report_mod.build_report_data(db, seeded["t1"], YEAR, 7, viewer=viewer, lang="fr")
    return freeze_report_data(db, data, as_of) if as_of else data


def _squad_row(data, name="Squad A"):
    return next(r for blk in data["tribes"] for r in blk["squads"] if r["name"] == name)


def _titles(row):
    return [it["title"] for qd in row["detail"]["quarters"] for it in qd["items"]]


def _seed_cycle(client, db, seeded):
    """Une squad avec un engagement date, deux jalons, et sa saisie soumise."""
    login(client, seeded["admin"])
    squad = db.get(Squad, seeded["squad_a"])
    otd = Otd(tribe_id=seeded["t1"], year=YEAR, title="Plan presente",
              committed_date=_utc(6, 30), owner_user_id=squad.leader_user_id)
    db.add(otd)
    db.flush()
    db.add(RoadmapItem(squad_id=squad.id, year=YEAR, quarter=1, title="Socle pose",
                       status="blocked", otd_id=otd.id))
    db.add(RoadmapItem(squad_id=squad.id, year=YEAR, quarter=2, title="Bascule",
                       status="on_track", otd_id=otd.id))
    squad.mood, squad.mood_at = "bad", _utc(6, 1)
    db.commit()
    return _submit(client, squad.id, "Soumission de juin")


# ----- ce qu'une version promet --------------------------------------------------

def test_a_version_does_not_move_when_the_data_moves(client, db, seeded):
    """C'est la promesse entiere: le document d'hier reste celui d'hier. Sans elle,
    une version n'est qu'un titre pose sur les chiffres du jour."""
    snap = _seed_cycle(client, db, seeded)
    day = snap["submitted_at"][:10]
    viewer = _viewer(db, seeded)

    # La vie continue: un jalon se debloque, un autre arrive, le moral remonte.
    item = db.scalar(select(RoadmapItem).where(RoadmapItem.title == "Socle pose"))
    item.status = "done"
    db.add(RoadmapItem(squad_id=seeded["squad_a"], year=YEAR, quarter=3,
                       title="Jalon arrive apres", status="on_track"))
    db.get(Squad, seeded["squad_a"]).mood = "good"
    db.commit()

    live = _squad_row(_data(db, seeded, viewer))
    past = _squad_row(_data(db, seeded, viewer, as_of=day))

    assert "Jalon arrive apres" in _titles(live)
    assert "Jalon arrive apres" not in _titles(past), "une version ne recoit pas la suite"
    assert past["blocked"] == 1 and live["blocked"] == 0, "les compteurs suivent la version"
    assert past["mood"] == "bad" and live["mood"] == "good"


def test_a_version_carries_the_commitments_that_held_the_milestones(client, db, seeded):
    """La frise range un jalon au mois de l'engagement qu'il tient. Sans les
    engagements figes, une version passee aurait pose ces jalons ailleurs."""
    snap = _seed_cycle(client, db, seeded)
    viewer = _viewer(db, seeded)
    past = _squad_row(_data(db, seeded, viewer, as_of=snap["submitted_at"][:10]))

    otd = next(o for o in past["detail"]["otds"] if o["title"] == "Plan presente")
    assert otd["month"] == 5, "juin"
    posed = sorted(it["title"] for g in report_mod.timeline_groups(past["detail"])
                   for it in g["items"] if g["month"] == 5)
    assert posed == ["Bascule", "Socle pose"]


def test_a_squad_that_had_not_submitted_is_named_not_replaced(client, db, seeded):
    """Une squad absente d'une version se lit comme une squad qui n'existait pas.
    La remplacer par son etat du jour serait pire: le document aurait l'air complet."""
    snap = _seed_cycle(client, db, seeded)
    viewer = _viewer(db, seeded)
    data = _data(db, seeded, viewer, as_of=snap["submitted_at"][:10])

    names = [r["name"] for blk in data["tribes"] for r in blk["squads"]]
    assert names == ["Squad A"]
    assert data["as_of_missing"] == ["Squad B"]
    assert data["summary"]["squads_total"] == 1


def test_the_document_says_that_it_is_a_version(client, db, seeded):
    """Un document date qui ne se dit pas date est le pire des deux mondes: il a
    l'air du rapport d'aujourd'hui et il en donne les chiffres d'hier."""
    snap = _seed_cycle(client, db, seeded)
    viewer = _viewer(db, seeded)
    data = _data(db, seeded, viewer, as_of=snap["submitted_at"][:10])

    html = report_mod.render_html(data)
    from app.reportcommon import fmt_date
    assert f'version du {fmt_date(data["as_of"], "fr")}' in html  # 22/08/2026, not ISO
    assert "1 squad sans saisie" in html
    deck = report_mod.render_pptx(data)
    assert isinstance(deck, bytes) and len(deck) > 10_000


def test_the_versions_are_listed_with_the_day_and_the_count(client, db, seeded):
    """Une version est une journee, pas une soumission: treize squads soumettent le
    meme lundi et c'est cette date que le lecteur choisit."""
    snap = _seed_cycle(client, db, seeded)
    _submit(client, seeded["squad_b"])
    day = snap["submitted_at"][:10]

    versions = list_versions(db, [seeded["squad_a"], seeded["squad_b"]], YEAR)
    assert [v["date"] for v in versions] == [day]
    assert versions[0]["squads"] == 2

    r = client.get(f"/api/reports/versions?year={YEAR}&tribe_id={seeded['t1']}")
    assert r.status_code == 200, r.text
    assert r.json()["versions"][0]["date"] == day


def test_the_export_routes_take_that_version(client, db, seeded):
    """Le parametre est le meme sur les trois documents: une version se demande
    une fois et se lit partout."""
    snap = _seed_cycle(client, db, seeded)
    day = snap["submitted_at"][:10]

    r = client.get(f"/api/reports/dashboard.html?year={YEAR}&as_of={day}")
    from app.reportcommon import fmt_date
    assert r.status_code == 200 and f"version du {fmt_date(day, 'fr')}" in r.text
    assert client.get(f"/api/reports/roadmap.html?year={YEAR}&as_of={day}").status_code == 200
    assert client.get(f"/api/reports/dashboard.pptx?year={YEAR}&as_of={day}").status_code == 200
    # Une date illisible est refusee, elle n'est pas ignoree en silence: un
    # document rendu sur la date du jour se lirait comme la version demandee.
    assert client.get(f"/api/reports/dashboard.html?year={YEAR}&as_of=hier").status_code == 422


def test_the_frozen_payload_carries_no_budget_figure(client, db, seeded):
    """Une saisie figee se lit par tout utilisateur qui voit la squad, alors que le
    budget ne se montre qu'a ses responsables: le geler l'aurait ouvert a tous."""
    squad = db.get(Squad, seeded["squad_a"])
    squad.budget_enabled = True
    db.commit()
    _seed_cycle(client, db, seeded)

    snap = db.scalar(select(ReportSnapshot).where(ReportSnapshot.squad_id == seeded["squad_a"]))
    assert "budget" not in snap.payload

    login(client, seeded["member"])
    body = client.get(f"/api/squads/{seeded['squad_a']}/snapshots/{snap.id}").json()
    assert "budget" not in body["payload"]


def test_a_version_does_not_widen_what_a_reader_may_see(client, db, seeded):
    """Le perimetre reste celui d'aujourd'hui: une version passee n'est pas une
    porte derobee vers les squads d'une autre tribu."""
    _seed_cycle(client, db, seeded)
    login(client, seeded["admin"])
    _submit(client, seeded["squad_c"])          # squad de l'autre tribu

    login(client, seeded["sl_a"])               # squad leader de la tribu 1
    versions = client.get(f"/api/reports/versions?year={YEAR}").json()["versions"]
    assert versions, "sa propre tribu a bien une version"
    r = client.get(f"/api/reports/dashboard.html?year={YEAR}&as_of={versions[0]['date']}")
    assert r.status_code == 200
    assert "Squad C" not in r.text


def test_a_submission_opens_as_its_own_document(client, db, seeded):
    """The frozen report's HTML/PPTX buttons replay the export at the submission's
    own instant: two submissions of the same day stay two documents."""
    login(client, seeded["sl_a"])
    sq = seeded["squad_a"]
    client.put(f"/api/squads/{sq}/mood", json={"mood": "good"})
    first = client.post(f"/api/squads/{sq}/snapshots", json={"year": YEAR}).json()
    client.put(f"/api/squads/{sq}/mood", json={"mood": "bad"})
    second = client.post(f"/api/squads/{sq}/snapshots", json={"year": YEAR}).json()
    login(client, seeded["admin"])
    a = client.get(f"/api/reports/weekly.html?squad_id={sq}&year={YEAR}&as_of={first['submitted_at']}")
    b = client.get(f"/api/reports/weekly.html?squad_id={sq}&year={YEAR}&as_of={second['submitted_at']}")
    assert a.status_code == 200 and b.status_code == 200
    assert a.text != b.text
    assert client.get(f"/api/reports/weekly.pptx?squad_id={sq}&year={YEAR}"
                      f"&as_of={second['submitted_at']}").status_code == 200
