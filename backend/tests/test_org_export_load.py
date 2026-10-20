"""L'organigramme exporte sous forte charge: lisible quel que soit le nombre de noeuds.

Au-dela de ce qu'une slide tient en cartes lisibles, l'export passe sur plusieurs
slides (vue d'ensemble, puis une par branche, coupee en « (suite) » au besoin).
Ces tests le tiennent sur des arbres ecrits pour casser une slide unique: une
branche de cent vingt equipes, quarante branches sous la racine, un arbre profond.
"""
from __future__ import annotations

import io

import pytest

from app.orgrender import render_org_pptx

EMU = 914400


def _node(title, person=None, children=(), squad_id=None, status=None):
    return {"id": None, "title": title, "person_name": person, "squad_id": squad_id,
            "squad_status": status, "children": list(children)}


def _wide():
    """Dix domaines de dix equipes, une branche geante et des titres longs."""
    domains = [_node(f"Domaine {d} et services associes", None,
                     [_node(f"Equipe {d}.{p} exploitation", f"Prenom Nomdefamille{p}",
                            squad_id=p + 1, status=("on_track", "at_risk", "blocked")[p % 3])
                      for p in range(10)])
               for d in range(10)]
    giant = _node("Branche geante", "Responsable Branche",
                  [_node(f"Cellule {i} supervision", f"Agent Numero{i}") for i in range(120)])
    return [_node("Direction de la tribe", "Thomas Lefevre", domains + [giant])]


def _flat():
    """Quarante branches directement sous la racine, chacune avec deux equipes."""
    return [_node("Direction", "Chef", [_node(f"Branche {i} produit", None,
                                              [_node(f"Squad {i}.{k}", f"Nom Prenom{k}") for k in range(2)])
                                        for i in range(40)])]


def _deep():
    """Une chaine de sept niveaux, chacun avec trois enfants a son dernier etage."""
    node = _node("Niveau 7", None, [_node(f"Feuille {k}", f"Personne {k}") for k in range(3)])
    for lvl in range(6, 0, -1):
        node = _node(f"Niveau {lvl}", f"Chef {lvl}", [node, _node(f"Voisin {lvl}", None)])
    return [node]


def _titles(roots):
    out = []

    def walk(n):
        out.append(n["title"])
        for k in n["children"]:
            walk(k)
    for r in roots:
        walk(r)
    return out


def _boxes(slide):
    from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
    return [sh for sh in slide.shapes
            if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
            and sh.auto_shape_type == MSO_SHAPE.ROUNDED_RECTANGLE
            and sh.has_text_frame and sh.text_frame.text.strip()]


@pytest.fixture(params=["wide", "flat", "deep"])
def case(request):
    pytest.importorskip("pptx")
    from pptx import Presentation
    roots = {"wide": _wide, "flat": _flat, "deep": _deep}[request.param]()
    return roots, Presentation(io.BytesIO(render_org_pptx(roots, "Charge", lang="fr")))


def test_a_wide_tree_spreads_over_several_slides(case):
    """Un arbre large passe sur plusieurs slides; un arbre profond mais etroit
    tient sur une, ses cartes restant lisibles (verifie plus bas)."""
    roots, prs = case
    if roots[0]["title"] != "Niveau 1":
        assert len(prs.slides) > 1


def test_every_node_is_on_a_slide_in_full(case):
    """Chaque noeud a sa carte, avec son titre entier: rien n'est tu ni ampute."""
    roots, prs = case
    texts = {sh.text_frame.paragraphs[0].text for s in prs.slides for sh in _boxes(s)}
    missing = [t for t in _titles(roots) if t not in texts]
    assert not missing, missing[:5]


def test_no_shape_falls_outside_a_slide(case):
    _, prs = case
    w, h = prs.slide_width, prs.slide_height
    outside = [(i, sh.name) for i, s in enumerate(prs.slides) for sh in s.shapes
               if sh.left < 0 or sh.top < 0 or sh.left + sh.width > w or sh.top + sh.height > h]
    assert not outside, outside[:5]


def test_two_boxes_never_overlap(case):
    _, prs = case
    clashes = []
    for i, s in enumerate(prs.slides):
        boxes = _boxes(s)
        for k, a in enumerate(boxes):
            for b in boxes[k + 1:]:
                if (a.left < b.left + b.width and b.left < a.left + a.width
                        and a.top < b.top + b.height and b.top < a.top + a.height):
                    clashes.append((i, a.text_frame.text[:20], b.text_frame.text[:20]))
    assert not clashes, clashes[:5]


def test_cards_stay_readable(case):
    """Des cartes d'au moins 1,2 pouce sur 0,42, un titre d'au moins 9 points et
    un nom d'au moins 8,5: c'est le seuil sous lequel l'export change de slide."""
    _, prs = case
    bad = []
    for i, s in enumerate(prs.slides):
        for box in _boxes(s):
            if box.width < 1.2 * EMU or box.height < 0.42 * EMU:
                bad.append((i, "size", box.text_frame.text[:20], box.width / EMU, box.height / EMU))
            paras = box.text_frame.paragraphs
            if paras[0].runs and paras[0].runs[0].font.size.pt < 9:
                bad.append((i, "title", paras[0].text, paras[0].runs[0].font.size.pt))
            for p in paras[1:]:
                if p.runs and p.runs[0].font.size.pt < 8.5:
                    bad.append((i, "name", p.text, p.runs[0].font.size.pt))
    assert not bad, bad[:5]


def test_a_continued_branch_says_so():
    """Une branche coupee sur plusieurs slides porte « (suite) » dans son titre."""
    pytest.importorskip("pptx")
    from pptx import Presentation
    prs = Presentation(io.BytesIO(render_org_pptx(_wide(), "Charge", lang="fr")))
    heads = [s.shapes[0].text_frame.text for s in prs.slides]
    assert any("Branche geante" in h and "(suite)" in h for h in heads), heads
    # La vue d'ensemble dit ce que porte chaque branche.
    over = " ".join(sh.text_frame.text for sh in _boxes(prs.slides[0]))
    assert "120 éléments" in over and "10 éléments" in over
