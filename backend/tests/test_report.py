import pytest

from app import status as st
from app.report import build_report_data, render_html, render_pptx, send_due_weekly_reports
from app.reportconfig import get_report, set_report
from tests.conftest import login


# ---- data + rendering ----------------------------------------------------------

def test_build_report_data_combines_scope(db, seeded):
    year = st.current_year_quarter()[0]
    data = build_report_data(db, None, year, 7)
    assert data["summary"]["squads_total"] == 3  # A, B (t1) + C (t2)
    names = {r["name"] for blk in data["tribes"] for r in blk["squads"]}
    assert {"Squad A", "Squad B", "Squad C"} <= names

    scoped = build_report_data(db, seeded["t1"], year, 7)
    assert scoped["summary"]["squads_total"] == 2
    scoped_names = {r["name"] for blk in scoped["tribes"] for r in blk["squads"]}
    assert "Squad C" not in scoped_names


def test_build_report_data_squad_ids_subset(db, seeded):
    year = st.current_year_quarter()[0]
    # Restrict a global report to a chosen subset of squads.
    data = build_report_data(db, None, year, 7, squad_ids=[seeded["squad_a"], seeded["squad_c"]])
    names = {r["name"] for blk in data["tribes"] for r in blk["squads"]}
    assert names == {"Squad A", "Squad C"}
    assert data["summary"]["squads_total"] == 2


def test_roadmap_pptx_endpoint_squad_ids(client, seeded):
    import pytest
    pytest.importorskip("pptx")
    login(client, seeded["admin"])
    r = client.get(f"/api/reports/roadmap.html?squad_ids={seeded['squad_a']}")
    assert r.status_code == 200
    assert "Squad A" in r.text and "Squad B" not in r.text


def test_dashboard_export_html_squad_selection(client, seeded):
    login(client, seeded["admin"])
    # Dashboard export honours the squad selection (same granularity as the roadmap).
    r = client.get(f"/api/reports/dashboard.html?squad_ids={seeded['squad_a']}")
    assert r.status_code == 200
    assert "Squad A" in r.text and "Squad B" not in r.text
    # Single-squad export (the squad-detail case).
    r2 = client.get(f"/api/reports/dashboard.html?squad_id={seeded['squad_b']}")
    assert r2.status_code == 200 and "Squad B" in r2.text


def test_dashboard_export_pptx(client, seeded):
    import pytest
    pytest.importorskip("pptx")
    login(client, seeded["admin"])
    r = client.get("/api/reports/dashboard.pptx")
    assert r.status_code == 200
    assert "presentationml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"


def test_dashboard_export_gated_by_dashboard_module(client, seeded):
    login(client, seeded["admin"])
    client.put("/api/admin/modules-config", json={"dashboard": {"enabled": False}})
    assert client.get("/api/reports/dashboard.html").status_code == 404
    client.put("/api/admin/modules-config", json={"dashboard": {"enabled": True}})


def test_render_html_contains_squads(db, seeded):
    year = st.current_year_quarter()[0]
    html = render_html(build_report_data(db, None, year, 7))
    assert "<table" in html
    assert "Squad A" in html
    assert "Rapport hebdomadaire" in html


def test_render_html_follows_lang(db, seeded):
    year = st.current_year_quarter()[0]
    fr = render_html(build_report_data(db, None, year, 7, lang="fr"))
    en = render_html(build_report_data(db, None, year, 7, lang="en"))
    assert "Rapport hebdomadaire" in fr and "Responsable" in fr
    assert "Weekly report" in en and "Leader" in en
    assert "Rapport hebdomadaire" not in en


def test_weekly_html_endpoint_lang_query(client, seeded):
    login(client, seeded["admin"])
    r = client.get("/api/reports/weekly.html?lang=en")
    assert r.status_code == 200
    assert "Weekly report" in r.text and "Rapport hebdomadaire" not in r.text


def test_render_pptx_produces_valid_deck(db, seeded):
    pptx = pytest.importorskip("pptx")
    year = st.current_year_quarter()[0]
    data = build_report_data(db, None, year, 7)
    blob = render_pptx(data)
    assert blob[:2] == b"PK"  # zip/OOXML magic
    import io
    prs = pptx.Presentation(io.BytesIO(blob))
    n_squads = sum(len(blk["squads"]) for blk in data["tribes"])
    # Summary one-pager + one full detail slide (objectives + roadmap) per squad.
    assert len(prs.slides) == 1 + n_squads


def _slide_texts(prs):
    return [sh.text_frame.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame]


