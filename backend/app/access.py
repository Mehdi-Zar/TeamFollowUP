"""SSO access-approval workflow.

SSO authenticates *who* a user is; this module governs *whether* they may enter.
New SSO accounts are provisioned "pending" and must be validated by a manager:

  - admin        : validate anyone, any role / tribe (full rights);
  - tribe_leader : validate into their own tribe as squad_leader / member;
  - squad_leader : validate a person into one of their own squads (as member).

Denial disables the account (kept for audit). Visibility of the pending queue is
intentionally broad (a brand-new account has no tribe yet), but the *action* is
strictly scoped to what the approver may grant.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .deps import record_audit
from .models import Notification, Squad, User
from .rbac import ADMIN, MEMBER, SQUAD, TRIBE


def can_review_access(user: User) -> bool:
    """Qui peut ouvrir la file des demandes d'acces.

    Les memes que ceux qui peuvent revoquer: accorder l'entree dans l'application
    n'est pas la meme decision que composer une equipe, et une file ou l'on ne
    peut qu'ajouter est une demi-delegation qui vieillit mal.
    """
    return user.role in (ADMIN, TRIBE)


def approval_roles(actor: User) -> list[str]:
    """Roles an approver may grant when validating a pending account."""
    if actor.role == ADMIN:
        return [ADMIN, TRIBE, SQUAD, "contributor", MEMBER]
    if actor.role == TRIBE:
        return [SQUAD, "contributor", MEMBER]
    return []


def pending_users(db: Session) -> list[User]:
    """All accounts awaiting validation (oldest first)."""
    return list(db.scalars(
        select(User).where(User.status == "pending").order_by(User.created_at.asc())
    ).all())


def pending_count(db: Session, reviewer: User) -> int:
    """Badge count of pending requests, or 0 for a viewer who can't review any.

    Returns the global pending total (the queue is intentionally broad,
    a brand-new account has no tribe yet), but only to actual reviewers so a plain
    member never sees a nonzero badge.
    """
    if not can_review_access(reviewer):
        return 0
    return int(db.scalar(select(func.count()).select_from(User).where(User.status == "pending")) or 0)


#: Audit actions that make up the access story: an account appearing through SSO,
#: then the decision taken on it. Ordered newest first when read back.
HISTORY_ACTIONS = ("access.approve", "access.deny",
                   "user.provisioned.oidc", "user.provisioned.saml")


def decision_history(db: Session, actor: User, limit: int = 60) -> list[dict]:
    """What has already been done on access requests, newest first.

    Reads the audit trail rather than the users table, because the question is
    "who decided what, and when", which only the trail answers: a validated
    account looks like any other account afterwards.

    Seuls les gardiens (admin, tribe leader) arrivent ici, et ils voient tout, y
    compris les arrivees SSO qui n'ont encore ni tribu ni decision: ce sont
    justement celles qui attendent qu'on s'en occupe.
    """
    from .models import AuditLog

    stmt = select(AuditLog).where(AuditLog.action.in_(HISTORY_ACTIONS))
    rows = list(db.scalars(stmt.order_by(AuditLog.timestamp.desc()).limit(limit * 4 if actor.role != ADMIN else limit)).all())
    if actor.role != ADMIN:
        # A tribe leader: the decisions on accounts of their tribe, and those on
        # accounts that have no tribe yet (the arrivals waiting for someone).
        ids = {r.entity_id for r in rows if r.entity_id}
        tribe_of = {u.id: u.tribe_id for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
        rows = [r for r in rows
                if (r.detail or {}).get("tribe_id") in (None, actor.tribe_id)
                and tribe_of.get(r.entity_id) in (None, actor.tribe_id)][:limit]

    # Resolve the names in one pass rather than per row.
    actor_ids = {r.user_id for r in rows if r.user_id}
    actors = {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(actor_ids)))} if actor_ids else {}
    squads = {s.id: s.name for s in db.scalars(select(Squad))}
    from .models import Tribe
    tribes = {t.id: t.name for t in db.scalars(select(Tribe))}

    out = []
    for r in rows:
        detail = r.detail or {}
        out.append({
            "id": r.id,
            "action": r.action,
            "at": r.timestamp,
            "actor": actors.get(r.user_id) if r.user_id else None,
            "email": detail.get("email"),
            "role": detail.get("role"),
            "tribe": tribes.get(detail.get("tribe_id")),
            "squad": squads.get(detail.get("squad_id")),
            "status": detail.get("status"),
        })
    return out


def led_squads(db: Session, actor: User) -> list[Squad]:
    """Squads an actor may validate someone into."""
    if actor.role == ADMIN:
        return list(db.scalars(select(Squad).order_by(Squad.display_order, Squad.id)).all())
    if actor.role == TRIBE:
        return list(db.scalars(select(Squad).where(Squad.tribe_id == actor.tribe_id)
                               .order_by(Squad.display_order, Squad.id)).all())
    if actor.role == SQUAD:
        from .deps import led_squad_ids
        return list(db.scalars(select(Squad).where(Squad.id.in_(led_squad_ids(db, actor)))
                               .order_by(Squad.display_order, Squad.id)).all())
    return []


def approve(db: Session, actor: User, target: User, *, role: str,
            tribe_id: int | None, squad_id: int | None) -> User:
    """Validate a pending account, or reinstate a disabled one: set role + tribe
    scope and activate it.

    Un compte desactive est accepte ici parce que le retablir est exactement la
    meme operation qu'une validation, avec les memes limites de delegation:
    choisir un role, une tribu, une squad, activer. Le refuser aurait fait d'une
    revocation une decision definitive, ce qui n'est jamais ce qu'on veut d'un
    droit d'acces.

    Raises 4xx HTTPException when the actor exceeds their delegation scope.
    """
    if target.status == "active":
        raise HTTPException(status_code=409, detail="Ce compte est déjà actif.")
    if target.status not in ("pending", "disabled"):
        raise HTTPException(status_code=409, detail="Cette demande a déjà été traitée.")
    was = target.status
    if role not in approval_roles(actor):
        raise HTTPException(status_code=403, detail="Vous ne pouvez pas attribuer ce rôle.")
    # Reinstating is the mirror of revoking (see deny): a non-admin only brings
    # back an account of their own tribe, and never an administrator. Otherwise a
    # tribe leader could pull another tribe's revoked account, or a former admin,
    # into their tribe.
    if actor.role != ADMIN and target.tribe_id is not None and target.tribe_id != actor.tribe_id:
        raise HTTPException(status_code=403, detail="Ce compte n'est pas dans votre tribe.")
    if was == "disabled" and actor.role != ADMIN:
        if target.role == ADMIN:
            raise HTTPException(status_code=403, detail="Seul un administrateur rétablit un administrateur.")
        if target.tribe_id != actor.tribe_id:
            raise HTTPException(status_code=403, detail="Ce compte n'est pas dans votre tribe.")

    if actor.role == ADMIN:
        if tribe_id is not None:
            from .models import Tribe
            if db.get(Tribe, tribe_id) is None:
                raise HTTPException(status_code=404, detail="Tribe introuvable")
        scope_tribe = tribe_id
        if squad_id is not None:
            sq = db.get(Squad, squad_id)
            if sq is None:
                raise HTTPException(status_code=404, detail="Squad introuvable")
            scope_tribe = sq.tribe_id
    elif actor.role == TRIBE:
        scope_tribe = actor.tribe_id
        if squad_id is not None:
            sq = db.get(Squad, squad_id)
            if sq is None or sq.tribe_id != actor.tribe_id:
                raise HTTPException(status_code=403, detail="Cette squad n'est pas dans votre tribe.")
    else:  # SQUAD leader: must place the person into one of their own squads.
        if squad_id is None:
            raise HTTPException(status_code=400, detail="Choisissez la squad d'accueil.")
        from .deps import leads_this_squad
        sq = db.get(Squad, squad_id)
        if sq is None or not leads_this_squad(sq, actor):
            raise HTTPException(status_code=403, detail="Vous ne pouvez valider que pour vos squads.")
        scope_tribe = sq.tribe_id

    target.status = "active"
    target.role = role
    target.tribe_id = scope_tribe
    from .memberlink import link_members_to
    link_members_to(db, target)  # members added with this email while it waited
    record_audit(db, actor.id, "access.approve", entity="user", entity_id=target.id,
                 detail={"email": target.email, "role": role, "tribe_id": scope_tribe,
                         "squad_id": squad_id, "from": was})
    _notify_user_granted(db, target, actor)
    return target


def deny(db: Session, actor: User, target: User) -> User:
    """Reject a request, or revoke an account already granted. Reserved to admin &
    tribe leaders (gatekeepers).

    Le compte de secours est intouchable ici: c'est la porte qui reste ouverte
    quand toutes les autres se sont refermees, y compris sur celui qui appuie.
    Se revoquer soi-meme l'est aussi, pour la meme raison.
    """
    if actor.role not in (ADMIN, TRIBE):
        raise HTTPException(status_code=403, detail="Seuls un admin ou un tribe leader peuvent refuser un accès.")
    if target.is_break_glass:
        raise HTTPException(status_code=403, detail="Le compte de secours ne peut pas être désactivé.")
    if target.id == actor.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas révoquer votre propre accès.")
    if actor.role == TRIBE:
        if target.role == ADMIN:
            raise HTTPException(status_code=403, detail="Un tribe leader ne révoque pas un administrateur.")
        # A request already attached to another tribe is that tribe's to decide.
        if target.tribe_id is not None and target.tribe_id != actor.tribe_id:
            raise HTTPException(status_code=403, detail="Ce compte n'est pas dans votre tribe.")
        if target.status != "pending" and target.tribe_id != actor.tribe_id:
            raise HTTPException(status_code=403, detail="Ce compte n'est pas dans votre tribe.")
    if _would_leave_no_gatekeeper(db, target):
        raise HTTPException(status_code=400,
                            detail="Il doit rester au moins un administrateur actif.")
    was_pending = target.status == "pending"
    target.status = "disabled"
    record_audit(db, actor.id, "access.deny", entity="user", entity_id=target.id,
                 detail={"email": target.email})
    if was_pending:
        # A refused request is answered: otherwise the person waits for nothing.
        _email_account(db, target, granted=False)
    return target


def _would_leave_no_gatekeeper(db: Session, target: User) -> bool:
    """Revoquer ce compte laisserait-il l'application sans administrateur actif ?

    Le compte de secours compte comme les autres: c'est un administrateur actif,
    et c'est le filet prevu pour ce cas. L'exclure du decompte aurait interdit de
    revoquer un administrateur compromis dans une installation qui n'en a qu'un,
    ce qui est exactement la situation ou il faut pouvoir le faire.
    """
    if target.role != ADMIN or target.status != "active":
        return False
    others = db.scalar(select(func.count()).select_from(User).where(
        User.role == ADMIN, User.status == "active", User.id != target.id))
    return not int(others or 0)


def managed_accounts(db: Session, actor: User) -> list[dict]:
    """Les comptes deja decides que ce relecteur peut reprendre en main.

    La file d'attente ne repond qu'a « que reste-t-il a faire ». Celle-ci repond a
    « qui a acces », qui est la question qu'on se pose le lendemain. Seuls les
    gardiens (admin, tribe leader) la voient, parce qu'eux seuls peuvent revoquer.
    Le compte de secours n'y figure pas: il ne se gere pas depuis un ecran.
    """
    if actor.role not in (ADMIN, TRIBE):
        return []
    stmt = select(User).where(User.status != "pending", User.is_break_glass.is_(False))
    if actor.role == TRIBE:
        stmt = stmt.where(User.tribe_id == actor.tribe_id)
    rows = list(db.scalars(stmt.order_by(User.display_name, User.id)).all())
    from .models import Tribe
    tribes = {t.id: t.name for t in db.scalars(select(Tribe))}
    return [{
        "id": u.id, "email": u.email, "display_name": u.display_name,
        "role": u.role, "status": u.status, "tribe_id": u.tribe_id,
        "tribe": tribes.get(u.tribe_id), "last_login_at": u.last_login_at,
        "is_self": u.id == actor.id,
    } for u in rows]


# ----- notifications ----------------------------------------------------------

def _reviewers(db: Session, requester: User | None = None) -> list[User]:
    """Accounts that should hear about a new access request: active admins and
    tribe leaders (the gatekeepers). When the request already carries a tribe,
    only that tribe's leaders (the others cannot place the person anyway)."""
    q = select(User).where(User.status == "active", User.role.in_([ADMIN, TRIBE]))
    rows = list(db.scalars(q).all())
    tid = getattr(requester, "tribe_id", None)
    if tid is not None:
        rows = [u for u in rows if u.role == ADMIN or u.tribe_id == tid]
    return rows


