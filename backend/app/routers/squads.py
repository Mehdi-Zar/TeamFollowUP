"""Squad endpoints (prefix ``/api/squads``).

A squad is the reporting unit inside a tribe. This router covers reading squads
and their quarterly detail, dependency surfacing, per-squad roadmap exports
(PPTX/HTML), CRUD on squads, and the squad-leader reporting surface: quarter
progress, budget, and curated key messages.

Access model (layered helpers from ``deps``):
- ``assert_tribe_scope``: the caller may only see/act within their own tribe
  (admins see everything).
- ``assert_can_edit_squad``: the caller may report on this squad (squad leader,
  tribe leader, or admin).
- ``assert_leads_squad``: stricter, squad leader of this squad (or admin) only.
- ``require_tribe_or_admin``: tribe leader or admin.
Some tribe-leader-only fields are additionally gated inside ``update_squad``.
Reporting mutations write an audit entry and emit ``notify_change`` so the
change-notification pipeline can pick them up.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session, selectinload

from .. import pptxtpl
from .. import status as st
from ..database import get_db
from ..generalconfig import reference_year
from ..deps import (
    ADMIN,
    CONTRIB,
    MEMBER,
    SQUAD,
    TRIBE,
    assert_can_edit_squad,
    assert_can_read_squad,
    assert_can_report,
    assert_reports_for_squad,
    assert_tribe_scope,
    get_current_user,
    get_threshold,
    is_squad_privileged,
    leads_this_squad,
    manages_squad,
    led_squad_ids,
    record_audit,
    require_module,
    require_tribe_or_admin,
    require_writer,
    update_data,
    visible_tribe_id,
)
from ..models import (
    utcnow,
    FeedPost,
    KeyMessage,
    Member,
    OrgNode,
    QuarterProgress,
    ReportSubscription,
    RoadmapItem,
    Squad,
    SquadBudget,
    User,
)
from ..changenotify import notify_change
from ..schemas import (
    DependentItemOut,
    KeyMessageCreate,
    KeyMessageOut,
    KeyMessageUpdate,
    QuarterProgressIn,
    QuarterProgressOut,
    SquadBudgetIn,
    SquadBudgetOut,
    MoodIn,
    SquadCreate,
    SquadDetail,
    SquadOut,
    SquadUpdate,
)
from ..serializers import budget_out, squad_detail

router = APIRouter(prefix="/api/squads", tags=["squads"])


def _set_co_leaders(db: Session, squad: Squad, user_ids: list[int]) -> None:
    """Replace a squad's co-leaders, refusing anyone outside its tribe.

    A co-leader of another tribe would read that tribe's squad through a door the
    tribe scope is supposed to close.

    Naming somebody co-leader promotes a plain member to ``squad_leader``: without
    it the account would be listed as a leader and refused by every squad-level
    check, which reads as the feature being broken. An admin or a tribe leader keeps
    their role, the higher one wins (same rule as the org import).
    """
    people = []
    for uid in dict.fromkeys(user_ids):
        target = db.get(User, int(uid))
        if target is None:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        if target.tribe_id is not None and target.tribe_id != squad.tribe_id:
            raise HTTPException(status_code=400,
                                detail=f"{target.display_name} n'appartient pas à la tribe de cette squad")
        if target.role in (MEMBER, CONTRIB):
            target.role = SQUAD
            target.tribe_id = target.tribe_id or squad.tribe_id
        people.append(target)
    squad.co_leaders = people
    # Leading includes the reporting: a co-leader is not also a contributor.
    squad.contributors = [u for u in squad.contributors if u not in people]


def _set_contributors(db: Session, squad: Squad, user_ids: list[int]) -> None:
    """Replace a squad's contributors, refusing anyone outside its tribe.

    Naming a plain member contributor gives them the "contributor" persona, so
    the reporting opens for them; anyone with a wider role keeps it.
    """
    people = []
    for uid in dict.fromkeys(user_ids):
        target = db.get(User, int(uid))
        if target is None:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        if target.tribe_id is not None and target.tribe_id != squad.tribe_id:
            raise HTTPException(status_code=400,
                                detail=f"{target.display_name} n'appartient pas à la tribe de cette squad")
        if target.role == MEMBER:
            target.role = CONTRIB
            target.tribe_id = target.tribe_id or squad.tribe_id
        people.append(target)
    squad.contributors = people


def _assert_unique_name(db: Session, tribe_id: int, name: str, exclude: int | None = None) -> None:
    """Two squads of one tribe with the same name read as one everywhere: refused."""
    q = select(Squad.id).where(Squad.tribe_id == tribe_id, Squad.name == name.strip())
    if exclude is not None:
        q = q.where(Squad.id != exclude)
    if db.scalar(q) is not None:
        raise HTTPException(status_code=409, detail=f"Une squad s'appelle déjà « {name.strip()} » dans cette tribe")


def _name_leader(db: Session, user: User, squad: Squad, leader_id: int) -> None:
    """Set the squad's leader: known account, of the squad's tribe (the admin may
    pick anyone), promoted to squad leader if it was a member or contributor."""
    leader = db.get(User, leader_id)
    if leader is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if leader.tribe_id is not None and leader.tribe_id != squad.tribe_id and user.role != ADMIN:
        raise HTTPException(status_code=400, detail=f"{leader.display_name} n'appartient pas à la tribe de cette squad")
    if leader.role in (MEMBER, CONTRIB):
        leader.role = SQUAD
        leader.tribe_id = leader.tribe_id or squad.tribe_id
    squad.leader_user_id = leader.id
    squad.contributors = [u for u in squad.contributors if u.id != leader.id]


def _leave_tribe(db: Session, squad: Squad, new_tribe: int) -> None:
    """What a move to another tribe does to what hung on the old one."""
    from ..models import Initiative, Otd
    db.execute(update(OrgNode).where(OrgNode.squad_id == squad.id).values(squad_id=None))
    db.execute(update(Initiative).where(Initiative.squad_id == squad.id,
                                        Initiative.tribe_id != new_tribe).values(squad_id=None))
    db.execute(update(Otd).where(Otd.squad_id == squad.id, Otd.scope == "management",
                                 Otd.tribe_id != new_tribe).values(squad_id=None))
    db.execute(update(Otd).where(Otd.squad_id == squad.id, Otd.scope == "squad").values(tribe_id=new_tribe))
    squad.co_leaders = [u for u in squad.co_leaders if u.tribe_id in (None, new_tribe)]
    squad.contributors = [u for u in squad.contributors if u.tribe_id in (None, new_tribe)]


@router.get("", response_model=list[SquadOut])
def list_squads(tribe_id: int | None = Query(default=None),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/squads: list squads visible to the caller.

    A tribe-scoped user sees their own tribe, plus the squads they lead in
    another one; an admin (no scope) may filter by the optional ``tribe_id``."""
    q = select(Squad).order_by(Squad.display_order, Squad.id).options(
        selectinload(Squad.co_leaders), selectinload(Squad.contributors))
    scope = visible_tribe_id(user)
    if scope is not None:
        q = q.where(or_(Squad.tribe_id == scope, Squad.id.in_(led_squad_ids(db, user))))
    elif tribe_id is not None:
        q = q.where(Squad.tribe_id == tribe_id)
    return list(db.scalars(q).all())


