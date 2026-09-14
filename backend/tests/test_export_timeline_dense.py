"""La frise a la densite du jeu de donnees de demonstration.

``test_export_timeline.py`` monte une squad a la main, avec ce qu'il faut pour
verifier une regle a la fois. Une mise en page, elle, ne casse pas sur un cas: elle
casse quand tout arrive ensemble, neuf jalons dont trois dans le meme trimestre,
cinq engagements dont un en decembre, deux initiatives et une ligne de jalons qui
n'en sert aucune. C'est ce que produit ``seed_fake``, et ce fichier s'en sert comme
d'un cas de charge.

Il tient donc deux choses, et la premiere garde la seconde: que le jeu de
donnees reste assez dense pour avoir une valeur de test (il a longtemps porte cinq
jalons de titre court, jamais plus de deux par trimestre, et aucun engagement, si
bien que la bande du haut n'etait jamais dessinee), puis qu'a cette densite rien
ne sorte de la slide et qu'aucun titre d'engagement n'en recouvre un autre.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app import report as report_mod
from app import seed_fake
from app.models import Squad, User

YEAR = datetime.now(timezone.utc).year


@pytest.fixture()
def fake(db):
    """La tribe de demonstration, avec le tribe leader comme lecteur."""
    seed_fake.run(db)
    return db.scalar(select(User).where(User.role == "tribe_leader"))


def _details(db, viewer):
    """Le detail de chaque squad, tel que les exports le recoivent."""
    data = report_mod.build_report_data(db, None, YEAR, 7, lang="fr", viewer=viewer)
    return [r["detail"] for blk in data["tribes"] for r in blk["squads"] if r.get("detail")]


def test_the_demo_data_is_dense_enough_to_be_a_test_case(db, fake):
    """Un jeu de donnees trop sage valide une mise en page qui n'a rien eu a ranger."""
    dets = _details(db, fake)
    assert len(dets) >= 10

    jalons = [(d, it) for d in dets for q in d["quarters"] for it in q["items"]]
    assert len(jalons) >= 100, "il faut des jalons en nombre, pas un par trimestre"
    # Un trimestre charge est ce qui fait grandir une ligne de la frise.
    assert max(len(q["items"]) for d in dets for q in d["quarters"]) >= 3
    # Un titre plus long qu'une ligne de boite est ce qui fait travailler la coupe.
    assert max(len(it["title"]) for _, it in jalons) >= 70
    # Une ligne sans initiative, celle des jalons qui ne servent rien.
    assert any(it.get("initiative_id") is None for _, it in jalons)
    # Et des jalons rattaches, sinon la frise n'a qu'une ligne quoi qu'il arrive.
    assert any(it.get("initiative_id") for _, it in jalons)
    assert any(d.get("initiatives") for d in dets)


def test_the_commitment_band_is_loaded_and_reaches_december(db, fake):
    """La bande des engagements etait vide: aucune donnee de demonstration n'en
    portait, donc la moitie haute de la frise ne se dessinait jamais. Decembre
    compte a part, c'est le mois ou plus rien ne tient a droite du repere."""
    dets = _details(db, fake)
    otds = [o for d in dets for o in d["otds"]]
    assert len(otds) >= 40
    assert max(len(d["otds"]) for d in dets) >= 4, "il en faut assez pour s'empiler"
    assert any(o["month"] == 11 for o in otds), "aucun engagement en decembre"
    assert any(o["month"] == 10 for o in otds)
    assert max(len(o["title"]) for o in otds) >= 50


def test_no_shape_falls_outside_a_loaded_slide(db, fake):
    """Une forme hors cadre ne se voit pas a la lecture du code, seulement a la
    projection, et c'est la densite qui l'y pousse."""
    pptx = pytest.importorskip("pptx")
    data = report_mod.build_report_data(db, None, YEAR, 7, lang="fr", viewer=fake)
    prs = pptx.Presentation(io.BytesIO(report_mod.render_pptx(data)))
    w, h = prs.slide_width, prs.slide_height

    outside = [(i, sh.name, sh.left, sh.top, sh.width, sh.height)
               for i, s in enumerate(prs.slides) for sh in s.shapes
               if sh.left < 0 or sh.top < 0 or sh.left + sh.width > w or sh.top + sh.height > h]
    assert not outside, outside[:5]


def test_two_commitment_titles_never_cover_each_other(db, fake):
    """Un titre pose sur un autre en cache un: l'engagement est toujours la, mais
    il ne se lit plus, ce qui revient au meme en comite. Le cas se produit quand
    un titre s'ecrit vers la gauche faute de place a droite, donc vers ses voisins."""
    pptx = pytest.importorskip("pptx")
    data = report_mod.build_report_data(db, None, YEAR, 7, lang="fr", viewer=fake)
    prs = pptx.Presentation(io.BytesIO(report_mod.render_pptx(data)))

    titles = {o["title"] for blk in data["tribes"] for r in blk["squads"]
              if r.get("detail") for o in r["detail"]["otds"]}
    assert titles, "sans engagement, ce test ne verifie rien"

    for i, slide in enumerate(prs.slides):
        boxes = []
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            txt = sh.text_frame.text
            # Un titre coupe ne se reconnait que par son debut; un titre entier
            # doit correspondre exactement, sinon un jalon dont le titre commence
            # comme un engagement se ferait passer pour lui.
            cut = txt.endswith("…")
            head = txt[:-1] if cut else txt
            if not head:
                continue
            if not (txt in titles or (cut and any(t.startswith(head) for t in titles))):
                continue
            boxes.append((sh.left, sh.top, sh.left + sh.width, sh.top + sh.height, txt))
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                l1, t1, r1, b1, x1 = boxes[a]
                l2, t2, r2, b2, x2 = boxes[b]
                if l1 < r2 and l2 < r1 and t1 < b2 and t2 < b1:
                    raise AssertionError(f"slide {i}: « {x1} » recouvre « {x2} »")
