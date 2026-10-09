"""Carry-over of the OTDs not delivered at the end of their year.

On January 1st (the hourly scheduler runs it, and it does nothing the rest of the
year), every OTD of a past year that is neither delivered, nor cancelled, nor
declared by hand, gets a copy in the next year:

  * the copy keeps the title, the description, the scope, the squad and the
    owner, has no committed date yet (it has to be replanned) and points back to
    the original (``carried_from_id``);
  * the milestones of the original that are not done follow it: a milestone
    still in the old year is copied into Q1 of the new year (the original stays
    in the old roadmap, as it was on December 31st), a milestone that had already
    slipped to the new year moves its link to the copy;
  * the original stays in its year, with what was done, and reads "not
    delivered" from then on (``status.otd_state``);
  * the tribe leader (management OTD) or the squad's leaders (squad OTD) get an
    in-app notification.

The run is idempotent: an OTD already carried has a copy and is skipped. An OTD
created after the end of its year (entered afterwards, to be declared by hand)
is never carried.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import status as st
from .models import Notification, Otd, RoadmapDependency, RoadmapItem, Squad, User

# Year-bound links a copied milestone does not keep: they point to objects of
# the old year.
_NOT_COPIED = {"id", "year", "quarter", "done_at", "otd_id", "squad_otd_id", "objective_id",
               "initiative_id"}


def _copy_item(db: Session, item: RoadmapItem, year: int) -> RoadmapItem:
    """A copy of a milestone in Q1 of ``year``, with its dependencies."""
    cols = {c.key: getattr(item, c.key) for c in RoadmapItem.__table__.columns if c.key not in _NOT_COPIED}
    copy = RoadmapItem(**cols, year=year, quarter=1)
    db.add(copy)
    db.flush()
    for d in item.deps:
        db.add(RoadmapDependency(item_id=copy.id, position=d.position, kind=d.kind,
                                 squad_id=d.squad_id, tribe_id=d.tribe_id, text=d.text))
    return copy


def _recipients(db: Session, otd: Otd) -> set[int]:
    """Who is told: the squad's leaders for a squad OTD, the tribe leaders for a
    management one, and the owner in both cases."""
    ids = {otd.owner_user_id} if otd.owner_user_id else set()
    if otd.scope == "squad" and otd.squad_id:
        sq = db.get(Squad, otd.squad_id)
        if sq is not None and sq.leader_user_id:
            ids.add(sq.leader_user_id)
    else:
        ids.update(db.scalars(select(User.id).where(User.role == "tribe_leader",
                                                    User.tribe_id == otd.tribe_id)).all())
    return ids


def due(otd: Otd, now: datetime) -> bool:
    """Is this OTD to be carried over now?"""
    if otd.year >= now.year or otd.cancelled_at is not None or otd.declared_status or otd.carried_to:
        return False
    created = st._aware(otd.created_at)
    if created is not None and created >= datetime(otd.year + 1, 1, 1, tzinfo=timezone.utc):
        return False
    return st.otd_status(otd.members, otd.committed_date, now) not in ("delivered", "delivered_late")


def carry_over_otds(db: Session, now: datetime | None = None) -> int:
    """Carry over every OTD that is due. Returns how many were carried."""
    now = st._aware(now) or datetime.now(timezone.utc)
    rows = db.scalars(select(Otd).where(Otd.year < now.year, Otd.cancelled_at.is_(None),
                                        Otd.declared_status.is_(None))
                      .order_by(Otd.year, Otd.id)).all()
    copies: dict[int, RoadmapItem] = {}   # one copy per milestone, whatever OTDs it serves
    from .modulesconfig import get_modules, is_active
    inapp = is_active(get_modules(db), "notifications", "inapp")
    done = 0
    for otd in rows:
        if not due(otd, now):
            continue
        year = otd.year + 1
        new = Otd(tribe_id=otd.tribe_id, year=year, title=otd.title, description=otd.description,
                  budget_ref=otd.budget_ref, owner_user_id=otd.owner_user_id,
                  display_order=otd.display_order, scope=otd.scope, squad_id=otd.squad_id,
                  carried_from_id=otd.id, committed_date=None, initial_committed_date=None)
        db.add(new)
        db.flush()
        link = "squad_otd_id" if otd.scope == "squad" else "otd_id"
        for j in list(otd.members):
            if j.status == "done":
                continue
            if j.year >= year:
                setattr(j, link, new.id)
                continue
            if j.id not in copies:
                copies[j.id] = _copy_item(db, j, year)
            setattr(copies[j.id], link, new.id)
        if inapp:
            to = (f"/squads/{otd.squad_id}?year={year}" if otd.squad_id else "/")
            for uid in _recipients(db, otd):
                db.add(Notification(user_id=uid, kind="otd_carry", actor_name=str(otd.year),
                                    excerpt=otd.title[:300], link=to))
        db.expire(otd, ["carried_copies"])
        done += 1
    if done:
        db.commit()
    return done
