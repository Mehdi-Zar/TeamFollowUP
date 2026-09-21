"""La frise annuelle telle qu'elle part: en HTML, en JPG et en PPTX.

Les trois exports racontaient l'annee en trois blocs separes, comme le faisait la
page: les initiatives, les engagements OTD, puis une roadmap en quatre colonnes.
Ils les posent maintenant sur un seul axe, le temps, qui est la seule chose que
ces objets ont en commun.

Ce qui se teste ici n'est pas la mise en page, qui bougera, mais ce qu'elle ne
doit jamais perdre: un jalon rattache a son engagement, un jalon rattache a rien
qui reste visible quand meme, un engagement pose au bon mois, un engagement sans
date qui est dit plutot que tu, et deux engagements qui ne se recouvrent pas. Le
JPG n'a pas de test propre: il est produit par le navigateur a partir de ce meme
HTML, donc le tester reviendrait a tester le navigateur.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import zipfile

import pytest
from sqlalchemy import select

from app import report as report_mod
from app.models import Initiative, Objective, Otd, RoadmapItem, Squad, User
from app.reportcommon import pack_otds

YEAR = 2026


def _utc(month: int, day: int, year: int = YEAR) -> dt.datetime:
    return dt.datetime(year, month, day, tzinfo=dt.timezone.utc)


@pytest.fixture()
def chained(db, seeded):
    """Une squad ou le chainage complet existe: une initiative, un objectif qui la
    sert, des jalons qui repondent a l'objectif, un jalon qui ne repond a rien, et
    des engagements OTD dates."""
    squad_id, tribe_id = seeded["squad_a"], seeded["t1"]
    squad = db.get(Squad, squad_id)
    squad.mood, squad.mood_at = "mixed", _utc(9, 1)
    squad.mood_comment = "Charge forte sur la fin de trimestre"

    init = Initiative(tribe_id=tribe_id, year=YEAR, title="Reduire le temps de build",
                      squad_id=squad_id, owner="Alice Martin", deadline=_utc(6, 30))
    db.add(init)
    db.flush()
    obj = Objective(squad_id=squad_id, year=YEAR, title="Diviser le demarrage par deux",
                    initiative_id=init.id, rag_status="amber", weight=1)
    db.add(obj)
    db.flush()
    leader = db.get(User, squad.leader_user_id)
    manage = Otd(tribe_id=tribe_id, year=YEAR, title="Plan VCF9 presente",
                 committed_date=_utc(2, 15), owner_user_id=leader.id, display_order=1)
    db.add(manage)
    db.add(Otd(tribe_id=tribe_id, year=YEAR, title="Adoption du modele dans deux pays",
               committed_date=_utc(2, 20), owner_user_id=leader.id, display_order=2))
    db.add(Otd(tribe_id=tribe_id, year=YEAR, title="Engagement sans date arretee",
               committed_date=None, owner_user_id=leader.id, display_order=3))
    # L'engagement que la squad prend elle-meme, a cote de celui du management.
    own = Otd(tribe_id=tribe_id, year=YEAR, title="Bascule 25G", scope="squad",
              squad_id=squad_id, committed_date=_utc(9, 30), owner_user_id=leader.id,
              display_order=4)
    db.add(own)
    db.flush()

    db.add(RoadmapItem(squad_id=squad_id, year=YEAR, quarter=1, title="Cache des dependances",
                       release_stage="EA", status="on_track", objective_id=obj.id,
                       otd_id=manage.id))
    # Celui-ci tient les deux engagements a la fois: le lien du management et
    # celui de la squad sont deux colonnes distinctes, justement pour cela.
    db.add(RoadmapItem(squad_id=squad_id, year=YEAR, quarter=3, title="Build incremental",
                       release_stage="GA", status="at_risk", objective_id=obj.id,
                       otd_id=manage.id, squad_otd_id=own.id))
    # Celui-la ne tient aucun engagement: il doit rester visible.
    db.add(RoadmapItem(squad_id=squad_id, year=YEAR, quarter=2, title="Nettoyage des images",
                       release_stage="EA", status="blocked"))
    db.commit()
    return squad_id, db.scalar(select(User).where(User.email == seeded["admin"]))


def _data(db, squad_id, viewer, **kw):
    return report_mod.build_report_data(db, None, YEAR, 7, squad_id=squad_id,
                                        viewer=viewer, lang="fr", **kw)


def _deck_text(blob: bytes) -> str:
    runs: list[str] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                runs += re.findall(r"<a:t>(.*?)</a:t>", z.read(name).decode("utf-8"), re.S)
    return "\n".join(runs)


# ----- ce que la frise assemble --------------------------------------------------

def test_the_milestones_hang_under_the_commitment_they_hold(db, chained):
    """La frise repond a « quels jalons tiennent cet engagement », qui est la
    question du comite: une initiative est une intention, un engagement est une date."""
    squad_id, viewer = chained
    det = _data(db, squad_id, viewer)["tribes"][0]["squads"][0]["detail"]
    rows = report_mod.timeline_rows(det, "fr")

    held = next(r for r in rows if r["title"] == "Plan VCF9 presente")
    assert {it["title"] for it in held["items"]} == {"Cache des dependances", "Build incremental"}
    assert {it["quarter"] for it in held["items"]} == {1, 3}
    assert held["scope"] == "management"


def test_a_milestone_holding_both_commitments_appears_under_both(db, chained):
    """Le meme travail lu par deux promesses. Avec un lien unique, le dernier qui
    rattache defaisait le travail de l'autre sans le lui dire."""
    squad_id, viewer = chained
    det = _data(db, squad_id, viewer)["tribes"][0]["squads"][0]["detail"]
    rows = {r["title"]: r for r in report_mod.timeline_rows(det, "fr")}

    assert "Build incremental" in {it["title"] for it in rows["Plan VCF9 presente"]["items"]}
    assert [it["title"] for it in rows["Bascule 25G"]["items"]] == ["Build incremental"]
    assert rows["Bascule 25G"]["scope"] == "squad"


