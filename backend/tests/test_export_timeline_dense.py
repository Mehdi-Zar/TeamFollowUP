"""La frise a la densite du jeu de donnees de demonstration.

``test_export_timeline.py`` monte une squad a la main, avec ce qu'il faut pour
verifier une regle a la fois. Une mise en page, elle, ne casse pas sur un cas:
elle casse quand tout arrive ensemble, neuf jalons dont trois dans le meme
trimestre, cinq engagements dont un en decembre, plusieurs themes et des titres
de soixante-dix caracteres. C'est ce que produit ``seed_fake``, et ce fichier
s'en sert comme d'un cas de charge.

Il tient donc deux choses, et la premiere garde la seconde: que le jeu de donnees
reste assez dense pour avoir une valeur de test (il a longtemps porte cinq jalons
de titre court, jamais plus de deux par trimestre, et aucun engagement, si bien
que la bande du haut n'etait jamais dessinee), puis que **rien ne se recouvre et
rien ne soit coupe** a cette densite, sur aucune des treize slides.

Ces regles sont ce qu'on attend de cette mise en page, et elles disent pourquoi
elle est faite ainsi: les engagements tiennent dans leur case de mois, les boites
de jalons sont rangees dans l'ordre des dates, et leurs traits passent sous la
bande des engagements. Aucun trait ne peut donc en traverser un autre ni recouvrir
un titre.
Les jalons ont d'abord flotte dans des boites reliees a leur mois par des fleches,
qui devaient elles-memes eviter les engagements; chaque cas particulier appelait
son correctif, et aucun test ne pouvait promettre que le suivant ne casserait pas.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app import report as report_mod
from app import seed_fake
from app.models import User

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


def _deck(db, viewer):
    pptx = pytest.importorskip("pptx")
    data = report_mod.build_report_data(db, None, YEAR, 7, lang="fr", viewer=viewer)
    return pptx.Presentation(io.BytesIO(report_mod.render_pptx(data))), data


def _texts(slide):
    """Les formes qui portent du texte, en rectangles (gauche, haut, droite, bas)."""
    return [(sh.left, sh.top, sh.left + sh.width, sh.top + sh.height, sh.text_frame.text)
            for sh in slide.shapes
            if sh.has_text_frame and sh.text_frame.text.strip()]


def test_the_demo_data_is_dense_enough_to_be_a_test_case(db, fake):
    """Un jeu de donnees trop sage valide une mise en page qui n'a rien eu a ranger."""
    dets = _details(db, fake)
    assert len(dets) >= 10

    jalons = [(d, it) for d in dets for q in d["quarters"] for it in q["items"]]
    assert len(jalons) >= 100, "il faut des jalons en nombre, pas un par trimestre"
    # Un trimestre charge est ce qui fait grandir une voie de la frise.
    assert max(len(q["items"]) for d in dets for q in d["quarters"]) >= 3
    # Un titre plus long qu'une ligne est ce qui fait travailler le rangement.
    assert max(len(it["title"]) for _, it in jalons) >= 70
    # Plusieurs boites par squad, sinon la frise n'a rien eu a ranger.
    assert max(len(report_mod.timeline_groups(d)) for d in dets) >= 4


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
    prs, _ = _deck(db, fake)
    w, h = prs.slide_width, prs.slide_height

    outside = [(i, sh.name, sh.left, sh.top, sh.width, sh.height)
               for i, s in enumerate(prs.slides) for sh in s.shapes
               if sh.left < 0 or sh.top < 0 or sh.left + sh.width > w or sh.top + sh.height > h]
    assert not outside, outside[:5]


def test_no_two_texts_ever_overlap(db, fake):
    """La promesse de la grille, et la seule qui vaille: deux textes ne se
    recouvrent jamais.

    Un titre pose sur un autre en cache un. L'engagement ou le jalon est toujours
    la, mais il ne se lit plus, ce qui revient au meme en comite. Une forme qui en
    contient une autre n'est pas un recouvrement: c'est le cas d'une carte et de
    son titre, ou d'une voie et de ses jalons.
    """
    prs, _ = _deck(db, fake)
    clashes = []
    for i, slide in enumerate(prs.slides):
        boxes = _texts(slide)
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                l1, t1, r1, b1, x1 = boxes[a]
                l2, t2, r2, b2, x2 = boxes[b]
                if not (l1 < r2 and l2 < r1 and t1 < b2 and t2 < b1):
                    continue
                if (l1 <= l2 and t1 <= t2 and r1 >= r2 and b1 >= b2) or \
                   (l2 <= l1 and t2 <= t1 and r2 >= r1 and b2 >= b1):
                    continue                      # l'un contient l'autre
                clashes.append(f"slide {i}: « {x1[:30]} » recouvre « {x2[:30]} »")
    assert not clashes, clashes[:5]


