from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from ..database import get_db
from ..deps import get_current_user, record_audit, require_writer, visible_tribe_id
from ..generalconfig import get_general
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

router = APIRouter(prefix="/api/feed", tags=["feed"])

ADMIN_TRIBE = ("admin", "tribe_leader")


def _author(u: User | None) -> AuthorInfo:
    if u is None:
        return AuthorInfo()
    return AuthorInfo(id=u.id, display_name=u.display_name, role=u.role)


def _serialize(post: FeedPost, user: User, squad_names: dict[int, str]) -> FeedPostOut:
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
    )


@router.get("", response_model=list[FeedPostOut])
def list_feed(squad_id: int | None = Query(default=None), kind: str | None = Query(default=None),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(FeedPost)
    scope = visible_tribe_id(user)
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
    return [_serialize(p, user, squad_names) for p in posts]


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.post("", response_model=FeedPostOut, status_code=201)
def create_post(payload: FeedPostCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cfg = get_general(db)
    if cfg.get("feed_post_scope", "leaders") == "leaders" and user.role not in ("admin", "tribe_leader", "squad_leader"):
        raise HTTPException(status_code=403, detail="Seuls les responsables peuvent publier")
    squad = db.get(Squad, payload.squad_id) if payload.squad_id is not None else None
    if payload.squad_id is not None and squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    # tribe of the post: the author's tribe, or (for admin) the tagged squad's tribe, else global
    tribe_id = user.tribe_id or (squad.tribe_id if squad else None)
    post = FeedPost(tribe_id=tribe_id, author_user_id=user.id, content=payload.content,
                    kind=payload.kind, squad_id=payload.squad_id)
    db.add(post)
    db.flush()
    notify_new_post(db, post)
    record_audit(db, user.id, "feed.post", entity="feed_post", entity_id=post.id, detail={"kind": post.kind})
    db.commit()
    db.refresh(post)
    squad_names = {s.id: s.name for s in db.scalars(select(Squad)).all()}
    return _serialize(post, user, squad_names)


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    post = db.get(FeedPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Message introuvable")
    if post.author_user_id != user.id and user.role not in ADMIN_TRIBE:
        raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos messages")
    record_audit(db, user.id, "feed.delete", entity="feed_post", entity_id=post.id)
    db.delete(post)
    db.commit()


@router.put("/{post_id}/pin", response_model=FeedPostOut)
def pin_post(post_id: int, payload: PinIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    post = db.get(FeedPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Message introuvable")
    post.is_pinned = payload.is_pinned
    record_audit(db, user.id, "feed.pin", entity="feed_post", entity_id=post.id, detail={"pinned": payload.is_pinned})
    db.commit()
    db.refresh(post)
    squad_names = {s.id: s.name for s in db.scalars(select(Squad)).all()}
    return _serialize(post, user, squad_names)


@router.post("/{post_id}/replies", response_model=FeedPostOut, status_code=201)
def add_reply(post_id: int, payload: FeedReplyCreate, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    post = db.get(FeedPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Message introuvable")
    reply = FeedReply(post_id=post_id, author_user_id=user.id, content=payload.content)
    db.add(reply)
    db.flush()
    notify_reply(db, post, reply)
    record_audit(db, user.id, "feed.reply", entity="feed_post", entity_id=post_id)
    db.commit()
    db.refresh(post)
    squad_names = {s.id: s.name for s in db.scalars(select(Squad)).all()}
    return _serialize(post, user, squad_names)


@router.delete("/replies/{reply_id}", status_code=204)
def delete_reply(reply_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    reply = db.get(FeedReply, reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="Réponse introuvable")
    if reply.author_user_id != user.id and user.role not in ADMIN_TRIBE:
        raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos réponses")
    db.delete(reply)
    db.commit()


@router.post("/{post_id}/reactions", response_model=FeedPostOut)
def toggle_reaction(post_id: int, payload: ReactionIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    post = db.get(FeedPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Message introuvable")
    existing = db.scalar(select(FeedReaction).where(
        FeedReaction.post_id == post_id, FeedReaction.user_id == user.id, FeedReaction.kind == payload.kind))
    if existing:
        db.delete(existing)
    else:
        db.add(FeedReaction(post_id=post_id, user_id=user.id, kind=payload.kind))
    db.commit()
    db.refresh(post)
    squad_names = {s.id: s.name for s in db.scalars(select(Squad)).all()}
    return _serialize(post, user, squad_names)
