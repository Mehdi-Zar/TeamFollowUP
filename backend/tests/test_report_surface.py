"""Every public entry point of the reporting module produces something.

A smoke test, deliberately. `report` builds four kinds of document in two formats
each, and most of that surface is only reached through an HTTP route in a
different test file, or through the scheduler. Nothing asserted that the entry
points themselves still exist and still return a document.

It is also the net for restructuring that module: run it before, restructure, run
it after. It asserts the shape of the output, not its content - the detailed
rendering assertions live in test_report.py and are the right place for those.
"""
import io
import zipfile

import pytest

from app import report as report_mod


@pytest.fixture()
def data(db, seeded):
    """A report payload over the whole organisation, the way a route builds one."""
    year = 2026
    return report_mod.build_report_data(db, None, year, 7)


def _is_pptx(blob: bytes) -> bool:
    """A .pptx is a zip holding the presentation part; anything else is not one."""
    if not blob or not blob.startswith(b"PK"):
        return False
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return "ppt/presentation.xml" in z.namelist()


def _is_html_document(text: str) -> bool:
    return bool(text) and "<html" in text.lower() and "</html>" in text.lower()


# ---- the builders --------------------------------------------------------------

def test_build_report_data(db, seeded):
    d = report_mod.build_report_data(db, None, 2026, 7)
    assert isinstance(d, dict)
    # The payload every renderer reads: tribes, each holding its squads.
    assert "tribes" in d and "app_name" in d and "lang" in d


def test_build_initiative_list(db, seeded):
    d = report_mod.build_initiative_list(db, None, 2026)
    assert isinstance(d, dict)


def test_build_dependencies_data(db, seeded):
    d = report_mod.build_dependencies_data(db, None, 2026)
    assert isinstance(d, dict)


# ---- the four documents, in both formats ---------------------------------------

def test_dashboard_html(data):
    assert _is_html_document(report_mod.render_html(data))


def test_dashboard_pptx(data):
    assert _is_pptx(report_mod.render_pptx(data))


def test_roadmap_html(data):
    assert _is_html_document(report_mod.render_roadmap_html(data))


def test_roadmap_pptx(data):
    assert _is_pptx(report_mod.render_roadmap_pptx(data))


def test_initiatives_html(db, seeded):
    d = report_mod.build_initiative_list(db, None, 2026)
    assert _is_html_document(report_mod.render_initiatives_html(d))


def test_initiatives_pptx(db, seeded):
    d = report_mod.build_initiative_list(db, None, 2026)
    assert _is_pptx(report_mod.render_initiatives_pptx(d))


def test_dependencies_html(db, seeded):
    d = report_mod.build_dependencies_data(db, None, 2026)
    assert _is_html_document(report_mod.render_dependencies_html(d))


def test_dependencies_pptx(db, seeded):
    d = report_mod.build_dependencies_data(db, None, 2026)
    assert _is_pptx(report_mod.render_dependencies_pptx(d))


# ---- change detection and baselines --------------------------------------------

def test_signature_and_diff_round_trip(data):
    """diff_report compares two SIGNATURES, not two report payloads."""
    sig = report_mod.report_signature(data)
    assert isinstance(sig, dict)

    # No previous baseline: the first run must say so rather than raise.
    first = report_mod.diff_report(None, sig, "fr")
    assert first["first"] is True and first["count"] == 0

    # A signature compared with itself has changed in no way.
    same = report_mod.diff_report(sig, sig, "fr")
    assert same["count"] == 0


def test_change_rendering_accepts_no_changes(data):
    assert isinstance(report_mod.render_changes_html(None, "fr"), str)
    assert isinstance(report_mod.subject_prefix(None, "fr"), str)


def test_baseline_round_trip(db, data):
    assert report_mod.get_baseline(db, "scope:test") is None
    sig = report_mod.report_signature(data)
    report_mod.set_baseline(db, "scope:test", sig)
    db.commit()
    assert report_mod.get_baseline(db, "scope:test") == sig


# ---- delivery ------------------------------------------------------------------

def test_the_schedulers_entry_points_are_callable(db, seeded):
    """Nothing is configured to be sent, so both must return 0 rather than raise."""
    assert report_mod.send_due_weekly_reports(db) == 0
    assert report_mod.send_personal_subscriptions(db) == 0


# ---- helpers used from outside --------------------------------------------------

def test_group_by_theme_keeps_every_item(data):
    items = [{"theme": "A", "id": 1}, {"theme": None, "id": 2}, {"theme": "A", "id": 3}]
    grouped = report_mod.group_by_theme(items)
    assert sum(len(v) for _, v in grouped) == 3


def test_translation_helper_answers_in_both_languages():
    fr = report_mod.rt("fr", "report.title")
    en = report_mod.rt("en", "report.title")
    assert isinstance(fr, str) and isinstance(en, str) and fr and en