def notify_access_request(db: Session, requester: User) -> None:
    """Ping the gatekeepers (in-app, best-effort email) about a pending request.
    Never let a notification failure break the login/provisioning path."""
    try:
        for r in _reviewers(db, requester):
            db.add(Notification(user_id=r.id, kind="access_request", actor_name=requester.display_name,
                                excerpt=f"Demande d'accès : {requester.email}", link="/acces"))
        db.flush()
        _email_reviewers(db, requester)
    except Exception:
        pass


def _notify_user_granted(db: Session, target: User, actor: User) -> None:
    """In-app "welcome, your access is validated" notice for the approved user.
    Best-effort: never let a notification failure roll back the approval."""
    try:
        db.add(Notification(user_id=target.id, kind="access_granted", actor_name=actor.display_name,
                            excerpt="Votre accès a été validé. Bienvenue !", link="/"))
    except Exception:
        pass
    # By mail too: the in-app notice is only seen once signed in, which the
    # person had no reason to try again.
    _email_account(db, target, granted=True)


def _email_account(db: Session, target: User, granted: bool) -> None:
    """Tell the person their access request was granted or refused. Best-effort."""
    try:
        from .smtpconfig import get_smtp
        from .mail import send_email
        from .mailbody import app_link, instance_lang, simple_mail
        cfg = get_smtp(db)
        if not cfg.get("enabled") or not target.email:
            return
        lang = instance_lang(db)
        name = cfg.get("from_name") or "TeamFollowUP"
        if granted:
            subject = f"[{name}] " + ("Your access is granted" if lang == "en" else "Votre accès est validé")
            lines = (["Your access has been granted. Welcome!", "Sign in with your company account."]
                     if lang == "en" else
                     ["Votre accès a été validé. Bienvenue !", "Connectez-vous avec le compte de votre entreprise."])
            link = app_link(db, "/")
        else:
            subject = f"[{name}] " + ("Your access request" if lang == "en" else "Votre demande d'accès")
            lines = (["Your access request was not granted.",
                      "If you think this is a mistake, contact your tribe leader."]
                     if lang == "en" else
                     ["Votre demande d'accès n'a pas été acceptée.",
                      "Si vous pensez qu'il s'agit d'une erreur, contactez votre tribe leader."])
            link = None
        body = simple_mail(subject, lines, lang=lang, why="account", link=link)
        send_email(cfg, target.email, subject, body, html=True, lang=lang)
    except Exception:
        pass


