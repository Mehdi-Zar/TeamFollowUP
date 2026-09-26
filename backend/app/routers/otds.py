"""OTD (On-Time Delivery) commitments, en deux portees.

Un OTD est une promesse datee et les jalons qui la rendent vraie. Son statut est
derive de ces jalons, jamais saisi.

  * portee ``management`` : l'engagement fixe par le haut. Seuls le tribe leader
    et l'admin l'ecrivent, et eux seuls y rattachent des jalons. C'est le
    comportement historique, inchange.
  * portee ``squad`` : l'engagement que le squad leader prend sur sa propre
    squad. Il le cree, le modifie, le supprime et y rattache ses jalons sans
    demander l'autorisation, parce que c'est son engagement.

Les deux portees ne partagent pas le meme lien vers les jalons
(``RoadmapItem.otd_id`` contre ``squad_otd_id``) : un jalon sert souvent les deux
a la fois, et avec un lien unique le dernier qui rattache defaisait le travail de
l'autre sans le lui dire.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .. import status as st
from ..database import get_db
from ..generalconfig import reference_year
from ..deps import (ADMIN, SQUAD, TRIBE, reports_for_squad, scoped_tribe_id, update_data, assert_can_manage_tribe_reporting,
                    get_current_user, led_squad_ids, contributed_squad_ids, record_audit)
from ..models import Otd, RoadmapItem, Squad, Tribe, User
from ..changenotify import notify_change
from ..schemas import OtdCreate, OtdMembers, OtdOut, OtdUpdate

router = APIRouter(prefix="/api/otds", tags=["otds"])

MANAGEMENT, SQUAD_SCOPE = "management", "squad"


def _scope_tribe(user: User, tribe_id: int | None) -> int | None:
    """Resolve which tribe to read: admins may pass any ``tribe_id``; others are
    pinned to their own tribe."""
    return scoped_tribe_id(user, tribe_id)


def _leads(db: Session, user: User, squad_id: int | None) -> bool:
    """L'utilisateur fait-il le reporting de cette squad (leader, co-leader ou
    contributeur) ? Les engagements de la squad font partie de son reporting."""
    if squad_id is None:
        return False
    if user.role == ADMIN:
        return True
    return reports_for_squad(db, user, squad_id)


def _assert_can_write(db: Session, user: User, otd: Otd) -> None:
    """Qui ecrit cet engagement : son proprietaire, et personne d'autre.

    Un engagement de squad appartient a la squad. Le tribe leader le voit, le
    lit dans ses rapports, et ne l'ecrit pas : s'il pouvait le corriger,
    l'engagement cesserait d'etre celui de la squad, ce qui est precisement ce
    que la portee sert a distinguer.
    """
    if otd.scope == SQUAD_SCOPE:
        if not _leads(db, user, otd.squad_id):
            raise HTTPException(status_code=403,
                                detail="Cet engagement appartient au leader de sa squad")
        return
    assert_can_manage_tribe_reporting(user, otd.tribe_id)


def _jalon_brief(j) -> dict:
    """Compact milestone view embedded in an OTD payload."""
    return {"id": j.id, "title": j.title, "quarter": j.quarter, "stage": j.release_stage,
            "status": j.status, "squad_id": j.squad_id, "squad_name": j.squad.name if j.squad else ""}


def _otd_payload(otd: Otd) -> dict:
    """Serialize an OTD with its derived on-time status, member-milestone counts,
    and the milestone briefs. The status is computed from the milestones and the
    committed date (``st.otd_status``), not stored."""
    jalons = sorted(otd.members, key=lambda x: (x.squad_id, x.quarter, x.id))
    return {
        **OtdOut.model_validate(otd).model_dump(),
        "owner_name": otd.owner.display_name if otd.owner else None,
        "squad_name": otd.squad.name if otd.squad else None,
        "status": st.otd_status(jalons, otd.committed_date),
        "counts": {"total": len(jalons),
                   "done": sum(1 for j in jalons if j.status == "done"),
                   "blocked": sum(1 for j in jalons if j.status == "blocked"),
                   "at_risk": sum(1 for j in jalons if j.status == "at_risk")},
        "jalons": [_jalon_brief(j) for j in jalons],
    }


@router.get("/candidate-jalons")
def candidate_jalons(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
                     squad_id: int | None = Query(default=None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/otds/candidate-jalons: milestones available for an OTD.

    Le perimetre suit ce que l'appelant a le droit d'engager : un admin peut
    viser n'importe quelle ``tribe_id``, un tribe leader est fixe sur sa tribe, et
    les autres ne voient que les jalons des squads dont ils font le reporting
    (leader, co-leader, contributeur). Chaque ligne
    porte ses deux rattachements courants (``otd_id`` pour l'engagement
    management, ``squad_otd_id`` pour celui de la squad), pour que l'ecran sache
    ce qui est deja pris de son cote sans rien supposer de l'autre.
    """
    year = year or reference_year(db)
    q = (select(RoadmapItem).join(Squad, Squad.id == RoadmapItem.squad_id)
         .where(RoadmapItem.year == year)
         .order_by(Squad.display_order, RoadmapItem.quarter, RoadmapItem.id))
    if squad_id is not None and user.role != ADMIN and reports_for_squad(db, user, squad_id):
        # The squad's own commitment: the squad's milestones, from any tribe.
        q = q.where(RoadmapItem.squad_id == squad_id)
    elif user.role in (ADMIN, TRIBE):
        scope = _scope_tribe(user, tribe_id)
        if scope is not None:
            q = q.where(Squad.tribe_id == scope)
        if squad_id is not None:
            q = q.where(RoadmapItem.squad_id == squad_id)
    elif squad_id is not None:
        # The squad's own commitment: whoever does its reporting (leader,
        # co-leaders, contributors) attaches its milestones.
        if not reports_for_squad(db, user, squad_id):
            return []
        q = q.where(RoadmapItem.squad_id == squad_id)
    else:
        q = q.where(or_(RoadmapItem.squad_id.in_(led_squad_ids(db, user)),
                        RoadmapItem.squad_id.in_(contributed_squad_ids(db, user))))
    return [{"id": j.id, "title": j.title, "quarter": j.quarter, "theme": j.theme,
             "squad_id": j.squad_id, "squad_name": j.squad.name if j.squad else "",
             "otd_id": j.otd_id, "squad_otd_id": j.squad_otd_id} for j in db.scalars(q).all()]


