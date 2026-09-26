"""Ce que les decks disent maintenant, et qu'une slide projetee doit dire.

Chaque test tient une regle issue de la relecture des exports: rien d'important
ne disparait derriere « +3 autres », un mois vide dit qui doit encore sa part, un
budget sans montant n'affirme pas qu'il est « sur les rails », et aucun texte ne
descend sous 8 points.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest

from app import report as report_mod
from app.models import Squad

YEAR = datetime.now(timezone.utc).year


def _prs(blob):
    pptx = pytest.importorskip("pptx")
    return pptx.Presentation(io.BytesIO(blob))


def _text(slide):
    """Le texte d'une slide, cellules de tableau comprises."""
    out = []
    for sh in slide.shapes:
        if sh.has_text_frame:
            out.append(sh.text_frame.text)
        if getattr(sh, "has_table", False) and sh.has_table:
            out += [c.text for row in sh.table.rows for c in row.cells]
    return "\n".join(out)


def test_the_summary_table_continues_instead_of_hiding_squads(db, seeded):
    for i in range(25):
        db.add(Squad(name=f"Sq {i:02d}", tribe_id=seeded["t1"], display_order=100 + i))
    db.commit()
    data = report_mod.build_report_data(db, None, YEAR, 7, lang="fr")
    prs = _prs(report_mod.render_pptx({**data, "doc": "dashboard"}))
    names = {r["name"] for blk in data["tribes"] for r in blk["squads"]}
    summary = "\n".join(_text(s) for s in list(prs.slides)[:2])
    assert all(n in summary for n in names)
    assert "autres squads" not in summary
    assert "(suite)" in _text(prs.slides[1])
    assert "Dernière saisie" in _text(prs.slides[0])


def test_a_budget_without_amounts_shows_no_status_chip(db, seeded):
    from app.models import SquadBudget, User
    from sqlalchemy import select
    sq = db.get(Squad, seeded["squad_a"])
    sq.budget_enabled = True
    db.add(SquadBudget(squad_id=sq.id, year=YEAR))
    db.commit()
    admin = db.scalar(select(User).where(User.role == "admin"))
    data = report_mod.build_report_data(db, None, YEAR, 7, squad_id=sq.id, lang="fr", viewer=admin)
    txt = _text(_prs(report_mod.render_pptx(data)).slides[0])
    assert "Montants non renseignés" in txt
    assert "Sur les rails" not in txt


def test_no_text_below_8_points_in_the_weekly_deck(db, seeded):
    data = report_mod.build_report_data(db, None, YEAR, 7, lang="en")
    prs = _prs(report_mod.render_pptx(data))
    small = [r.font.size.pt for s in prs.slides for sh in s.shapes if sh.has_text_frame
             for p in sh.text_frame.paragraphs for r in p.runs
             if r.font.size is not None and r.text.strip() and r.font.size.pt < 8]
    assert not small


def test_the_weekly_deck_ends_on_its_attention_points(db, seeded):
    data = report_mod.build_report_data(db, None, YEAR, 7, lang="fr")
    prs = _prs(report_mod.render_pptx(data))
    assert "Points d'attention" in _text(prs.slides[-1])
    dash = _prs(report_mod.render_pptx({**data, "doc": "dashboard"}))
    assert "Points d'attention" not in _text(dash.slides[-1])


def test_the_initiatives_deck_is_dated_and_keeps_every_row(db, seeded):
    items = [{"id": i, "title": f"Initiative {i:02d}", "owner": None, "squad_name": None,
              "deadline": f"{YEAR - 1}-0{1 + i % 9}-10"} for i in range(20)]
    prs = _prs(report_mod.render_initiatives_pptx({"year": YEAR, "scope_name": "T", "items": items}, lang="fr"))
    txt = "\n".join(_text(s) for s in prs.slides)
    assert len(prs.slides) == 2
    assert all(f"Initiative {i:02d}" in txt for i in range(20))
    assert "Généré le" in _text(prs.slides[0]) or "généré le" in _text(prs.slides[0])
    assert "(dépassée)" in txt


def test_an_empty_org_chart_says_so(db):
    pytest.importorskip("pptx")
    from app.orgrender import render_org_pptx
    txt = _text(_prs(render_org_pptx([], "T", lang="fr")).slides[0])
    assert "Aucun élément à afficher." in txt


def test_a_steerco_month_not_filled_names_who_owes_it(db, seeded):
    pytest.importorskip("pptx")
    from app.routers.steerco import I18N, _render_pptx
    d = {"kpis": [], "missing": ["Squad A"], "sla": {}, "kpi_chart": {}, "incidents_chart": {},
         "last_events": [], "next_events": []}
    txt = _text(_prs(_render_pptx([{"squad_name": "P", "data": d}], f"{YEAR}-12", I18N["fr"])).slides[0])
    assert f"Non renseigné pour décembre {YEAR}." in txt
    assert "Attendu de : Squad A." in txt
