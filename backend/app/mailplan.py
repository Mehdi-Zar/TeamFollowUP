"""Who receives which mail of a diffusion (see app/reportconfig.py).

A plan is a list of mails. Each mail is one document (the tribe's, a squad's, or
every tribe's for the Direction) with its recipients, each tagged with the line
of the settings that put them there:

  * ``leader``    : the tribe leader, main recipient;
  * ``roles``     : the squad's leader, co-leaders or contributors;
  * ``copy:<i>``  : the i-th other recipient (persona, person or address).

Rules: the tribe leader receives the tribe's mail (``leader_tribe``), every
squad's mail (``leader_squads``), or both. The squads' people named by role join
the tribe leader's mail when it is the tribe's alone (one mail, they see the
whole tribe, as before); otherwise they are on their own squad's mail. A mail
with nobody in "To" promotes its copies to "To". An address appears once per
mail, "To" winning over copy. People the plan names but who have no address are
listed as ``missing``. Mail keys start with the diffusion (``d<id>:``): each
diffusion has its own "what's new" baselines.

The same plan drives the scheduled send, "send now", the preview and the list
of recipients on the settings screen.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Squad, Tribe, User


def _active(u: User | None) -> bool:
    return u is not None and u.status == "active"


def _who(u: User, line: str, role: str) -> dict:
    return {"email": (u.email or "").strip(), "name": u.display_name or u.email or "", "line": line,
            "role": role, "user_id": u.id}


def _finish(mail: dict) -> dict | None:
    """De-duplicate, promote copies when nobody is in To, drop an empty mail."""
    out, seen, missing = [], {}, []
    for r in sorted(mail["recipients"], key=lambda r: r["role"] != "to"):
        if not r["email"]:
            if r["name"] not in [m["name"] for m in missing]:
                missing.append({"name": r["name"], "line": r["line"]})
            continue
        k = r["email"].lower()
        if k in seen:
            continue
        seen[k] = True
        out.append(r)
    if out and not any(r["role"] == "to" for r in out):
        for r in out:
            r["role"] = "to"
    mail["recipients"] = out
    mail["missing"] = missing
    return mail if out or missing else None


def _squads_of(db: Session, tribe_id: int, squad_ids: list[int]) -> list[Squad]:
    q = select(Squad).where(Squad.tribe_id == tribe_id).order_by(Squad.display_order, Squad.id)
    if squad_ids:
        q = q.where(Squad.id.in_(squad_ids))
    return list(db.scalars(q).all())


def _copy_people(db: Session, c: dict, tribe_id: int | None, i: int) -> list[dict]:
    """The recipients one other recipient stands for."""
    line = f"copy:{i}"
    if c["type"] == "email":
        return [{"email": c["value"], "name": c["value"], "line": line, "role": "cc", "user_id": None}]
    if c["type"] == "user":
        u = db.get(User, c["value"])
        return [_who(u, line, "cc")] if _active(u) else []
    # A persona: the people who hold it, of this tribe for a tribe's diffusion
    # (an admin has no tribe), of every tribe for the Direction's.
    q = select(User).where(User.role == c["value"], User.status == "active")
    if c["value"] != "admin" and tribe_id is not None:
        q = q.where(User.tribe_id == tribe_id)
    return [_who(u, line, "cc") for u in db.scalars(q.order_by(User.display_name)).all()]


def tribe_leaders(db: Session, tribe_id: int) -> list[User]:
    return list(db.scalars(select(User).where(User.role == "tribe_leader", User.tribe_id == tribe_id,
                                              User.status == "active").order_by(User.display_name)).all())


def _roles(cfg: dict, sq: Squad) -> list[dict]:
    """A squad's people the settings name by role (leader, co-leaders, contributors)."""
    rec = []
    if cfg.get("copy_leader") and _active(sq.leader):
        rec.append(_who(sq.leader, "roles", "cc"))
    if cfg.get("copy_co_leaders"):
        rec += [_who(u, "roles", "cc") for u in sq.co_leaders if _active(u)]
    if cfg.get("copy_contributors"):
        rec += [_who(u, "roles", "cc") for u in sq.contributors if _active(u)]
    return rec


