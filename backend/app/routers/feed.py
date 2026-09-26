"""Social feed endpoints (posts, replies, reactions, pins).

A lightweight internal timeline: leaders (configurable) publish posts scoped to a
tribe (or global), everyone in scope can read them, and - when the sub-modules are
enabled - reply, react and pin. Visibility follows the caller's tribe scope; new
posts and replies fan out in-app/e-mail notifications. The whole router is gated by
the `feed` module toggle and the `feed` persona capability.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from ..database import get_db
from ..deps import (get_current_user, record_audit, require_capability, require_module,
                    require_writer, visible_tribe_id)
from ..generalconfig import get_general
from ..modulesconfig import get_modules, is_active
from ..models import FeedPost, FeedReaction, FeedReply, Squad, User
from ..notify import notify_new_post, notify_reply
from ..schemas import (
    AuthorInfo,
    FeedPostCreate,
    FeedPostOut,
    FeedReplyCreate,
    FeedReplyOut,
    PinIn,
    ReactionIn,
)

router = APIRouter(prefix="/api/feed", tags=["feed"],
                   dependencies=[Depends(require_module("feed")),
                                 Depends(require_capability("feed"))])



def _author(u: User | None) -> AuthorInfo:
    """Public author card for a post/reply. Returns an empty card for a deleted or
    missing user so the timeline never leaks a null author."""
    if u is None:
        return AuthorInfo()
    return AuthorInfo(id=u.id, display_name=u.display_name, role=u.role)


def _serialize(post: FeedPost, user: User, squad_names: dict[int, str], db: Session | None = None) -> FeedPostOut:
    """Shape a FeedPost into its API form for the given viewer.

    Aggregates reaction counts by kind and marks which kinds the current user
    reacted with (my_reactions); replies are sorted oldest-first.
    """
    reactions = {"like": 0, "ack": 0}
    mine: list[str] = []
    for r in post.reactions:
        reactions[r.kind] = reactions.get(r.kind, 0) + 1
        if r.user_id == user.id:
            mine.append(r.kind)
    return FeedPostOut(
        id=post.id,
        content=post.content,
        kind=post.kind,
        squad_id=post.squad_id,
        squad_name=squad_names.get(post.squad_id) if post.squad_id else None,
        is_pinned=post.is_pinned,
        created_at=post.created_at,
        author=_author(post.author),
        replies=[
            FeedReplyOut(id=rp.id, content=rp.content, created_at=rp.created_at, author=_author(rp.author))
            for rp in sorted(post.replies, key=lambda x: x.created_at or x.id)
        ],
        reactions=reactions,
        my_reactions=mine,
        can_delete=post.author_user_id == user.id or _moderates(user, post, db),
        can_pin=user.role in ("admin", "tribe_leader", "squad_leader")
        and (post.tribe_id is not None or user.role == "admin"),
    )


def _visible_post(db: Session, user: User, post_id: int) -> FeedPost:
    """A post the caller can read (same rule as the list: own tribe + global), else
    404. Every action on a post goes through here: without it a post of another
    tribe could be deleted, pinned, replied to or reacted to by id."""
    post = db.get(FeedPost, post_id)
    scope = visible_tribe_id(user)
    if post is None or (scope is not None and post.tribe_id not in (scope, None)):
        raise HTTPException(status_code=404, detail="Message introuvable")
    return post


def _moderates(user: User, post: FeedPost, db: Session | None = None) -> bool:
    """An admin moderates every post, and so does whoever holds the Moderation tab
    (Admin > Personas) among the posts they can see; a tribe leader those of their
    own tribe only (a global post is the admin's)."""
    if user.role == "admin":
        return True
    if db is not None:
        from ..tabaccess import has_tab
        if has_tab(db, user, "moderation"):
            return True
    return user.role == "tribe_leader" and post.tribe_id is not None and post.tribe_id == user.tribe_id


@router.get("", response_model=list[FeedPostOut])
def list_feed(squad_id: int | None = Query(default=None), kind: str | None = Query(default=None),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """List feed posts visible to the caller, newest first (pinned on top).

    GET /api/feed?squad_id=...&kind=...
    Access: any authenticated user; results are limited to the caller's tribe scope
    (visible_tribe_id) plus global posts. Optional squad_id / kind filters.
    Business rule: the `feed_retention_days` general setting hides posts older than
    the cutoff (pinned posts are always kept). The `kind` filter is ignored when the
    `feed > kinds` feature is off: the switch has to mean the same thing to the API
    as it does to the screen, or turning it off only hides the selector.
    """
    if kind and not is_active(get_modules(db), "feed", "kinds"):
        kind = None
    q = select(FeedPost)
    scope = visible_tribe_id(user)
    # None scope = cross-tribe visibility (admin); otherwise own tribe + globals.
    if scope is not None:
        q = q.where(or_(FeedPost.tribe_id == scope, FeedPost.tribe_id.is_(None)))
    if squad_id is not None:
        q = q.where(FeedPost.squad_id == squad_id)
    if kind:
        q = q.where(FeedPost.kind == kind)
    posts = db.scalars(q.order_by(FeedPost.is_pinned.desc(), FeedPost.created_at.desc())).all()
    retention = get_general(db).get("feed_retention_days") or 0
    if retention > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
        posts = [p for p in posts if p.is_pinned or (p.created_at and _aware(p.created_at) >= cutoff)]
    squad_names = {s.id: s.name for s in db.scalars(select(Squad)).all()}
    return [_serialize(p, user, squad_names, db) for p in posts]


def _aware(dt):
    """Normalize a possibly-naive datetime to UTC-aware so retention comparisons
    against a timezone-aware cutoff never raise."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.post("", response_model=FeedPostOut, status_code=201)
def create_post(payload: FeedPostCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Publish a feed post.

    POST /api/feed
    Access: any authenticated user, but when the `feed_post_scope` setting is
    "leaders" (default) only admin/tribe/squad leaders may post.
    Business rule: the post's tribe is the author's tribe, or (for an admin tagging
    a squad) that squad's tribe, else global.
    Side effects: fans out new-post notifications; writes a "feed.post" audit entry.
    """
    cfg = get_general(db)
    # Optional restriction: when scope is "leaders", ordinary members can't post.
    if cfg.get("feed_post_scope", "leaders") == "leaders" and user.role not in ("admin", "tribe_leader", "squad_leader"):
        raise HTTPException(status_code=403, detail="Seuls les leaders peuvent publier")
    # Without a tribe, a post would be global (every tribe reads it): only an
    # admin speaks to everyone.
    if user.role != "admin" and user.tribe_id is None:
        raise HTTPException(status_code=403, detail="Rattachez-vous d'abord à une tribe pour publier")
    squad = db.get(Squad, payload.squad_id) if payload.squad_id is not None else None
    # A squad of another tribe is not taggable (the post would sit in the
    # author's tribe under a foreign squad's name). Admins tag any squad.
    if payload.squad_id is not None and (squad is None or (
            user.role != "admin" and squad.tribe_id != user.tribe_id)):
        raise HTTPException(status_code=404, detail="Squad introuvable")
    # tribe of the post: the author's tribe, or (for admin) the tagged squad's tribe, else global
    tribe_id = user.tribe_id or (squad.tribe_id if squad else None)
    # With `feed > kinds` off the SPA hides the selector and posts "info". Enforce
    # the same server-side rather than trusting the screen: the flag is an admin
    # decision about the data, not a cosmetic one, and its three siblings
    # (reactions, replies, pin) are all enforced on the route.
    kind = payload.kind if is_active(get_modules(db), "feed", "kinds") else "info"
    post = FeedPost(tribe_id=tribe_id, author_user_id=user.id, content=payload.content,
                    kind=kind, squad_id=payload.squad_id)
    db.add(post)
    db.flush()
    notify_new_post(db, post)
    record_audit(db, user.id, "feed.post", entity="feed_post", entity_id=post.id, detail={"kind": post.kind})
    db.commit()
    db.refresh(post)
    squad_names = {s.id: s.name for s in db.scalars(select(Squad)).all()}
    return _serialize(post, user, squad_names, db)


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Delete a feed post.

    DELETE /api/feed/{post_id} -> 204 No Content
    Access: the post's author, or a moderator of its tribe (_moderates).
    Side effects: writes a "feed.delete" audit entry.
    """
    post = _visible_post(db, user, post_id)
    # Only the author or a moderator of the post's tribe may remove it.
    if post.author_user_id != user.id and not _moderates(user, post, db):
        raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos messages")
    record_audit(db, user.id, "feed.delete", entity="feed_post", entity_id=post.id)
    db.delete(post)
    db.commit()


@router.put("/{post_id}/pin", response_model=FeedPostOut,
            dependencies=[Depends(require_module("feed", "pin"))])
def pin_post(post_id: int, payload: PinIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Pin or unpin a post (pinned posts sort to the top and bypass retention).

    PUT /api/feed/{post_id}/pin
    Access: writer role; additionally gated by the `feed > pin` sub-module.
    Side effects: writes a "feed.pin" audit entry.
    """
    # Pinning is the leaders' call: a contributor writes the reporting, not the feed's order.
    if user.role not in ("admin", "tribe_leader", "squad_leader"):
        raise HTTPException(status_code=403, detail="Épingler un message est réservé aux leaders")
    post = _visible_post(db, user, post_id)
    # A global post shows in every tribe: pinning it is an admin decision.
    if post.tribe_id is None and user.role != "admin":
        raise HTTPException(status_code=403, detail="Seul un administrateur épingle un message global")
    post.is_pinned = payload.is_pinned
    record_audit(db, user.id, "feed.pin", entity="feed_post", entity_id=post.id, detail={"pinned": payload.is_pinned})
    db.commit()
    db.refresh(post)
    squad_names = {s.id: s.name for s in db.scalars(select(Squad)).all()}
    return _serialize(post, user, squad_names, db)


@router.post("/{post_id}/replies", response_model=FeedPostOut, status_code=201,
             dependencies=[Depends(require_module("feed", "replies"))])
def add_reply(post_id: int, payload: FeedReplyCreate, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Reply to a post.

    POST /api/feed/{post_id}/replies
    Access: any authenticated user; gated by the `feed > replies` sub-module.
    Side effects: fans out reply notifications; writes a "feed.reply" audit entry.
    Returns the whole post (with the new reply) so the client can refresh in place.
    """
    post = _visible_post(db, user, post_id)
    reply = FeedReply(post_id=post_id, author_user_id=user.id, content=payload.content)
    db.add(reply)
    db.flush()
    notify_reply(db, post, reply)
    record_audit(db, user.id, "feed.reply", entity="feed_post", entity_id=post_id)
    db.commit()
    db.refresh(post)
    squad_names = {s.id: s.name for s in db.scalars(select(Squad)).all()}
    return _serialize(post, user, squad_names, db)


@router.delete("/replies/{reply_id}", status_code=204)
def delete_reply(reply_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Delete a reply.

    DELETE /api/feed/replies/{reply_id} -> 204 No Content
    Access: the reply's author, or a moderator of the post's tribe (_moderates).
    """
    reply = db.get(FeedReply, reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="Réponse introuvable")
    post = _visible_post(db, user, reply.post_id)
    if reply.author_user_id != user.id and not _moderates(user, post, db):
        raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos réponses")
    db.delete(reply)
    db.commit()


@router.post("/{post_id}/reactions", response_model=FeedPostOut,
             dependencies=[Depends(require_module("feed", "reactions"))])
def toggle_reaction(post_id: int, payload: ReactionIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Toggle the caller's reaction of a given kind on a post.

    POST /api/feed/{post_id}/reactions
    Access: any authenticated user; gated by the `feed > reactions` sub-module.
    Business rule: idempotent toggle - an existing reaction of the same kind is
    removed, otherwise it is added. Returns the refreshed post.
    """
    post = _visible_post(db, user, post_id)
    # Same (post, user, kind) already there → remove it; otherwise create it.
    existing = db.scalar(select(FeedReaction).where(
        FeedReaction.post_id == post_id, FeedReaction.user_id == user.id, FeedReaction.kind == payload.kind))
    if existing:
        db.delete(existing)
    else:
        db.add(FeedReaction(post_id=post_id, user_id=user.id, kind=payload.kind))
    db.commit()
    db.refresh(post)
    squad_names = {s.id: s.name for s in db.scalars(select(Squad)).all()}
    return _serialize(post, user, squad_names, db)
