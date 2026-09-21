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
from ..deps import (ADMIN, SQUAD, TRIBE, assert_can_manage_tribe_reporting,
                    get_current_user, led_squad_ids, record_audit)
from ..models import Otd, RoadmapItem, Squad, Tribe, User
from ..schemas import OtdCreate, OtdMembers, OtdOut, OtdUpdate

router = APIRouter(prefix="/api/otds", tags=["otds"])

MANAGEMENT, SQUAD_SCOPE = "management", "squad"


def _scope_tribe(user: User, tribe_id: int | None) -> int | None:
    """Resolve which tribe to read: admins may pass any ``tribe_id``; others are
    pinned to their own tribe."""
    return tribe_id if user.role == "admin" else user.tribe_id


def _leads(db: Session, user: User, squad_id: int | None) -> bool:
    """L'utilisateur dirige-t-il cette squad (leader ou co-leader) ?"""
    if squad_id is None:
        return False
    if user.role == ADMIN:
        return True
    return squad_id in set(db.scalars(led_squad_ids(db, user)).all())


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
    un squad leader ne voit que les jalons des squads qu'il dirige. Chaque ligne
    porte ses deux rattachements courants (``otd_id`` pour l'engagement
    management, ``squad_otd_id`` pour celui de la squad), pour que l'ecran sache
    ce qui est deja pris de son cote sans rien supposer de l'autre.
    """
    year = year or st.current_year_quarter()[0]
    q = (select(RoadmapItem).join(Squad, Squad.id == RoadmapItem.squad_id)
         .where(RoadmapItem.year == year)
         .order_by(Squad.display_order, RoadmapItem.quarter, RoadmapItem.id))
    if user.role in (ADMIN, TRIBE):
        scope = _scope_tribe(user, tribe_id)
        if scope is not None:
            q = q.where(Squad.tribe_id == scope)
    elif user.role == SQUAD:
        q = q.where(RoadmapItem.squad_id.in_(led_squad_ids(db, user)))
    else:
        return []
    if squad_id is not None:
        q = q.where(RoadmapItem.squad_id == squad_id)
    return [{"id": j.id, "title": j.title, "quarter": j.quarter, "theme": j.theme,
             "squad_id": j.squad_id, "squad_name": j.squad.name if j.squad else "",
             "otd_id": j.otd_id, "squad_otd_id": j.squad_otd_id} for j in db.scalars(q).all()]


@router.get("")
def list_otds(tribe_id: int | None = Query(default=None), year: int | None = Query(default=None),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """OTDs with their derived on-time status and member milestones.

    Visibility: le tribe leader (ou l'admin) voit tout ce qui concerne sa tribe,
    engagements de squad compris, puisque son rapport les montre. Un squad leader
    voit les siens, plus les engagements management qui lui sont assignes ou qui
    embarquent un de ses jalons. Les autres n'en voient aucun.
    """
    year = year or st.current_year_quarter()[0]
    q = (select(Otd).where(Otd.year == year).order_by(Otd.display_order, Otd.id)
         .options(selectinload(Otd.roadmap_items), selectinload(Otd.squad_items)))
    if user.role == ADMIN:
        if tribe_id is not None:
            q = q.where(Otd.tribe_id == tribe_id)
    elif user.role == TRIBE:
        q = q.where(Otd.tribe_id == user.tribe_id)
    elif user.role == SQUAD:
        # A squad leader sees the OTDs assigned to them (owner_user_id), those of
        # the squads they lead, plus any that group one of their milestones.
        led_squads = led_squad_ids(db, user)
        concerned = (select(RoadmapItem.otd_id)
                     .where(RoadmapItem.squad_id.in_(led_squads), RoadmapItem.otd_id.is_not(None)))
        q = q.where(or_(Otd.owner_user_id == user.id, Otd.id.in_(concerned),
                        Otd.squad_id.in_(led_squads)))
    else:
        return []  # members and custom personas do not see OTDs
    return [_otd_payload(o) for o in db.scalars(q).all()]


def _validate_owner(db: Session, tribe_id: int, owner_user_id: int | None) -> None:
    """The assigned owner must be a squad leader of THIS OTD's tribe. Without this
    a tribe leader could assign a squad leader of another tribe, who would then
    see this tribe's OTD (title, committed date, budget ref, milestones) via the
    owner-based visibility rule - a cross-tribe disclosure."""
    if owner_user_id is None:
        return
    owner = db.get(User, owner_user_id)
    if owner is None or owner.role != SQUAD or owner.tribe_id != tribe_id:
        raise HTTPException(status_code=400,
                            detail="L'owner doit être un squad leader de cette tribe")


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
    else:
        assert_can_manage_tribe_reporting(user, data["tribe_id"])
        _validate_owner(db, data["tribe_id"], data.get("owner_user_id"))
        data["squad_id"] = None

    otd = Otd(**data)
    db.add(otd)
    db.flush()
    record_audit(db, user.id, "otd.create", entity="otd", entity_id=otd.id,
                 detail={"tribe_id": otd.tribe_id, "title": otd.title, "scope": otd.scope})
    db.commit()
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
    data = payload.model_dump(exclude_unset=True)
    if "owner_user_id" in data:
        _validate_owner(db, otd.tribe_id, data["owner_user_id"])
    for k, v in data.items():
        setattr(otd, k, v)
    record_audit(db, user.id, "otd.update", entity="otd", entity_id=otd.id, detail=list(data.keys()))
    db.commit()
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
        if len(db.execute(q).scalars().all()) != len(wanted):
            raise HTTPException(status_code=400, detail=refus)

    link = "squad_otd_id" if otd.scope == SQUAD_SCOPE else "otd_id"
    for j in list(otd.members):
        setattr(j, link, None)
    for j in db.scalars(select(RoadmapItem).where(RoadmapItem.id.in_(wanted))).all() if wanted else []:
        setattr(j, link, otd.id)
    record_audit(db, user.id, "otd.set_jalons", entity="otd", entity_id=otd.id,
                 detail={"jalon_ids": sorted(wanted), "scope": otd.scope})
    db.commit()
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
    db.delete(otd)  # milestones keep existing; their link is set NULL
    db.commit()
