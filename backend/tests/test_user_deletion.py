"""Deleting a user must do what the documentation says it does.

It did not. `DELETE /api/admin/users/{id}` returned **500** for any account that
had ever logged in or done anything, because nineteen tables reference `users`
with `NO ACTION` and the endpoint detached none of them before deleting. The
first audit row the person ever produced was enough.

Nothing caught it. The suite ran on a SQLite that does not enforce foreign keys
unless asked (now it does, see `conftest`), and production runs PostgreSQL, which
does. So the endpoint 500ed in the real product while 402 tests passed.

The policy is not a design question here: it is written down in three places and
this endpoint was the only one not applying it.

  * ``models.AuditLog``: "``user_id`` stays nullable so the trail survives
    deletion of the acting user";
  * ``docs/20`` section 5, which lists what is erased without discussion
    (personal rows: leaves, feed posts, replies, reactions), says the audit trail
    is **anonymised and not erased**, and states that the account itself should be
    removed through Administration because it "handles the detachments";
  * ``scripts/prune_users.py``, which nullifies the audit rows and the squad
    leadership before deleting, exactly as intended.

These tests pin both halves of that policy: what must survive the deletion, and
what must go with it.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog, FeedPost, Notification, Squad, User
from tests.conftest import login


def _member(client, seeded, email="tobedeleted@test"):
    """Create a member through the API, the way an administrator would."""
    login(client, seeded["admin"])
    r = client.post("/api/admin/users", json={
        "email": email, "display_name": "To Be Deleted", "role": "member",
        "tribe_id": seeded["t1"], "password": "pw",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_a_user_who_has_acted_can_still_be_deleted(client, seeded, db):
    """The regression itself: one audit row used to make an account undeletable."""
    uid = _member(client, seeded)

    # Anything at all produces an audit row for them. Logging in is the cheapest.
    login(client, "tobedeleted@test")
    assert client.get("/api/dashboard").status_code == 200
    login(client, seeded["admin"])
    assert db.scalars(select(AuditLog).where(AuditLog.user_id == uid)).first() is not None

    r = client.delete(f"/api/admin/users/{uid}")
    assert r.status_code == 204, r.text
    assert db.get(User, uid) is None


def test_the_audit_trail_survives_the_deletion_but_loses_the_name(client, seeded, db):
    """Anonymised, not erased: destroying it would destroy the evidence that the
    action happened, which is the one thing an audit log is for."""
    uid = _member(client, seeded)
    login(client, "tobedeleted@test")
    client.get("/api/dashboard")
    login(client, seeded["admin"])
    before = len(db.scalars(select(AuditLog)).all())

    assert client.delete(f"/api/admin/users/{uid}").status_code == 204
    db.expire_all()

    rows = db.scalars(select(AuditLog)).all()
    assert len(rows) >= before, "audit rows were destroyed instead of detached"
    assert db.scalars(select(AuditLog).where(AuditLog.user_id == uid)).first() is None
    # And the deletion is itself recorded, by the administrator who did it.
    assert any(r.action == "user.delete" for r in rows)


def test_a_squad_the_person_led_survives_without_a_leader(client, seeded, db):
    """`prune_users.py` already did this. The endpoint did not, and a squad is
    somebody else's work: it cannot disappear with its leader."""
    uid = _member(client, seeded)
    squad = db.get(Squad, seeded["squad_a"])
    squad.leader_user_id = uid
    db.commit()

    login(client, seeded["admin"])
    assert client.delete(f"/api/admin/users/{uid}").status_code == 204

    db.expire_all()
    kept = db.get(Squad, seeded["squad_a"])
    assert kept is not None, "the squad was deleted with its leader"
    assert kept.leader_user_id is None


def test_their_own_personal_rows_go_with_them(client, seeded, db):
    """docs/20: personal records have no value beyond the person. They are also
    NOT NULL references, so leaving them would block the deletion outright."""
    uid = _member(client, seeded)
    login(client, "tobedeleted@test")
    posted = client.post("/api/feed", json={"content": "mine", "kind": "info"})
    assert posted.status_code in (201, 403), posted.text   # 403 if posting is leaders-only
    db.add(Notification(user_id=uid, kind="tweet", actor_name="Someone", excerpt="hello"))
    db.commit()

    login(client, seeded["admin"])
    assert client.delete(f"/api/admin/users/{uid}").status_code == 204

    db.expire_all()
    assert db.scalars(select(Notification).where(Notification.user_id == uid)).first() is None
    assert db.scalars(select(FeedPost).where(FeedPost.author_user_id == uid)).first() is None
