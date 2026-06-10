from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.status import freshness


def squad_with_last_submission(days_ago=None):
    snapshots = []
    if days_ago is not None:
        snapshots = [SimpleNamespace(submitted_at=datetime.now(timezone.utc) - timedelta(days=days_ago))]
    return SimpleNamespace(snapshots=snapshots)


def test_never_submitted_is_stale():
    f = freshness(squad_with_last_submission(None), threshold=7)
    assert f["is_stale"] is True
    assert f["never_submitted"] is True


def test_recent_is_fresh():
    f = freshness(squad_with_last_submission(days_ago=2), threshold=7)
    assert f["is_stale"] is False
    assert f["age_days"] == 2


def test_old_is_stale():
    f = freshness(squad_with_last_submission(days_ago=10), threshold=7)
    assert f["is_stale"] is True


def test_boundary_not_stale_at_threshold():
    assert freshness(squad_with_last_submission(days_ago=7), threshold=7)["is_stale"] is False


def test_threshold_configurable():
    s = squad_with_last_submission(days_ago=5)
    assert freshness(s, threshold=3)["is_stale"] is True
    assert freshness(s, threshold=10)["is_stale"] is False
