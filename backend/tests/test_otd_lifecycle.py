"""The status of an OTD, case by case, and its life over the year.

The rules (app/status.py, ``otd_state``), first match wins:

  cancelled > declared by hand > carried over (not delivered) > computed.

Computed: no milestone -> unscoped, or late once the date has passed; all done
-> delivered, or delivered late when the last one was finished after the date;
date passed -> late (from the day after); a milestone blocked or at risk, the
date less than 15 days away, or a milestone planned in a quarter ending after
the date -> at risk; otherwise on track.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

from app import status as st
from app.models import Otd, RoadmapItem
from app.otdcarry import carry_over_otds
from tests.conftest import login

NOW = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
YEAR = datetime.now(timezone.utc).year


def j(status="on_track", q=2, year=2026, done_at=None):
    return NS(status=status, quarter=q, year=year, done_at=done_at)


def at(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


def state(jalons, date, otd=None, now=NOW):
    return st.otd_state(jalons, date, now, otd)


# ---- computed status ------------------------------------------------------------------

def test_no_milestone_is_to_be_scoped_then_late():
    assert state([], at(2026, 9, 30))["status"] == "unscoped"
    assert state([], None)["status"] == "unscoped"
    assert state([], at(2026, 5, 31))["status"] == "late"


def test_all_done_on_time_or_late():
    on_time = [j("done", done_at=at(2026, 5, 2)), j("done", done_at=at(2026, 5, 20))]
    assert state(on_time, at(2026, 5, 31))["status"] == "delivered"
    late = [j("done", done_at=at(2026, 5, 2)), j("done", done_at=at(2026, 6, 3))]
    assert state(late, at(2026, 5, 31))["status"] == "delivered_late"
    # Done on the committed day itself is on time.
    assert state([j("done", done_at=at(2026, 5, 31))], at(2026, 5, 31))["status"] == "delivered"
    # A milestone finished before the tool kept no date: taken as on time.
    assert state([j("done")], at(2026, 5, 31))["status"] == "delivered"


def test_late_from_the_day_after():
    # Committed today: not late yet, but due soon.
    assert state([j()], at(2026, 6, 10))["status"] == "at_risk"
    assert state([j()], at(2026, 6, 9))["status"] == "late"


def test_due_soon_turns_at_risk_15_days_before():
    assert state([j(q=1)], at(2026, 6, 25)) == {"status": "at_risk", "reasons": ["due_soon"]}
    assert state([j(q=1)], at(2026, 6, 26)) == {"status": "on_track", "reasons": []}


def test_a_blocked_or_at_risk_milestone():
    assert state([j("blocked", q=3), j(q=3)], at(2026, 12, 1))["reasons"] == ["milestone_blocked"]
    assert state([j("at_risk", q=3)], at(2026, 12, 1))["reasons"] == ["milestone_at_risk"]


def test_a_milestone_planned_after_the_date():
    # Promised mid-May, a milestone sits in Q3: the plan cannot hold the date.
    r = state([j(q=2), j(q=3)], at(2026, 9, 15), now=at(2026, 4, 1))
    assert r == {"status": "at_risk", "reasons": ["milestone_beyond_date"]}
    # Already done, it no longer matters.
    r = state([j(q=2), j("done", q=4, done_at=at(2026, 3, 1))], at(2026, 9, 15), now=at(2026, 4, 1))
    assert r["status"] == "on_track"
    # A milestone slipped to next year is beyond any date of this one.
    r = state([j(q=1, year=2027)], at(2026, 12, 15), now=at(2026, 4, 1))
    assert r["reasons"] == ["milestone_beyond_date"]


def test_date_passed_wins_over_at_risk():
    assert state([j("blocked")], at(2026, 5, 31))["status"] == "late"


def test_facts_win_in_order():
    base = dict(cancelled_at=None, declared_status=None, carried_to=None)
    done = [j("done")]
    assert state(done, at(2026, 1, 1), NS(**{**base, "carried_to": object()}))["status"] == "not_delivered"
    declared = NS(**{**base, "declared_status": "delivered_late", "carried_to": object()})
    assert state([j("blocked")], at(2026, 1, 1), declared) == {"status": "delivered_late", "reasons": ["declared"]}
    cancelled = NS(**{**base, "cancelled_at": NOW, "declared_status": "delivered"})
    assert state(done, at(2026, 1, 1), cancelled)["status"] == "cancelled"


def test_a_milestone_remembers_when_it_was_finished(db, seeded):
    it = RoadmapItem(squad_id=seeded["squad_a"], year=2026, quarter=1, title="J")
    db.add(it)
    db.flush()
    assert it.done_at is None
    it.status = "done"
    assert it.done_at is not None
    first = it.done_at
    it.status = "done"            # unchanged: keeps its date
    assert it.done_at == first
    it.status = "blocked"         # reopened: forgets it
    assert it.done_at is None


# ---- through the API --------------------------------------------------------------------

def _otd(client, **kw):
    r = client.post("/api/otds", json={"year": YEAR, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _get(client, oid, year=YEAR):
    return next(o for o in client.get(f"/api/otds?year={year}").json() if o["id"] == oid)


def test_replanning_keeps_the_first_date(client, seeded):
    login(client, seeded["sl_a"])
    o = _otd(client, tribe_id=seeded["t1"], title="P", scope="squad", squad_id=seeded["squad_a"],
             committed_date=f"{YEAR}-11-30T00:00:00Z")
    assert o["replanned_days"] == 0 and o["initial_committed_date"].startswith(f"{YEAR}-11-30")
    r = client.put(f"/api/otds/{o['id']}", json={"committed_date": f"{YEAR}-12-15T00:00:00Z"})
    assert r.status_code == 200
    assert r.json()["replanned_days"] == 15
    assert r.json()["initial_committed_date"].startswith(f"{YEAR}-11-30")


def test_cancel_needs_a_reason_and_can_be_undone(client, seeded):
    login(client, seeded["sl_a"])
    o = _otd(client, tribe_id=seeded["t1"], title="P", scope="squad", squad_id=seeded["squad_a"],
             committed_date=f"{YEAR}-01-15T00:00:00Z")
    r = client.put(f"/api/otds/{o['id']}", json={"cancelled": True})
    assert r.status_code == 422
    r = client.put(f"/api/otds/{o['id']}", json={"cancelled": True, "cancel_reason": "Descopé"})
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled" and r.json()["cancel_reason"] == "Descopé"
    assert r.json()["cancelled_at"]
    r = client.put(f"/api/otds/{o['id']}", json={"cancelled": False})
    assert r.json()["status"] != "cancelled" and r.json()["cancel_reason"] is None


def test_a_declared_status_wins_until_it_is_cleared(client, seeded):
    """Starting mid-year: a past OTD is declared, not rebuilt milestone by milestone."""
    login(client, seeded["sl_a"])
    o = _otd(client, tribe_id=seeded["t1"], title="Avant l'outil", scope="squad", squad_id=seeded["squad_a"],
             committed_date=f"{YEAR}-01-15T00:00:00Z", declared_status="delivered_late",
             declared_on=f"{YEAR}-02-01T00:00:00Z", declared_note="Livré début février")
    assert o["status"] == "delivered_late" and o["reasons"] == ["declared"]
    # Milestones linked later do not change it.
    jid = client.post("/api/roadmap-items", json={"squad_id": seeded["squad_a"], "year": YEAR, "quarter": 1,
                                                  "title": "J", "theme": "LZ", "status": "blocked"}).json()["id"]
    assert client.put(f"/api/otds/{o['id']}/jalons", json={"jalon_ids": [jid]}).status_code == 200
    assert _get(client, o["id"])["status"] == "delivered_late"
    # Cleared: back to the computed status, and the note goes with it.
    r = client.put(f"/api/otds/{o['id']}", json={"declared_status": None})
    assert r.json()["status"] == "late" and r.json()["declared_note"] is None


def test_a_milestone_that_slips_to_next_year_stays_linked(client, seeded):
    login(client, seeded["sl_a"])
    o = _otd(client, tribe_id=seeded["t1"], title="P", scope="squad", squad_id=seeded["squad_a"],
             committed_date=f"{YEAR}-12-15T00:00:00Z")
    jid = client.post("/api/roadmap-items", json={"squad_id": seeded["squad_a"], "year": YEAR, "quarter": 4,
                                                  "title": "J", "theme": "LZ", "squad_otd_id": o["id"]}).json()["id"]
    r = client.put(f"/api/roadmap-items/{jid}", json={"year": YEAR + 1, "quarter": 1})
    assert r.status_code == 200 and r.json()["squad_otd_id"] == o["id"]
    got = _get(client, o["id"])
    assert got["slipped"] == [{"id": jid, "title": "J", "year": YEAR + 1}]
    assert "milestone_beyond_date" in got["reasons"] or got["status"] == "late"
    # Saving the OTD window (which lists this year's milestones) keeps it.
    assert client.put(f"/api/otds/{o['id']}/jalons", json={"jalon_ids": []}).status_code == 200
    assert [x["id"] for x in _get(client, o["id"])["jalons"]] == [jid]
    # Unlinked from its own window.
    assert client.put(f"/api/roadmap-items/{jid}", json={"squad_otd_id": None}).status_code == 200
    assert _get(client, o["id"])["jalons"] == []


def test_each_squad_sees_its_share(client, seeded):
    login(client, seeded["tribe"])
    o = _otd(client, tribe_id=seeded["t1"], title="Promesse", committed_date=f"{YEAR}-12-15T00:00:00Z")
    ids = []
    for who, sq, status in (("sl_a", "squad_a", "done"), ("sl_a", "squad_a", "on_track"), ("sl_b", "squad_b", "on_track")):
        login(client, seeded[who])
        ids.append(client.post("/api/roadmap-items", json={"squad_id": seeded[sq], "year": YEAR, "quarter": 4,
                                                          "title": "J", "theme": "LZ", "status": status}).json()["id"])
    login(client, seeded["tribe"])
    assert client.put(f"/api/otds/{o['id']}/jalons", json={"jalon_ids": ids}).status_code == 200
    shares = {s["squad_name"]: (s["total"], s["done"]) for s in _get(client, o["id"])["by_squad"]}
    assert shares == {"Squad A": (2, 1), "Squad B": (1, 0)}


# ---- carry-over on January 1st --------------------------------------------------------

def _carry_setup(db, seeded):
    otd = Otd(tribe_id=seeded["t1"], year=2025, title="Promesse 2025", scope="squad",
              squad_id=seeded["squad_a"], committed_date=at(2025, 11, 30),
              owner_user_id=seeded["sl_a_id"], created_at=at(2025, 3, 1))
    db.add(otd)
    db.flush()
    done = RoadmapItem(squad_id=seeded["squad_a"], year=2025, quarter=3, title="Fait", status="done",
                       squad_otd_id=otd.id)
    todo = RoadmapItem(squad_id=seeded["squad_a"], year=2025, quarter=4, title="Reste", status="blocked",
                       squad_otd_id=otd.id)
    slipped = RoadmapItem(squad_id=seeded["squad_a"], year=2026, quarter=1, title="Glissé",
                          squad_otd_id=otd.id)
    db.add_all([done, todo, slipped])
    db.commit()
    return otd, done, todo, slipped


def test_carry_over_on_january_first(db, seeded):
    from app.models import Notification
    otd, done, todo, slipped = _carry_setup(db, seeded)
    # Nothing happens during the year itself.
    assert carry_over_otds(db, now=at(2025, 12, 31)) == 0
    assert carry_over_otds(db, now=at(2026, 1, 1)) == 1
    db.expire_all()
    new = otd.carried_to
    assert new is not None and new.year == 2026 and new.title == "Promesse 2025"
    assert new.committed_date is None and new.carried_from_id == otd.id
    # The original stays in 2025, not delivered, with what was done.
    assert st.otd_status(otd.members, otd.committed_date, at(2026, 1, 2), otd) == "not_delivered"
    assert {j.title for j in otd.members} == {"Fait", "Reste"}
    # The copy holds what remains: a copy of "Reste" in Q1 2026, and "Glissé".
    assert sorted((j.title, j.year, j.quarter, j.status) for j in new.members) == [
        ("Glissé", 2026, 1, "on_track"), ("Reste", 2026, 1, "blocked")]
    assert db.get(RoadmapItem, todo.id).year == 2025
    # The squad leader is told, once.
    notes = db.query(Notification).filter_by(kind="otd_carry").all()
    assert [(n.user_id, n.excerpt) for n in notes] == [(seeded["sl_a_id"], "Promesse 2025")]
    # Idempotent.
    assert carry_over_otds(db, now=at(2026, 1, 1, ) + timedelta(hours=1)) == 0


def test_not_carried_when_delivered_cancelled_declared_or_entered_later(db, seeded):
    otd, done, todo, slipped = _carry_setup(db, seeded)
    todo.status = "done"
    slipped.status = "done"
    late_entry = Otd(tribe_id=seeded["t1"], year=2025, title="Saisi en 2026", scope="squad",
                     squad_id=seeded["squad_a"], created_at=at(2026, 1, 5))
    cancelled = Otd(tribe_id=seeded["t1"], year=2025, title="Annulé", scope="squad",
                    squad_id=seeded["squad_a"], created_at=at(2025, 2, 1), cancelled_at=at(2025, 6, 1),
                    cancel_reason="Descopé")
    declared = Otd(tribe_id=seeded["t1"], year=2025, title="Déclaré", scope="squad",
                   squad_id=seeded["squad_a"], created_at=at(2025, 2, 1), declared_status="not_delivered")
    db.add_all([late_entry, cancelled, declared])
    db.commit()
    assert carry_over_otds(db, now=at(2026, 1, 10)) == 0


def test_a_milestone_serving_two_otds_is_copied_once(db, seeded):
    mgmt = Otd(tribe_id=seeded["t1"], year=2025, title="Mgmt", scope="management",
               squad_id=seeded["squad_a"], created_at=at(2025, 3, 1))
    own = Otd(tribe_id=seeded["t1"], year=2025, title="Squad", scope="squad",
              squad_id=seeded["squad_a"], created_at=at(2025, 3, 1))
    db.add_all([mgmt, own])
    db.flush()
    db.add(RoadmapItem(squad_id=seeded["squad_a"], year=2025, quarter=4, title="Commun",
                       otd_id=mgmt.id, squad_otd_id=own.id))
    db.commit()
    assert carry_over_otds(db, now=at(2026, 1, 1)) == 2
    db.expire_all()
    copies = db.query(RoadmapItem).filter_by(year=2026, title="Commun").all()
    assert len(copies) == 1
    assert copies[0].otd_id == mgmt.carried_to.id and copies[0].squad_otd_id == own.carried_to.id
