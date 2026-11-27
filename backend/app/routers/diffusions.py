"""Administration > Reports by email: the diffusions (app/reportconfig.py).

A diffusion is one scheduled mailing. The admin sees and sets every one, the
Direction's included; a persona holding the "report" tab (by default the tribe
leader) those of its own tribe only. The change alerts stay the admin's
(routers/admin.py, change-notify-config).

The screen edits a draft: ``/plan`` and ``/preview`` take the settings being
edited (``{"cfg": {...}}``) and save nothing, so the list of recipients and the
mail follow every click before Save. A real mail (test, send now) uses what is
saved.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import ADMIN, get_current_user, record_audit
from ..models import Squad, Tribe, User
from ..tabaccess import acting_manager

router = APIRouter(prefix="/api/admin/diffusions", tags=["admin"])


def _scope(db: Session, user: User, tribe_id: int | None) -> int | None:
    """Check that ``user`` may act on a diffusion of this scope (None = the
    Direction, admin only). 403 / 404 otherwise."""
    if user.role == ADMIN:
        if tribe_id is not None and db.get(Tribe, tribe_id) is None:
            raise HTTPException(status_code=404, detail="Tribe introuvable")
        return tribe_id
    me = acting_manager(db, user, "report")
    if tribe_id is None or tribe_id != me.tribe_id:
        raise HTTPException(status_code=403, detail="Seules les diffusions de votre tribe vous sont ouvertes")
    return tribe_id


def _own(db: Session, user: User, diffusion_id: int) -> dict:
    from ..reportconfig import get_diffusion
    cfg = get_diffusion(db, diffusion_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Diffusion introuvable")
    _scope(db, user, cfg["tribe_id"])
    return cfg


def _clean_payload(db: Session, tid: int | None, payload: dict | None) -> dict:
    """What the screen sends, kept to what the scope may set: the bookkeeping
    goes, and in a tribe's diffusion the squads and the people named are those
    of the tribe."""
    from ..reportconfig import BOOKKEEPING
    payload = {k: v for k, v in (payload or {}).items()
               if k not in BOOKKEEPING and k != "tribe_id" and not k.startswith("_")}
    if tid is None:
        for k in ("leader_tribe", "leader_squads", "squad_ids", "copy_leader", "copy_co_leaders",
                  "copy_contributors"):
            payload.pop(k, None)
        return payload
    own = set(db.scalars(select(Squad.id).where(Squad.tribe_id == tid)).all())
    people = set(db.scalars(select(User.id).where(User.tribe_id == tid)).all())

    def _mine(ids):
        return [int(i) for i in (ids or []) if str(i).lstrip("-").isdigit() and int(i) in own]
    if "squad_ids" in payload:
        payload["squad_ids"] = _mine(payload.get("squad_ids"))
    if "copies" in payload:
        copies = []
        for c in payload.get("copies") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "user":
                try:
                    if int(c.get("value")) not in people:
                        raise HTTPException(status_code=400, detail="Personne hors de cette tribe")
                except (TypeError, ValueError):
                    continue
            copies.append({**c, "squad_ids": _mine(c.get("squad_ids"))})
        payload["copies"] = copies
    return payload


def _draft(db: Session, user: User, payload: dict | None) -> dict:
    """The settings being edited (``payload["cfg"]``), checked but not saved: of
    a saved diffusion (``cfg.id``) or of a new one (``cfg.tribe_id``)."""
    from ..reportconfig import defaults, normalize
    raw = (payload or {}).get("cfg")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Réglages manquants")
    if raw.get("id"):
        base = _own(db, user, int(raw["id"]))
    else:
        tid = raw.get("tribe_id")
        base = defaults(_scope(db, user, int(tid) if tid is not None else None))
    return normalize(base, _clean_payload(db, base["tribe_id"], raw))


def _plan_rows(db: Session, cfg: dict) -> list[dict]:
    from ..mailplan import plan_for
    return [{k: m.get(k) for k in ("key", "kind", "label", "squad_id", "recipients", "missing", "docs")}
            for m in plan_for(db, cfg)]


def _card(db: Session, cfg: dict, last: dict | None) -> dict:
    """A diffusion as its card shows it: the settings, the next send, the last
    one, and who receives it (counts and the first names)."""
    from ..mailplan import plan_for
    from ..report import next_send
    mails = plan_for(db, cfg)
    to, cc = {}, {}
    for m in mails:
        for r in m["recipients"]:
            (to if r["role"] == "to" else cc).setdefault(r["email"].lower(), r["name"] or r["email"])
    for k in to:
        cc.pop(k, None)
    nxt = next_send(cfg)
    tribe = db.get(Tribe, cfg["tribe_id"]) if cfg["tribe_id"] is not None else None
    return {**cfg, "_tribe_name": tribe.name if tribe else None, "_next": nxt.isoformat() if nxt else None,
            "_last": last, "_mails": len(mails), "_to": list(to.values()), "_cc": list(cc.values()),
            "_missing": list(dict.fromkeys(x["name"] for m in mails for x in m["missing"]))}


@router.get("")
def list_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/admin/diffusions: the diffusions this user may set (every one for
    the admin, its own tribe's otherwise), as cards. ``tribes`` lists the scopes
    a new diffusion can take, ``direction`` whether the Direction is one of them,
    ``smtp`` whether mails can go out at all. The schedules of the earlier
    shapes are converted on the way (reportconfig.ensure_diffusions)."""
    from ..reportconfig import ensure_diffusions, list_diffusions
    from ..report import last_sends
    from ..smtpconfig import get_smtp
    if user.role == ADMIN:
        tribes = db.scalars(select(Tribe).order_by(Tribe.name)).all()
    else:
        me = acting_manager(db, user, "report")
        tribes = [t for t in [db.get(Tribe, me.tribe_id)] if t is not None]
    if ensure_diffusions(db):
        db.commit()
    ids = {t.id for t in tribes}
    last = last_sends(db)
    rows = [d for d in list_diffusions(db)
            if (d["tribe_id"] in ids) or (d["tribe_id"] is None and user.role == ADMIN)]
    return {"diffusions": [_card(db, d, last.get(d["id"])) for d in rows],
            "tribes": [{"id": t.id, "name": t.name} for t in tribes],
            "direction": user.role == ADMIN, "smtp": bool(get_smtp(db).get("enabled"))}


