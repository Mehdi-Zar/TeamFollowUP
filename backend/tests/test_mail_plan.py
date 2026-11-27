"""The scheduled reports by email: the diffusions, and who receives which mail
(app/reportconfig.py, app/mailplan.py).

A diffusion is one scheduled mailing; there can be several per tribe. In a
tribe's, the tribe leader is the main recipient: the tribe's mail, one mail per
squad, or both. The squads' people named by role join the tribe's mail when the
tribe leader gets it alone (one mail, never two for one person), their own
squad's mail otherwise. Others are added by persona, name or address, each with
what it receives (the tribe's document, or the squads' mails). Each kind of mail
says which documents it carries. The Direction gets the whole document, every
tribe.
"""
import datetime as dt
import json

from sqlalchemy import select

from app import report as report_mod
from app.mailplan import plan_for
from app.models import AppSetting, ReportBaseline, ReportSend, RoadmapItem, User
from app.reportconfig import (create_diffusion, defaults, ensure_diffusions, get_diffusion,
                              list_diffusions, normalize)
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
    d = create_diffusion(db, seeded["t1"], {"enabled": True, "weekdays": [0], "hour": 0, **cfg})
    db.commit()
    return d


def _plan(db, d):
    return plan_for(db, get_diffusion(db, d["id"]))


def _people(mail, role):
    return sorted(r["email"] for r in mail["recipients"] if r["role"] == role)


def test_one_mail_with_the_tribe_leader_and_the_squad_leaders_in_copy(db, seeded):
    d = _tribe(db, seeded, copy_leader=True)
    mails = _plan(db, d)
    assert [m["label"] for m in mails] == ["Tribe One"]          # no second mail
    assert _people(mails[0], "to") == ["tribe@test"]
    assert _people(mails[0], "cc") == ["sl_a@test", "sl_b@test"]


def test_one_mail_per_squad_for_the_tribe_leader(db, seeded):
    d = _tribe(db, seeded, leader_tribe=False, leader_squads=True, copy_leader=True)
    mails = {m["label"]: m for m in _plan(db, d)}
    assert set(mails) == {"Squad A", "Squad B"}
    assert _people(mails["Squad A"], "to") == ["tribe@test"] and _people(mails["Squad A"], "cc") == ["sl_a@test"]


def test_the_tribe_leader_can_have_both(db, seeded):
    d = _tribe(db, seeded, leader_tribe=True, leader_squads=True, copy_leader=True)
    mails = {m["label"]: m for m in _plan(db, d)}
    assert set(mails) == {"Tribe One", "Squad A", "Squad B"}
    assert _people(mails["Tribe One"], "to") == ["tribe@test"] and _people(mails["Tribe One"], "cc") == []
    # The squad leaders are on their own squad's mail, not on the tribe's.
    assert _people(mails["Squad B"], "to") == ["tribe@test"] and _people(mails["Squad B"], "cc") == ["sl_b@test"]


def test_without_the_tribe_leader_the_squads_get_their_own_mail(db, seeded):
    d = _tribe(db, seeded, leader_tribe=False, leader_squads=False, copy_leader=True)
    mails = {m["label"]: m for m in _plan(db, d)}
    assert set(mails) == {"Squad A", "Squad B"}
    assert _people(mails["Squad A"], "to") == ["sl_a@test"]      # promoted to To


def test_the_squads_covered_narrow_who_is_in_copy(db, seeded):
    d = _tribe(db, seeded, copy_leader=True, squad_ids=[seeded["squad_a"]])
    assert _people(_plan(db, d)[0], "cc") == ["sl_a@test"]


def test_copies_by_persona_name_and_address(db, seeded):
    d = _tribe(db, seeded, copies=[
        {"type": "persona", "value": "member", "content": "tribe"},
        {"type": "user", "value": seeded["sl_b_id"], "content": "tribe"},
        {"type": "email", "value": "pmo@x.io", "content": "squads", "squad_ids": [seeded["squad_a"]]},
    ])
    mails = {m["label"]: m for m in _plan(db, d)}
    assert _people(mails["Tribe One"], "to") == ["tribe@test"]
    assert _people(mails["Tribe One"], "cc") == ["member@test", "sl_b@test"]
    # Only squad A's mail, and with nobody in To, the copy is promoted.
    assert set(mails) == {"Tribe One", "Squad A"}
    assert _people(mails["Squad A"], "to") == ["pmo@x.io"]