@router.get("/{squad_id}", response_model=SquadDetail)
def get_squad(squad_id: int, year: int | None = Query(default=None),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/squads/{squad_id}: full squad detail for a year.

    Requires the caller to be in the squad's tribe. ``privileged`` (budget and
    other sensitive fields) is computed from ``is_squad_privileged`` and controls
    what the serializer exposes. ``year`` defaults to the current one."""
    # Freshness needs the date of each snapshot, not its payload (a whole report
    # each): only those columns are loaded. Every screen of a squad calls this.
    from ..models import ReportSnapshot
    squad = db.get(Squad, squad_id, options=[selectinload(Squad.snapshots).load_only(
        ReportSnapshot.id, ReportSnapshot.squad_id, ReportSnapshot.submitted_at)])
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_read_squad(user, squad)
    if year is None:
        year = reference_year(db)
    return squad_detail(squad, year, get_threshold(db), privileged=is_squad_privileged(user, squad))


@router.get("/{squad_id}/dependents", response_model=list[DependentItemOut])
def squad_dependents(squad_id: int, year: int | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/squads/{squad_id}/dependents: milestones in *other* squads that
    declared a dependency on this squad.

    A dependency targets this squad directly, or this squad's tribe. This lets a
    squad surface what other teams are waiting on from them ("le faire apparaître").
    Requires tribe scope on the squad; ``year`` defaults to the current one.
    """
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_read_squad(user, squad)
    if year is None:
        year = reference_year(db)
    stmt = select(RoadmapItem).where(
        RoadmapItem.year == year,
        RoadmapItem.squad_id != squad_id,
        ((RoadmapItem.dependency_kind == "squad") & (RoadmapItem.dependency_squad_id == squad_id))
        | ((RoadmapItem.dependency_kind == "tribe") & (RoadmapItem.dependency_tribe_id == squad.tribe_id)),
    )
    out: list[DependentItemOut] = []
    for r in db.scalars(stmt).all():
        src = r.squad
        out.append(DependentItemOut(
            squad_id=r.squad_id,
            squad_name=src.name if src else "-",
            tribe_name=src.tribe.name if src and src.tribe else None,
            year=r.year, quarter=r.quarter, title=r.title, status=r.status,
            via="squad" if r.dependency_kind == "squad" else "tribe",
        ))
    out.sort(key=lambda d: (d.quarter, d.squad_name, d.title))
    return out


