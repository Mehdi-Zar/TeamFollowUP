"""The mails as received: readable in any client, sent once, at the right hour,
never lost when the mail server is down, never sent to the author of a change."""
import datetime as dt

import app.changeconfig as changeconfig
import app.changenotify as changenotify
import app.database as dbmod
import app.mail as mail
import app.modulesconfig as modulesconfig
from app import report as report_mod
from app.reportcommon import rt
from app.reportconfig import get_report, set_report
from app.smtpconfig import set_smtp

from .conftest import TestingSessionLocal


def _capture(monkeypatch, ok=True):
    sent = []

    def fake(cfg, to, subject, body, attachment=None, html=False, cc=None, **k):
        atts = attachment if isinstance(attachment, list) else ([attachment] if attachment else [])
        sent.append({"to": to, "subject": subject, "body": body, "cc": cc or [],
                     "files": [a[0] for a in atts if a]})
        return ok
    monkeypatch.setattr(mail, "send_email", fake)
    return sent


def _schedule(db, now, **extra):
    set_smtp(db, {"enabled": True, "host": "smtp.local"})
    set_report(db, {"enabled": True, "recipients": ["copil@test"], "weekdays": [now.weekday()],
                    "hour": 8, **extra})
    db.commit()


def test_the_report_mail_is_a_summary_any_client_renders(db, seeded, monkeypatch):
    now = dt.datetime(2026, 1, 5, 9, 0, tzinfo=dt.timezone.utc)  # Monday, 10:00 Paris
    _schedule(db, now)
    monkeypatch.setattr(report_mod, "render_pptx", lambda d: b"PK")
    sent = _capture(monkeypatch)
    assert report_mod.send_due_weekly_reports(db, now=now) == 1
    body = sent[0]["body"]
    for browser_only in ("var(--", "display:flex", "display:grid", "<svg", "min-width:1326"):
        assert browser_only not in body, browser_only
    assert 'width="640"' in body and "Squad A" in body
    # The full document travels attached, named after what it is and when.
    assert sent[0]["files"] == ["Rapport_hebdomadaire_Toutes_les_tribes_2026-01-05.html",
                                "Rapport_hebdomadaire_Toutes_les_tribes_2026-01-05.pptx"]


def test_a_mail_server_down_does_not_lose_the_week(db, seeded, monkeypatch):
    now = dt.datetime(2026, 1, 5, 9, 0, tzinfo=dt.timezone.utc)
    _schedule(db, now)
    monkeypatch.setattr(report_mod, "render_pptx", lambda d: b"")
    _capture(monkeypatch, ok=False)
    assert report_mod.send_due_weekly_reports(db, now=now) == 0
    assert get_report(db).get("last_sent_day") != "2026-01-05"
    # An hour later the server is back: the report leaves, first of its kind.
    sent = _capture(monkeypatch, ok=True)
    assert report_mod.send_due_weekly_reports(db, now=now + dt.timedelta(hours=1)) == 1
    assert "nouveaut" not in sent[0]["subject"]


def test_the_hour_is_paris_time(db, seeded, monkeypatch):
    summer = dt.datetime(2026, 7, 6, 5, 30, tzinfo=dt.timezone.utc)  # Monday 07:30 Paris
    _schedule(db, summer)
    monkeypatch.setattr(report_mod, "render_pptx", lambda d: b"")
    sent = _capture(monkeypatch)
    assert report_mod.send_due_weekly_reports(db, now=summer) == 0
    assert report_mod.send_due_weekly_reports(db, now=summer + dt.timedelta(hours=1)) == 1  # 08:30
    assert len(sent) == 1


def test_a_leader_also_on_the_fixed_list_gets_the_squad_document_once(db, seeded, monkeypatch):
    now = dt.datetime(2026, 1, 5, 9, 0, tzinfo=dt.timezone.utc)
    _schedule(db, now, recipients=["sl_a@test"], global_doc=False, per_squad=True, squad_leaders=True)
    monkeypatch.setattr(report_mod, "render_pptx", lambda d: b"")
    sent = _capture(monkeypatch)
    report_mod.send_due_weekly_reports(db, now=now)
    squad_a = [m for m in sent if "Squad A" in m["subject"]]
    assert [m["to"] for m in squad_a] == ["sl_a@test"], squad_a


