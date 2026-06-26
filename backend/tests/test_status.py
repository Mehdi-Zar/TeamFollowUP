from types import SimpleNamespace

from app.status import (
    current_year_quarter,
    squad_status,
    risk_rank,
    year_progress,
    counts,
    quarter_breakdown,
    blocked_count,
)

YEAR = 2026


def make_squad(objectives=(), roadmap=(), progress=()):
    return SimpleNamespace(
        objectives=[SimpleNamespace(rag_status=r, is_active=a, year=YEAR, target_date=None) for (r, a) in objectives],
        roadmap_items=[SimpleNamespace(status=s, year=YEAR, quarter=q, display_order=0, id=i)
                       for i, (q, s) in enumerate(roadmap)],
        quarter_progress=[SimpleNamespace(year=YEAR, quarter=q, progress_pct=p) for (q, p) in progress],
        kpis=[],
        snapshots=[],
    )


def test_on_track_when_clear():
    s = make_squad(roadmap=[(2, "on_track"), (2, "done")])
    assert squad_status(s, YEAR, 2) == "on_track"


def test_blocked_when_quarter_jalon_blocked():
    s = make_squad(roadmap=[(2, "blocked")])
    assert squad_status(s, YEAR, 2) == "blocked"


def test_at_risk_when_quarter_jalon_at_risk():
    s = make_squad(roadmap=[(2, "at_risk"), (2, "on_track")])
    assert squad_status(s, YEAR, 2) == "at_risk"


def test_blocked_takes_priority_over_at_risk():
    s = make_squad(roadmap=[(2, "at_risk"), (2, "blocked")])
    assert squad_status(s, YEAR, 2) == "blocked"


def test_other_quarter_does_not_affect_current():
    s = make_squad(roadmap=[(1, "blocked")])
    assert squad_status(s, YEAR, 2) == "on_track"


def test_quarter_none_aggregates_year():
    s = make_squad(roadmap=[(1, "blocked")])
    assert squad_status(s, YEAR, None) == "blocked"


def test_year_progress_is_derived_from_milestones():
    # Q1: 2 of 2 done → 100%. Q2: 1 of 2 done → 50%. Others have no jalons → 0%.
    s = make_squad(roadmap=[(1, "done"), (1, "done"), (2, "done"), (2, "on_track")])
    p = year_progress(s, YEAR)
    assert p[1] == 100 and p[2] == 50 and p[3] == 0 and p[4] == 0


def test_year_progress_rounds_share_done():
    # 1 of 3 done → 33%. Not hand-entered; blocked/at_risk count as not-done.
    s = make_squad(roadmap=[(2, "done"), (2, "blocked"), (2, "at_risk")])
    assert year_progress(s, YEAR)[2] == 33


def test_risk_rank_order():
    assert risk_rank("blocked") > risk_rank("at_risk") > risk_rank("on_track")


def test_quarter_breakdown_counts():
    s = make_squad(roadmap=[(2, "blocked"), (2, "done"), (2, "on_track"), (3, "at_risk")])
    b = quarter_breakdown(s, YEAR, 2)
    assert b["total"] == 3 and b["blocked"] == 1 and b["done"] == 1 and b["on_track"] == 1
    assert quarter_breakdown(s, YEAR, None)["total"] == 4


def test_blocked_count_scoped():
    s = make_squad(roadmap=[(2, "blocked"), (3, "blocked")])
    assert blocked_count(s, YEAR, 2) == 1
    assert blocked_count(s, YEAR, None) == 2


def test_counts():
    # Objective RAG is now derived from advancement, not entered: an objective with
    # a deadline already in the past and no progress is necessarily red.
    from datetime import datetime, timezone
    s = make_squad(objectives=[("green", True)], roadmap=[(2, "blocked"), (3, "done")])
    s.objectives[0].target_date = datetime(YEAR, 1, 1, tzinfo=timezone.utc)  # past deadline
    c = counts(s, YEAR)
    assert c["objectives_red"] == 1
    assert c["roadmap_total"] == 2 and c["roadmap_blocked"] == 1 and c["roadmap_done"] == 1


def test_current_year_quarter_shape():
    y, q = current_year_quarter()
    assert isinstance(y, int) and 1 <= q <= 4