def test_the_two_scopes_are_told_apart_in_the_timeline_data(db, chained):
    """La distinction doit exister dans la donnee, pas seulement dans la couleur:
    c'est elle que les deux rendus peignent."""
    squad_id, viewer = chained
    det = _data(db, squad_id, viewer)["tribes"][0]["squads"][0]["detail"]
    scopes = {o["title"]: o["scope"] for o in det["otds"]}

    assert scopes["Plan VCF9 presente"] == "management"
    assert scopes["Bascule 25G"] == "squad"
    # Le management d'abord: la frise se lit de l'engagement subi vers celui qu'on choisit.
    assert [o["scope"] for o in det["otds"]][-1] == "squad"


def test_a_milestone_holding_nothing_keeps_its_own_row(db, chained):
    """Un jalon absent d'un export se lit comme un jalon qui n'existe pas."""
    squad_id, viewer = chained
    det = _data(db, squad_id, viewer)["tribes"][0]["squads"][0]["detail"]
    rows = report_mod.timeline_rows(det, "fr")

    orphans = next(r for r in rows if r["key"] == "none")
    assert [it["title"] for it in orphans["items"]] == ["Nettoyage des images"]
    assert orphans["title"] is None, "ces jalons ne forment pas une categorie nommee"


def test_the_commitments_carry_their_month_and_their_status(db, chained):
    """Le mois est ce qui pose un engagement sur l'axe; sans lui il n'a pas de place."""
    squad_id, viewer = chained
    det = _data(db, squad_id, viewer)["tribes"][0]["squads"][0]["detail"]
    by_title = {o["title"]: o for o in det["otds"]}

    assert by_title["Plan VCF9 presente"]["month"] == 1          # fevrier
    assert by_title["Engagement sans date arretee"]["month"] is None
    assert by_title["Plan VCF9 presente"]["status"] == "late"    # date passee, rien de livre


