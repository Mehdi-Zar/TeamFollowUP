"""Seconde relecture des decks: les coupes de texte ne mangent plus les mots,
une squad qui n'a rien saisi n'est pas « En cours », et les traits de
l'organigramme sont droits et sans ombre."""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest

from app import report as report_mod
from app.reportpptx import _cut, _cut_middle, _pct, _wrap_fit
from app.models import Squad

YEAR = datetime.now(timezone.utc).year


def _prs(blob):
    pptx = pytest.importorskip("pptx")
    return pptx.Presentation(io.BytesIO(blob))


def _text(slide):
    out = []
    for sh in slide.shapes:
        if sh.has_text_frame:
            out.append(sh.text_frame.text)
        if getattr(sh, "has_table", False) and sh.has_table:
            out += [c.text for row in sh.table.rows for c in row.cells]
    return "\n".join(out)


def test_an_already_shortened_word_gets_one_ellipsis_only():
    assert "……" not in _cut("Reversibili… des flux applicatifs", 12)
    assert _cut("Reversibili… des flux applicatifs", 12).count("…") == 1


def test_a_wrapped_title_ends_on_a_whole_word():
    title = "Landing zones certifiees et durcies pour la production"
    out = _wrap_fit(title, 14, 2)
    assert out.endswith("…") and out.count("…") == 1
    assert out[:-1].split()[-1] in title.split()   # un mot entier, pas « certi »
    # Ce qui tient n'est pas touche.
    assert _wrap_fit("Court titre", 20, 2) == "Court titre"


def test_names_cut_in_the_middle_stay_distinct():
    a, b = _cut_middle("Squad supplementaire 12", 16), _cut_middle("Squad supplementaire 13", 16)
    assert a != b and a.endswith("12") and b.endswith("13")


def test_percentages_follow_the_language():
    assert _pct(48, "fr") == "48 %"
    assert _pct(48, "en") == "48%"


def test_a_squad_that_never_submitted_is_not_on_track(db, seeded):
    db.add(Squad(name="Toute neuve", tribe_id=seeded["t1"], display_order=99))
    db.commit()
    data = report_mod.build_report_data(db, None, YEAR, 7, lang="fr")
    txt = "\n".join(_text(s) for s in _prs(report_mod.render_pptx({**data, "doc": "dashboard"})).slides)
    row = next(ln for ln in txt.split("\n") if ln == "Toute neuve")
    assert row and "Non renseigné" in txt


def test_no_leaves_column_when_the_module_is_off(db, seeded):
    data = report_mod.build_report_data(db, None, YEAR, 7, lang="fr")
    last = _prs(report_mod.render_pptx({**data, "leaves_enabled": False})).slides[-1]
    assert "Absences à venir" not in _text(last)
    last = _prs(report_mod.render_pptx(data)).slides[-1]
    assert "Absences à venir" in _text(last)


def test_a_squad_without_leader_says_so(db, seeded):
    sq = db.get(Squad, seeded["squad_c"])  # no leader
    data = report_mod.build_report_data(db, None, YEAR, 7, squad_id=sq.id, lang="fr")
    txt = _text(_prs(report_mod.render_pptx(data)).slides[0])
    assert "Aucun squad leader" in txt and "Squad leader : -" not in txt


def test_org_connectors_are_straight_and_without_shadow():
    from app.orgrender import render_org_pptx
    roots = [{"id": 1, "title": "Direction", "person_name": "Camille Dubois-Martin", "children": [
        {"id": 2, "title": "A", "children": []}, {"id": 3, "title": "B", "children": []},
        {"id": 4, "title": "C", "children": []}]}]
    prs = _prs(render_org_pptx(roots, "Tribe", lang="fr"))
    conns = [sh for sh in prs.slides[0].shapes if sh.shape_type == 4 or sh.__class__.__name__ == "Connector"]
    assert conns
    for c in conns:
        # horizontal ou vertical, jamais en diagonale
        assert c.begin_x == c.end_x or c.begin_y == c.end_y
        assert c.shadow.inherit is False