def test_dashboard_pptx_never_silently_drops_squads(db, seeded):
    """Regression for the 40-slide cap: a large selection must yield one detail
    slide per squad — no squad the user picked may vanish from the deck."""
    pptx = pytest.importorskip("pptx")
    import io
    from app.models import Squad
    # Well past the historical cap of 40.
    for i in range(60):
        db.add(Squad(name=f"Extra {i:02d}", tribe_id=seeded["t1"], display_order=100 + i))
    db.commit()
    year = st.current_year_quarter()[0]
    data = build_report_data(db, None, year, 7)
    n = sum(len(blk["squads"]) for blk in data["tribes"])
    assert n >= 63
    prs = pptx.Presentation(io.BytesIO(render_pptx(data)))
    assert len(prs.slides) == 1 + n  # summary + exactly one detail slide per squad
    # Every squad appears somewhere in the deck (its own detail slide header).
    all_text = "\n".join(_slide_texts(prs))
    names = {r["name"] for blk in data["tribes"] for r in blk["squads"]}
    missing = {nm for nm in names if nm not in all_text}
    assert not missing, f"squads missing from deck: {missing}"


def test_dashboard_pptx_marks_omitted_squads_when_cap_hit(db, seeded, monkeypatch):
    """If the runaway guard is ever exceeded, the omitted squads are announced on
    a visible notice slide — never dropped without a trace."""
    pptx = pytest.importorskip("pptx")
    import io
    import app.report as report_mod
    from app.models import Squad
    monkeypatch.setattr(report_mod, "_MAX_DETAIL_SLIDES", 4)
    for i in range(10):
        db.add(Squad(name=f"Over {i:02d}", tribe_id=seeded["t1"], display_order=200 + i))
    db.commit()
    year = st.current_year_quarter()[0]
    data = build_report_data(db, None, year, 7)
    n = sum(len(blk["squads"]) for blk in data["tribes"])
    prs = pptx.Presentation(io.BytesIO(render_pptx(data)))
    # 1 summary + 4 detail + 1 notice slide.
    assert len(prs.slides) == 1 + 4 + 1
    notice = " ".join(sh.text_frame.text for sh in prs.slides[-1].shapes if sh.has_text_frame)
    assert str(n - 4) in notice and "autres squads" in notice


