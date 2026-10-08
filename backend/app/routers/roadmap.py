"""Roadmap milestone (jalon) endpoints (prefix ``/api/roadmap-items``).

Milestones are the quarter-level deliverables a squad tracks. This router covers
theme autocomplete and milestone CRUD. The whole router is gated by the
``squad_content``/``roadmap`` module.

Access model: all mutations require ``require_writer`` and, per milestone, that
the caller reports for the owning squad (``assert_reports_for_squad``: leader,
admin). On write, the dependency reference is normalized to match the chosen
kind, and a milestone moved to another year leaves the commitments and the
initiative of the old one. The OTD a milestone delivers (management and squad)
can be picked on the milestone itself, under the rules of ``may_link_otd``. Mutations are audited and emit ``notify_change(..., "roadmap",
...)``.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_reports_for_squad, record_audit, require_module, require_writer, update_data
from ..changenotify import notify_change
from ..models import RoadmapItem, Squad, User
from ..schemas import RoadmapItemCreate, RoadmapItemOut, RoadmapItemUpdate
from ..serializers import roadmap_item_out

router = APIRouter(prefix="/api/roadmap-items", tags=["roadmap"],
                   dependencies=[Depends(require_module("squad_content", "roadmap"))])


@router.get("/themes", response_model=list[str])
def list_themes(db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """GET /api/roadmap-items/themes: distinct existing milestone themes,
    most-used first, for reuse/autocomplete.

    Requires ``require_writer``. Scoped to the writer's visibility: admins see
    every theme, others see the themes used across their own tribe's squads."""
    q = (select(RoadmapItem.theme, func.count(RoadmapItem.id).label("n"))
         .where(RoadmapItem.theme.is_not(None), func.trim(RoadmapItem.theme) != "")
         .group_by(RoadmapItem.theme))
    if user.role != "admin":
        q = q.join(Squad, Squad.id == RoadmapItem.squad_id).where(Squad.tribe_id == user.tribe_id)
    rows = db.execute(q.order_by(func.count(RoadmapItem.id).desc())).all()
    return [theme for theme, _ in rows]


def _check_dependency_target(db: Session, item: RoadmapItem) -> None:
    """The squad or tribe a milestone depends on must exist (the foreign key
    otherwise failed as a 500). Called after _normalize_dependency."""
    from ..models import Tribe
    # No autoflush: on an update the item is already dirty with the unknown id.
    with db.no_autoflush:
        if item.dependency_squad_id is not None and db.get(Squad, item.dependency_squad_id) is None:
            raise HTTPException(status_code=400, detail="Squad de dépendance introuvable")
        if item.dependency_tribe_id is not None and db.get(Tribe, item.dependency_tribe_id) is None:
            raise HTTPException(status_code=400, detail="Tribe de dépendance introuvable")


def _normalize_dependency(item: RoadmapItem) -> None:
    """Keep only the reference matching the chosen dependency kind (clear the others)."""
    kind = item.dependency_kind
    if kind == "squad":
        item.dependency_tribe_id = None
    elif kind == "tribe":
        item.dependency_squad_id = None
    else:  # text or none
        item.dependency_squad_id = None
        item.dependency_tribe_id = None
        if kind not in ("text", None):
            item.dependency_kind = None


def _normalize_stage(item: RoadmapItem) -> None:
    """« Autre » se nomme; les autres phases n'ont pas de libelle libre."""
    if item.release_stage == "OT":
        item.release_stage_other = (item.release_stage_other or "").strip() or None
        if not item.release_stage_other:
            raise HTTPException(status_code=422, detail="Précisez le type du jalon (phase « Autre »)")
    else:
        item.release_stage_other = None


# The two commitments a milestone can deliver, and the scope each link belongs to.
OTD_LINKS = {"otd_id": "management", "squad_otd_id": "squad"}


def may_link_otd(db: Session, user: User, item: RoadmapItem, otd) -> bool:
    """May ``user`` attach this milestone to ``otd`` (or detach it from it).

    An engagement de squad: whoever reports for the squad, which ``assert_reports_
    for_squad`` already checked. An engagement management: its writers (the tribe
    leader of its tribe, the admin), and also the squad's own reporting people when
    the commitment was fixed on their squad: management fixes the promise, the
    squad knows which of its milestones keep it. Same for the squad leader the
    commitment is assigned to. A management commitment of the whole tribe, assigned
    to nobody, stays with the tribe leader."""
    if otd.scope == "squad":
        return otd.squad_id == item.squad_id
    if user.role == "admin":
        return True
    if user.role == "tribe_leader" and user.tribe_id == otd.tribe_id:
        return True
    if otd.squad_id is not None and otd.squad_id == item.squad_id:
        return True
    return otd.owner_user_id is not None and otd.owner_user_id == user.id