def _email_reviewers(db: Session, requester: User) -> None:
    """Best-effort email to gatekeepers when SMTP is configured."""
    try:
        from .smtpconfig import get_smtp
        from .mail import send_email
        cfg = get_smtp(db)
        if not cfg.get("enabled"):
            return
        from html import escape
        from .mailbody import app_link, instance_lang, simple_mail
        lang = instance_lang(db)
        name = cfg.get("from_name") or "TeamFollowUP"
        who = escape(f"{requester.display_name} ({requester.email})")
        if lang == "en":
            subject = f"[{name}] Access request: {requester.email}"
            lines = [f"<strong>{who}</strong> signed in with SSO and is waiting for access.",
                     "Grant or refuse it in the app, Access menu."]
            label = "Review the request"
        else:
            subject = f"[{name}] Demande d'accès : {requester.email}"
            lines = [f"<strong>{who}</strong> s'est connecté par SSO et attend la validation de son accès.",
                     "Validez ou refusez dans l'application, menu Accès."]
            label = "Examiner la demande"
        body = simple_mail(subject, lines, lang=lang, why="access", link=app_link(db, "/acces"),
                           link_label=label)
        for r in _reviewers(db, requester):
            if r.email:
                send_email(cfg, r.email, subject, body, html=True, lang=lang)
    except Exception:
        pass