def body_of(cfg: dict, kind: str) -> list[str]:
    """The blocks of a mail of this kind (see reportconfig.BODY_SECTIONS)."""
    from .reportconfig import DEFAULT_BODY
    got = (cfg.get("body") or {}).get(kind)
    return list(got) if isinstance(got, list) else list(DEFAULT_BODY[kind])


def docs_of(cfg: dict, kind: str) -> list[str]:
    """The documents a mail of this kind carries (see reportconfig.DOC_TYPES)."""
    return list((cfg.get("docs") or {}).get(kind) or [])


def roles_on_tribe_mail(cfg: dict) -> bool:
    """Whether the squads' people named by role join the tribe's mail (the
    tribe leader gets the tribe's mail alone) rather than their squad's."""
    return bool(cfg.get("leader_tribe")) and not cfg.get("leader_squads")


def _prefix(cfg: dict) -> str:
    return f"d{cfg.get('id') or 'new'}:"


def tribe_plan(db: Session, cfg: dict, tribe_id: int) -> list[dict]:
    """The mails of a tribe's diffusion: the tribe's mail, then one per squad."""
    tribe = db.get(Tribe, tribe_id)
    if tribe is None:
        return []
    pre = _prefix(cfg)
    leaders = [_who(u, "leader", "to") for u in tribe_leaders(db, tribe_id)]
    squads = _squads_of(db, tribe_id, cfg.get("squad_ids") or [])
    copies = [(c, _copy_people(db, c, tribe_id, i)) for i, c in enumerate(cfg.get("copies") or [])]
    on_tribe = roles_on_tribe_mail(cfg)
    mails = []
    rec = list(leaders) if cfg.get("leader_tribe") else []
    if on_tribe:
        rec += [r for sq in squads for r in _roles(cfg, sq)]
    rec += [dict(p) for c, ps in copies if c["content"] == "tribe" for p in ps]
    m = _finish({"key": f"{pre}t{tribe_id}:tribe", "kind": "tribe", "tribe_id": tribe_id, "squad_id": None,
                 "label": tribe.name, "recipients": rec, "docs": docs_of(cfg, "tribe"),
                 "body": body_of(cfg, "tribe")})
    if m:
        mails.append(m)
    for sq in squads:
        rec = [dict(p) for p in leaders] if cfg.get("leader_squads") else []
        if not on_tribe:
            rec += _roles(cfg, sq)
        for c, ps in copies:
            if c["content"] == "squads" and (not c["squad_ids"] or sq.id in c["squad_ids"]):
                rec += [dict(p) for p in ps]
        m = _finish({"key": f"{pre}t{tribe_id}:squad:{sq.id}", "kind": "squad", "tribe_id": tribe_id,
                     "squad_id": sq.id, "label": sq.name, "recipients": rec, "docs": docs_of(cfg, "squad"),
                     "body": body_of(cfg, "squad")})
        if m:
            mails.append(m)
    return mails


def direction_plan(db: Session, cfg: dict) -> list[dict]:
    """The Direction's mail: every tribe, to the people and addresses named."""
    from .reportcommon import rt
    from .mailbody import instance_lang
    rec = []
    for i, c in enumerate(cfg.get("copies") or []):
        for p in _copy_people(db, c, None, i):
            rec.append({**p, "role": "to"})
    m = _finish({"key": f"{_prefix(cfg)}global", "kind": "all", "tribe_id": None, "squad_id": None,
                 "label": rt(instance_lang(db), "all_tribes"), "recipients": rec, "docs": docs_of(cfg, "all"),
                 "body": body_of(cfg, "all")})
    return [m] if m else []


def plan_for(db: Session, cfg: dict) -> list[dict]:
    """The mails of a diffusion (saved, or a draft being edited). Each mail also
    says which documents it carries (``docs``)."""
    tid = cfg.get("tribe_id")
    return direction_plan(db, cfg) if tid is None else tribe_plan(db, cfg, tid)