def _roadmap_data(db: Session, user: User, squad_id: int, year: int | None, lang: str | None):
    """Shared loader for the per-squad roadmap exports: verifies the squad exists
    and the caller is in its tribe, then builds the report payload. Returns the
    ``(data, year)`` pair (year resolved to the current one when omitted)."""
    from ..report import build_report_data
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_read_squad(user, squad)
    if year is None:
        year = reference_year(db)
    return build_report_data(db, None, year, 7, squad_id=squad_id, lang=lang), year


@router.get("/{squad_id}/roadmap.pptx",
            dependencies=[Depends(require_module("squad_content", "roadmap"))])
def export_squad_roadmap_pptx(squad_id: int, year: int | None = Query(default=None),
                              lang: str | None = Query(default=None),
                              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/squads/{squad_id}/roadmap.pptx: roadmap-only PowerPoint for a
    single squad (title slide + roadmap slide).

    Gated by the ``squad_content``/``roadmap`` module and tribe scope. Returns 501
    if python-pptx is not installed."""
    from ..report import render_roadmap_pptx
    data, year = _roadmap_data(db, user, squad_id, year, lang)
    try:
        pptxtpl.use(pptxtpl.get(db))
        payload = render_roadmap_pptx(data)
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    # Buffered artifact → plain Response so Content-Length is set (not chunked),
    # so a truncated download is detectable instead of silently corrupt.
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="roadmap_{squad_id}_{year}.pptx"'},
    )


@router.get("/{squad_id}/roadmap.html",
            dependencies=[Depends(require_module("squad_content", "roadmap"))])
def export_squad_roadmap_html(squad_id: int, year: int | None = Query(default=None),
                              lang: str | None = Query(default=None),
                              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/squads/{squad_id}/roadmap.html: roadmap-only web page for a
    single squad. Gated by the roadmap module and tribe scope."""
    from fastapi.responses import HTMLResponse
    from ..report import render_roadmap_html
    data, _ = _roadmap_data(db, user, squad_id, year, lang)
    return HTMLResponse(render_roadmap_html(data, standalone=True))


@router.post("", response_model=SquadOut, status_code=201)
def create_squad(payload: SquadCreate, db: Session = Depends(get_db), user: User = Depends(require_tribe_or_admin)):
    """POST /api/squads: create a squad (201). Tribe leader or admin only.

    A tribe leader may only create in their own tribe (the payload's ``tribe_id``
    is ignored for them and forced to their tribe); an admin picks the tribe.
    Audited."""
    # tribe leaders can only create squads in their own tribe
    tribe_id = payload.tribe_id if user.role == ADMIN else user.tribe_id
    if tribe_id is None:
        raise HTTPException(status_code=400, detail="Tribe requise")
    assert_tribe_scope(user, tribe_id)
    data = payload.model_dump()
    data["tribe_id"] = tribe_id
    _assert_unique_name(db, tribe_id, data.get("name") or "")
    leader_id = data.pop("leader_user_id", None)
    squad = Squad(**data)
    db.add(squad)
    db.flush()
    # The leader is checked and promoted exactly as on an update.
    if leader_id:
        _name_leader(db, user, squad, leader_id)
    record_audit(db, user.id, "squad.create", entity="squad", entity_id=squad.id, detail={"name": squad.name})
    db.commit()
    db.refresh(squad)
    return squad


@router.put("/{squad_id}", response_model=SquadOut)
def update_squad(squad_id: int, payload: SquadUpdate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """PUT /api/squads/{squad_id}: update a squad.

    Requires tribe scope. Only an admin may move a squad to another tribe.
    Structural fields (leader assignment, ordering, KPI/budget toggles) are
    reserved to tribe leaders and admins; a squad leader may edit the squad but
    not those fields (403 if attempted). Audited."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    # A persona holding the Squads tab manages squads as the tribe leader of its
    # tribe would (same rule as creating or deleting one).
    if user.role not in (ADMIN, TRIBE) and not leads_this_squad(squad, user):
        from ..tabaccess import has_tab, acting_manager
        if has_tab(db, user, "squads"):
            user = acting_manager(db, user, "squads")
    if not leads_this_squad(squad, user):  # a leader may lead in another tribe
        assert_tribe_scope(user, squad.tribe_id)
    data = update_data(payload, Squad)
    if "tribe_id" in data and user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Seul l'administrateur peut déplacer une squad de tribe")
    # KPI / budget on/off is a tribe-leader decision (like leader assignment & ordering).
    structural = {"leader_user_id", "co_leader_user_ids", "display_order",
                  "kpis_enabled", "budget_enabled"}
    if not manages_squad(user, squad):
        assert_can_edit_squad(db, user, squad_id)
        if structural & data.keys():
            raise HTTPException(status_code=403, detail="Champs réservés au tribe leader")
    # Co-leaders are a relationship, not a column, and naming one has a side effect
    # on the account (see _set_co_leaders), so it is applied apart from the plain
    # field copy below.
    if "co_leader_user_ids" in data:
        _set_co_leaders(db, squad, data.pop("co_leader_user_ids") or [])
    # Contributors: the squad's leadership names them too (the tribe scope and
    # the edit right were checked above).
    if "contributor_user_ids" in data:
        _set_contributors(db, squad, data.pop("contributor_user_ids") or [])
    # Naming the leader promotes a member or contributor, as for a co-leader, and
    # takes them out of the contributors (leading includes the reporting).
    if data.get("leader_user_id"):
        _name_leader(db, user, squad, data.pop("leader_user_id"))
    if "name" in data and data["name"] != squad.name:
        _assert_unique_name(db, data.get("tribe_id", squad.tribe_id), data["name"], exclude=squad.id)
    # Moving to another tribe takes everything that hung on the old one with it,
    # or lets it go: its org box, the initiatives and management commitments of
    # the old tribe no longer point at it, its own commitments move with it, and
    # co-leaders or contributors of the old tribe leave it.
    if "tribe_id" in data and data["tribe_id"] != squad.tribe_id:
        _leave_tribe(db, squad, data["tribe_id"])
    for k, v in data.items():
        setattr(squad, k, v)
    record_audit(db, user.id, "squad.update", entity="squad", entity_id=squad.id, detail=data)
    db.commit()
    db.refresh(squad)
    return squad


@router.delete("/{squad_id}", status_code=204)
def delete_squad(squad_id: int, db: Session = Depends(get_db), user: User = Depends(require_tribe_or_admin)):
    """DELETE /api/squads/{squad_id}: delete a squad (204). Tribe leader or admin
    only, within tribe scope.

    Side effect: org-chart nodes and feed posts that pointed at this squad are
    detached (their ``squad_id`` is cleared) rather than deleted. Audited."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_tribe_scope(user, squad.tribe_id)
    # Detach references not owned by the squad (keep the org boxes and feed posts).
    for node in db.scalars(select(OrgNode).where(OrgNode.squad_id == squad_id)).all():
        node.squad_id = None
    for post in db.scalars(select(FeedPost).where(FeedPost.squad_id == squad_id)).all():
        post.squad_id = None
    # Another squad's milestone that depends on this one keeps the dependency, as
    # free text under this squad's name (the foreign key refused the delete).
    for item in db.scalars(select(RoadmapItem).where(RoadmapItem.dependency_squad_id == squad_id,
                                                     RoadmapItem.squad_id != squad_id)).all():
        item.dependency_to_text(squad.name)
    db.execute(delete(ReportSubscription).where(ReportSubscription.squad_id == squad_id))
    # A management commitment set on this squad belongs to the tribe: it loses its
    # squad, it does not go with it (the squad's own commitments do).
    from ..models import Otd
    db.execute(update(Otd).where(Otd.squad_id == squad_id, Otd.scope == "management").values(squad_id=None))
    # Members report to one another and the cascade deletes them in no set order.
    db.execute(update(Member).where(Member.squad_id == squad_id).values(manager_id=None))
    db.flush()  # write the detachments before the delete, whatever the unit-of-work order
    record_audit(db, user.id, "squad.delete", entity="squad", entity_id=squad.id, detail={"name": squad.name})
    db.delete(squad)
    db.commit()


@router.put("/{squad_id}/mood", response_model=SquadOut)
def set_mood(squad_id: int, payload: MoodIn, db: Session = Depends(get_db),
             user: User = Depends(require_writer)):
    """PUT /api/squads/{squad_id}/mood : declare le moral de l'equipe.

    Trois niveaux (good | mixed | bad), ou ``null`` pour retirer la declaration.
    Meme regle que le reste de l'edition d'une squad: ses leaders, ses
    contributeurs, et le tribe leader de sa tribu (qui peut corriger une saisie). La date est posee par le serveur, parce qu'un moral
    sans fraicheur se lit comme un moral actuel. Audite.
    """
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_report(db, user, squad_id)
    # Only the comment moved (same level, "mood" not re-declared): its date stays.
    comment_only = ("mood" not in payload.model_fields_set) and squad.mood is not None
    if comment_only:
        payload.mood = squad.mood
    squad.mood = payload.mood
    # The comment changes only when it is sent: picking another face used to wipe
    # the sentence that went with it. Withdrawing the mood withdraws its comment.
    if "comment" in payload.model_fields_set:
        squad.mood_comment = (payload.comment or "").strip()[:300] or None
    elif payload.mood is None:
        squad.mood_comment = None
    if not comment_only:
        squad.mood_at = utcnow() if payload.mood else None
    record_audit(db, user.id, "squad.mood", entity="squad", entity_id=squad_id,
                 detail={"mood": squad.mood})
    db.commit()
    notify_change(squad.id, "mood", user)
    db.refresh(squad)
    return squad


@router.put("/{squad_id}/quarter-progress", response_model=QuarterProgressOut,
            dependencies=[Depends(require_module("squad_content", "quarter_progress"))])
def set_quarter_progress(squad_id: int, payload: QuarterProgressIn, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """PUT /api/squads/{squad_id}/quarter-progress: record a quarter's comment.

    The percentage is derived from the quarter's milestones and is what the screens
    display; it is stored here so the row matches what was shown, and only an
    explicit ``progress_pct`` from an API caller overrides it.

    Squad-leader reporting: requires ``assert_can_edit_squad``. Audited, then
    emits ``notify_change(..., "progress", ...)``."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_report(db, user, squad_id)
    row = db.scalar(
        select(QuarterProgress).where(
            QuarterProgress.squad_id == squad_id,
            QuarterProgress.year == payload.year,
            QuarterProgress.quarter == payload.quarter,
        )
    )
    pct = payload.progress_pct
    if pct is None:
        pct = st.year_progress(squad, payload.year).get(payload.quarter, 0)
    if row is None:
        row = QuarterProgress(squad_id=squad_id, year=payload.year, quarter=payload.quarter,
                              progress_pct=pct, comment=payload.comment)
        db.add(row)
    else:
        row.progress_pct = pct
        row.comment = payload.comment
    record_audit(db, user.id, "quarter_progress.set", entity="squad", entity_id=squad_id,
                 detail={"year": payload.year, "quarter": payload.quarter, "progress_pct": pct})
    db.commit()
    db.refresh(row)
    notify_change(squad_id, "progress", user, payload.year)
    return row


# ---------- Budget (squad-leader reporting, privileged-visible) ----------
@router.put("/{squad_id}/budget", response_model=SquadBudgetOut)
def set_squad_budget(squad_id: int, payload: SquadBudgetIn, year: int | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """PUT /api/squads/{squad_id}/budget: set the squad's budget line for a year
    (upsert).

    Requires ``assert_can_edit_squad`` and the squad's budget module to be enabled
    (403 otherwise). Business rule: the total envelope is a tribe-leader/admin
    decision: a squad leader may only report spent/forecast/comment, so an
    incoming ``total`` from a squad leader is ignored. Audited, then
    ``notify_change(..., "budget", ...)``."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_edit_squad(db, user, squad_id)
    if not squad.budget_enabled:
        raise HTTPException(status_code=403, detail="Le budget n'est pas activé pour cette squad")
    if year is None:
        year = reference_year(db)
    row = db.scalar(select(SquadBudget).where(SquadBudget.squad_id == squad_id, SquadBudget.year == year))
    if row is None:
        row = SquadBudget(squad_id=squad_id, year=year)
        db.add(row)
    # The total envelope is a tribe-leader (or admin) decision; a squad leader only
    # reports where the squad stands (spent / forecast) and comments. Ignore an
    # incoming total from a squad leader so they can't move the envelope.
    if manages_squad(user, db.get(Squad, squad_id)):
        row.total = payload.total
    row.spent = payload.spent
    row.forecast = payload.forecast
    row.comment = payload.comment
    record_audit(db, user.id, "squad_budget.set", entity="squad", entity_id=squad_id,
                 detail={"year": year, "total": float(row.total) if row.total is not None else None,
                         "spent": payload.spent, "forecast": payload.forecast})
    db.commit()
    notify_change(squad_id, "budget", user, year)
    return budget_out(squad, year)


# ---------- Key messages (curated success / alert / risk) ----------
def _get_key_message(db: Session, user: User, squad_id: int, msg_id: int) -> KeyMessage:
    """Fetch a key message, asserting the caller leads the squad (squad leader or
    admin) and that the message actually belongs to that squad. 404 if either the
    squad or the message is missing/mismatched."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_reports_for_squad(db, user, squad_id)   # key messages: leadership + contributors
    km = db.get(KeyMessage, msg_id)
    if km is None or km.squad_id != squad_id:
        raise HTTPException(status_code=404, detail="Message introuvable")
    return km


@router.post("/{squad_id}/key-messages", response_model=KeyMessageOut, status_code=201)
def create_key_message(squad_id: int, payload: KeyMessageCreate, year: int | None = Query(default=None),
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """POST /api/squads/{squad_id}/key-messages: add a curated key message
    (success/alert/risk) for a year (201).

    Squad leader (or admin) only. Audited, then ``notify_change(..., "key_message",
    ...)``. ``year`` defaults to the current one."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_reports_for_squad(db, user, squad_id)   # key messages: leadership + contributors
    if year is None:
        year = reference_year(db)
    km = KeyMessage(squad_id=squad_id, year=year, kind=payload.kind, text=payload.text,
                    display_order=payload.display_order, created_by_user_id=user.id)
    db.add(km)
    record_audit(db, user.id, "key_message.create", entity="squad", entity_id=squad_id,
                 detail={"year": year, "kind": payload.kind})
    db.commit()
    db.refresh(km)
    notify_change(squad_id, "key_message", user, year)
    return km


@router.put("/{squad_id}/key-messages/{msg_id}", response_model=KeyMessageOut)
def update_key_message(squad_id: int, msg_id: int, payload: KeyMessageUpdate,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """PUT /api/squads/{squad_id}/key-messages/{msg_id}: update a key message.

    Squad leader (or admin) only, message must belong to the squad. Audited, then
    ``notify_change(..., "key_message", ...)``."""
    km = _get_key_message(db, user, squad_id, msg_id)
    for k, v in update_data(payload, KeyMessage).items():
        setattr(km, k, v)
    record_audit(db, user.id, "key_message.update", entity="squad", entity_id=squad_id, detail={"id": msg_id})
    km_year = km.year
    db.commit()
    db.refresh(km)
    notify_change(squad_id, "key_message", user, km_year)
    return km


@router.delete("/{squad_id}/key-messages/{msg_id}", status_code=204)
def delete_key_message(squad_id: int, msg_id: int,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """DELETE /api/squads/{squad_id}/key-messages/{msg_id}: delete a key message
    (204).

    Squad leader (or admin) only, message must belong to the squad. Audited, then
    ``notify_change(..., "key_message", ...)``."""
    km = _get_key_message(db, user, squad_id, msg_id)
    km_year = km.year
    record_audit(db, user.id, "key_message.delete", entity="squad", entity_id=squad_id, detail={"id": msg_id})
    db.delete(km)
    db.commit()
    notify_change(squad_id, "key_message", user, km_year)
