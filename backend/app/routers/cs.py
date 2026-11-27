"""Customer Success: the projects a CS team delivers (ADR 0020, docs/37).

A flat list of projects per tribe. Each project has a short card (stage,
health, delivery, money, links), a dated **journal** and a short list
of **points to follow** (actions, risks, blockers). What the screens show on top of
that is computed, never typed twice:

* the **blocker** is the open blocker point (the oldest one);
* the **next action** is the open action due first;
* the **last contact** is the latest journal date;
* the dashboard badges (overdue points, access ending soon, no news) follow.

The **recap** is the mail the CS lead used to write by hand: an opening text, a
summary table, then per project its key facts and the journal entries ticked
"in the recap". Entries added since the recap was last marked as sent read "New".

Who may do what is in ``app/csaccess.py``. Gated by the optional
``customer_success`` module.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html import escape

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from .. import csaccess as acc
from .. import csconfig
from ..database import get_db
from ..deps import get_current_user, record_audit, require_module
from ..models import CsContributor, CsItem, CsJournalEntry, CsLeader, CsProject, Tribe, User

router = APIRouter(prefix="/api/cs", tags=["customer-success"],
                   dependencies=[Depends(require_module("customer_success"))])

JOURNAL_KINDS = ["request", "decision", "proposal", "delivery", "reminder", "blocker", "note"]
# Ticked "in the recap" by default: what the recap mail is made of.
RECAP_BY_DEFAULT = {"request", "decision", "proposal", "delivery"}
ITEM_KINDS = ["action", "risk", "blocker"]
HEALTH = {"green", "amber", "red"}
# Where the billing stands: to invoice, invoiced (waiting for the payment), paid.
BILLING = ("todo", "invoiced", "paid")
DISCOUNT_KINDS = ("pct", "amount")

_TEXT_FIELDS = {"title": 255, "client": 255, "requesters": 500,
                "cost_code": 255}
_DATE_FIELDS = ("planned_delivery", "actual_delivery")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return date.today()


# --------------------------------------------------------------------------
# Input cleaning
# --------------------------------------------------------------------------

def _date(v, field: str) -> date | None:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Date invalide ({field}) : AAAA-MM-JJ attendu")


def _text(v, n: int) -> str | None:
    v = str(v).strip() if v is not None else ""
    return v[:n] or None


def _links(raw) -> list[dict]:
    """Links only (ADR 0020: no file is stored). http(s) and nothing else, so a
    link can never run a script when clicked."""
    out = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        url = str(x.get("url") or "").strip()[:2000]
        if not url:
            continue
        if not (url.lower().startswith("https://") or url.lower().startswith("http://")):
            raise HTTPException(status_code=400, detail="Un lien commence par https:// ou http://")
        out.append({"label": str(x.get("label") or "").strip()[:200], "url": url})
    return out[:50]


def _amount(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        d = Decimal(str(v).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Montant invalide")
    if d < 0 or d > Decimal("9999999999"):
        raise HTTPException(status_code=400, detail="Montant invalide")
    return d.quantize(Decimal("0.01"))


def _apply(db: Session, p: CsProject, payload: dict, cfg: dict) -> None:
    for f, n in _TEXT_FIELDS.items():
        if f in payload:
            setattr(p, f, _text(payload.get(f), n))
    if "title" in payload and not p.title:
        raise HTTPException(status_code=400, detail="Le projet doit avoir un titre")
    for f in _DATE_FIELDS:
        if f in payload:
            setattr(p, f, _date(payload.get(f), f))
    if "stage" in payload:
        stage = str(payload.get("stage") or "")
        if stage not in csconfig.stage_keys(cfg):
            raise HTTPException(status_code=400, detail="Étape inconnue")
        p.stage = stage
    if "health" in payload:
        h = payload.get("health") or None
        if h is not None and h not in HEALTH:
            raise HTTPException(status_code=400, detail="Statut inconnu")
        p.health = h
    if "build_amount" in payload:
        p.build_amount = _amount(payload.get("build_amount"))
    if "discount_kind" in payload:
        k = payload.get("discount_kind") or "pct"
        if k not in DISCOUNT_KINDS:
            raise HTTPException(status_code=400, detail="Type de remise inconnu")
        p.discount_kind = k
    if "discount_value" in payload:
        p.discount_value = _amount(payload.get("discount_value"))
    if p.discount_value is not None:
        if p.discount_kind == "pct" and p.discount_value > 100:
            raise HTTPException(status_code=400, detail="Une remise ne dépasse pas 100 %")
        if p.discount_kind == "amount" and p.build_amount is not None and p.discount_value > Decimal(str(p.build_amount)):
            raise HTTPException(status_code=400, detail="La remise dépasse le prix")
    if "billing" in payload:
        b = payload.get("billing") or "todo"
        if b not in BILLING:
            raise HTTPException(status_code=400, detail="Facturation inconnue")
        p.billing = b
    if "links" in payload:
        p.links = _links(payload.get("links"))
    if "notes" in payload:
        p.notes = (str(payload.get("notes") or "").strip()[:20000]) or None


# --------------------------------------------------------------------------
# Computed facts and serialization
# --------------------------------------------------------------------------

def _iso(d) -> str | None:
    return d.isoformat() if d else None


def _blocker(p: CsProject) -> CsItem | None:
    open_ = [i for i in p.items if i.kind == "blocker" and not i.done]
    return min(open_, key=lambda i: (i.opened_on or date.max, i.id)) if open_ else None


def _next_action(p: CsProject) -> CsItem | None:
    open_ = [i for i in p.items if i.kind == "action" and not i.done]
    return min(open_, key=lambda i: (i.due or date.max, i.id)) if open_ else None


def _last_contact(p: CsProject) -> date | None:
    return max((e.entry_date for e in p.journal), default=None)


def facts(p: CsProject, cfg: dict, today: date | None = None) -> dict:
    """What the screens show on top of the stored fields."""
    today = today or _today()
    closed = p.stage in csconfig.closed_keys(cfg)
    b, a, last = _blocker(p), _next_action(p), _last_contact(p)
    since = last or (p.created_at.date() if p.created_at else today)
    overdue = sum(1 for i in p.items if not i.done and i.due and i.due < today)
    return {
        "closed": closed,
        "blocked": b is not None and not closed,
        "blocker": None if b is None else {
            "id": b.id, "label": b.label, "owner": b.owner, "since": _iso(b.opened_on),
            "days": (today - b.opened_on).days if b.opened_on else None},
        "next_action": None if a is None else {
            "id": a.id, "label": a.label, "owner": a.owner, "due": _iso(a.due),
            "overdue": bool(a.due and a.due < today)},
        "last_contact": _iso(last),
        "days_since_contact": (today - since).days,
        "stale": (not closed) and (today - since).days >= cfg["stale_days"],
        "overdue_items": overdue,
    }


def _item_out(i: CsItem) -> dict:
    return {"id": i.id, "kind": i.kind, "label": i.label, "owner": i.owner, "due": _iso(i.due),
            "opened_on": _iso(i.opened_on), "done": i.done, "done_on": _iso(i.done_on)}


def _entry_out(e: CsJournalEntry, marked: datetime | None = None) -> dict:
    created = e.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {"id": e.id, "date": _iso(e.entry_date), "kind": e.kind, "people": e.people,
            "text": e.text, "links": e.links or [], "in_recap": e.in_recap,
            "new": bool(marked is not None and created is not None and created > marked)}


def _project_out(db: Session, user: User, p: CsProject, cfg: dict, full: bool = False) -> dict:
    out = {
        "id": p.id, "tribe_id": p.tribe_id, "title": p.title, "client": p.client,
        "requesters": p.requesters,
        "stage": p.stage, "health": p.health,
        "planned_delivery": _iso(p.planned_delivery), "actual_delivery": _iso(p.actual_delivery),
        "build_amount": float(p.build_amount) if p.build_amount is not None else None,
        "discount_value": float(p.discount_value) if p.discount_value is not None else None,
        "discount_kind": p.discount_kind,
        "net_amount": float(p.net_amount) if p.net_amount is not None else None,
        "billing": p.billing, "cost_code": p.cost_code,
        "links": p.links or [], "notes": p.notes,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "can_edit": acc.can_edit(db, user, p),
        "can_run": acc.runs(db, user, p.tribe_id),
        **facts(p, cfg),
    }
    if full:
        marked = _marked(cfg)
        out["journal"] = [_entry_out(e, marked) for e in p.journal]
        out["items"] = [_item_out(i) for i in p.items]
        out["contributors"] = acc.contributors_of(p)
    return out


def _marked(cfg: dict) -> datetime | None:
    m = cfg.get("recap_marked_at")
    if not m:
        return None
    try:
        d = datetime.fromisoformat(m)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------

def _tribe(db: Session, tribe_id: int | None, user: User) -> int:
    tid = tribe_id if tribe_id is not None else user.tribe_id
    if tid is None:
        led = acc.led_tribe_ids(db, user)
        if led:
            tid = sorted(led)[0]
    if tid is None or db.get(Tribe, tid) is None:
        raise HTTPException(status_code=400, detail="Précisez la tribe")
    return int(tid)


def _visible_projects(db: Session, user: User, tid: int) -> list[CsProject]:
    q = db.query(CsProject).filter(CsProject.tribe_id == tid)
    if not acc.reads_tribe(db, user, tid):
        mine = acc.contributed_project_ids(db, user)
        if not mine:
            raise HTTPException(status_code=403, detail="Customer Success ne vous est pas ouvert")
        q = q.filter(CsProject.id.in_(mine))
    return q.order_by(CsProject.title).all()


def _project(db: Session, user: User, project_id: int) -> CsProject:
    p = db.get(CsProject, project_id)
    if p is None or not acc.can_see(db, user, p):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return p


def _editable(db: Session, user: User, project_id: int) -> CsProject:
    p = db.get(CsProject, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    acc.ensure_edit(db, user, p)
    return p


def _touch(p: CsProject) -> None:
    p.updated_at = _now()


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

@router.get("/settings")
def get_settings(tribe_id: int | None = Query(None), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """The tribe's stages and thresholds. Readable by anyone who sees a
    project of the tribe (the screens need the stage labels)."""
    tid = _tribe(db, tribe_id, user)
    if not (acc.reads_tribe(db, user, tid) or acc.can_designate(user, tid)
            or any(p.tribe_id == tid for p in db.query(CsProject).filter(
                CsProject.id.in_(acc.contributed_project_ids(db, user) or [-1])))):
        raise HTTPException(status_code=403, detail="Customer Success ne vous est pas ouvert")
    return {"tribe_id": tid, **csconfig.get(db, tid), "can_run": acc.runs(db, user, tid)}


@router.put("/settings")
def put_settings(payload: dict = Body(...), tribe_id: int | None = Query(None),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Change the stages (labels, order, colours, which ones count as done) and
    the thresholds. A stage still used by a project cannot be removed.
    CS leaders. Audited."""
    tid = _tribe(db, tribe_id, user)
    acc.ensure_runs(db, user, tid)
    patch = {k: v for k, v in payload.items()
             if k in ("stages", "stale_days", "recap_intro")}
    if "stages" in patch:
        new = csconfig.normalize({"stages": patch["stages"]})["stages"]
        if not patch["stages"]:
            raise HTTPException(status_code=400, detail="Il faut au moins une étape")
        keys = {s["key"] for s in new}
        used = {s for (s,) in db.query(CsProject.stage).filter(CsProject.tribe_id == tid).distinct()}
        gone = used - keys
        if gone:
            labels = {s["key"]: s["label"] for s in csconfig.get(db, tid)["stages"]}
            raise HTTPException(status_code=409, detail=(
                "Étape encore utilisée par un projet : "
                + ", ".join(sorted(labels.get(k, k) for k in gone))))
        patch["stages"] = new
    cfg = csconfig.save(db, tid, patch)
    record_audit(db, user.id, "cs.settings", entity="tribe", entity_id=tid,
                 detail={"keys": sorted(patch)})
    db.commit()
    return {"tribe_id": tid, **cfg, "can_run": True}


