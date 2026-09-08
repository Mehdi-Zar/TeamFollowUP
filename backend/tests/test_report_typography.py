"""The rendered documents themselves must be clean, not just the source.

``test_typography.py`` guards string literals; it cannot see what an f-string
assembles at runtime, and coverage said most of the separator sites in
``report.py`` and ``reportpptx.py`` were never executed: the shared fixtures carry
no budget, no deadlines, no dependencies and no key messages, so exactly the
branches that used to hold a middot went unrendered. The single-squad deck
(``squad_page_slide``, 130 lines) was reached by nothing at all.

So this fills a squad with all of it, renders every document **for a viewer**
(without one the budget is withheld, which is how those figures stayed
unrendered), and reads the result. It asserts two things on purpose: that the
banned characters are absent from the real output, and that what replaced them
still says what it used to say, so a future "cleanup" cannot satisfy the ban by
dropping the information instead of rewording it.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import zipfile

import pytest
from sqlalchemy import select

from app import report as report_mod
from app.models import Initiative, KeyMessage, Objective, RoadmapItem, Squad, SquadBudget, User

YEAR = 2026
BANNED = {"—": "em dash", "·": "middot"}


@pytest.fixture()
def rich(db, seeded):
    """A squad carrying every optional field the report can render, plus the
    viewer allowed to see all of it (the budget is viewer-gated)."""
    squad_id, tribe_id = seeded["squad_a"], seeded["t1"]
    db.get(Squad, squad_id).budget_enabled = True

    db.add(Initiative(tribe_id=tribe_id, year=YEAR, title="Cut the build time",
                      squad_id=squad_id, owner="Alice Martin",
                      deadline=dt.datetime(YEAR, 6, 30, tzinfo=dt.timezone.utc)))
    db.add(Objective(squad_id=squad_id, year=YEAR, title="Halve the cold start",
                     target_date=dt.datetime(YEAR, 3, 31, tzinfo=dt.timezone.utc),
                     rag_status="amber", weight=1))
    db.add(RoadmapItem(squad_id=squad_id, year=YEAR, quarter=2, title="Ship the new agent",
                       release_stage="GA", status="at_risk", owner="Bob Chen",
                       dependencies="Platform team", dependency_kind="tribe",
                       dependency_tribe_id=seeded["t2"]))
    db.add(KeyMessage(squad_id=squad_id, year=YEAR, kind="risk", text="Vendor slipped a week"))
    # Over budget on purpose: that is the branch rendering the "+amount, percent" pair.
    db.add(SquadBudget(squad_id=squad_id, year=YEAR, total=100000, spent=80000, forecast=125000))
    db.commit()
    return squad_id, db.scalar(select(User).where(User.email == seeded["admin"]))


def _deck_text(blob: bytes) -> str:
    """Every text run in the deck, read from the raw slide XML so table cells and
    grouped shapes are included as they actually ship."""
    runs: list[str] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                runs += re.findall(r"<a:t>(.*?)</a:t>", z.read(name).decode("utf-8"), re.S)
    return "\n".join(runs)


def _assert_clean(text: str, what: str) -> None:
    for char, label in BANNED.items():
        if char in text:
            i = text.index(char)
            raise AssertionError(f"{what} contains a {label}: ...{text[max(0, i - 90):i + 60]}...")


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_the_rendered_weekly_report_carries_neither_character(db, rich, lang):
    _, viewer = rich
    data = report_mod.build_report_data(db, None, YEAR, 7, lang=lang, viewer=viewer)
    _assert_clean(report_mod.render_html(data), f"the {lang} weekly HTML report")
    _assert_clean(_deck_text(report_mod.render_pptx(data)), f"the {lang} weekly PPTX")


def test_the_single_squad_export_too(db, rich):
    """A squad-scoped export uses its own slide builder, with its own budget,
    initiative and objective lines. Nothing reached it before this test."""
    squad_id, viewer = rich
    data = report_mod.build_report_data(db, None, YEAR, 7, squad_id=squad_id, viewer=viewer)
    assert data["squad_scoped"] is True
    _assert_clean(report_mod.render_html(data), "the single-squad HTML")

    deck = _deck_text(report_mod.render_pptx(data))
    _assert_clean(deck, "the single-squad PPTX")
    assert "(Alice Martin, échéance 2026-06-30)" in deck   # metadata, comma inside parentheses
    assert "(80%)" in deck and "(125%)" in deck            # percentage after its amount


def test_every_other_document_too(db, rich):
    """The roadmap, initiative and dependency documents share the same helpers."""
    _, viewer = rich
    data = report_mod.build_report_data(db, None, YEAR, 7, viewer=viewer)
    _assert_clean(report_mod.render_roadmap_html(data), "the roadmap HTML")
    _assert_clean(_deck_text(report_mod.render_roadmap_pptx(data)), "the roadmap PPTX")

    inits = report_mod.build_initiative_list(db, None, YEAR)
    _assert_clean(report_mod.render_initiatives_html(inits), "the initiatives HTML")
    _assert_clean(_deck_text(report_mod.render_initiatives_pptx(inits)), "the initiatives PPTX")

    dep = report_mod.build_dependencies_data(db, None, YEAR)
    assert dep["total"] > 0, "the fixture must produce a cross-tribe dependency to render"
    _assert_clean(report_mod.render_dependencies_html(dep), "the dependencies HTML")
    _assert_clean(_deck_text(report_mod.render_dependencies_pptx(dep)), "the dependencies PPTX")


def test_the_separators_were_replaced_and_not_simply_dropped(db, rich):
    """Removing the character must not remove the information with it."""
    _, viewer = rich
    html = report_mod.render_html(
        report_mod.build_report_data(db, None, YEAR, 7, lang="fr", viewer=viewer))

    assert "Alice Martin, échéance 2026-06-30" in html     # initiative owner then deadline
    assert "(Dép. Tribe Two)" in html                      # dependency in parentheses
    assert "Vendor slipped a week" in html                 # key message survived
    assert ", 25%)" in html                                # budget overrun keeps both figures
    assert "(80%)" in html and "(125%)" in html            # consumed and forecast percentages
    assert "Année 2026, généré le" in html                 # header breadcrumb
