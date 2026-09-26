"""Per-request cache for the settings stored in ``app_settings``.

A single request used to read the same rows four or five times (general settings,
modules, threshold), once per dependency that needed them. The cache lives on the
Session (``db.info``), which is per request, and is dropped as soon as a setting
is written in that session, so a request that changes a setting reads the new one.
Callers get a deep copy: several of them adjust the dict they receive.
"""
import copy

from sqlalchemy import event
from sqlalchemy.orm import Session

_KEY = "_settings_cache"


def cached(db: Session, name: str, load):
    """``load(db)`` once per session for ``name``, then copies of that value."""
    store = db.info.setdefault(_KEY, {})
    if name not in store:
        store[name] = load(db)
    return copy.deepcopy(store[name])


def _after_flush(session: Session, flush_context) -> None:
    from .models import AppSetting
    if any(isinstance(o, AppSetting) for o in list(session.new) + list(session.dirty) + list(session.deleted)):
        session.info.pop(_KEY, None)


def install() -> None:
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)