# --------------------------------------------------------------------------
# CS leaders
# --------------------------------------------------------------------------

def _leaders_out(db: Session, user: User, tid: int) -> dict:
    return {"tribe_id": tid, "leaders": acc.leaders_of(db, tid),
            "can_designate": acc.can_designate(user, tid),
            "can_exclude_default": user.role == "admin"}


@router.get("/leaders")
def list_leaders(tribe_id: int | None = Query(None), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """The tribe's CS leaders: its tribe leader (by default) and the designated users."""
    tid = _tribe(db, tribe_id, user)
    if not (acc.runs(db, user, tid) or acc.can_designate(user, tid)):
        raise HTTPException(status_code=403, detail="Réservé aux responsables Customer Success de cette tribe")
    return _leaders_out(db, user, tid)


@router.post("/leaders", status_code=201)
def designate_leader(payload: dict = Body(...), db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Designate a CS leader (``{"tribe_id", "user_id"}``): the administrator
    anywhere, the tribe leader on their own tribe. Audited."""
    tid = _tribe(db, payload.get("tribe_id"), user)
    if not acc.can_designate(user, tid):
        raise HTTPException(status_code=403,
                            detail="Seuls l'administrateur et le tribe leader désignent les responsables Customer Success")
    try:
        target = db.get(User, int(payload.get("user_id")))
    except (TypeError, ValueError):
        target = None
    if target is None or (target.status or "active") != "active":
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.role != "admin" and target.tribe_id != tid:
        raise HTTPException(status_code=400, detail="Cette personne n'appartient pas à votre tribe")
    row = db.query(CsLeader).filter(CsLeader.user_id == target.id, CsLeader.tribe_id == tid).one_or_none()
    if target.role == "tribe_leader" and target.tribe_id == tid:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(CsLeader(user_id=target.id, tribe_id=tid, excluded=False,
                        created_by_user_id=user.id, created_at=_now()))
    elif row.excluded:
        row.excluded = False
    record_audit(db, user.id, "cs.leader.add", entity="user", entity_id=target.id,
                 detail={"tribe_id": tid, "name": target.display_name})
    db.commit()
    return _leaders_out(db, user, tid)


@router.delete("/leaders/{user_id}")
def remove_leader(user_id: int, tribe_id: int | None = Query(None), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Withdraw a CS leader. Only the administrator withdraws a tribe leader's
    default designation. Audited."""
    tid = _tribe(db, tribe_id, user)
    if not acc.can_designate(user, tid):
        raise HTTPException(status_code=403,
                            detail="Seuls l'administrateur et le tribe leader désignent les responsables Customer Success")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    row = db.query(CsLeader).filter(CsLeader.user_id == target.id, CsLeader.tribe_id == tid).one_or_none()
    if target.role == "tribe_leader" and target.tribe_id == tid:
        if user.role != "admin":
            raise HTTPException(status_code=403,
                                detail="Seul l'administrateur retire au tribe leader sa désignation par défaut")
        if row is None:
            db.add(CsLeader(user_id=target.id, tribe_id=tid, excluded=True,
                            created_by_user_id=user.id, created_at=_now()))
        else:
            row.excluded = True
    elif row is not None:
        db.delete(row)
    record_audit(db, user.id, "cs.leader.remove", entity="user", entity_id=target.id,
                 detail={"tribe_id": tid, "name": target.display_name})
    db.commit()
    return _leaders_out(db, user, tid)


# --------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------

@router.get("/projects")
def list_projects(tribe_id: int | None = Query(None), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """The tribe's projects with their computed facts (blocker, next action, last
    contact, badges). A contributor gets only the projects they were named on."""
    tid = _tribe(db, tribe_id, user)
    cfg = csconfig.get(db, tid)
    return [_project_out(db, user, p, cfg) for p in _visible_projects(db, user, tid)]


@router.get("/dashboard")
def dashboard(tribe_id: int | None = Query(None), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """The figures above the projects: open, blocked, delivered this year, build
    amounts, and the three badges. Computed on the projects the caller sees."""
    tid = _tribe(db, tribe_id, user)
    cfg = csconfig.get(db, tid)
    projects = _visible_projects(db, user, tid)
    today = _today()
    rows = [(p, facts(p, cfg, today)) for p in projects]
    year = today.year
    open_ = [(p, f) for p, f in rows if not f["closed"]]
    last_stage = cfg["stages"][-1]["key"]
    return {
        "tribe_id": tid,
        "total": len(rows),
        "open": len(open_),
        "blocked": sum(1 for _, f in rows if f["blocked"]),
        "delivered_year": sum(1 for p, _ in rows if p.actual_delivery and p.actual_delivery.year == year),
        "year": year,
        # The money, by where its billing stands (any stage: a delivered project can
        # still be waiting for its invoice or its payment).
        # The net price, after the discount: what is actually invoiced.
        **{f"{b}_total": float(sum((p.net_amount or 0) for p, _ in rows if p.billing == b)) for b in BILLING},
        "overdue_items": sum(f["overdue_items"] for _, f in rows),
        "overdue_projects": sum(1 for _, f in rows if f["overdue_items"]),
        "stale": sum(1 for _, f in rows if f["stale"]),
        "by_stage": {s["key"]: sum(1 for p, _ in rows if p.stage == s["key"]) for s in cfg["stages"]},
        "stale_days": cfg["stale_days"],
    }


@router.post("/projects", status_code=201)
def create_project(payload: dict = Body(...), tribe_id: int | None = Query(None),
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Create a project (``title`` at least). CS leaders. Audited."""
    tid = _tribe(db, payload.get("tribe_id", tribe_id), user)
    acc.ensure_runs(db, user, tid)
    cfg = csconfig.get(db, tid)
    if not _text(payload.get("title"), 255):
        raise HTTPException(status_code=400, detail="Le projet doit avoir un titre")
    p = CsProject(tribe_id=tid, title="", stage=cfg["stages"][0]["key"],
                  links=[], created_by_user_id=user.id, created_at=_now(),
                  updated_at=_now())
    _apply(db, p, payload, cfg)
    db.add(p)
    db.flush()
    if "contributor_user_ids" in payload:
        _set_contributors(db, user, p, payload.get("contributor_user_ids"))
    record_audit(db, user.id, "cs.project.create", entity="cs_project", entity_id=p.id,
                 detail={"title": p.title, "tribe_id": tid})
    db.commit()
    db.refresh(p)
    return _project_out(db, user, p, cfg, full=True)


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """A project with its journal (most recent first), its points and its contributors."""
    p = _project(db, user, project_id)
    return _project_out(db, user, p, csconfig.get(db, p.tribe_id), full=True)


@router.put("/projects/{project_id}")
def update_project(project_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Change a project's card; only the fields sent change. CS leaders and the
    project's contributors; the contributors list is the CS leaders' alone."""
    p = _editable(db, user, project_id)
    cfg = csconfig.get(db, p.tribe_id)
    _apply(db, p, payload, cfg)
    if "contributor_user_ids" in payload:
        acc.ensure_runs(db, user, p.tribe_id)
        _set_contributors(db, user, p, payload.get("contributor_user_ids"))
    _touch(p)
    record_audit(db, user.id, "cs.project.update", entity="cs_project", entity_id=p.id,
                 detail={"title": p.title, "fields": sorted(payload)})
    db.commit()
    db.refresh(p)
    return _project_out(db, user, p, cfg, full=True)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Delete a project with its journal and its points. CS leaders. Audited."""
    p = _project(db, user, project_id)
    acc.ensure_runs(db, user, p.tribe_id)
    record_audit(db, user.id, "cs.project.delete", entity="cs_project", entity_id=p.id,
                 detail={"title": p.title, "tribe_id": p.tribe_id})
    db.delete(p)
    db.commit()
    return Response(status_code=204)


def _set_contributors(db: Session, user: User, p: CsProject, ids) -> None:
    """Replace the project's contributors. Active accounts of the project's tribe
    (any tribe for the administrator)."""
    wanted = []
    try:
        raw = [int(x) for x in (ids or [])]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Contributeur introuvable")
    for uid in dict.fromkeys(raw):
        target = db.get(User, uid)
        if target is None or (target.status or "active") != "active":
            raise HTTPException(status_code=400, detail="Contributeur introuvable")
        if user.role != "admin" and target.tribe_id != p.tribe_id:
            raise HTTPException(status_code=400, detail="Cette personne n'appartient pas à la tribe du projet")
        wanted.append(uid)
    have = {r.user_id: r for r in p.contributors}
    for uid, row in have.items():
        if uid not in wanted:
            p.contributors.remove(row)
    for uid in wanted:
        if uid not in have:
            p.contributors.append(CsContributor(user_id=uid, created_at=_now()))


# --------------------------------------------------------------------------
# Journal
# --------------------------------------------------------------------------

def _apply_entry(e: CsJournalEntry, payload: dict, creating: bool) -> None:
    if "kind" in payload or creating:
        kind = payload.get("kind") or "note"
        if kind not in JOURNAL_KINDS:
            raise HTTPException(status_code=400, detail="Type d'entrée inconnu")
        e.kind = kind
    if "date" in payload or creating:
        d = _date(payload.get("date"), "date")
        e.entry_date = d or _today()
    if "people" in payload:
        e.people = _text(payload.get("people"), 500)
    if "text" in payload or creating:
        e.text = str(payload.get("text") or "").strip()[:20000]
        if not e.text:
            raise HTTPException(status_code=400, detail="L'entrée est vide")
    if "links" in payload:
        e.links = _links(payload.get("links"))
    if "in_recap" in payload:
        e.in_recap = bool(payload.get("in_recap"))
    elif creating:
        e.in_recap = e.kind in RECAP_BY_DEFAULT


@router.post("/projects/{project_id}/journal", status_code=201)
def add_entry(project_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Add a journal entry (``date`` defaults to today, a past date is fine).
    ``in_recap`` defaults on for requests, decisions, proposals and deliveries."""
    p = _editable(db, user, project_id)
    e = CsJournalEntry(project_id=p.id, links=[], created_by_user_id=user.id, created_at=_now())
    _apply_entry(e, payload, creating=True)
    db.add(e)
    _touch(p)
    db.commit()
    db.refresh(e)
    return _entry_out(e, _marked(csconfig.get(db, p.tribe_id)))


def _entry(db: Session, user: User, entry_id: int) -> tuple[CsJournalEntry, CsProject]:
    e = db.get(CsJournalEntry, entry_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Entrée introuvable")
    p = _editable(db, user, e.project_id)
    return e, p


@router.put("/journal/{entry_id}")
def update_entry(entry_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    e, p = _entry(db, user, entry_id)
    _apply_entry(e, payload, creating=False)
    _touch(p)
    db.commit()
    db.refresh(e)
    return _entry_out(e, _marked(csconfig.get(db, p.tribe_id)))


@router.delete("/journal/{entry_id}", status_code=204)
def delete_entry(entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    e, p = _entry(db, user, entry_id)
    db.delete(e)
    _touch(p)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Points to follow
# --------------------------------------------------------------------------

def _apply_item(i: CsItem, payload: dict, creating: bool) -> None:
    if "kind" in payload or creating:
        kind = payload.get("kind") or "action"
        if kind not in ITEM_KINDS:
            raise HTTPException(status_code=400, detail="Type de point inconnu")
        i.kind = kind
    if "label" in payload or creating:
        i.label = str(payload.get("label") or "").strip()[:500]
        if not i.label:
            raise HTTPException(status_code=400, detail="Le point doit avoir un libellé")
    if "owner" in payload:
        i.owner = _text(payload.get("owner"), 255)
    if "due" in payload:
        i.due = _date(payload.get("due"), "échéance")
    if "opened_on" in payload or creating:
        i.opened_on = _date(payload.get("opened_on"), "depuis") or (i.opened_on or _today())
    if "done" in payload:
        done = bool(payload.get("done"))
        if done and not i.done:
            i.done_on = _today()
        if not done:
            i.done_on = None
        i.done = done


@router.post("/projects/{project_id}/items", status_code=201)
def add_item(project_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Add a point to follow: an action, a risk or a blocker."""
    p = _editable(db, user, project_id)
    i = CsItem(project_id=p.id, created_at=_now(), done=False)
    _apply_item(i, payload, creating=True)
    db.add(i)
    _touch(p)
    db.commit()
    db.refresh(i)
    return _item_out(i)


def _item(db: Session, user: User, item_id: int) -> tuple[CsItem, CsProject]:
    i = db.get(CsItem, item_id)
    if i is None:
        raise HTTPException(status_code=404, detail="Point introuvable")
    return i, _editable(db, user, i.project_id)


@router.put("/items/{item_id}")
def update_item(item_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    i, p = _item(db, user, item_id)
    _apply_item(i, payload, creating=False)
    _touch(p)
    db.commit()
    db.refresh(i)
    return _item_out(i)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    i, p = _item(db, user, item_id)
    db.delete(i)
    _touch(p)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------
# The recap
# --------------------------------------------------------------------------

RECAP_L = {
    "fr": {
        "summary": "En résumé", "h_topic": "Sujet", "h_requester": "Demandeur",
        "h_status": "Statut",
        "delivered_on": "Livré le {d}",
        "blocked": "En attente : {label}", "new": "Nouveau", "open_points": "Points ouverts",
        "due": "échéance {d}", "no_project": "Aucun projet dans ce périmètre.",
        "discount": "({off} de remise sur {price})",
        "f_amount": "Prix", "billing": {"todo": "à facturer", "invoiced": "facturé", "paid": "payé"},
        "f_cost_code": "Code d'imputation",
        "f_planned": "Livraison prévue", "f_delivered": "Livré le",
        "kind": {"request": "Demande", "decision": "Décision", "proposal": "Proposition",
                 "delivery": "Livraison", "reminder": "Relance", "blocker": "Blocage", "note": "Note"},
        "item": {"action": "Action", "risk": "Risque", "blocker": "Blocage"},
    },
    "en": {
        "summary": "Summary", "h_topic": "Topic", "h_requester": "Requester",
        "h_status": "Status",
        "delivered_on": "Delivered on {d}",
        "blocked": "Waiting for: {label}", "new": "New", "open_points": "Open points",
        "due": "due {d}", "no_project": "No project in this scope.",
        "discount": "({off} off {price})",
        "f_amount": "Price", "billing": {"todo": "not invoiced yet", "invoiced": "awaiting payment", "paid": "paid"},
        "f_cost_code": "Cost code",
        "f_planned": "Planned delivery", "f_delivered": "Delivered on",
        "kind": {"request": "Request", "decision": "Decision", "proposal": "Proposal",
                 "delivery": "Delivery", "reminder": "Reminder", "blocker": "Blocker", "note": "Note"},
        "item": {"action": "Action", "risk": "Risk", "blocker": "Blocker"},
    },
}

_FONT = "font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#1D2939"
_TD = "border:1px solid #D0D5DD;padding:4px 8px;vertical-align:top"


def _dm(d: date | None, lang: str) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m") if lang == "fr" else d.strftime("%d %b")


def _amount_txt(v: Decimal | None, lang: str) -> str:
    if v is None:
        return ""
    n = f"{v:,.0f}" if v == v.to_integral() else f"{v:,.2f}"
    if lang == "fr":
        n = n.replace(",", " ").replace(".", ",")
        return f"{n} € HT"
    return f"€{n} excl. VAT"


def _discount_txt(p: CsProject, L: dict, lang: str) -> str:
    """ " (10 % de remise sur 10 000 € HT)", or nothing without a discount."""
    if not p.discount_value:
        return ""
    off = (f"{p.discount_value:g} %" if p.discount_kind == "pct" else _amount_txt(p.discount_value, lang))
    return " " + L["discount"].format(off=off, price=_amount_txt(p.build_amount, lang))


def _status_txt(p: CsProject, f: dict, cfg: dict, L: dict, lang: str) -> str:
    if p.actual_delivery and f["closed"]:
        return L["delivered_on"].format(d=_dm(p.actual_delivery, lang))
    if f["blocker"]:
        return L["blocked"].format(label=f["blocker"]["label"])
    labels = {s["key"]: csconfig.stage_label(s, lang) for s in cfg["stages"]}
    return labels.get(p.stage, p.stage)


def _p(text: str) -> str:
    """Plain text to paragraphs (blank lines) and line breaks, escaped."""
    blocks = [b.strip() for b in (text or "").replace("\r\n", "\n").split("\n\n")]
    return "".join(f'<p style="margin:0 0 8px">{escape(b).replace(chr(10), "<br>")}</p>'
                   for b in blocks if b)


def _project_facts(p: CsProject, L: dict, lang: str) -> list[str]:
    out = []

    def add(label, value):
        if value:
            out.append(f"<li><b>{escape(label)}</b> : {escape(str(value))}</li>" if lang == "fr"
                       else f"<li><b>{escape(label)}</b>: {escape(str(value))}</li>")
    if p.build_amount is not None:
        add(L["f_amount"], f"{_amount_txt(p.net_amount, lang)}{_discount_txt(p, L, lang)}, "
                           f"{L['billing'].get(p.billing, p.billing)}")
    add(L["f_cost_code"], p.cost_code)
    if p.actual_delivery:
        add(L["f_delivered"], p.actual_delivery.strftime("%d/%m/%Y"))
    elif p.planned_delivery:
        add(L["f_planned"], p.planned_delivery.strftime("%d/%m/%Y"))
    return out


def recap_html(db: Session, user: User, tid: int, lang: str = "fr",
               stages: list[str] | None = None,
               project_ids: list[int] | None = None) -> str:
    """The recap mail, as HTML that pastes cleanly into Outlook (inline styles,
    tables, no script, no external resource)."""
    L = RECAP_L.get(lang, RECAP_L["fr"])
    cfg = csconfig.get(db, tid)
    marked = _marked(cfg)
    order = {k: i for i, k in enumerate(csconfig.stage_keys(cfg))}
    projects = _visible_projects(db, user, tid)
    if stages:
        projects = [p for p in projects if p.stage in stages]
    if project_ids:
        projects = [p for p in projects if p.id in project_ids]
    projects.sort(key=lambda p: (order.get(p.stage, 99), p.title.lower()))
    today = _today()

    parts = [f'<div style="{_FONT}">']
    parts.append(_p(cfg["recap_intro"]))
    if not projects:
        parts.append(f"<p>{escape(L['no_project'])}</p></div>")
        return "".join(parts)

    parts.append(f'<p style="margin:12px 0 4px"><b>{escape(L["summary"])}</b></p>')
    parts.append(f'<table style="border-collapse:collapse;{_FONT}">')
    parts.append("<tr>" + "".join(
        f'<th style="{_TD};background:#F2F4F7;text-align:left">{escape(h)}</th>'
        for h in (L["h_topic"], L["h_requester"], L["h_status"])) + "</tr>")
    rows = [(p, facts(p, cfg, today)) for p in projects]
    for p, f in rows:
        topic = f"{p.client} : {p.title}" if p.client and lang == "fr" else (
            f"{p.client}: {p.title}" if p.client else p.title)
        parts.append("<tr>" + "".join(f'<td style="{_TD}">{escape(c)}</td>' for c in (
            topic, p.requesters or "", _status_txt(p, f, cfg, L, lang))) + "</tr>")
    parts.append("</table>")

    for n, (p, f) in enumerate(rows, start=1):
        topic = f"{p.client} : {p.title}" if p.client and lang == "fr" else (
            f"{p.client}: {p.title}" if p.client else p.title)
        parts.append(f'<p style="margin:16px 0 4px;font-size:12pt"><b>{n}. {escape(topic)}</b></p>')
        bullets = _project_facts(p, L, lang)
        if bullets:
            parts.append('<ul style="margin:0 0 6px">' + "".join(bullets) + "</ul>")
        entries = sorted((e for e in p.journal if e.in_recap), key=lambda e: (e.entry_date, e.id))
        if entries:
            parts.append('<ul style="margin:0 0 6px">')
            for e in entries:
                head = L["kind"].get(e.kind, e.kind)
                if e.people:
                    head += f" ({escape(e.people)}, {_dm(e.entry_date, lang)})"
                else:
                    head += f" ({_dm(e.entry_date, lang)})"
                created = e.created_at
                if created is not None and created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                new = (f' <span style="background:#E8F0FE;color:#13315C;padding:0 4px">'
                       f'{escape(L["new"])}</span>') if marked and created and created > marked else ""
                sep = " : " if lang == "fr" else ": "
                body = escape(e.text).replace("\n", "<br>")
                links = "".join(f' <a href="{escape(l["url"])}">{escape(l["label"] or l["url"])}</a>'
                                for l in (e.links or []))
                # ``head`` is built from escaped parts (the kind labels are constants).
                parts.append(f"<li><b>{head}</b>{new}{sep}{body}{links}</li>")
            parts.append("</ul>")
        open_items = [i for i in p.items if not i.done]
        if open_items:
            parts.append(f'<p style="margin:4px 0 2px"><i>{escape(L["open_points"])}</i></p><ul style="margin:0 0 6px">')
            for i in open_items:
                tail = []
                if i.owner:
                    tail.append(escape(i.owner))
                if i.due:
                    tail.append(escape(L["due"].format(d=_dm(i.due, lang))))
                extra = f" ({', '.join(tail)})" if tail else ""
                parts.append(f"<li>{escape(L['item'].get(i.kind, i.kind))} : {escape(i.label)}{extra}</li>"
                             if lang == "fr" else
                             f"<li>{escape(L['item'].get(i.kind, i.kind))}: {escape(i.label)}{extra}</li>")
            parts.append("</ul>")
    parts.append("</div>")
    return "".join(parts)


def _ids(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Liste de projets invalide")


@router.get("/recap.html", response_class=HTMLResponse)
def recap(tribe_id: int | None = Query(None), lang: str = Query("fr"),
          stages: str | None = Query(None, description="Étapes retenues, séparées par des virgules"),
          projects: str | None = Query(None),
          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The recap mail as HTML, ready to paste into Outlook. Shows the projects the
    caller sees, filtered by stages or a list of project ids."""
    tid = _tribe(db, tribe_id, user)
    st = [s for s in (stages or "").split(",") if s] or None
    html = recap_html(db, user, tid, "en" if lang == "en" else "fr", st, _ids(projects))
    return HTMLResponse(html)


@router.get("/export.html", response_class=HTMLResponse)
def export_html(tribe_id: int | None = Query(None), lang: str = Query("fr"), closed: bool = Query(True),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The projects the caller sees as a standalone page: the four figures, then
    one line per project (the HTML of the Export menu, and its JPG)."""
    from ..csreport import build_cs_list, render_cs_html
    tid = _tribe(db, tribe_id, user)
    return HTMLResponse(render_cs_html(build_cs_list(db, user, tid, lang, closed=closed)))


@router.get("/export.pptx")
def export_pptx(tribe_id: int | None = Query(None), lang: str = Query("fr"), closed: bool = Query(True),
                template_id: int | None = Query(None),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The same projects as a deck, through the tribe's export template (Studio,
    document "Customer Success"). Returns 501 if python-pptx is not installed."""
    from .. import exportstore
    from ..csreport import build_cs_list
    tid = _tribe(db, tribe_id, user)
    data = build_cs_list(db, user, tid, lang, closed=closed)
    try:
        payload, filename, _m = exportstore.render(
            db, user, "cs", {"cs": lambda: data}, chain=exportstore.chain_for(db, tribe_id=tid),
            lang=data["lang"], scope_name=data["scope_name"], year=data["year"], template_id=template_id,
            legacy_name=f"customer_success_{date.today().isoformat()}.pptx")
    except ImportError:
        raise HTTPException(status_code=501, detail="Génération PPTX indisponible (python-pptx non installé)")
    except LookupError:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    db.commit()
    return Response(content=payload,
                    media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/recap/mark")
def mark_recap(tribe_id: int | None = Query(None), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Note that the recap was sent: entries added after now will read "New" in
    the next one. CS leaders."""
    tid = _tribe(db, tribe_id, user)
    acc.ensure_runs(db, user, tid)
    cfg = csconfig.save(db, tid, {"recap_marked_at": _now().isoformat()})
    record_audit(db, user.id, "cs.recap.mark", entity="tribe", entity_id=tid)
    db.commit()
    return {"tribe_id": tid, "recap_marked_at": cfg["recap_marked_at"]}
