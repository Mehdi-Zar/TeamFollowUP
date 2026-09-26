"""Squad member CRUD endpoints.

Manages the roster of people (Member rows) attached to a squad. Writes require the
"writer" role plus edit rights on the target squad. Reads of members happen through
the squad endpoints, not here. A member is tied to a login account by its email
(see memberlink).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_can_edit_squad, record_audit, require_writer, update_data
from ..memberlink import account_for, name_from_email, normalize_email
from ..models import Member, Squad, User
from ..changenotify import notify_change
from ..schemas import MemberCreate, MemberOut, MemberUpdate

router = APIRouter(prefix="/api/members", tags=["members"])


def _check_manager(db: Session, squad_id: int, manager_id: int | None, member_id: int | None = None) -> None:
    """A member reports to someone of the same squad, and the chain never loops.

    Without this, a manager_id from another squad (or an unknown id) was accepted
    and only failed later, as a 500 on the foreign key or a broken org chart.
    """
    if manager_id is None:
        return
    seen = {member_id} if member_id is not None else set()
    current = db.get(Member, manager_id)
    if current is None or current.squad_id != squad_id:
        raise HTTPException(status_code=422, detail="Le manager doit être un membre de la même squad")
    while current is not None:
        if current.id in seen:
            raise HTTPException(status_code=422, detail="Ce rattachement créerait une boucle")
        seen.add(current.id)
        current = db.get(Member, current.manager_id) if current.manager_id is not None else None


def _resolve_account(db: Session, squad: Squad, email: str | None, user_id: int | None) -> tuple[str | None, User | None]:
    """(email, account) for a member: an explicit account must be of the squad's
    tribe and gives its email; otherwise the email finds the account, if any."""
    if user_id is not None:
        acc = db.get(User, user_id)
        if acc is None or acc.tribe_id != squad.tribe_id:
            raise HTTPException(status_code=400, detail="Compte introuvable dans cette tribe")
        return acc.email.lower(), acc
    return email, account_for(db, squad, email)


def _assert_may_enrol(db: Session, actor: User, squad: Squad, account: User | None) -> None:
    """Putting an account in a squad hands its leaders that person's absences
    (approve, refuse, read the reasons). A squad leader may do it for people of
    the tribe, not for an admin, a tribe leader or the leader of another squad:
    that is the tribe leader's (or the admin's) call."""
    if account is None or actor.role in ("admin", "tribe_leader"):
        return
    leads_other = db.scalar(select(Squad.id).where(Squad.leader_user_id == account.id,
                                                   Squad.id != squad.id)) is not None
    if account.role in ("admin", "tribe_leader") or leads_other:
        raise HTTPException(status_code=403,
                            detail="Seul le tribe leader peut ajouter cette personne à une squad")


def _check_unique(db: Session, squad_id: int, email: str | None, user_id: int | None,
                  member_id: int | None = None) -> None:
    """The same person appears once in a squad (by email or by account)."""
    for col, val in ((Member.email, email), (Member.user_id, user_id)):
        if val is None:
            continue
        q = select(Member.id).where(Member.squad_id == squad_id, col == val)
        if member_id is not None:
            q = q.where(Member.id != member_id)
        if db.scalar(q) is not None:
            raise HTTPException(status_code=409, detail="Cette personne est déjà dans l'équipe")


@router.get("/candidates")
def list_candidates(squad_id: int = Query(...), db: Session = Depends(get_db),
                    user: User = Depends(require_writer)):
    """Active accounts of the squad's tribe, to pick when adding a member.

    GET /api/members/candidates?squad_id=
    Access: edit rights on the squad. Only its tribe: a member is never linked
    across tribes. ``in_squad`` flags those already in the team."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    taken = set(db.scalars(select(Member.user_id).where(Member.squad_id == squad_id,
                                                        Member.user_id.isnot(None))).all())
    rows = db.scalars(select(User).where(User.tribe_id == squad.tribe_id, User.status == "active")
                      .order_by(User.display_name)).all()
    return [{"id": u.id, "display_name": u.display_name, "email": u.email, "in_squad": u.id in taken}
            for u in rows]


@router.post("", response_model=MemberOut, status_code=201)
def create_member(payload: MemberCreate, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Add a member to a squad.

    POST /api/members
    Access: writer role + edit rights on the target squad (assert_can_edit_squad).
    Side effects: writes a "member.create" audit entry.
    Returns 404 if the referenced squad does not exist.
    """
    squad = db.get(Squad, payload.squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, payload.squad_id)
    _check_manager(db, payload.squad_id, payload.manager_id)
    email, account = _resolve_account(db, squad, normalize_email(payload.email), payload.user_id)
    _assert_may_enrol(db, user, squad, account)
    typed = " ".join(p.strip() for p in (payload.first_name, payload.last_name) if p and p.strip())
    full_name = ((payload.full_name or "").strip() or typed
                 or (account.display_name if account else "") or (name_from_email(email) if email else ""))
    if not full_name:
        raise HTTPException(status_code=422, detail="Indiquez l'email ou le nom de la personne")
    _check_unique(db, squad.id, email, account.id if account else None)
    member = Member(squad_id=squad.id, full_name=full_name[:255], role_title=payload.role_title,
                    email=email, user_id=account.id if account else None,
                    manager_id=payload.manager_id, display_order=payload.display_order)
    db.add(member)
    db.flush()
    record_audit(db, user.id, "member.create", entity="member", entity_id=member.id,
                 detail={"squad_id": member.squad_id, "full_name": member.full_name})
    db.commit()
    db.refresh(member)
    notify_change(member.squad_id, "team", user)
    return member


@router.put("/{member_id}", response_model=MemberOut)
def update_member(member_id: int, payload: MemberUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_writer)):
    """Partially update a member.

    PUT /api/members/{member_id}
    Access: writer role + edit rights on the member's squad.
    Side effects: writes a "member.update" audit entry (with the changed fields).
    Only fields present in the payload are applied (exclude_unset). 404 if unknown.
    """
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    assert_can_edit_squad(db, user, member.squad_id)
    data = update_data(payload, Member)
    if "manager_id" in data:
        _check_manager(db, member.squad_id, data["manager_id"], member.id)
    if "email" in data or "user_id" in data:
        # A new email (or account) re-links: the old link goes with the old email.
        email = normalize_email(data["email"]) if "email" in data else member.email
        email, account = _resolve_account(db, member.squad, email, data.get("user_id"))
        _assert_may_enrol(db, user, member.squad, account)
        _check_unique(db, member.squad_id, email, account.id if account else None, member.id)
        data["email"], data["user_id"] = email, (account.id if account else None)
    for k, v in data.items():
        setattr(member, k, v)
    record_audit(db, user.id, "member.update", entity="member", entity_id=member.id, detail=data)
    db.commit()
    db.refresh(member)
    notify_change(member.squad_id, "team", user)
    return member


@router.delete("/{member_id}", status_code=204)
def delete_member(member_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Remove a member from a squad.

    DELETE /api/members/{member_id} -> 204 No Content
    Access: writer role + edit rights on the member's squad.
    Side effects: writes a "member.delete" audit entry. 404 if unknown.
    """
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    assert_can_edit_squad(db, user, member.squad_id)
    record_audit(db, user.id, "member.delete", entity="member", entity_id=member.id,
                 detail={"squad_id": member.squad_id})
    # Those who reported to this member now report to nobody: the foreign key
    # would otherwise refuse the delete (500 on Postgres).
    db.execute(update(Member).where(Member.manager_id == member.id).values(manager_id=None))
    sid = member.squad_id
    db.delete(member)
    db.commit()
    notify_change(sid, "team", user)
