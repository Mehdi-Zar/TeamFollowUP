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


def test_render_html_contains_squads(db, seeded):
    year = st.current_year_quarter()[0]
    html = render_html(build_report_data(db, None, year, 7))
    assert "<table" in html
    assert "Squad A" in html
    assert "Rapport hebdomadaire" in html


def test_render_pptx_produces_valid_deck(db, seeded):
    pptx = pytest.importorskip("pptx")
    year = st.current_year_quarter()[0]
    blob = render_pptx(build_report_data(db, None, year, 7))
    assert blob[:2] == b"PK"  # zip/OOXML magic
    import io
    prs = pptx.Presentation(io.BytesIO(blob))
    assert len(prs.slides) >= 3  # title + summary + at least one tribe


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


def test_send_personal_subscriptions_needs_smtp(db, seeded):
    from app.report import send_personal_subscriptions
    from app.models import User
    from app.subscriptions import set_subscription
    from sqlalchemy import select
    u = db.scalar(select(User).where(User.email == "member@test"))
    set_subscription(db, u, None, 7)
    db.commit()
    assert send_personal_subscriptions(db) == 0  # SMTP disabled