@router.get("/choices")
def choices(tribe_id: int | None = Query(default=None), db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """GET /api/admin/diffusions/choices: what the editor offers to pick for a
    scope: its squads and tribe leaders, the people one can name (of the tribe,
    or every active account for the Direction) and the personas."""
    from ..mailplan import tribe_leaders
    from ..personasconfig import get_personas
    tid = _scope(db, user, tribe_id)
    q = select(User).where(User.status == "active").order_by(User.display_name)
    if tid is not None:
        q = q.where(User.tribe_id == tid)
    squads = db.scalars(select(Squad).where(Squad.tribe_id == tid).order_by(Squad.display_order, Squad.id)
                        ).all() if tid is not None else []
    return {
        "squads": [{"id": s.id, "name": s.name} for s in squads],
        "users": [{"id": u.id, "name": u.display_name or u.email, "email": u.email} for u in db.scalars(q).all()],
        "personas": [{"key": p["key"], "label": p.get("label") or p["key"]} for p in get_personas(db)],
        "tribe_leaders": [{"id": u.id, "name": u.display_name, "email": u.email}
                          for u in (tribe_leaders(db, tid) if tid is not None else [])],
    }


@router.post("")
def create(payload: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """POST /api/admin/diffusions: a new diffusion (body: its settings, with
    ``tribe_id``, null for the Direction). Audited."""
    from ..reportconfig import create_diffusion
    raw = payload.get("tribe_id")
    tid = _scope(db, user, int(raw) if raw is not None else None)
    cfg = create_diffusion(db, tid, _clean_payload(db, tid, payload))
    record_audit(db, user.id, "report_diffusion.create", entity="report_diffusion", entity_id=str(cfg["id"]),
                 detail={"tribe_id": tid, "name": cfg["name"], "enabled": cfg["enabled"]})
    db.commit()
    return cfg


@router.post("/plan")
def plan(payload: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """POST /api/admin/diffusions/plan: who receives which mail, for the settings
    being edited (``{"cfg": {...}}``, not saved): one row per mail, the
    documents it carries, its "To" and copies (each tagged with the line of the
    settings that put them there), and the people named without an address."""
    return {"mails": _plan_rows(db, _draft(db, user, payload))}


@router.post("/preview")
def preview(payload: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """POST /api/admin/diffusions/preview: one mail of the settings being edited
    (``{"cfg": {...}, "key": <mail key>}``, the first mail without a key), as it
    will look: subject, recipients, documents and HTML body. 404 when the
    settings send nothing."""
    from ..report import plan_preview
    out = plan_preview(db, _draft(db, user, payload), (payload or {}).get("key"))
    if out is None:
        raise HTTPException(status_code=404, detail="Aucun mail à prévisualiser")
    return out


@router.get("/{diffusion_id}")
def read(diffusion_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/admin/diffusions/{id}: one diffusion's settings."""
    return _own(db, user, diffusion_id)


@router.put("/{diffusion_id}")
def update(diffusion_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    """PUT /api/admin/diffusions/{id}: update a diffusion (all its settings, or
    some: ``{"enabled": false}`` pauses it). The scope and the bookkeeping
    cannot change. Audited."""
    from ..reportconfig import normalize, save_diffusion
    base = _own(db, user, diffusion_id)
    cfg = save_diffusion(db, normalize(base, _clean_payload(db, base["tribe_id"], payload)))
    record_audit(db, user.id, "report_diffusion.update", entity="report_diffusion", entity_id=str(diffusion_id),
                 detail={"tribe_id": cfg["tribe_id"], "enabled": cfg["enabled"], "weekdays": cfg["weekdays"],
                         "hour": cfg["hour"], "copies": len(cfg.get("copies") or []), "docs": cfg.get("docs")})
    db.commit()
    return cfg


@router.delete("/{diffusion_id}")
def delete(diffusion_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """DELETE /api/admin/diffusions/{id}: remove a diffusion, its "what's new"
    baselines and its history. Audited."""
    from sqlalchemy import delete as sql_delete
    from ..models import ReportSend
    from ..reportconfig import delete_diffusion
    cfg = _own(db, user, diffusion_id)
    delete_diffusion(db, diffusion_id)
    db.execute(sql_delete(ReportSend).where(ReportSend.diffusion_id == diffusion_id))
    record_audit(db, user.id, "report_diffusion.delete", entity="report_diffusion", entity_id=str(diffusion_id),
                 detail={"tribe_id": cfg["tribe_id"], "name": cfg["name"]})
    db.commit()
    return {"ok": True}


@router.get("/{diffusion_id}/history")
def read_history(diffusion_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/admin/diffusions/{id}/history: its latest sends, newest first
    (scheduled, sent now, tests): how many mails, which were refused and why."""
    from ..report import history
    _own(db, user, diffusion_id)
    return {"sends": history(db, diffusion_id)}


@router.post("/{diffusion_id}/test")
def test(diffusion_id: int, payload: dict = Body(default=None), db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    """POST /api/admin/diffusions/{id}/test: one of its mails (``{"key": ...}``,
    the first without), as saved, to the caller, now. 400 when SMTP is off.
    Audited."""
    from ..mail import last_error
    from ..report import plan_test
    cfg = _own(db, user, diffusion_id)
    to = user.email or ""
    if not to:
        raise HTTPException(status_code=400, detail="Votre compte n'a pas d'adresse mail")
    res = plan_test(db, cfg, to, (payload or {}).get("key"))
    if not res["smtp"]:
        raise HTTPException(status_code=400, detail="SMTP désactivé")
    record_audit(db, user.id, "report_diffusion.test", entity="report_diffusion", entity_id=str(diffusion_id),
                 detail={"tribe_id": cfg["tribe_id"], "ok": res["ok"]})
    db.commit()
    return {**res, "error": None if res["ok"] else last_error()}


@router.post("/{diffusion_id}/send-now")
def send_now(diffusion_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """POST /api/admin/diffusions/{id}/send-now: all its mails, as saved, now, out
    of its calendar. 400 when SMTP is off. Audited."""
    from ..report import send_plan_now
    cfg = _own(db, user, diffusion_id)
    res = send_plan_now(db, cfg)
    if not res["smtp"]:
        raise HTTPException(status_code=400, detail="SMTP désactivé")
    record_audit(db, user.id, "report.send_now", entity="report_diffusion", entity_id=str(diffusion_id),
                 detail={"tribe_id": cfg["tribe_id"], "sent": res["sent"]})
    db.commit()
    return res
