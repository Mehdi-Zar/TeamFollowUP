"""Data retention: what actually gets deleted, and what must not be.

The feed half of this exists because the setting used to lie. "Message retention
(days)" hid old posts from one endpoint and kept them in the database and in
every backup, so an administrator who set it to satisfy a policy had satisfied
nothing. These tests are what keeps the promise real.
"""
from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.generalconfig import get_general, set_general
from app.maintenance import purge_old_records
from app.models import AuditLog, FeedPost, FeedReaction, FeedReply, User, utcnow


def _post(db, days_old: int, pinned: bool = False, author: User | None = None) -> FeedPost:
    p = FeedPost(content=f"post from {days_old} days ago", kind="info",
                 is_pinned=pinned, created_at=utcnow() - timedelta(days=days_old),
                 author_user_id=author.id if author else None)
    db.add(p)
    db.flush()
    return p


# ---- audit -------------------------------------------------------------------

def test_audit_retention_is_opt_in(db, monkeypatch):
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    db.add(AuditLog(action="old.thing", timestamp=utcnow() - timedelta(days=3650)))
    db.commit()
    assert purge_old_records(db) == {}
    assert db.scalar(select(AuditLog).where(AuditLog.action == "old.thing")) is not None


def test_audit_entries_past_the_window_are_deleted(db, monkeypatch):
    monkeypatch.setattr(settings, "audit_retention_days", 30)
    db.add(AuditLog(action="ancient", timestamp=utcnow() - timedelta(days=90)))
    db.add(AuditLog(action="recent", timestamp=utcnow() - timedelta(days=5)))
    db.commit()

    out = purge_old_records(db)
    assert out["audit"] == 1
    assert db.scalar(select(AuditLog).where(AuditLog.action == "ancient")) is None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "recent")) is not None


# ---- feed --------------------------------------------------------------------

def test_feed_retention_is_opt_in(db, monkeypatch):
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    set_general(db, {"feed_retention_days": 0})
    db.commit()   # the router owns the transaction; mirror it
    _post(db, days_old=400)
    db.commit()

    purge_old_records(db)
    assert len(db.scalars(select(FeedPost)).all()) == 1


def test_feed_posts_past_the_window_are_really_deleted(db, monkeypatch):
    """Not hidden. Deleted. That is the whole point of the change."""
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    set_general(db, {"feed_retention_days": 30})
    db.commit()   # the router owns the transaction; mirror it
    old = _post(db, days_old=90)
    fresh = _post(db, days_old=2)
    db.commit()

    out = purge_old_records(db)
    assert out["feed"] == 1
    assert db.get(FeedPost, old.id) is None
    assert db.get(FeedPost, fresh.id) is not None


def test_pinned_posts_survive_retention(db, monkeypatch):
    """Pinning is somebody deciding this one stays; the listing agrees."""
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    set_general(db, {"feed_retention_days": 30})
    db.commit()   # the router owns the transaction; mirror it
    pinned = _post(db, days_old=900, pinned=True)
    db.commit()

    purge_old_records(db)
    assert db.get(FeedPost, pinned.id) is not None


def test_deleting_a_post_takes_its_replies_and_reactions(db, seeded, monkeypatch):
    """The foreign keys have no ON DELETE CASCADE, so this has to go through the ORM."""
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    set_general(db, {"feed_retention_days": 30})
    db.commit()   # the router owns the transaction; mirror it
    user = db.scalar(select(User).where(User.email == seeded["admin"]))
    post = _post(db, days_old=90, author=user)
    db.add(FeedReply(post_id=post.id, author_user_id=user.id, content="a reply"))
    db.add(FeedReaction(post_id=post.id, user_id=user.id, kind="like"))
    db.commit()

    purge_old_records(db)

    assert db.get(FeedPost, post.id) is None
    assert db.scalars(select(FeedReply).where(FeedReply.post_id == post.id)).all() == []
    assert db.scalars(select(FeedReaction).where(FeedReaction.post_id == post.id)).all() == []


def test_the_setting_read_by_the_purge_is_the_one_the_admin_screen_writes(db, monkeypatch):
    """A retention setting nothing enforces is worse than no setting at all."""
    monkeypatch.setattr(settings, "audit_retention_days", 0)
    set_general(db, {"feed_retention_days": 7})
    db.commit()   # the router owns the transaction; mirror it
    assert get_general(db)["feed_retention_days"] == 7

    _post(db, days_old=10)
    db.commit()
    assert purge_old_records(db)["feed"] == 1


def test_purge_commits_nothing_when_there_is_nothing_to_delete(db, monkeypatch):
    monkeypatch.setattr(settings, "audit_retention_days", 30)
    set_general(db, {"feed_retention_days": 30})
    db.commit()   # the router owns the transaction; mirror it
    _post(db, days_old=1)
    db.commit()

    out = purge_old_records(db)
    assert out == {"audit": 0, "feed": 0}
    assert len(db.scalars(select(FeedPost)).all()) == 1