def test_plural_forms_replace_parentheses():
    assert rt("fr", "subj_changes", n=1) == "[1 nouveauté]"
    assert rt("fr", "subj_changes", n=3) == "[3 nouveautés]"
    assert rt("en", "subj_changes", n=1) == "[1 update]"
    assert rt("en", "sum_moved", n=2) == "2 squads moved"


def _arm_changes(db, monkeypatch, **cfg):
    changeconfig.set_change_notify(db, {"enabled": True, "recipients": ["copil@test", "sl_a@test"],
                                        "events": list(changeconfig.ALL_EVENTS), "attach_pptx": False,
                                        **cfg})
    set_smtp(db, {"enabled": True, "host": "smtp.local"})
    db.commit()
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(modulesconfig, "is_active", lambda *a, **k: True)
    return _capture(monkeypatch)


def test_the_author_of_a_change_does_not_receive_it(db, seeded, monkeypatch):
    sent = _arm_changes(db, monkeypatch, min_interval_minutes=0)
    changenotify._run(seeded["squad_a"], "kpi", "SL A", 2026, "sl_a@test")
    assert [m["to"] for m in sent] == ["copil@test"]
    assert "mis à jour" in sent[0]["body"] and "UTC" not in sent[0]["body"]


def test_close_changes_leave_as_one_mail(db, seeded, monkeypatch):
    sent = _arm_changes(db, monkeypatch, min_interval_minutes=15)
    monkeypatch.setattr(changenotify.threading, "Timer",
                        lambda *a, **k: type("T", (), {"start": lambda s: None, "daemon": True})())
    changenotify._run(seeded["squad_a"], "kpi", "Alice", 2026, "alice@test")
    changenotify._run(seeded["squad_a"], "budget", "Bob", 2026, "bob@test")
    assert sent == []  # gathered, not sent yet
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=16)
    assert changenotify.flush_pending(later) == 1
    assert len(sent) == 2  # one mail per recipient, not per change
    subject = sent[0]["subject"]
    assert "KPI" in subject and "budget" in subject and "Alice" in subject and "Bob" in subject


def test_submitting_the_reporting_sends_the_notice(db, seeded, monkeypatch):
    """By default, the submission (not each autosave) is what notifies."""
    changeconfig.set_change_notify(db, {"enabled": True, "recipients": ["copil@test"],
                                        "attach_pptx": False, "min_interval_minutes": 0})
    set_smtp(db, {"enabled": True, "host": "smtp.local"})
    db.commit()
    assert changeconfig.get_change_notify(db)["events"] == ["submission"]
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(modulesconfig, "is_active", lambda *a, **k: True)
    sent = _capture(monkeypatch)
    changenotify._run(seeded["squad_a"], "kpi", "SL A", 2026, "sl_a@test")
    assert sent == []  # an edit alone does not notify by default
    changenotify._run(seeded["squad_a"], "submission", "SL A", 2026, "sl_a@test")
    assert len(sent) == 1
    assert "reporting soumis par SL A" in sent[0]["subject"]
    assert "a soumis le reporting" in sent[0]["body"]


def test_a_refused_batch_goes_back_in_the_queue(db, seeded, monkeypatch):
    sent = _arm_changes(db, monkeypatch, min_interval_minutes=15)
    monkeypatch.setattr(changenotify.threading, "Timer",
                        lambda *a, **k: type("T", (), {"start": lambda s: None, "daemon": True})())
    changenotify._run(seeded["squad_a"], "kpi", "Alice", 2026, "alice@test")
    _capture(monkeypatch, ok=False)
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=16)
    assert changenotify.flush_pending(later) == 0
    assert str(seeded["squad_a"]) in changeconfig.get_state(db).get("pending", {})
    sent = _capture(monkeypatch, ok=True)
    assert changenotify.flush_pending(later) == 1 and sent


def test_a_past_version_mail_says_it_is_a_version(db, seeded):
    from app.mailbody import render_email
    data = {"lang": "fr", "app_name": "TeamFollowUP", "scope_name": "Tribe One", "as_of": "2026-08-23",
            "generated_at": dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc), "summary": {},
            "tribes": [{"tribe_name": "Tribe One", "squads": [
                {"squad_id": 1, "name": "Squad A", "status": "on_track", "status_rag": "green",
                 "annual_pct": 40, "age_days": 0, "is_stale": False}]}]}
    body = render_email(data)
    assert "version du 23/08/2026" in body
    assert "Dernière saisie" not in body and "aujourd'hui" not in body
