"""The scheduled report by email: who receives which mail (app/mailplan.py).

The reports by email are the admin's. A tribe's schedule has one main
recipient, the tribe leader, who receives the tribe's document or one mail per
squad. The squads' people put in copy join that same mail: one mail, never two
for one person. Others are added by persona, name or address, each with what it
receives (the tribe's document, or the squads' mails). Each kind of mail says
which documents it carries. The Direction gets the whole document, every tribe.
"""
import datetime as dt
import json

from sqlalchemy import select

from app import report as report_mod
from app.mailplan import plan_for
from app.models import AppSetting, RoadmapItem, User
from app.reportconfig import ensure_v2, get_report, normalize, set_report
from tests.conftest import login

MONDAY = dt.datetime(2026, 9, 21, 9, tzinfo=dt.timezone.utc)


def _mailbox(db, monkeypatch):
    from app.smtpconfig import set_smtp
    set_smtp(db, {"enabled": True, "host": "smtp.local"})
    db.commit()
    sent = []
    monkeypatch.setattr(report_mod._Sender, "deck", lambda self, kind, mail, data: f"{kind}".encode())
    monkeypatch.setattr("app.mail.send_email",
                        lambda cfg, to, subject, body, cc=None, attachment=None, **k:
                        sent.append({"to": to, "cc": sorted(cc or []), "subject": subject, "body": body,
                                     "files": [a[0] for a in attachment or [] if a[0].endswith(".pptx")]}) or True)
    return sent


def _tribe(db, seeded, **cfg):
    set_report(db, {"enabled": True, "weekdays": [0], "hour": 0, **cfg}, seeded["t1"])
    db.commit()


def _people(mail, role):
    return sorted(r["email"] for r in mail["recipients"] if r["role"] == role)


def test_one_mail_with_the_tribe_leader_and_the_squad_leaders_in_copy(db, seeded):
    _tribe(db, seeded, copy_leader=True)
    mails = plan_for(db, seeded["t1"])
    assert [m["label"] for m in mails] == ["Tribe One"]          # no second mail
    assert _people(mails[0], "to") == ["tribe@test"]
    assert _people(mails[0], "cc") == ["sl_a@test", "sl_b@test"]


def test_one_mail_per_squad_for_the_tribe_leader(db, seeded):
    _tribe(db, seeded, leader_mode="per_squad", copy_leader=True)
    mails = {m["label"]: m for m in plan_for(db, seeded["t1"])}
    assert set(mails) == {"Squad A", "Squad B"}
    assert _people(mails["Squad A"], "to") == ["tribe@test"] and _people(mails["Squad A"], "cc") == ["sl_a@test"]


def test_the_squads_covered_narrow_who_is_in_copy(db, seeded):
    _tribe(db, seeded, copy_leader=True, squad_ids=[seeded["squad_a"]])
    assert _people(plan_for(db, seeded["t1"])[0], "cc") == ["sl_a@test"]


def test_copies_by_persona_name_and_address(db, seeded):
    _tribe(db, seeded, copies=[
        {"type": "persona", "value": "member", "content": "tribe"},
        {"type": "user", "value": seeded["sl_b_id"], "content": "tribe"},
        {"type": "email", "value": "pmo@x.io", "content": "squads", "squad_ids": [seeded["squad_a"]]},
    ])
    mails = {m["label"]: m for m in plan_for(db, seeded["t1"])}
    assert _people(mails["Tribe One"], "to") == ["tribe@test"]
    assert _people(mails["Tribe One"], "cc") == ["member@test", "sl_b@test"]
    # Only squad A's mail, and with nobody in To, the copy is promoted.
    assert set(mails) == {"Tribe One", "Squad A"}
    assert _people(mails["Squad A"], "to") == ["pmo@x.io"]


def test_an_address_appears_once_per_mail(db, seeded):
    _tribe(db, seeded, copy_leader=True, copies=[{"type": "email", "value": "SL_A@test", "content": "tribe"}])
    tribe = plan_for(db, seeded["t1"])[0]
    assert sorted(r["email"].lower() for r in tribe["recipients"]) == ["sl_a@test", "sl_b@test", "tribe@test"]


def test_people_without_an_address_are_listed(db, seeded):
    u = db.scalar(select(User).where(User.email == "sl_a@test"))
    u.email = ""
    db.commit()
    _tribe(db, seeded, copy_leader=True)
    assert plan_for(db, seeded["t1"])[0]["missing"] == [{"name": "SL A", "line": "roles"}]