def test_nothing_is_dropped_and_nothing_is_written_below_8_points(db, fake):
    """A cette densite, aucune boite de jalons ne disparait et aucun texte ne
    descend sous 8 points.

    La regle a change: la frise descendait jusqu'a 6,6 points pour ne jamais
    couper un titre, et ce texte ne se lisait plus une fois la slide projetee. Le
    corps s'arrete maintenant a 8 points, et c'est le titre qui se coupe, avec
    « … » (sur un mot, jamais au milieu d'un mot sans le signaler). Une coupe
    reste preferable a une boite retiree: la boite absente ne dit plus rien.
    """
    prs, _ = _deck(db, fake)
    small = [(i, r.font.size.pt, r.text[:30]) for i, s in enumerate(prs.slides) for sh in s.shapes
             if sh.has_text_frame for p in sh.text_frame.paragraphs for r in p.runs
             if r.font.size is not None and r.font.size.pt < 8 and r.text.strip()]
    assert not small, small[:5]
    dropped = [(i, sh.text_frame.text[:60]) for i, s in enumerate(prs.slides) for sh in s.shapes
               if sh.has_text_frame and "faute de place" in sh.text_frame.text]
    assert not dropped, dropped[:5]


def _box_top(slide):
    """Le haut des boites de jalons, qui separe la bande des engagements du reste.

    Une boite est le seul rectangle arrondi en pointille de la slide.
    """
    from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
    from pptx.enum.dml import MSO_LINE_DASH_STYLE
    tops = [sh.top for sh in slide.shapes
            if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
            and sh.auto_shape_type == MSO_SHAPE.ROUNDED_RECTANGLE
            and sh.line.dash_style == MSO_LINE_DASH_STYLE.DASH]
    return min(tops) if tops else None


def _commitment_shapes(slide, titles):
    """Les etoiles et les titres de la bande des engagements, en rectangles.

    Le titre d'une boite reprend celui de son engagement: on ne garde donc que ce
    qui est au-dessus des boites.
    """
    from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
    top = _box_top(slide)
    out = []
    for sh in slide.shapes:
        if top is not None and sh.top >= top:
            continue
        if (sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
                and sh.auto_shape_type == MSO_SHAPE.STAR_5_POINT):
            out.append((sh.left, sh.top, sh.left + sh.width, sh.top + sh.height, "*"))
        elif sh.has_text_frame and sh.text_frame.text in titles:
            out.append((sh.left, sh.top, sh.left + sh.width, sh.top + sh.height,
                        sh.text_frame.text))
    return out


def test_a_commitment_never_spills_out_of_its_month(db, fake):
    """Un engagement tient dans la largeur d'une case de mois, son titre passant a
    la ligne. Etale a cote de son etoile, il courait sur trois ou quatre mois et on
    ne savait plus a quelle colonne il repondait."""
    pytest.importorskip("pptx")
    from pptx.util import Inches

    prs, data = _deck(db, fake)
    titles = {o["title"] for blk in data["tribes"] for r in blk["squads"]
              if r.get("detail") for o in r["detail"]["otds"]}
    month = Inches((12.80 - 2.20) / 12)

    seen = 0
    for i, slide in enumerate(prs.slides):
        for left, _t, right, _b, txt in _commitment_shapes(slide, titles):
            if txt == "*":
                continue
            assert right - left <= month, f"slide {i}: « {txt[:30] } » deborde son mois"
            seen += 1
    assert seen >= 20, "la densite du jeu de demonstration doit fournir des cas"


def test_no_link_ever_touches_a_commitment(db, fake):
    """Les traits qui relient une boite a sa date partent d'un point pose **sous**
    la bande des engagements, jamais dessus.

    C'est ce qui remplace le routage: la geometrie interdit le croisement au lieu
    de l'eviter au cas par cas. Les mises en page precedentes faisaient passer ces
    traits au milieu des titres, puis derriere eux, puis dans les couloirs libres
    entre eux, et chaque cas particulier appelait son correctif.
    """
    pytest.importorskip("pptx")
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs, data = _deck(db, fake)
    titles = {o["title"] for blk in data["tribes"] for r in blk["squads"]
              if r.get("detail") for o in r["detail"]["otds"]}

    links = 0
    for i, slide in enumerate(prs.slides):
        blocks = _commitment_shapes(slide, titles)
        for sh in slide.shapes:
            if sh.shape_type != MSO_SHAPE_TYPE.LINE:
                continue
            links += 1
            l1, t1 = sh.left, sh.top
            r1, b1 = sh.left + sh.width, sh.top + sh.height
            for l2, t2, r2, b2, txt in blocks:
                assert not (l1 < r2 and l2 < r1 and t1 < b2 and t2 < b1), \
                    f"slide {i}: un trait traverse « {txt[:30]} »"
    assert links >= 30, "sans trait, ce test ne verifie rien"