def test_render_roadmap_swimlane_pptx(db, seeded):
    pptx = pytest.importorskip("pptx")
    from app.report import render_roadmap_pptx
    import io
    year = st.current_year_quarter()[0]
    data = build_report_data(db, None, year, 7)
    prs = pptx.Presentation(io.BytesIO(render_roadmap_pptx(data)))
    # The roadmap export always fits on a single page (one slide), whatever the count.
    assert len(prs.slides) == 1
    texts = [sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    # Quarter headers (Q1..Q4 with the year) and the swimlane labels (squad names) are present.
    assert any(t == f"Q1 {year}" for t in texts) and any(t == f"Q4 {year}" for t in texts)
    names = {sq["name"] for blk in data["tribes"] for sq in blk["squads"]}
    assert names & set(texts)


def test_roadmap_pptx_single_page_even_with_many_squads(db, seeded):
    pptx = pytest.importorskip("pptx")
    from app.report import render_roadmap_pptx
    from app.models import Squad
    import io
    # Add many squads; the deck must still be exactly one slide.
    for i in range(20):
        db.add(Squad(name=f"Extra {i}", tribe_id=seeded["t1"], display_order=10 + i))
    db.commit()
    year = st.current_year_quarter()[0]
    data = build_report_data(db, None, year, 7)
    prs = pptx.Presentation(io.BytesIO(render_roadmap_pptx(data)))
    assert len(prs.slides) == 1


# ---- config sanitization -------------------------------------------------------

def test_report_config_sanitizes(db, seeded):
    cfg = set_report(db, {
        "enabled": True,
        "recipients": "a@x.com\nbad\nb@y.com; a@x.com",  # dedup + drop invalid
        "weekday": 99, "hour": -3, "since_days": 999,
        "last_sent_week": "hack",
    })
    db.commit()
    assert cfg["recipients"] == ["a@x.com", "b@y.com"]
    assert cfg["weekday"] == 6 and cfg["hour"] == 0 and cfg["since_days"] == 120
    assert get_report(db)["enabled"] is True


# ---- automatic send gating -----------------------------------------------------

def test_send_due_skips_when_disabled(db, seeded):
    set_report(db, {"enabled": False})
    db.commit()
    assert send_due_weekly_reports(db) == 0


def test_send_due_skips_without_smtp(db, seeded):
    # Enabled report but SMTP off → nothing sent.
    set_report(db, {"enabled": True, "weekday": 0, "hour": 0, "recipients": ["x@y.com"]})
    db.commit()
    assert send_due_weekly_reports(db) == 0


# ---- API endpoints -------------------------------------------------------------

def test_weekly_html_endpoint_admin(client, seeded):
    login(client, seeded["admin"])
    r = client.get("/api/reports/weekly.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Squad A" in r.text


def test_weekly_pptx_endpoint_admin(client, seeded):
    pytest.importorskip("pptx")
    login(client, seeded["admin"])
    r = client.get("/api/reports/weekly.pptx")
    assert r.status_code == 200
    assert "presentationml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"


def test_weekly_report_available_to_member_scoped(client, seeded):
    # Report export is available to any authenticated user, scoped to their tribe.
    login(client, seeded["member"])  # tribe 1
    r = client.get("/api/reports/weekly.html")
    assert r.status_code == 200
    assert "Squad C" not in r.text  # tribe 2 squad excluded


def test_weekly_report_squad_scope(client, seeded):
    login(client, seeded["sl_a"])  # leads squad A (tribe 1)
    r = client.get(f"/api/reports/weekly.html?squad_id={seeded['squad_a']}")
    assert r.status_code == 200
    assert "Squad A" in r.text and "Squad B" not in r.text
    # A squad outside the user's visibility is 404.
    assert client.get(f"/api/reports/weekly.html?squad_id={seeded['squad_c']}").status_code == 404


def test_tribe_leader_scoped_to_own_tribe(client, seeded):
    login(client, seeded["tribe"])  # tribe 1 leader
    r = client.get("/api/reports/weekly.html")
    assert r.status_code == 200
    assert "Squad C" not in r.text  # tribe 2 squad excluded


def test_report_config_admin_roundtrip(client, seeded):
    login(client, seeded["admin"])
    assert client.get("/api/admin/report-config").json()["enabled"] is False
    out = client.put("/api/admin/report-config", json={
        "enabled": True, "recipients": ["dir@x.com"], "weekday": 2, "hour": 9,
    }).json()
    assert out["enabled"] is True and out["weekday"] == 2 and out["recipients"] == ["dir@x.com"]


def test_report_config_forbidden_for_member(client, seeded):
    login(client, seeded["member"])
    assert client.get("/api/admin/report-config").status_code == 403


def test_report_test_requires_smtp(client, seeded):
    login(client, seeded["admin"])
    assert client.post("/api/admin/report-config/test", json={}).status_code == 400


def test_preferences_expose_weekly_subscription(client, seeded):
    login(client, seeded["member"])
    assert client.get("/api/me/preferences").json()["subscribe_weekly_report"] is False
    out = client.put("/api/me/preferences", json={"subscribe_weekly_report": True}).json()
    assert out["subscribe_weekly_report"] is True


# ---- personal subscription (every N days) --------------------------------------

def test_subscription_roundtrip(client, seeded):
    login(client, seeded["member"])
    assert client.get("/api/reports/subscription").json()["interval_days"] == 0
    out = client.put("/api/reports/subscription", json={"interval_days": 14}).json()
    assert out["interval_days"] == 14
    # preferences boolean reflects the subscription
    assert client.get("/api/me/preferences").json()["subscribe_weekly_report"] is True
    assert client.put("/api/reports/subscription", json={"interval_days": 0}).json()["interval_days"] == 0


def test_preferences_toggle_drives_interval(client, seeded):
    login(client, seeded["member"])
    client.put("/api/me/preferences", json={"subscribe_weekly_report": True})
    assert client.get("/api/reports/subscription").json()["interval_days"] == 7
    client.put("/api/me/preferences", json={"subscribe_weekly_report": False})
    assert client.get("/api/reports/subscription").json()["interval_days"] == 0


def test_send_personal_subscriptions(db, seeded, monkeypatch):
    from app import report as report_mod
    from app.smtpconfig import set_smtp
    from app.models import User
    from app.subscriptions import set_subscription
    from sqlalchemy import select

    set_smtp(db, {"enabled": True, "host": "smtp.local"})
    user = db.scalar(select(User).where(User.email == "member@test"))
    set_subscription(db, user, None, 7)  # global subscription
    db.commit()

    sent_to = []
    monkeypatch.setattr(report_mod, "render_pptx", lambda data: b"")  # skip pptx
    monkeypatch.setattr("app.mail.send_email",
                        lambda *a, **k: (sent_to.append(a[1]) or True))

    n = report_mod.send_personal_subscriptions(db)
    assert n == 1 and "member@test" in sent_to
    # Not due again immediately.
    assert report_mod.send_personal_subscriptions(db) == 0


def test_send_per_squad_subscription(db, seeded, monkeypatch):
    from app import report as report_mod
    from app.smtpconfig import set_smtp
    from app.models import User
    from app.subscriptions import set_subscription
    from sqlalchemy import select

    set_smtp(db, {"enabled": True, "host": "smtp.local"})
    tl = db.scalar(select(User).where(User.email == "tribe@test"))
    set_subscription(db, tl, seeded["squad_a"], 14)  # per-squad subscription
    db.commit()

    captured = {}
    monkeypatch.setattr(report_mod, "render_pptx", lambda data: b"")
    monkeypatch.setattr("app.mail.send_email",
                        lambda *a, **k: (captured.setdefault("body", a[3]) or True))
    assert report_mod.send_personal_subscriptions(db) == 1
    assert "Squad A" in captured["body"]  # report narrowed to that squad


def test_tribe_leader_digest_ccs_squad_leaders(db, seeded, monkeypatch):
    """Each tribe leader gets their tribe-scoped report with that tribe's squad
    leaders in CC."""
    import datetime as dt
    from app import report as report_mod
    from app.smtpconfig import set_smtp

    set_smtp(db, {"enabled": True, "host": "smtp.local"})
    now = dt.datetime(2026, 1, 5, 9, 0, tzinfo=dt.timezone.utc)  # a Monday
    set_report(db, {"enabled": True, "tribe_leader_digest": True,
                    "weekdays": [now.weekday()], "hour": 0, "recipients": []})
    db.commit()

    calls = []
    monkeypatch.setattr(report_mod, "render_pptx", lambda data: b"")  # skip pptx
    monkeypatch.setattr(
        "app.mail.send_email",
        lambda cfg, to, subject, body, attachment=None, html=False, cc=None:
            (calls.append({"to": to, "cc": [c.lower() for c in (cc or [])]}) or True))

    sent = report_mod.send_due_weekly_reports(db, now=now)
    assert sent >= 2
    by_to = {c["to"]: c for c in calls}

    # Tribe 1 leader → their tribe, squad leaders (sl_a, sl_b) in CC.
    assert "tribe@test" in by_to
    assert {"sl_a@test", "sl_b@test"} <= set(by_to["tribe@test"]["cc"])
    # Tribe 2 leader → their tribe; Squad C has no leader → empty CC.
    assert "tribe2@test" in by_to
    assert by_to["tribe2@test"]["cc"] == []


def test_whats_new_since_last_report(db, seeded, monkeypatch):
    """First report establishes a baseline; the next one flags what changed, with
    a subject prefix; and 'only_when_changes' skips an unchanged send."""
    import datetime as dt
    from app import report as report_mod, status as st
    from app.smtpconfig import set_smtp
    from app.models import RoadmapItem
    from sqlalchemy import select

    set_smtp(db, {"enabled": True, "host": "smtp.local"})
    now = dt.datetime(2026, 1, 5, 9, 0, tzinfo=dt.timezone.utc)  # Monday
    year = st.current_year_quarter(now)[0]
    set_report(db, {"enabled": True, "recipients": ["copil@test"],
                    "weekdays": [now.weekday()], "hour": 0})
    db.add(RoadmapItem(squad_id=seeded["squad_a"], year=year, quarter=1,
                       title="API v2", status="at_risk", release_stage="EA"))
    db.commit()

    caps: list[dict] = []
    monkeypatch.setattr(report_mod, "render_pptx", lambda d: b"")
    monkeypatch.setattr(
        "app.mail.send_email",
        lambda cfg, to, subject, body, attachment=None, html=False, cc=None:
            (caps.append({"subject": subject, "body": body}) or True))

    # 1) First send → baseline, no "changes" prefix (first report).
    assert report_mod.send_due_weekly_reports(db, now=now) == 1
    assert "nouveauté" not in caps[-1]["subject"] and "[à jour]" not in caps[-1]["subject"]

    # 2) A milestone is delivered; a week later the report flags it.
    item = db.scalar(select(RoadmapItem).where(RoadmapItem.title == "API v2"))
    item.status = "done"
    db.commit()
    caps.clear()
    now2 = now + dt.timedelta(days=7)
    assert report_mod.send_due_weekly_reports(db, now=now2) == 1
    assert caps[-1]["subject"].startswith("[")           # e.g. "[2 nouveauté(s)] …"
    assert "API v2" in caps[-1]["body"] and "Livré" in caps[-1]["body"]

    # 3) Nothing changes; with only_when_changes the next send is skipped.
    set_report(db, {"only_when_changes": True})
    caps.clear()
    now3 = now2 + dt.timedelta(days=7)
    assert report_mod.send_due_weekly_reports(db, now=now3) == 0
    assert caps == []


def test_send_personal_subscriptions_needs_smtp(db, seeded):
    from app.report import send_personal_subscriptions
    from app.models import User
    from app.subscriptions import set_subscription
    from sqlalchemy import select
    u = db.scalar(select(User).where(User.email == "member@test"))
    set_subscription(db, u, None, 7)
    db.commit()
    assert send_personal_subscriptions(db) == 0  # SMTP disabled