@router.get("")
def list_otds(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """OTDs with their derived on-time status and member milestones.

    Visibilite: toute la tribu lit tous ses engagements (management et squad),
    puisque les documents exportes depuis le tableau de bord les montrent deja a
    chacun. S'y ajoutent les tribus des squads qu'on dirige. L'admin voit tout.
    La lecture ouverte ne change rien a l'ecriture, qui reste gardee par portee.
    """
    year = year or reference_year(db)
    q = (select(Otd).where(Otd.year == year).order_by(Otd.display_order, Otd.id)
         .options(selectinload(Otd.roadmap_items).selectinload(RoadmapItem.squad),
                  selectinload(Otd.squad_items).selectinload(RoadmapItem.squad),
                  selectinload(Otd.owner), selectinload(Otd.squad)))
    if user.role == ADMIN:
        if tribe_id is not None:
            q = q.where(Otd.tribe_id == tribe_id)
    else:
        # Toute la tribu lit tous ses engagements, comme les exports les montrent:
        # la sienne, plus celles des squads qu'on dirige (diriger une squad d'une
        # autre tribu reste possible). L'ecriture reste fermee, voir plus bas.
        tribes = select(Squad.tribe_id).where(Squad.id.in_(led_squad_ids(db, user)))
        q = q.where(or_(Otd.tribe_id == user.tribe_id, Otd.tribe_id.in_(tribes)))
    return [_otd_payload(o) for o in db.scalars(q).all()]


def _validate_owner(db: Session, tribe_id: int, owner_user_id: int | None) -> None:
    """The assigned owner must lead a squad of THIS OTD's tribe (whatever their
    role), or be a squad leader of the tribe. Without this a tribe leader could
    assign someone of another tribe, who would then see this tribe's OTD (title,
    committed date, budget ref, milestones): a cross-tribe disclosure."""
    if owner_user_id is None:
        return
    owner = db.get(User, owner_user_id)
    if owner is None:
        raise HTTPException(status_code=400, detail="Porteur inconnu")
    if owner.role == SQUAD and owner.tribe_id == tribe_id:
        return
    leads_here = db.scalars(select(Squad.id).where(Squad.tribe_id == tribe_id,
                                                   Squad.id.in_(led_squad_ids(db, owner)))).first()
    if leads_here is None:
        raise HTTPException(status_code=400,
                            detail="Le porteur doit diriger une squad de cette tribe")


# At most this many commitments fall due in the same month, per tribe for the
# management ones and per squad for a squad's own. More in one month is a plan
# nobody can hold, and the timeline shows two per month.
MAX_OTD_PER_MONTH = 2


def _check_month_quota(db: Session, scope: str, tribe_id: int, squad_id: int | None,
                       committed, exclude_id: int | None = None) -> None:
    """409 when the month of ``committed`` already holds MAX_OTD_PER_MONTH."""
    if committed is None:
        return
    q = select(Otd).where(Otd.scope == scope)
    q = q.where(Otd.squad_id == squad_id) if scope == SQUAD_SCOPE else q.where(Otd.tribe_id == tribe_id)
    if exclude_id is not None:
        q = q.where(Otd.id != exclude_id)
    same = [o for o in db.scalars(q.where(Otd.committed_date.isnot(None))).all()
            if (o.committed_date.year, o.committed_date.month) == (committed.year, committed.month)]
    if len(same) >= MAX_OTD_PER_MONTH:
        raise HTTPException(status_code=409, detail=(
            f"{MAX_OTD_PER_MONTH} engagements au plus par mois : "
            f"{committed.month:02d}/{committed.year} en compte déjà {len(same)}"))


def _notify(otd_squad_id: int | None, user: User) -> None:
    """A squad's own commitment changed: the change mail goes out for that squad.
    A management commitment belongs to the tribe, not to one squad's document."""
    if otd_squad_id is not None:
        notify_change(otd_squad_id, "otd", user)


def _validate_squad_owner(db: Session, squad: Squad, owner_user_id: int | None) -> None:
    """A squad's own commitment is carried by one of its leaders (named leader or
    co-leader, whatever their role). Creation took any id, even another tribe's
    user or an unknown one (500); the update wanted a squad_leader role, which
    refused a co-leader who is a tribe leader."""
    if owner_user_id is None:
        return
    from ..deps import leads_this_squad
    owner = db.get(User, owner_user_id)
    if owner is None or not leads_this_squad(squad, owner):
        raise HTTPException(status_code=400, detail="Le porteur doit être le leader ou un co-leader de cette squad")


@router.post("", status_code=201)
def create_otd(payload: OtdCreate, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """POST /api/otds: create an OTD (201).

    Portee ``management`` : tribe leader ou admin, sur leur tribe
    (``assert_can_manage_tribe_reporting``), et tout owner assigne doit etre un
    squad leader de cette tribe (``_validate_owner``, garde anti-divulgation
    entre tribes). Portee ``squad`` : le leader de la squad visee, qui doit la
    diriger, et la tribe de l'engagement est celle de la squad, pas celle que le
    payload annonce. Audite.
    """
    if db.get(Tribe, payload.tribe_id) is None:
        raise HTTPException(status_code=404, detail="Tribe introuvable")
    data = payload.model_dump()

    if data["scope"] == SQUAD_SCOPE:
        squad = db.get(Squad, data.get("squad_id") or 0)
        if squad is None:
            raise HTTPException(status_code=400, detail="Un engagement de squad doit désigner sa squad")
        if not _leads(db, user, squad.id):
            raise HTTPException(status_code=403, detail="Vous ne dirigez pas cette squad")
        # La tribe suit la squad: la laisser au payload permettrait de poser
        # l'engagement dans une tribe voisine, qui le verrait dans ses rapports.
        data["tribe_id"] = squad.tribe_id
        data["owner_user_id"] = data.get("owner_user_id") or squad.leader_user_id
        _validate_squad_owner(db, squad, data["owner_user_id"])
    else:
        assert_can_manage_tribe_reporting(user, data["tribe_id"])
        _validate_owner(db, data["tribe_id"], data.get("owner_user_id"))
        # A management commitment may be set on one squad (the one it is about):
        # it then shows under that squad, and not under every squad of its owner.
        target = db.get(Squad, data["squad_id"]) if data.get("squad_id") else None
        if data.get("squad_id") and (target is None or target.tribe_id != data["tribe_id"]):
            raise HTTPException(status_code=400, detail="Squad hors de cette tribe")
        data["squad_id"] = target.id if target else None

    _check_month_quota(db, data["scope"], data["tribe_id"], data.get("squad_id"), data.get("committed_date"))
    otd = Otd(**data)
    db.add(otd)
    db.flush()
    record_audit(db, user.id, "otd.create", entity="otd", entity_id=otd.id,
                 detail={"tribe_id": otd.tribe_id, "title": otd.title, "scope": otd.scope})
    db.commit()
    _notify(otd.squad_id, user)
    db.refresh(otd)
    return _otd_payload(otd)


@router.put("/{otd_id}")
def update_otd(otd_id: int, payload: OtdUpdate, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """PUT /api/otds/{otd_id}: update an OTD.

    Ecrit par le proprietaire de la portee (``_assert_can_write``). Un owner
    change est revalide (``_validate_owner``). La portee, elle, ne se modifie pas.
    Audite."""
    otd = db.get(Otd, otd_id)
    if otd is None:
        raise HTTPException(status_code=404, detail="OTD introuvable")
    _assert_can_write(db, user, otd)
    data = update_data(payload, Otd)
    if "owner_user_id" in data:
        if otd.scope == SQUAD_SCOPE and otd.squad_id is not None:
            _validate_squad_owner(db, db.get(Squad, otd.squad_id), data["owner_user_id"])
        else:
            _validate_owner(db, otd.tribe_id, data["owner_user_id"])
    if data.get("committed_date") is not None:
        _check_month_quota(db, otd.scope or "management", otd.tribe_id, otd.squad_id,
                           data["committed_date"], exclude_id=otd.id)
    for k, v in data.items():
        setattr(otd, k, v)
    record_audit(db, user.id, "otd.update", entity="otd", entity_id=otd.id, detail=list(data.keys()))
    db.commit()
    _notify(otd.squad_id, user)
    db.refresh(otd)
    return _otd_payload(otd)


@router.put("/{otd_id}/jalons")
def set_otd_jalons(otd_id: int, payload: OtdMembers, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """PUT /api/otds/{otd_id}/jalons: set the milestones that make up this OTD
    (replaces the current set).

    Ecrit par le proprietaire de la portee. Un engagement management accepte les
    jalons de sa tribe; un engagement de squad n'accepte que ceux de sa squad, ce
    qui evite qu'un squad leader ne s'engage sur le travail d'une autre equipe.
    Chaque portee ecrit son propre lien, donc rattacher ici ne detache jamais
    rien de l'autre cote. Audite."""
    otd = db.get(Otd, otd_id)
    if otd is None:
        raise HTTPException(status_code=404, detail="OTD introuvable")
    _assert_can_write(db, user, otd)
    wanted = set(payload.jalon_ids)
    if wanted:
        q = (select(RoadmapItem).join(Squad, Squad.id == RoadmapItem.squad_id)
             .where(RoadmapItem.id.in_(wanted)))
        if otd.scope == SQUAD_SCOPE:
            q = q.where(RoadmapItem.squad_id == otd.squad_id)
            refus = "Un jalon n'appartient pas à cette squad"
        else:
            q = q.where(Squad.tribe_id == otd.tribe_id)
            refus = "Un jalon n'appartient pas à cette tribe"
        found = db.execute(q).scalars().all()
        if len(found) != len(wanted):
            raise HTTPException(status_code=400, detail=refus)
        if any(j.year != otd.year for j in found):
            raise HTTPException(status_code=400, detail="Un jalon n'est pas de l'année de cet engagement")
        if otd.scope == SQUAD_SCOPE and any(j.squad_otd_id not in (None, otd.id) for j in found):
            raise HTTPException(status_code=409, detail="Un jalon tient déjà un autre engagement de la squad")

    link = "squad_otd_id" if otd.scope == SQUAD_SCOPE else "otd_id"
    for j in list(otd.members):
        setattr(j, link, None)
    for j in db.scalars(select(RoadmapItem).where(RoadmapItem.id.in_(wanted))).all() if wanted else []:
        setattr(j, link, otd.id)
    record_audit(db, user.id, "otd.set_jalons", entity="otd", entity_id=otd.id,
                 detail={"jalon_ids": sorted(wanted), "scope": otd.scope})
    db.commit()
    _notify(otd.squad_id, user)
    db.refresh(otd)
    return _otd_payload(otd)


@router.delete("/{otd_id}", status_code=204)
def delete_otd(otd_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """DELETE /api/otds/{otd_id}: delete an OTD (204). Proprietaire de la portee.

    Side effect: member milestones keep existing; only their link is cleared.
    Audited."""
    otd = db.get(Otd, otd_id)
    if otd is None:
        raise HTTPException(status_code=404, detail="OTD introuvable")
    _assert_can_write(db, user, otd)
    record_audit(db, user.id, "otd.delete", entity="otd", entity_id=otd.id,
                 detail={"tribe_id": otd.tribe_id, "scope": otd.scope})
    sid = otd.squad_id
    db.delete(otd)  # milestones keep existing; their link is set NULL
    db.commit()
    _notify(sid, user)