def test_each_kind_of_mail_carries_its_documents(db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    _tribe(db, seeded, copies=[{"type": "email", "value": "pmo@x.io", "content": "squads"}],
           docs={"tribe": ["weekly", "roadmap"], "squad": ["dependencies"]})
    assert report_mod.send_due_weekly_reports(db, MONDAY) == 3
    by_to = {m["to"]: m for m in sent if m["to"] == "tribe@test"}
    assert [f.split("_")[0] for f in by_to["tribe@test"]["files"]] == ["Rapport", "Roadmap"]
    squad_files = [m["files"] for m in sent if m["to"] == "pmo@x.io"]
    assert all(len(f) == 1 and f[0].startswith("Dependances_") for f in squad_files)


def test_no_document_means_the_summary_alone(db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    _tribe(db, seeded, docs={"tribe": [], "squad": []})
    report_mod.send_due_weekly_reports(db, MONDAY)
    assert sent[0]["files"] == []


def test_only_when_something_is_new_is_decided_mail_by_mail(db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    _tribe(db, seeded, leader_mode="per_squad", only_when_changes=True)
    assert report_mod.send_due_weekly_reports(db, MONDAY) == 2         # first: every mail
    db.add(RoadmapItem(squad_id=seeded["squad_a"], year=MONDAY.year, quarter=4, title="Nouveau"))
    db.commit()
    sent.clear()
    assert report_mod.send_due_weekly_reports(db, MONDAY + dt.timedelta(days=7)) == 1
    assert "Squad A" in sent[0]["subject"]                            # squad B did not move


def test_the_direction_gets_every_tribe(db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    set_report(db, {"enabled": True, "recipients": ["dir@x.io"], "weekdays": [0], "hour": 0})
    db.commit()
    assert report_mod.send_due_weekly_reports(db, MONDAY) == 1
    assert sent[0]["to"] == "dir@x.io" and "Squad A" in sent[0]["body"] and "Squad C" in sent[0]["body"]
    # Once a day.
    assert report_mod.send_due_weekly_reports(db, MONDAY + dt.timedelta(hours=2)) == 0


def test_settings_of_the_first_shape_are_converted(db, seeded):
    db.add(AppSetting(key="weekly_report", value=json.dumps({
        "enabled": True, "recipients": ["dir@x.io"], "weekdays": [1], "hour": 9, "global_doc": False,
        "per_squad": True, "squad_leaders": True, "tribe_leader_digest": True, "attach_pptx": False})))
    db.add(AppSetting(key=f"weekly_report:tribe:{seeded['t1']}", value=json.dumps({
        "enabled": True, "recipients": ["copil@x.io"], "weekdays": [3], "hour": 7, "global_doc": False,
        "per_squad": True, "squad_ids": [seeded["squad_a"]], "squad_leaders": True})))
    db.commit()
    assert ensure_v2(db) is True
    assert ensure_v2(db) is False                 # once
    d = get_report(db)
    assert d["enabled"] and d["recipients"] == ["dir@x.io"] and d["weekdays"] == [1]
    assert d["docs"] == {"all": []}               # "attach the PPTX" was off
    t1 = get_report(db, seeded["t1"])
    assert t1["weekdays"] == [3] and t1["copy_leader"] and t1["copy_co_leaders"]
    assert t1["docs"] == {"tribe": ["weekly"], "squad": ["weekly"]}
    assert t1["copies"] == [{"type": "email", "value": "copil@x.io", "content": "squads",
                             "squad_ids": [seeded["squad_a"]]}]
    # The digest becomes tribe 2's own schedule, on the Direction's calendar.
    t2 = get_report(db, seeded["t2"])
    assert t2["enabled"] and t2["weekdays"] == [1] and t2["hour"] == 9 and t2["leader_mode"] == "tribe"


def test_a_draft_is_checked_but_not_saved(db, seeded):
    cfg = normalize(db, {"leader_mode": "nope", "docs": {"tribe": ["roadmap", "bogus"]}}, seeded["t1"])
    assert cfg["leader_mode"] == "tribe" and cfg["docs"]["tribe"] == ["roadmap"]
    assert db.get(AppSetting, f"weekly_report:tribe:{seeded['t1']}") is None


# ---- the screen's API -------------------------------------------------------------------

def test_the_reports_by_email_are_the_admins(client, seeded):
    for who in ("tribe", "sl_a", "member"):
        login(client, seeded[who])
        assert client.get("/api/admin/report-config").status_code == 403
        assert client.post("/api/admin/report-config/plan", json={}).status_code == 403


def test_the_list_follows_the_screen_before_saving(client, db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    login(client, seeded["admin"])
    q = f"?tribe_id={seeded['t1']}"
    saved = client.get(f"/api/admin/report-config{q}").json()
    assert {s["name"] for s in saved["_choices"]["squads"]} == {"Squad A", "Squad B"}
    draft = {"enabled": True, "copy_leader": True, "docs": {"tribe": ["dashboard"], "squad": []}}
    plan = client.post(f"/api/admin/report-config/plan{q}", json={"cfg": draft}).json()["mails"]
    assert [(m["label"], m["docs"]) for m in plan] == [("Tribe One", ["dashboard"])]
    assert sorted(r["email"] for r in plan[0]["recipients"]) == ["sl_a@test", "sl_b@test", "tribe@test"]
    # Nothing was saved.
    assert client.get(f"/api/admin/report-config{q}").json()["copy_leader"] is False
    prev = client.post(f"/api/admin/report-config/preview{q}", json={"line": "roles", "cfg": draft}).json()
    assert prev["to"] == ["tribe@test"] and prev["cc"] == ["sl_a@test", "sl_b@test"]
    assert prev["docs"] == ["dashboard"] and "<html" in prev["html"].lower()
    # A real mail goes from the saved settings.
    assert client.put(f"/api/admin/report-config{q}", json=draft).status_code == 200
    r = client.post(f"/api/admin/report-config/test{q}", json={"line": "roles"})
    assert r.json()["ok"] and sent[-1]["to"] == "admin@test" and "(test)" in sent[-1]["subject"]
    sent.clear()
    r = client.post(f"/api/admin/report-config/send-now{q}", json={})
    assert r.json()["sent"] == 1 and sent[0]["to"] == "tribe@test" and sent[0]["cc"] == ["sl_a@test", "sl_b@test"]


def test_only_people_of_the_tribe_are_named(client, db, seeded):
    login(client, seeded["admin"])
    q = f"?tribe_id={seeded['t1']}"
    other = db.scalar(select(User).where(User.email == "tribe2@test"))
    assert client.put(f"/api/admin/report-config{q}", json={"copies": [{"type": "user", "value": other.id}]}).status_code == 400
    r = client.put(f"/api/admin/report-config{q}", json={"squad_ids": [seeded["squad_c"], seeded["squad_a"]]})
    assert r.json()["squad_ids"] == [seeded["squad_a"]]