def test_an_address_appears_once_per_mail(db, seeded):
    d = _tribe(db, seeded, copy_leader=True, copies=[{"type": "email", "value": "SL_A@test", "content": "tribe"}])
    tribe = _plan(db, d)[0]
    assert sorted(r["email"].lower() for r in tribe["recipients"]) == ["sl_a@test", "sl_b@test", "tribe@test"]


def test_people_without_an_address_are_listed(db, seeded):
    u = db.scalar(select(User).where(User.email == "sl_a@test"))
    u.email = ""
    db.commit()
    d = _tribe(db, seeded, copy_leader=True)
    assert _plan(db, d)[0]["missing"] == [{"name": "SL A", "line": "roles"}]


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
    _tribe(db, seeded, leader_tribe=False, leader_squads=True, only_when_changes=True)
    assert report_mod.send_due_weekly_reports(db, MONDAY) == 2         # first: every mail
    db.add(RoadmapItem(squad_id=seeded["squad_a"], year=MONDAY.year, quarter=4, title="Nouveau"))
    db.commit()
    sent.clear()
    assert report_mod.send_due_weekly_reports(db, MONDAY + dt.timedelta(days=7)) == 1
    assert "Squad A" in sent[0]["subject"]                            # squad B did not move


def test_several_diffusions_for_one_tribe_each_on_its_calendar(db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    _tribe(db, seeded)                                                 # Monday
    _tribe(db, seeded, weekdays=[4], leader_tribe=False,
           copies=[{"type": "email", "value": "copil@x.io", "content": "tribe"}])   # Friday
    assert report_mod.send_due_weekly_reports(db, MONDAY) == 1
    assert [m["to"] for m in sent] == ["tribe@test"]
    sent.clear()
    assert report_mod.send_due_weekly_reports(db, MONDAY + dt.timedelta(days=4)) == 1
    assert [m["to"] for m in sent] == ["copil@x.io"]


def test_the_direction_gets_every_tribe(db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    create_diffusion(db, None, {"enabled": True, "weekdays": [0], "hour": 0,
                                "copies": [{"type": "email", "value": "dir@x.io"},
                                           {"type": "user", "value": seeded["sl_b_id"]}]})
    db.commit()
    assert report_mod.send_due_weekly_reports(db, MONDAY) == 1
    assert sent[0]["to"] == "dir@x.io, sl_b@test" and "Squad A" in sent[0]["body"] and "Squad C" in sent[0]["body"]
    # Once a day.
    assert report_mod.send_due_weekly_reports(db, MONDAY + dt.timedelta(hours=2)) == 0


def test_every_send_is_in_the_history(db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    d = _tribe(db, seeded, copy_leader=True)
    report_mod.send_due_weekly_reports(db, MONDAY)
    rows = db.scalars(select(ReportSend).where(ReportSend.diffusion_id == d["id"])).all()
    assert [(r.trigger, r.sent, r.recipients) for r in rows] == [("schedule", 1, 3)]
    # A refused mail is noted with the reason, once a day while it keeps failing.
    monkeypatch.setattr("app.mail.send_email", lambda *a, **k: False)
    monkeypatch.setattr("app.mail.last_error", lambda: "Connection refused")
    nxt = MONDAY + dt.timedelta(days=7)
    for h in range(3):
        assert report_mod.send_due_weekly_reports(db, nxt + dt.timedelta(hours=h)) == 0
    h = report_mod.history(db, d["id"])
    assert len(h) == 2 and h[0]["sent"] == 0 and h[0]["failed"] == ["Tribe One"]
    assert h[0]["error"] == "Connection refused"
    assert len(sent) == 1


def test_the_next_send_is_shown(db, seeded):
    d = normalize({**defaults(seeded["t1"]), "id": 1}, {"enabled": True, "weekdays": [0, 3], "hour": 8})
    wednesday = dt.datetime(2026, 9, 23, 12, tzinfo=dt.timezone.utc)
    nxt = report_mod.next_send(d, wednesday)
    assert (nxt.weekday(), nxt.hour) == (3, 8)
    # Today, not yet sent: today (it leaves at the next tick if past the hour).
    assert report_mod.next_send(d, MONDAY).date() == MONDAY.date()
    d["last_sent_day"] = MONDAY.date().isoformat()
    assert report_mod.next_send(d, MONDAY).weekday() == 3
    assert report_mod.next_send({**d, "enabled": False}, MONDAY) is None


def test_settings_of_the_earlier_shapes_become_diffusions(db, seeded):
    db.add(AppSetting(key="weekly_report", value=json.dumps({
        "enabled": True, "recipients": ["dir@x.io"], "weekdays": [1], "hour": 9, "global_doc": False,
        "per_squad": True, "squad_leaders": True, "tribe_leader_digest": True, "attach_pptx": False})))
    db.add(AppSetting(key=f"weekly_report:tribe:{seeded['t1']}", value=json.dumps({
        "enabled": True, "recipients": ["copil@x.io"], "weekdays": [3], "hour": 7, "global_doc": False,
        "per_squad": True, "squad_ids": [seeded["squad_a"]], "squad_leaders": True,
        "last_sent_day": "2026-09-17"})))
    db.add(ReportBaseline(scope_key=f"t{seeded['t1']}:tribe", signature={"x": 1}))
    db.commit()
    assert ensure_diffusions(db) is True
    assert ensure_diffusions(db) is False                 # once
    assert db.get(AppSetting, "weekly_report") is None
    by_scope = {d["tribe_id"]: d for d in list_diffusions(db)}
    d = by_scope[None]
    assert d["enabled"] and d["copies"] == [{"type": "email", "value": "dir@x.io", "content": "tribe",
                                             "squad_ids": []}]
    assert d["weekdays"] == [1] and d["docs"] == {"all": []}      # "attach the PPTX" was off
    t1 = by_scope[seeded["t1"]]
    assert t1["weekdays"] == [3] and t1["copy_leader"] and t1["copy_co_leaders"]
    assert t1["leader_tribe"] and not t1["leader_squads"] and t1["last_sent_day"] == "2026-09-17"
    assert t1["copies"] == [{"type": "email", "value": "copil@x.io", "content": "squads",
                             "squad_ids": [seeded["squad_a"]]}]
    # The "what's new" baseline follows the diffusion.
    assert db.get(ReportBaseline, f"d{t1['id']}:t{seeded['t1']}:tribe").signature == {"x": 1}
    # The digest becomes tribe 2's own diffusion, on the Direction's calendar.
    t2 = by_scope[seeded["t2"]]
    assert t2["enabled"] and t2["weekdays"] == [1] and t2["hour"] == 9 and t2["leader_tribe"]


def test_a_schedule_never_set_up_is_not_converted(db, seeded):
    db.add(AppSetting(key=f"weekly_report:tribe:{seeded['t1']}", value=json.dumps({"v": 2, "enabled": False})))
    db.commit()
    assert ensure_diffusions(db) is True
    assert list_diffusions(db) == []


def test_a_draft_is_checked_but_not_saved(db, seeded):
    cfg = normalize(defaults(seeded["t1"]), {"leader_tribe": "yes", "docs": {"tribe": ["roadmap", "bogus"]},
                                             "last_sent_day": "2026-01-01", "tribe_id": 99})
    assert cfg["leader_tribe"] is True and cfg["docs"]["tribe"] == ["roadmap"]
    assert cfg["last_sent_day"] == "" and cfg["tribe_id"] == seeded["t1"]
    assert list_diffusions(db) == []


# ---- the screen's API -------------------------------------------------------------------

def test_a_tribe_leader_sets_the_diffusions_of_their_tribe_only(client, db, seeded):
    login(client, seeded["tribe"])
    out = client.get("/api/admin/diffusions").json()
    assert out["direction"] is False and [t["id"] for t in out["tribes"]] == [seeded["t1"]]
    r = client.post("/api/admin/diffusions", json={"tribe_id": seeded["t1"], "name": "Hebdo"})
    assert r.status_code == 200, r.text
    assert client.post("/api/admin/diffusions", json={"tribe_id": seeded["t2"]}).status_code == 403
    assert client.post("/api/admin/diffusions", json={"tribe_id": None}).status_code == 403
    login(client, seeded["admin"])
    other = client.post("/api/admin/diffusions", json={"tribe_id": seeded["t2"]}).json()
    direction = client.post("/api/admin/diffusions", json={"tribe_id": None}).json()
    login(client, seeded["tribe"])
    assert [d["name"] for d in client.get("/api/admin/diffusions").json()["diffusions"]] == ["Hebdo"]
    for d in (other, direction):
        assert client.get(f"/api/admin/diffusions/{d['id']}").status_code == 403
        assert client.put(f"/api/admin/diffusions/{d['id']}", json={"enabled": True}).status_code == 403
    for who in ("sl_a", "member"):
        login(client, seeded[who])
        assert client.get("/api/admin/diffusions").status_code == 403
        assert client.post("/api/admin/diffusions/plan", json={"cfg": {"tribe_id": seeded["t1"]}}).status_code == 403


def test_the_list_follows_the_screen_before_saving(client, db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    login(client, seeded["admin"])
    ch = client.get(f"/api/admin/diffusions/choices?tribe_id={seeded['t1']}").json()
    assert {s["name"] for s in ch["squads"]} == {"Squad A", "Squad B"}
    draft = {"tribe_id": seeded["t1"], "enabled": True, "copy_leader": True,
             "docs": {"tribe": ["dashboard"], "squad": []}}
    plan = client.post("/api/admin/diffusions/plan", json={"cfg": draft}).json()["mails"]
    assert [(m["label"], m["docs"]) for m in plan] == [("Tribe One", ["dashboard"])]
    assert sorted(r["email"] for r in plan[0]["recipients"]) == ["sl_a@test", "sl_b@test", "tribe@test"]
    prev = client.post("/api/admin/diffusions/preview", json={"cfg": draft}).json()
    assert prev["to"] == ["tribe@test"] and prev["cc"] == ["sl_a@test", "sl_b@test"]
    assert prev["docs"] == ["dashboard"] and "<html" in prev["html"].lower()
    # Nothing was saved.
    assert client.get("/api/admin/diffusions").json()["diffusions"] == []
    d = client.post("/api/admin/diffusions", json=draft).json()
    card = client.get("/api/admin/diffusions").json()["diffusions"][0]
    assert len(card["_to"]) == 1 and card["_mails"] == 1 and len(card["_cc"]) == 2
    assert card["_next"] is not None
    # Pausing is a partial update.
    assert client.put(f"/api/admin/diffusions/{d['id']}", json={"enabled": False}).json()["copy_leader"] is True
    assert client.get("/api/admin/diffusions").json()["diffusions"][0]["_next"] is None
    # A real mail goes from the saved settings.
    r = client.post(f"/api/admin/diffusions/{d['id']}/test", json={})
    assert r.json()["ok"] and sent[-1]["to"] == "admin@test" and "(test)" in sent[-1]["subject"]
    sent.clear()
    r = client.post(f"/api/admin/diffusions/{d['id']}/send-now")
    assert r.json()["sent"] == 1 and sent[0]["to"] == "tribe@test" and sent[0]["cc"] == ["sl_a@test", "sl_b@test"]
    hist = client.get(f"/api/admin/diffusions/{d['id']}/history").json()["sends"]
    assert [h["trigger"] for h in hist] == ["now", "test"]
    assert client.get("/api/admin/diffusions").json()["diffusions"][0]["_last"]["trigger"] == "now"
    # Deleting takes its history along.
    assert client.delete(f"/api/admin/diffusions/{d['id']}").status_code == 200
    assert db.scalars(select(ReportSend).where(ReportSend.diffusion_id == d["id"])).all() == []


def test_only_people_of_the_tribe_are_named(client, db, seeded):
    login(client, seeded["admin"])
    d = client.post("/api/admin/diffusions", json={"tribe_id": seeded["t1"]}).json()
    other = db.scalar(select(User).where(User.email == "tribe2@test"))
    assert client.put(f"/api/admin/diffusions/{d['id']}",
                      json={"copies": [{"type": "user", "value": other.id}]}).status_code == 400
    r = client.put(f"/api/admin/diffusions/{d['id']}", json={"squad_ids": [seeded["squad_c"], seeded["squad_a"]]})
    assert r.json()["squad_ids"] == [seeded["squad_a"]]


def test_the_mail_holds_the_blocks_chosen(client, db, seeded):
    # A blocked milestone in Squad A: an attention point for its tribe and for it.
    db.add(RoadmapItem(squad_id=seeded["squad_a"], year=dt.date.today().year, quarter=4,
                       title="Migration bloquee", status="blocked"))
    db.commit()
    login(client, seeded["admin"])
    base = {"tribe_id": seeded["t1"], "enabled": True, "leader_squads": True, "squad_ids": [seeded["squad_a"]]}

    def html(body, key_kind="tribe"):
        cfg = {**base, "body": body}
        plan = client.post("/api/admin/diffusions/plan", json={"cfg": cfg}).json()["mails"]
        key = next(m["key"] for m in plan if m["kind"] == key_kind)
        return client.post("/api/admin/diffusions/preview", json={"cfg": cfg, "key": key}).json()["html"]

    # The usual tribe recap: figures and squads, no attention list.
    usual = html({"tribe": ["kpis", "squads"], "squad": []})
    assert "Jalons bloqu" in usual and "Migration bloquee" not in usual
    # Attention points only: the milestone, named after its squad, and no table.
    att = html({"tribe": ["milestones", "late_otds"], "squad": []})
    assert "Migration bloquee" in att and "Squad A" in att and "Dernière saisie" not in att
    # The squad mail keeps its own choice; the table of squads never applies to it.
    sq = html({"tribe": [], "squad": ["kpis", "squads"]}, "squad")
    assert "Migration bloquee" not in sq and "Squad leader" in sq
    # Nothing to flag says so instead of an empty mail.
    calm = html({"tribe": ["late_otds", "kpi_watch"], "squad": []})
    assert "Aucun point d" in calm and "cette semaine" in calm
    # Saved, in the fixed order, unknown blocks dropped.
    d = client.post("/api/admin/diffusions", json={**base, "body": {"tribe": ["squads", "bogus", "changes"],
                                                                      "squad": ["squads", "kpis"]}}).json()
    assert d["body"] == {"tribe": ["changes", "squads"], "squad": ["kpis"]}


def test_a_diffusion_saved_before_the_choice_keeps_its_usual_mail(db, seeded):
    d = _tribe(db, seeded)
    row = db.get(AppSetting, f"report_diffusion:{d['id']}")
    stored = json.loads(row.value)
    stored.pop("body", None)
    row.value = json.dumps(stored)
    db.commit()
    assert get_diffusion(db, d["id"])["body"] == {"tribe": ["changes", "kpis", "squads"],
                                                 "squad": ["changes", "kpis", "key_messages", "late_otds",
                                                           "kpi_watch", "milestones"]}


def test_the_minute_is_kept_and_a_failure_retries_once_an_hour(db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    d = _tribe(db, seeded, hour=8, minute=17, copy_leader=True)
    assert get_diffusion(db, d["id"])["minute"] == 15          # by 5 minutes
    monday_paris = lambda h, m: dt.datetime(2026, 9, 21, h - 2, m, 30, tzinfo=dt.timezone.utc)  # noqa: E731
    assert report_mod.send_due_weekly_reports(db, now=monday_paris(8, 10)) == 0
    assert report_mod.next_send(get_diffusion(db, d["id"]), monday_paris(8, 10)).strftime("%H:%M") == "08:15"
    # The mail server refuses: noted, then left alone until the next full hour.
    monkeypatch.setattr("app.mail.send_email", lambda *a, **k: False)
    assert report_mod.send_due_weekly_reports(db, now=monday_paris(8, 15)) == 0
    calls = []
    monkeypatch.setattr("app.mail.send_email", lambda *a, **k: calls.append(1) or True)
    report_mod.send_due_weekly_reports(db, now=monday_paris(8, 20))
    assert calls == []
    report_mod.send_due_weekly_reports(db, now=monday_paris(9, 0))
    assert calls and get_diffusion(db, d["id"])["last_sent_day"] == "2026-09-21"
    assert sent == []


def test_a_late_mail_goes_at_the_next_tick(db, seeded, monkeypatch):
    sent = _mailbox(db, monkeypatch)
    _tribe(db, seeded, hour=8, minute=0, copy_leader=True)
    # The app was down at 8 h: back at 8 h 40, the mail leaves without waiting for 9 h.
    report_mod.send_due_weekly_reports(db, now=dt.datetime(2026, 9, 21, 6, 40, 30, tzinfo=dt.timezone.utc))
    assert len(sent) == 1
