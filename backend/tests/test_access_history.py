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


def test_a_gatekeeper_sees_every_decision(client, seeded, db):
    """Les deux gardiens lisent la meme histoire.

    L'historique repond a « qui a decide quoi, et quand »: la partager en deux
    selon qui regarde donnerait deux recits d'un meme evenement, et l'arrivee SSO
    qui n'a encore ni tribu ni decision disparaitrait de l'un des deux.
    """
    theirs = _sso_user(db, email="theirs@test")
    others = _sso_user(db, email="others@test")

    login(client, seeded["tribe"])
    assert client.post(f"/api/access-requests/{theirs.id}/approve",
                       json={"role": "member", "squad_id": seeded["squad_a"]}).status_code == 200
    login(client, seeded["admin"])
    client.post(f"/api/access-requests/{others.id}/deny")

    for who in (seeded["admin"], seeded["tribe"]):
        login(client, who)
        seen = {e["email"] for e in client.get("/api/access-requests/history").json()["entries"]}
        assert {"theirs@test", "others@test"} <= seen


def test_a_squad_leader_does_not_read_the_history(client, seeded, db):
    login(client, seeded["sl_a"])
    assert client.get("/api/access-requests/history").status_code == 403


def test_history_needs_reviewer_rights(client, seeded):
    login(client, seeded["member"])
    assert client.get("/api/access-requests/history").status_code == 403
