"""The link between a squad member (a line of the team) and a login account.

A member is the person in the org chart; a user is the account that logs in. The
link (``Member.user_id``) is what makes the person's leaves go to their squad
leader and the squad's reports reach them. Nothing used to set it: every member
added from a screen was a name with no account behind it.

The email is the key. A member added with an email is linked at once when an
account of the squad's tribe has that email, and otherwise as soon as one appears:
at login, at creation by an admin, at the validation of an access request.

A link never crosses a tribe. Being someone's member makes their squad leader the
manager of their leaves: tying an account of another tribe to one's own squad
would hand that over to anyone who knows an email address.
"""
from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Member, Squad, User

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")  # local domains (admin@local) are valid here


def normalize_email(value: str | None) -> str | None:
    """Lowercased, trimmed email, None when blank; 422 when it is not an email."""
    v = (value or "").strip().lower()
    if not v:
        return None
    if not _EMAIL_RE.match(v) or len(v) > 255:
        raise HTTPException(status_code=422, detail="Adresse email invalide")
    return v


def name_from_email(email: str) -> str:
    """A readable name from the local part: « jean.dupont » gives « Jean Dupont »."""
    local = email.split("@", 1)[0]
    parts = [p for p in re.split(r"[._\-+]+", local) if p]
    return " ".join(p.capitalize() for p in parts) or email


def account_for(db: Session, squad: Squad, email: str | None) -> User | None:
    """The account of the squad's tribe with this email, if any.

    An account of another tribe is not linked, and answered exactly like an
    unknown email: a distinct message told anyone which addresses have an
    account elsewhere (enumeration).
    """
    if not email:
        return None
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        return None
    if user.tribe_id is not None and user.tribe_id != squad.tribe_id:
        return None
    # An account without a tribe yet (pending) is linked when it gets one.
    return user if user.tribe_id == squad.tribe_id else None


def link_members_to(db: Session, user: User) -> int:
    """Link the not yet linked members carrying this account's email, in its tribe,
    and drop the links left in another tribe (the account moved).

    Called whenever an account appears or changes tribe: login, creation or edit by
    an admin, validation of an access request. Does not commit.
    """
    if not user.email or user.tribe_id is None or user.id is None:
        return 0
    for m in db.scalars(
        select(Member).join(Squad, Squad.id == Member.squad_id)
        .where(Member.user_id == user.id, Squad.tribe_id != user.tribe_id)
    ).all():
        m.user_id = None
    rows = db.scalars(
        select(Member).join(Squad, Squad.id == Member.squad_id)
        .where(Member.user_id.is_(None), Member.email == user.email.lower(),
               Squad.tribe_id == user.tribe_id)
    ).all()
    for m in rows:
        m.user_id = user.id
    return len(rows)
