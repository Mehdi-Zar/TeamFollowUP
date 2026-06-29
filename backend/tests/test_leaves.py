"""Leave / absence management: type admin, per-tribe approval workflow,
tribe-scoped visibility, motif privacy, half-day counting and overlap alert."""
from sqlalchemy import select

from app.models import Leave, LeaveType, Member, User
from app.security import hash_password
from .conftest import login


def _seed_types(db):
    cp = LeaveType(label="Congés payés", color="#2563EB", display_order=1, is_active=True)
    rtt = LeaveType(label="RTT", color="#7C3AED", display_order=2, is_active=True)
    db.add_all([cp, rtt])
    db.commit()
    return cp.id, rtt.id


def _uid(db, email):
    return db.scalar(select(User).where(User.email == email)).id


def _link(db, email, squad_id):
    uid = _uid(db, email)
    db.add(Member(squad_id=squad_id, full_name=email, user_id=uid))
    db.commit()
    return uid


# ----- leave types -----------------------------------------------------------

def test_only_admin_manages_types(seeded, client):
    login(client, seeded["member"])
    assert client.post("/api/leaves/types", json={"label": "X"}).status_code == 403
    login(client, seeded["admin"])
    r = client.post("/api/leaves/types", json={"label": "Congé sans solde", "color": "#111111"})
    assert r.status_code == 201, r.text
    assert client.get("/api/leaves/types").json()[0]["label"] == "Congé sans solde"


# ----- approval workflow -----------------------------------------------------

def test_member_request_pending_then_leader_approves(seeded, db, client):
    cp, _ = _seed_types(db)
    _link(db, seeded["member"], seeded["squad_a"])  # member belongs to squad A (led by SL A)

    login(client, seeded["member"])
    r = client.post("/api/leaves", json={"type_id": cp, "start_date": "2026-07-06", "end_date": "2026-07-10"})
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    assert r.json()["status"] == "pending"

    # A squad leader of another squad cannot decide.
    login(client, seeded["sl_b"])
    assert client.post(f"/api/leaves/{lid}/decision", json={"action": "approve"}).status_code == 403

    # The member's own squad leader can.
    login(client, seeded["sl_a"])
    r = client.post(f"/api/leaves/{lid}/decision", json={"action": "approve"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["decided_by_name"] == "SL A"


def test_no_approval_when_tribe_disables_it(seeded, db, client):
    cp, _ = _seed_types(db)
    login(client, seeded["tribe"])
    r = client.put("/api/leaves/config", json={"require_approval": False})
    assert r.status_code == 200 and r.json()["require_approval"] is False

    login(client, seeded["member"])
    r = client.post("/api/leaves", json={"type_id": cp, "start_date": "2026-08-03", "end_date": "2026-08-03"})
    assert r.status_code == 201 and r.json()["status"] == "approved"


def test_member_cannot_file_for_someone_else(seeded, db, client):
    cp, _ = _seed_types(db)
    other = _uid(db, seeded["sl_a"])
    login(client, seeded["member"])
    r = client.post("/api/leaves", json={"type_id": cp, "user_id": other,
                                         "start_date": "2026-07-06", "end_date": "2026-07-06"})
    assert r.status_code == 403


# ----- visibility & motif privacy -------------------------------------------

def test_scope_and_comment_privacy(seeded, db, client):
    cp, _ = _seed_types(db)
    _link(db, seeded["member"], seeded["squad_a"])

    login(client, seeded["member"])
    r = client.post("/api/leaves", json={"type_id": cp, "start_date": "2026-07-06",
                                         "end_date": "2026-07-06", "comment": "RDV médical"})
    assert r.status_code == 201

    # Other tribe: not visible at all.
    login(client, seeded["tribe2"])
    assert client.get("/api/leaves").json() == []

    # Same tribe but not a manager of the person: sees the leave, not the motif.
    login(client, seeded["sl_b"])
    rows = client.get("/api/leaves").json()
    assert len(rows) == 1 and rows[0]["comment"] is None and rows[0]["can_decide"] is False

    # The managing squad leader sees the motif and can decide.
    login(client, seeded["sl_a"])
    rows = client.get("/api/leaves").json()
    assert rows[0]["comment"] == "RDV médical" and rows[0]["can_decide"] is True

    # The owner always sees their own motif.
    login(client, seeded["member"])
    assert client.get("/api/leaves?mine=true").json()[0]["comment"] == "RDV médical"


# ----- half-day counting -----------------------------------------------------

def test_half_day_counting(seeded, db, client):
    cp, _ = _seed_types(db)
    login(client, seeded["member"])
    half = client.post("/api/leaves", json={"type_id": cp, "start_date": "2026-07-06",
                                            "end_date": "2026-07-06", "start_half": True}).json()
    assert half["days"] == 0.5
    span = client.post("/api/leaves", json={"type_id": cp, "start_date": "2026-07-06",
                                            "end_date": "2026-07-08", "start_half": True,
                                            "end_half": True}).json()
    assert span["days"] == 2.0


def test_type_requiring_detail(seeded, db, client):
    other = LeaveType(label="Autre", color="#6B7280", display_order=9, is_active=True, requires_detail=True)
    db.add(other)
    db.commit()
    login(client, seeded["member"])
    # Missing the mandatory detail → rejected.
    r = client.post("/api/leaves", json={"type_id": other.id, "start_date": "2026-09-01", "end_date": "2026-09-01"})
    assert r.status_code == 422
    # With the detail → accepted and echoed back (public field).
    r = client.post("/api/leaves", json={"type_id": other.id, "start_date": "2026-09-01",
                                         "end_date": "2026-09-01", "detail": "Déménagement"})
    assert r.status_code == 201 and r.json()["detail"] == "Déménagement"
    assert r.json()["type_requires_detail"] is True


def test_end_before_start_rejected(seeded, db, client):
    cp, _ = _seed_types(db)
    login(client, seeded["member"])
    r = client.post("/api/leaves", json={"type_id": cp, "start_date": "2026-07-10", "end_date": "2026-07-01"})
    assert r.status_code == 422


# ----- overlap alert ---------------------------------------------------------

def test_overlap_alert(seeded, db, client):
    cp, _ = _seed_types(db)
    # Three people of squad A absent on the same day → reaches the default threshold (3).
    emails = [seeded["member"]]
    for i in range(2):
        u = User(email=f"m{i}@test", display_name=f"M{i}", role="member",
                 tribe_id=seeded["t1"], password_hash=hash_password("pw"))
        db.add(u)
        db.commit()
        emails.append(u.email)
    for e in emails:
        _link(db, e, seeded["squad_a"])

    login(client, seeded["admin"])
    for e in emails:
        uid = _uid(db, e)
        r = client.post("/api/leaves", json={"type_id": cp, "user_id": uid,
                                             "start_date": "2026-07-15", "end_date": "2026-07-15"})
        assert r.status_code == 201

    login(client, seeded["sl_a"])
    rows = client.get("/api/leaves/overlaps?from=2026-07-15&to=2026-07-15").json()
    assert len(rows) == 1 and rows[0]["count"] == 3 and rows[0]["squad_id"] == seeded["squad_a"]