def test_a_commitment_of_another_year_does_not_land_on_this_axis(db, chained, seeded):
    """Une date de 2025 n'a pas de mois sur la frise 2026: elle serait posee a faux."""
    squad_id, viewer = chained
    squad = db.get(Squad, squad_id)
    db.add(Otd(tribe_id=seeded["t1"], year=YEAR, title="Reste de l'an dernier",
               committed_date=_utc(11, 30, YEAR - 1), owner_user_id=squad.leader_user_id))
    db.commit()

    det = _data(db, squad_id, viewer)["tribes"][0]["squads"][0]["detail"]
    assert next(o for o in det["otds"] if o["title"] == "Reste de l'an dernier")["month"] is None


def test_two_commitments_close_together_are_stacked_not_superimposed(db, chained):
    """Deux engagements de fevrier se genent: l'un descend d'une bande."""
    squad_id, viewer = chained
    det = _data(db, squad_id, viewer)["tribes"][0]["squads"][0]["detail"]
    placed, hidden = pack_otds(det["otds"], chars_per_month=8)

    assert hidden == 0
    assert {row for _, _, _, row in placed} == {0, 1}
    spans = [(start, start + width, row) for _, start, width, row in placed]
    assert all(not (a0 < b1 and b0 < a1) for i, (a0, a1, ar) in enumerate(spans)
               for (b0, b1, br) in spans[i + 1:] if ar == br)


def test_a_long_title_takes_more_room_than_a_short_one(db, chained):
    """Un titre tronque a trois lettres ne dit rien: la largeur suit le texte."""
    otds = [{"title": "Court", "month": 0}, {"title": "Un titre nettement plus long", "month": 6}]
    placed, _ = pack_otds(otds, chars_per_month=8)
    widths = {o["title"]: w for o, _, w, _ in placed}
    assert widths["Un titre nettement plus long"] > widths["Court"]


def test_a_band_that_is_full_says_so_instead_of_dropping_the_rest(db):
    """Sur une slide la hauteur ne s'etire pas; ce qui ne tient pas est compte."""
    otds = [{"title": f"Engagement {i}", "month": 3} for i in range(6)]
    placed, hidden = pack_otds(otds, chars_per_month=16, max_rows=3)
    assert len(placed) == 3 and hidden == 3


# ----- ce que les documents montrent ---------------------------------------------

def test_the_html_export_shows_the_whole_block(db, chained):
    squad_id, viewer = chained
    html = report_mod.render_html(_data(db, squad_id, viewer))

    assert 'class="xtl-grid"' in html
    assert len(re.findall(r"<b>Q[1-4]</b>", html)) == 4, "les quatre trimestres"
    assert len(re.findall(r'class="xtl-m"', html)) == 12, "les douze mois"
    assert "Plan VCF9 presente" in html and "Cache des dependances" in html
    # Le jalon est la; la ligne qui le porte n'annonce aucune categorie.
    assert "Nettoyage des images" in html
    assert "hors engagement" not in html
    # Les deux portees se distinguent, et leur legende voyage avec la frise.
    assert "xtl-scope-squad" in html and "Engagement de la squad" in html
    # Un engagement sans date est cite sous la bande, pas efface.
    assert "Engagements sans date" in html and "Engagement sans date arretee" in html
    # Le moral, avec la date qui le date (le libelle part echappe, pas le niveau).
    assert 'class="xtl-mood"' in html and "Moyen" in html and "2026-09-01" in html
    # La feuille de la frise voyage avec elle: l'export JPG n'en charge pas d'autre.
    assert ".xtl-jalon" in html


def test_the_deck_puts_one_squad_on_one_slide(db, chained):
    squad_id, viewer = chained
    deck = report_mod.render_pptx(_data(db, squad_id, viewer))
    text = _deck_text(deck)

    assert "Frise 2026" in text
    assert all(f"Q{q}" in text for q in (1, 2, 3, 4))
    assert "Build incremental" in text
    assert "Nettoyage des images" in text
    assert "Plan VCF9 presente" in text and "Bascule 25G" in text
    assert "Engagement management" in text, "la legende des deux portees"
    assert "Moyen" in text, "le moral declare"


