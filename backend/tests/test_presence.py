"""On site or remote (ADR 0021): the usual week, the change for one day, the
absence that wins over both, and who may set it."""
from datetime import date

from sqlalchemy import select

from app.models import Leave, LeaveType, Member, User
from .conftest import login

# Monday 30 November 2026 .. Sunday 6 December 2026.
WEEK = "from=2026-11-30&to=2026-12-06"


def _uid(db, email):
    return db.scalar(select(User).where(User.email == email)).id


def _person(body, uid):
    return next(p for p in body["people"] if p["user_id"] == uid)


def test_usual_week_and_one_day_change(seeded, db, client):
    uid = _uid(db, seeded["member"])
    login(client, seeded["member"])
    r = client.put(f"/api/presence/week/{uid}", json={"weekdays": [4, 0, 0, 6]})
    assert r.status_code == 200, r.text
    assert r.json()["weekdays"] == [0, 4]  # deduplicated, weekend dropped
    # On site on Monday this week, remote on Wednesday.
    assert client.put(f"/api/presence/day/{uid}", json={"day": "2026-11-30", "location": "onsite"}).json()["changed"]
    assert client.put(f"/api/presence/day/{uid}", json={"day": "2026-12-02", "location": "remote"}).json()["changed"]
    me = _person(client.get(f"/api/presence?{WEEK}").json(), uid)
    assert [me["days"][d] for d in sorted(me["days"])] == [
        "onsite", "onsite", "remote", "onsite", "remote", "off", "off"]
    assert me["can_edit"] is True
    # Back to the usual week: the change is gone.
    client.put(f"/api/presence/day/{uid}", json={"day": "2026-11-30", "location": None})
    me = _person(client.get(f"/api/presence?{WEEK}").json(), uid)
    assert me["days"]["2026-11-30"] == "remote" and "2026-11-30" not in me["changes"]
    # A change equal to the usual week is not stored.
    assert client.put(f"/api/presence/day/{uid}", json={"day": "2026-12-04", "location": "remote"}).json()["changed"] is False
    assert client.put(f"/api/presence/day/{uid}", json={"day": "2026-12-05", "location": "remote"}).status_code == 422


def test_an_absence_wins_over_remote_work(seeded, db, client):
    uid = _uid(db, seeded["member"])
    lt = LeaveType(label="RTT", color="#7C3AED", display_order=1, is_active=True)
    db.add(lt)
    db.commit()
    db.add(Leave(user_id=uid, tribe_id=seeded["t1"], type_id=lt.id, status="approved",
                 start_date=date(2026, 12, 4),
                 end_date=date(2026, 12, 4)))
    db.commit()
    login(client, seeded["member"])
    client.put(f"/api/presence/week/{uid}", json={"weekdays": [4]})
    me = _person(client.get(f"/api/presence?{WEEK}").json(), uid)
    assert me["days"]["2026-12-04"] == "leave"
    assert me["leaves"]["2026-12-04"]["label"] == "RTT"


def test_who_may_set_the_remote_days_of_someone(seeded, db, client):
    uid = _uid(db, seeded["member"])
    db.add(Member(squad_id=seeded["squad_a"], full_name="Member", user_id=uid))
    db.commit()
    # Another squad's leader sees the person but cannot change their week.
    login(client, seeded["sl_b"])
    body = client.get(f"/api/presence?{WEEK}").json()
    assert _person(body, uid)["can_edit"] is False
    assert client.put(f"/api/presence/week/{uid}", json={"weekdays": [1]}).status_code == 403
    # Their own squad leader can, and the squad filter keeps only that squad.
    login(client, seeded["sl_a"])
    assert client.put(f"/api/presence/week/{uid}", json={"weekdays": [1]}).status_code == 200
    body = client.get(f"/api/presence?{WEEK}&squad_id={seeded['squad_a']}").json()
    assert [p["user_id"] for p in body["people"]] == [uid]
    assert _person(body, uid)["days"]["2026-12-01"] == "remote"
    # The other tribe does not see this tribe.
    login(client, seeded["tribe2"])
    body = client.get(f"/api/presence?{WEEK}").json()
    assert uid not in [p["user_id"] for p in body["people"]]
    assert client.put(f"/api/presence/day/{uid}", json={"day": "2026-12-01", "location": "onsite"}).status_code == 403


def test_period_is_bounded(seeded, client):
    login(client, seeded["member"])
    assert client.get("/api/presence?from=2026-01-01&to=2026-06-30").status_code == 422
    assert client.get("/api/presence?from=2026-02-01&to=2026-01-01").status_code == 422