def test_two_commitments_of_the_same_month_are_stacked(db, fake):
    """Deux engagements du meme mois se suivent dans la meme colonne, l'un sous
    l'autre: cote a cote, chacun aurait un centimetre de large.

    Ce sont les etoiles qu'on mesure, et non les titres: le jeu de demonstration
    reutilise les memes intitules d'une squad a l'autre, donc un titre ne designe
    pas un engagement.
    """
    pytest.importorskip("pptx")
    from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
    from pptx.util import Inches

    prs, data = _deck(db, fake)
    AX0 = Inches(2.20)
    MW = (Inches(12.80) - AX0) / 12
    rows = [r for blk in data["tribes"] for r in blk["squads"] if r.get("detail")]

    pairs = 0
    for i, (slide, r) in enumerate(zip(list(prs.slides)[1:], rows)):
        top = _box_top(slide)
        stars = [sh for sh in slide.shapes
                 if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
                 and sh.auto_shape_type == MSO_SHAPE.STAR_5_POINT
                 and (top is None or sh.top < top)]
        months: dict[int, int] = {}
        for o in r["detail"]["otds"]:
            if o.get("month") is not None:
                months[o["month"]] = months.get(o["month"], 0) + 1
        for month, count in months.items():
            if count < 2:
                continue
            pairs += 1
            column = [sh for sh in stars
                      if 0 <= (sh.left + sh.width / 2) - (AX0 + month * MW) <= MW]
            assert len(column) == count, f"slide {i}: {len(column)} etoiles en {month}"
            assert len({sh.left for sh in column}) == 1, "deux etoiles cote a cote"
            assert len({sh.top for sh in column}) == count, "deux etoiles superposees"
    assert pairs >= 1, "le jeu de demonstration doit porter deux engagements le meme mois"


def test_every_milestone_carries_a_status_tick(db, fake):
    """Une coche par jalon, pleine quand il est livre: c'est ce qui se lit en
    premier dans une boite, avant meme son titre."""
    pytest.importorskip("pptx")
    from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
    from pptx.util import Inches

    prs, data = _deck(db, fake)
    rows = [r for blk in data["tribes"] for r in blk["squads"] if r.get("detail")]
    for i, (slide, r) in enumerate(zip(list(prs.slides)[1:], rows)):
        expected = sum(len(g["items"]) for g in report_mod.timeline_groups(r["detail"]))
        top = _box_top(slide)
        ticks = [sh for sh in slide.shapes
                 if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
                 and sh.auto_shape_type == MSO_SHAPE.OVAL
                 and top is not None and sh.top > top
                 and Inches(0.13) <= sh.width <= Inches(0.17)]
        # Les boites qui n'ont pas trouve de place sont comptees sous la frise: la
        # slide en porte donc au plus autant que la donnee en compte.
        assert 0 < len(ticks) <= expected, f"slide {i}: {len(ticks)} coches pour {expected} jalons"


def test_the_tick_tells_three_states_by_its_drawing(db, fake):
    """Fait, en cours, pas commence: trois dessins, pas trois nuances de la meme
    pastille. Une couleur seule ne se lit pas une fois la slide projetee."""
    pytest.importorskip("pptx")
    from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
    from pptx.util import Inches

    prs, data = _deck(db, fake)
    checks = dots = 0
    for slide in list(prs.slides)[1:]:
        top = _box_top(slide)
        if top is None:
            continue
        checks += sum(1 for sh in slide.shapes
                      if sh.shape_type == MSO_SHAPE_TYPE.FREEFORM and sh.top > top)
        dots += sum(1 for sh in slide.shapes
                    if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
                    and sh.auto_shape_type == MSO_SHAPE.OVAL
                    and sh.top > top and sh.width < Inches(0.10))
    assert checks > 0, "aucun jalon livre n'est coche"
    assert dots > 0, "aucun jalon en cours n'a son point central"


def test_no_box_is_dropped_at_this_density(db, fake):
    """Aucune boite comptee en « +... » sous la frise: le calcul doit trouver une
    mise en page pour toutes, quitte a empiler et a descendre d'un corps.

    C'est l'invariant qui paie les autres. Un corps plus gros qui fait tomber deux
    boites sous la frise rend le document moins lisible, pas plus: ce qui manque
    ne se lit pas du tout.
    """
    prs, _ = _deck(db, fake)
    notes = [(i, sh.text_frame.text) for i, s in enumerate(list(prs.slides)[1:])
             for sh in s.shapes
             if sh.has_text_frame and sh.text_frame.text.startswith("+")]
    assert not notes, notes[:5]
