"""Access history: the screen must show what was done, not only what is pending.

The history is read from the audit trail because that is the only place recording
*who decided*: once validated, an account looks like any other account.
"""
from app.models import User
from app.security import hash_password

from .conftest import login


def _sso_user(db, email="newcomer@test", status="pending"):
    u = User(email=email, display_name="Newcomer", role="member", status=status,
             auth_subject="sub-1", password_hash=hash_password("pw"))
    db.add(u)
    db.commit()
    return u


def test_history_records_an_approval_with_its_author(client, seeded, db):
    target = _sso_user(db)
    login(client, seeded["admin"])
    assert client.post(f"/api/access-requests/{target.id}/approve",
                       json={"role": "squad_leader", "tribe_id": seeded["t1"],
                             "squad_id": seeded["squad_a"]}).status_code == 200

    entries = client.get("/api/access-requests/history").json()["entries"]
    approvals = [e for e in entries if e["action"] == "access.approve"]
    assert len(approvals) == 1
    entry = approvals[0]
    assert entry["email"] == "newcomer@test"
    assert entry["role"] == "squad_leader"
    assert entry["actor"] == "Admin"          # who took the decision
    assert entry["squad"] == "Squad A"        # resolved to a name, not an id
    assert entry["tribe"] == "Tribe One"


def test_history_records_a_denial(client, seeded, db):
    target = _sso_user(db, email="rejected@test")
    login(client, seeded["admin"])
    assert client.post(f"/api/access-requests/{target.id}/deny").status_code == 200

    entries = client.get("/api/access-requests/history").json()["entries"]
    denials = [e for e in entries if e["action"] == "access.deny"]
    assert [e["email"] for e in denials] == ["rejected@test"]


def test_history_is_newest_first(client, seeded, db):
    first = _sso_user(db, email="one@test")
    second = _sso_user(db, email="two@test")
    login(client, seeded["admin"])
    client.post(f"/api/access-requests/{first.id}/deny")
    client.post(f"/api/access-requests/{second.id}/deny")

    entries = client.get("/api/access-requests/history").json()["entries"]
    emails = [e["email"] for e in entries if e["action"] == "access.deny"]
    assert emails == ["two@test", "one@test"]


def test_a_squad_leader_only_sees_their_own_decisions(client, seeded, db):
    """Scope follows the delegation model: gatekeepers see everything, a squad
    leader sees what they decided themselves."""
    theirs = _sso_user(db, email="theirs@test")
    others = _sso_user(db, email="others@test")

    login(client, seeded["sl_a"])
    assert client.post(f"/api/access-requests/{theirs.id}/approve",
                       json={"role": "member", "squad_id": seeded["squad_a"]}).status_code == 200
    login(client, seeded["admin"])
    client.post(f"/api/access-requests/{others.id}/deny")

    admin_emails = {e["email"] for e in client.get("/api/access-requests/history").json()["entries"]}
    assert {"theirs@test", "others@test"} <= admin_emails

    login(client, seeded["sl_a"])
    sl_emails = {e["email"] for e in client.get("/api/access-requests/history").json()["entries"]}
    assert "theirs@test" in sl_emails
    assert "others@test" not in sl_emails


def test_history_needs_reviewer_rights(client, seeded):
    login(client, seeded["member"])
    assert client.get("/api/access-requests/history").status_code == 403