def _apply_otd_links(db: Session, user: User, item: RoadmapItem, links: dict) -> None:
    """Set the OTD links asked for, after the year and the squad are known.

    A link is checked like the OTD screen checks it: the commitment exists, is of
    the scope of the link, belongs to the milestone's tribe (management) or squad
    (squad), and is of the milestone's year. Leaving a commitment needs the same
    right as joining it, so nobody quietly unhooks a link they could not have set."""
    from ..models import Otd
    for key, value in links.items():
        current = getattr(item, key)
        if value == current:
            continue
        if current is not None:
            cur = db.get(Otd, current)
            if cur is not None and not may_link_otd(db, user, item, cur):
                raise HTTPException(status_code=403,
                                    detail="Ce jalon est rattaché à un OTD que vous ne gérez pas")
        if value is not None:
            otd = db.get(Otd, value)
            if otd is None or otd.scope != OTD_LINKS[key]:
                raise HTTPException(status_code=400, detail="OTD introuvable")
            squad = db.get(Squad, item.squad_id)
            if otd.scope == "squad" and otd.squad_id != item.squad_id:
                raise HTTPException(status_code=400, detail="Cet OTD n'est pas celui de cette squad")
            if otd.scope == "management" and (squad is None or otd.tribe_id != squad.tribe_id):
                raise HTTPException(status_code=400, detail="Un jalon n'appartient pas à cette tribe")
            if otd.year != item.year:
                raise HTTPException(status_code=400, detail="Un jalon n'est pas de l'année de cet engagement")
            if not may_link_otd(db, user, item, otd):
                raise HTTPException(status_code=403, detail="Cet OTD est géré par le tribe leader")
        setattr(item, key, value)


MAX_DEPENDENCIES = 20


def set_dependencies(db: Session, item: RoadmapItem, entries) -> None:
    """Replace the milestone's dependencies, in order, without duplicates, and
    mirror the first one in the single dependency_* columns. A squad or tribe that
    does not exist is refused (400), as for the single dependency."""
    from ..models import RoadmapDependency, Tribe
    clean, seen = [], set()
    for e in entries or []:
        e = e.model_dump() if hasattr(e, "model_dump") else dict(e)
        kind = e.get("kind")
        if kind == "squad" and e.get("squad_id"):
            key, row = ("squad", int(e["squad_id"])), {"kind": "squad", "squad_id": int(e["squad_id"])}
            if row["squad_id"] == item.squad_id:
                continue                      # a milestone does not wait on its own squad
            with db.no_autoflush:
                if db.get(Squad, row["squad_id"]) is None:
                    raise HTTPException(status_code=400, detail="Squad de dépendance introuvable")
        elif kind == "tribe" and e.get("tribe_id"):
            key, row = ("tribe", int(e["tribe_id"])), {"kind": "tribe", "tribe_id": int(e["tribe_id"])}
            with db.no_autoflush:
                if db.get(Tribe, row["tribe_id"]) is None:
                    raise HTTPException(status_code=400, detail="Tribe de dépendance introuvable")
        elif kind == "text" and (e.get("text") or "").strip():
            txt = e["text"].strip()[:500]
            key, row = ("text", txt.lower()), {"kind": "text", "text": txt}
        else:
            continue
        if key in seen:
            continue
        seen.add(key)
        clean.append(row)
    if len(clean) > MAX_DEPENDENCIES:
        raise HTTPException(status_code=422, detail="20 dépendances au plus par jalon")
    item.deps = [RoadmapDependency(position=i, kind=r["kind"], squad_id=r.get("squad_id"),
                                   tribe_id=r.get("tribe_id"), text=r.get("text")) for i, r in enumerate(clean)]
    first = clean[0] if clean else None
    item.dependency_kind = first["kind"] if first else None
    item.dependency_squad_id = first.get("squad_id") if first else None
    item.dependency_tribe_id = first.get("tribe_id") if first else None
    item.dependencies = first.get("text") if first and first["kind"] == "text" else None


def _single_to_list(item: RoadmapItem) -> list[dict]:
    """The single dependency_* fields as a one-entry list (older clients)."""
    if item.dependency_kind == "squad" and item.dependency_squad_id:
        return [{"kind": "squad", "squad_id": item.dependency_squad_id}]
    if item.dependency_kind == "tribe" and item.dependency_tribe_id:
        return [{"kind": "tribe", "tribe_id": item.dependency_tribe_id}]
    if (item.dependencies or "").strip():
        return [{"kind": "text", "text": item.dependencies}]
    return []


