"""L'organigramme exporte: une carte par noeud, et rien qui deborde.

Une mise en page d'arbre casse sur la largeur, pas sur la profondeur: une tribu de
quatre branches tient sans effort, une tribu de quatorze squads serre ses cartes
jusqu'a ce qu'elles se touchent. C'est cette densite-la qui se teste ici, et elle
vient du jeu de demonstration plutot que d'un cas ecrit a la main.
"""
from __future__ import annotations

import io

import pytest
from sqlalchemy import select

from app import seed_fake
from app.models import Tribe
from app.orgrender import render_org_pptx
from app.routers.orgexport import _tree_dicts


@pytest.fixture()
def deck(db):
    pptx = pytest.importorskip("pptx")
    seed_fake.run(db)
    tid = db.scalar(select(Tribe.id))
    roots, name = _tree_dicts(db, tid)
    return pptx.Presentation(io.BytesIO(render_org_pptx(roots, name, lang="fr")))


def _boxes(slide):
    """Les cartes de l'arbre: les rectangles arrondis qui portent un nom."""
    from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
    return [sh for sh in slide.shapes
            if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
            and sh.auto_shape_type == MSO_SHAPE.ROUNDED_RECTANGLE
            and sh.has_text_frame and sh.text_frame.text.strip()]


def test_two_boxes_never_overlap(deck):
    """Une carte tient dans son emplacement, quelle que soit la largeur de l'arbre.

    Sa largeur avait un plancher d'1,1 pouce. A quatorze feuilles, un emplacement
    n'en fait plus que 0,9: chaque carte mordait donc sur sa voisine, bordure
    contre bordure, et le nom de l'une passait sur le cadre de l'autre.
    """
    slide = deck.slides[0]
    boxes = _boxes(slide)
    assert len(boxes) >= 14, "le jeu de demonstration doit produire un arbre large"
    clashes = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if (a.left < b.left + b.width and b.left < a.left + a.width
                    and a.top < b.top + b.height and b.top < a.top + a.height):
                clashes.append((a.text_frame.text, b.text_frame.text))
    assert not clashes, clashes[:5]


def test_a_name_never_spills_out_of_its_box(deck):
    """PowerPoint passe un titre a la ligne mais ne coupe pas un mot.

    « Management », plus large que sa carte, en sortait des deux cotes et
    s'ecrivait sur la voisine. Le corps descend donc jusqu'a ce que le mot le plus
    long rentre, et le mot est coupe en dernier ressort.
    """
    slide = deck.slides[0]
    CHAR_W = 0.0088 * 914400 / 72        # largeur d'un caractere gras, par point
    too_wide = []
    for box in _boxes(slide):
        inner = box.width - int(0.12 * 914400)
        for para in box.text_frame.paragraphs:
            for run in para.runs:
                longest = max((len(w) for w in run.text.split()), default=1)
                if longest * CHAR_W * run.font.size.pt > inner:
                    too_wide.append((run.text, round(run.font.size.pt, 1)))
    assert not too_wide, too_wide[:5]


def test_no_shape_falls_outside_the_slide(deck):
    """Hors cadre ne se voit qu'a la projection, et c'est la densite qui l'y pousse."""
    slide = deck.slides[0]
    w, h = deck.slide_width, deck.slide_height
    outside = [(sh.name, sh.left, sh.top) for sh in slide.shapes
               if sh.left < 0 or sh.top < 0 or sh.left + sh.width > w or sh.top + sh.height > h]
    assert not outside, outside[:5]