def test_the_deck_says_the_release_stage_of_each_milestone(db, chained):
    """EA ou GA repond a « est-ce ouvert a tout le monde », qui est la premiere
    question posee sur un jalon en comite. Les deux lettres sont dans la boite du
    jalon, et leur legende est au bas de la slide: une abreviation sans legende ne
    dit rien a qui decouvre le document."""
    pptx = pytest.importorskip("pptx")
    squad_id, viewer = chained
    blob = report_mod.render_pptx(_data(db, squad_id, viewer))
    text = _deck_text(blob)
    assert "EA" in text and "GA" in text
    assert "Accès anticipé" in text and "Disponibilité générale" in text

    # La phase suit son jalon dans la meme puce, a l'interieur de la carte: elle
    # ne peut donc plus se poser sur le titre, ce qui etait le risque du modele
    # precedent, ou les deux vivaient dans deux formes superposees.
    prs = pptx.Presentation(io.BytesIO(blob))
    cards = [sh for sh in prs.slides[0].shapes
             if sh.has_text_frame and "Build incremental" in sh.text_frame.text]
    assert cards, "le jalon est dans une carte"
    for card in cards:
        assert "Build incremental (GA)" in card.text_frame.text
        assert card.text_frame.word_wrap is True, "le texte passe a la ligne, il ne se coupe pas"


def test_no_title_is_cut_in_the_deck(db, chained):
    """La demande tient en une phrase: on voit tout le texte, la largeur est fixe,
    et au pire ca passe a la ligne. Un titre coupe ne dit plus rien, et personne
    ne peut deviner ce qui manque."""
    squad_id, viewer = chained
    text = _deck_text(report_mod.render_pptx(_data(db, squad_id, viewer)))

    for title in ("Cache des dependances", "Build incremental", "Nettoyage des images",
                  "Plan VCF9 presente", "Adoption du modele dans deux pays", "Bascule 25G"):
        assert title in text, f"« {title} » n'est pas sorti en entier"
    assert "\u2026" not in text, "aucun titre n'est tronque par des points de suspension"


def test_no_shape_falls_outside_the_slide(db, chained):
    """Une forme hors cadre ne se voit pas a la lecture du code, seulement a la
    projection."""
    pptx = pytest.importorskip("pptx")
    squad_id, viewer = chained
    blob = report_mod.render_pptx(_data(db, squad_id, viewer))
    prs = pptx.Presentation(io.BytesIO(blob))
    w, h = prs.slide_width, prs.slide_height

    outside = [(s_i, sh.name) for s_i, s in enumerate(prs.slides) for sh in s.shapes
               if sh.left < 0 or sh.top < 0 or sh.left + sh.width > w or sh.top + sh.height > h]
    assert not outside, outside[:5]


def test_the_multi_squad_deck_keeps_its_summary_then_one_slide_per_squad(db, chained, seeded):
    """Un export de plusieurs squads garde la synthese; un export d'une seule squad
    est le meme deck sans elle."""
    pptx = pytest.importorskip("pptx")
    _, viewer = chained
    wide = report_mod.build_report_data(db, seeded["t1"], YEAR, 7, viewer=viewer, lang="fr")
    n = len(wide["tribes"][0]["squads"])

    prs = pptx.Presentation(io.BytesIO(report_mod.render_pptx(wide)))
    assert len(prs.slides) == n + 1

    one = _data(db, seeded["squad_a"], viewer)
    assert len(pptx.Presentation(io.BytesIO(report_mod.render_pptx(one))).slides) == 1


def test_a_squad_with_nothing_says_so_rather_than_showing_an_empty_grid(db, seeded):
    """Une squad vierge est un cas normal en janvier, pas une erreur."""
    viewer = db.scalar(select(User).where(User.email == seeded["admin"]))
    html = report_mod.render_html(_data(db, seeded["squad_b"], viewer))
    assert "Aucun engagement, aucun jalon" in html
    assert "Aucun OTD" in html