@router.post("", response_model=RoadmapItemOut, status_code=201)
def create_item(payload: RoadmapItemCreate, db: Session = Depends(get_db),
                user: User = Depends(require_writer)):
    """POST /api/roadmap-items: create a milestone (201).

    Writer who reports for the target squad (``assert_reports_for_squad``). The
    dependency reference is normalized before insert. Audited, then ``notify_change(..., "roadmap", ...)``."""
    if db.get(Squad, payload.squad_id) is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_reports_for_squad(db, user, payload.squad_id)
    fields = payload.model_dump()
    links = {k: fields.pop(k) for k in OTD_LINKS if fields.get(k) is not None}
    for k in OTD_LINKS:
        fields.pop(k, None)
    dep_list = fields.pop("dependency_list", None)
    item = RoadmapItem(**fields)
    _normalize_stage(item)
    _normalize_dependency(item)
    _check_dependency_target(db, item)
    set_dependencies(db, item, payload.dependency_list if dep_list is not None else _single_to_list(item))
    with db.no_autoflush:
        _apply_otd_links(db, user, item, links)
    db.add(item)
    db.flush()
    record_audit(db, user.id, "roadmap.create", entity="roadmap_item", entity_id=item.id,
                 detail={"squad_id": item.squad_id, "year": item.year, "quarter": item.quarter, "title": item.title})
    db.commit()
    db.refresh(item)
    notify_change(item.squad_id, "roadmap", user, item.year)
    return roadmap_item_out(item)


@router.put("/{item_id}", response_model=RoadmapItemOut)
def update_item(item_id: int, payload: RoadmapItemUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_writer)):
    """PUT /api/roadmap-items/{item_id}: update a milestone.

    Writer who leads the milestone's squad only. Dependency fields are re-
    normalized when they are part of the update. Audited, then ``notify_change(..., "roadmap", ...)``."""
    item = db.get(RoadmapItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Jalon introuvable")
    assert_reports_for_squad(db, user, item.squad_id)
    data = update_data(payload, RoadmapItem)
    links = {k: data.pop(k) for k in list(data) if k in OTD_LINKS}
    dep_list = data.pop("dependency_list", None) if "dependency_list" in data else None
    for k, v in data.items():
        setattr(item, k, v)
    if "release_stage" in data or "release_stage_other" in data:
        _normalize_stage(item)
    if dep_list is not None:
        set_dependencies(db, item, payload.dependency_list)
        data["dependency_list"] = [{k: v for k, v in d.items() if v is not None} for d in dep_list]
    elif "dependency_kind" in data or "dependency_squad_id" in data or "dependency_tribe_id" in data \
            or "dependencies" in data:
        _normalize_dependency(item)
        _check_dependency_target(db, item)
        set_dependencies(db, item, _single_to_list(item))
    # Moved to another year: the commitments and the initiative of the old year
    # no longer count it (set_otd_jalons refuses a milestone of another year).
    if "year" in data:
        from ..models import Initiative, Otd
        for col, model in (("otd_id", Otd), ("squad_otd_id", Otd), ("initiative_id", Initiative)):
            ref = getattr(item, col)
            if ref is None or col in data:
                continue
            target = db.get(model, ref)
            if target is not None and target.year != item.year:
                setattr(item, col, None)
    if links:
        with db.no_autoflush:
            _apply_otd_links(db, user, item, links)
        data.update(links)
    record_audit(db, user.id, "roadmap.update", entity="roadmap_item", entity_id=item.id, detail=data)
    db.commit()
    db.refresh(item)
    notify_change(item.squad_id, "roadmap", user, item.year)
    return roadmap_item_out(item)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """DELETE /api/roadmap-items/{item_id}: delete a milestone (204).

    Writer who leads the milestone's squad only. Audited, then
    ``notify_change(..., "roadmap", ...)``."""
    item = db.get(RoadmapItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Jalon introuvable")
    assert_reports_for_squad(db, user, item.squad_id)
    sq_id, yr = item.squad_id, item.year
    record_audit(db, user.id, "roadmap.delete", entity="roadmap_item", entity_id=item.id,
                 detail={"squad_id": item.squad_id})
    db.delete(item)
    db.commit()
    notify_change(sq_id, "roadmap", user, yr)
