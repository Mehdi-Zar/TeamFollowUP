"""Change-notification: a squad modification emails that squad's export to the
configured recipients, with a clear subject, honouring the event filter."""
import app.changeconfig as changeconfig
import app.changenotify as changenotify
import app.database as dbmod
import app.mail as mail
import app.modulesconfig as modulesconfig
import app.smtpconfig as smtpconfig

from .conftest import TestingSessionLocal


def _arm(db, monkeypatch, events):
    changeconfig.set_change_notify(db, {
        "enabled": True, "recipients": ["copil@test"], "events": events,
        "attach_pptx": False, "min_interval_minutes": 0,
    })
    db.commit()
    # The notifier opens its own session and re-imports gates lazily.
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(smtpconfig, "get_smtp", lambda _db: {"enabled": True})
    monkeypatch.setattr(modulesconfig, "is_active", lambda *a, **k: True)
    sent = []
    monkeypatch.setattr(mail, "send_email",
                        lambda cfg, to, subject, body, attachment=None, html=False, **k:
                        sent.append({"to": to, "subject": subject, "body": body}) or True)
    return sent


def test_modification_emails_squad_export(seeded, db, monkeypatch):
    sent = _arm(db, monkeypatch, ["roadmap", "budget"])
    changenotify._run(seeded["squad_a"], "roadmap", "Alice", 2026)
    assert len(sent) == 1, sent
    msg = sent[0]
    assert msg["to"] == "copil@test"
    assert "Squad A" in msg["subject"]          # clear subject: which squad
    assert "roadmap" in msg["subject"].lower()  # ...and what changed
    assert "Alice" in msg["subject"]            # ...and by whom
    assert "<" in msg["body"] and "Squad A" in msg["body"]  # the squad's HTML export


def test_event_filter_blocks_unconfigured_event(seeded, db, monkeypatch):
    sent = _arm(db, monkeypatch, ["roadmap"])   # only roadmap enabled
    changenotify._run(seeded["squad_a"], "budget", "Bob", 2026)
    assert sent == []                           # budget change → no email


def test_disabled_sends_nothing(seeded, db, monkeypatch):
    changeconfig.set_change_notify(db, {"enabled": False, "recipients": ["x@test"], "events": ["roadmap"]})
    db.commit()
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(smtpconfig, "get_smtp", lambda _db: {"enabled": True})
    monkeypatch.setattr(modulesconfig, "is_active", lambda *a, **k: True)
    sent = []
    monkeypatch.setattr(mail, "send_email", lambda *a, **k: sent.append(1) or True)
    changenotify._run(seeded["squad_a"], "roadmap", "Z", 2026)
    assert sent == []


def test_the_mail_says_who_changed_what_and_reaches_the_leaders(seeded, db, monkeypatch):
    """The mail opens with « X a modifié : ... », and the tribe leader and the
    squad's own leaders can be put on it without typing their addresses."""
    sent = _arm(db, monkeypatch, ["kpi"])
    changeconfig.set_change_notify(db, {"tribe_leaders": True, "squad_leaders": True})
    db.commit()
    changenotify._run(seeded["squad_a"], "kpi", "Alice", 2026)
    to = sorted(m["to"] for m in sent)
    assert to == ["copil@test", "sl_a@test", "tribe@test"], to
    assert "Alice</strong> a mis à jour" in sent[0]["body"] and "KPI" in sent[0]["body"]


def test_a_config_that_had_every_event_keeps_every_event():
    """Saved before OTD/KPI/committee/team/mood existed, "all on" still means all."""
    import json
    from app.models import AppSetting
    from .conftest import TestingSessionLocal
    db = TestingSessionLocal()
    try:
        db.merge(AppSetting(key=changeconfig.CHANGE_KEY, value=json.dumps(
            {"enabled": True, "events": ["progress", "roadmap", "objectives", "budget", "key_message"]})))
        db.commit()
        assert set(changeconfig.get_change_notify(db)["events"]) == set(changeconfig.ALL_EVENTS)
    finally:
        db.close()
