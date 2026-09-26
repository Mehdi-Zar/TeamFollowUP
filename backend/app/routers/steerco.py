"""Steerco (steering committee) - monthly platform snapshots + consolidated one-pager.

The reporting unit is the **platform**, not the squad: the committee looks at one
slide per platform, and a platform can be served by several squads (Sovereign Platform is fed
by Managed Services and Sovereign LZ). Each month a platform reports one **snapshot**
(KPI counts, the month's SLA per COTS, the month's incident count, plus events).
Snapshots accumulate one per (platform, period), so the charts (January to December
of the report year) and the year-average SLA row are **computed** from the year's
snapshots - no need to re-enter history every time. The charts therefore always
start in January. For the first report a backfill endpoint seeds past months in one
shot (grid / paste-from-Excel in the UI).

Several squad leaders fill one slide without ever overwriting each other: the
platform's ``template`` assigns every KPI card and every SLA column to exactly one
contributing squad, and a save only takes the items the caller owns (see
``app/platforms.py``). Nothing is merged, and every figure on the slide has an
author. Events are the exception, a shared timeline where each contributor owns its
own lines.

Leadership reads/export a KPI one-pager per platform (HTML / PPTX), rendered in the
requested language (default English). Gated by the optional ``steerco`` module.

Stored snapshot shape (``SteercoEntry.data``), see frontend/src/steerco.ts:
    {"kpis":[{label,value}], "sla":{"services":[...],"cells":[{v}]},
     "incidents": <number>, "last_events":[...], "next_events":[...]}

It is positional against the template: ``data["kpis"][i]`` holds the value of
``template["kpis"][i]``. Only raw values are entered. The KPI variation vs M-1
(``trend`` / ``delta``) and the SLA colour (``s``) are recomputed at render time from
the numbers themselves, see ``_kpi_change`` and ``_sla_status``.
"""
import io
import math
import re
from html import escape

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from .. import platforms as plat
from .. import pptxtpl
from ..database import get_db
from ..deps import (can_report, get_current_user, record_audit, require_module,
                    require_admin_tab, require_writer, tribe_in_scope,
                    visible_tribe_id)
from ..models import Platform, SteercoEntry, Squad, Tribe, User

router = APIRouter(prefix="/api/steerco", tags=["steerco"],
                   dependencies=[Depends(require_module("steerco"))])

NAVY = "#0B2545"
SLA_CLASS = {"ok": "b-ok", "warn": "b-warn", "ko": "b-ko"}
# Event severity (entered on each event, in the wizard or the Excel): tints the type
# chip so a critical event reads at a glance. Same palette as the SLA statuses.
SEV_BG = {"red": "#F7E0E0", "amber": "#FBF0D9", "green": "#E4F3EA", "ice": "#E8F0FE"}
SEV_FG = {"red": "#B42318", "amber": "#9C7212", "green": "#027A48", "ice": "#13315C"}
TREND_CLASS = {"up": "up", "down": "down", "flat": "flat"}
TREND_ARROW = {"up": "▲", "down": "▼", "flat": "▬"}
# Les couleurs des courbes KPI, dans cet ordre et jamais recyclees.
#
# Les deux premieres tenaient du meme bleu marine (#0B2545 et #13315C, ecart 5,5
# sur 100): deux courbes de la meme squad etaient litteralement de la meme couleur,
# et la legende restait le seul moyen de les distinguer. Un gris-bleu pale et un
# ambre clair passaient par ailleurs sous le rapport de contraste de 3 pour 1 sur
# fond blanc, donc s'effacaient au videoprojecteur.
#
# Celles-ci sont choisies par calcul et non a l'oeil, sur fond blanc:
#   - pire ecart entre deux couleurs voisines 25,9, et 17,7 en vision deficiente
#     (protanopie, deuteranopie), pour une cible de 8;
#   - pire ecart entre deux couleurs quelconques 13,8, contre 5,5 auparavant;
#   - les six au-dessus du plancher de chroma, dans la bande de clarte, et toutes
#     au-dessus de 3 pour 1 de contraste.
#
# Elles s'ecartent aussi des couleurs de sante (vert, ambre, rouge des SLA, rouge
# des incidents) d'au moins 10: sur cette page, ces trois-la veulent dire quelque
# chose, et une courbe ne doit pas avoir l'air de le dire aussi.
SERIES_COLORS = ["#248FCC", "#B6770B", "#7C41AE", "#199E6E", "#175CD3", "#A72A6A"]

# Le corps du texte de la slide: voir pptxtpl.FONT_SCALE.
_fs = pptxtpl.font_size

# Fixed labels of the one-pager, per language (default English). Data (KPI labels,
# service names, event text) is user-entered and rendered as-is.
I18N = {
    "en": {
        "months": ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"],
        "key_figures": "KPI",
        "sla": "SLA", "sla_sub": "incidents &amp; SwF (by COTS)",
        "kpi_chart": "KPI trend", "kpi_chart_sub": "{year}",
        "axis_left": "left axis", "axis_right": "right axis",
        "inc_chart": "Incidents", "inc_chart_sub": "{year}",
        "period": "Period", "current": "Current month", "trailing": "Annual average",
        "last_events": "Last events", "next_events": "Next events",
        "no_kpi": "No KPI yet.", "no_sla": "No SLA data.", "no_data": "No data.",
        "no_event": "No event.", "no_squads": "No Steerco-enabled platform in your scope.",
        "not_filled": "Not filled in for {month}.", "expected_from": "Expected from: {names}.",
        "more_events": "+{n} more", "more_events_one": "+1 more",
    },
    "fr": {
        "months": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                   "août", "septembre", "octobre", "novembre", "décembre"],
        "key_figures": "KPI",
        "sla": "SLA", "sla_sub": "incidents &amp; SwF (par COTS)",
        "kpi_chart": "Évolution KPI", "kpi_chart_sub": "{year}",
        "axis_left": "axe gauche", "axis_right": "axe droit",
        "inc_chart": "Incidents", "inc_chart_sub": "{year}",
        "period": "Période", "current": "Mois en cours", "trailing": "Moyenne annuelle",
        "last_events": "Derniers évènements", "next_events": "Prochains évènements",
        "no_kpi": "Aucun KPI renseigné.", "no_sla": "Aucune donnée SLA.", "no_data": "Aucune donnée.",
        "no_event": "Aucun évènement.", "no_squads": "Aucune plateforme Steerco activée dans votre périmètre.",
        "not_filled": "Non renseigné pour {month}.", "expected_from": "Attendu de : {names}.",
        "more_events": "+{n} autres", "more_events_one": "+1 autre",
    },
}


def _cut(text: str, n: int) -> str:
    """Cut to n characters on a word, with an ellipsis (PowerPoint adds none)."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    head = text[:max(1, n - 1)]
    if " " in head[n // 2:]:
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,;:.") + "…"


def _lang(v: str | None) -> str:
    return "fr" if (v or "").lower().startswith("fr") else "en"


# --------------------------------------------------------------------------
# Platforms: declaration, contributors, and the slide template
# --------------------------------------------------------------------------

def _platforms_in_scope(db: Session, user: User) -> list[Platform]:
    q = db.query(Platform)
    tid = visible_tribe_id(user)
    if tid is not None:
        q = q.filter(Platform.tribe_id == tid)
    return q.order_by(Platform.display_order, Platform.name).all()


def _platform_in_scope(db: Session, user: User, platform_id: int) -> Platform:
    """The platform, or a 404 that says nothing about other tribes' platforms."""
    platform = db.get(Platform, platform_id)
    tid = visible_tribe_id(user)
    if platform is None or (tid is not None and platform.tribe_id != tid):
        raise HTTPException(status_code=404, detail="Plateforme introuvable")
    return platform


def _editable_squad_ids(db: Session, user: User, platform: Platform) -> list[int]:
    """The contributing squads this user may report for (possibly none)."""
    return [s.id for s in platform.contributors if can_report(db, user, s.id)]


def _may_manage(db: Session, user: User) -> bool:
    """Declaring platforms and assigning items is for whoever holds the "Platforms
    and Steerco" tab (the tribe leader by default, see Admin > Personas), always
    on their own tribe. A squad leader fills what was assigned to it, and cannot
    hand itself somebody else's column."""
    from ..tabaccess import has_tab
    return has_tab(db, user, "platforms") and (user.role == "admin" or user.tribe_id is not None)


def _contributor_squads(db: Session, user: User, tribe_id: int, ids) -> list[Squad]:
    """Load the requested contributors, refusing any squad outside the tribe.

    A platform fed by a squad of another tribe would publish that squad's figures
    to a committee that is not its own.
    """
    out = []
    for sid in dict.fromkeys(ids or []):
        squad = db.get(Squad, int(sid))
        if squad is None or squad.tribe_id != tribe_id:
            raise HTTPException(status_code=400,
                                detail="Une squad contributrice n'appartient pas à cette tribe")
        out.append(squad)
    return out


def _platform_out(db: Session, user: User, p: Platform) -> dict:
    editable = _editable_squad_ids(db, user, p)
    tpl = plat.normalize_template(p.template, [s.id for s in p.contributors])
    return {
        "id": p.id, "tribe_id": p.tribe_id, "name": p.name, "description": p.description,
        "display_order": p.display_order, "steerco_enabled": p.steerco_enabled,
        "template": tpl,
        "contributors": [{"id": s.id, "name": s.name} for s in
                         sorted(p.contributors, key=lambda x: x.name)],
        "editable_squad_ids": editable,
        "can_manage": _may_manage(db, user) and tribe_in_scope(user, p.tribe_id),
        "editable": plat.editable_items(tpl, editable) if not _may_manage(db, user)
        else {"kpis": list(range(len(tpl["kpis"]))), "sla": list(range(len(tpl["sla"]))),
              "incidents": True, "events": True},
    }


@router.get("/platforms")
def list_platforms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Platforms of the caller's scope, with contributors, template and what the
    caller may fill. Readable by anyone signed in: a contributor needs to see the
    whole slide, including the columns somebody else owes."""
    return [_platform_out(db, user, p) for p in _platforms_in_scope(db, user)]


@router.post("/platforms", status_code=201)
def create_platform(payload: dict = Body(...), db: Session = Depends(get_db),
                    user: User = Depends(require_admin_tab("platforms"))):
    """Declare a platform. Tribe leader or admin. Audited.

    The tribe comes from the payload, else from the caller, else from the first
    contributing squad. That last fallback is what makes the screen work for an
    administrator: an admin belongs to no tribe, so without it every creation from
    the admin console was refused as "out of scope" while naming the squads that
    obviously carried the answer.
    """
    tribe_id = payload.get("tribe_id") or user.tribe_id
    if tribe_id is None:
        ids = payload.get("contributor_ids") or []
        first = db.get(Squad, int(ids[0])) if ids else None
        tribe_id = first.tribe_id if first else None
    if tribe_id is None:
        raise HTTPException(status_code=400,
                            detail="Précisez la tribe de la plateforme, ou au moins une squad contributrice")
    if not tribe_in_scope(user, int(tribe_id)):
        raise HTTPException(status_code=403, detail="Tribe hors périmètre")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="La plateforme doit avoir un nom")
    if db.query(Platform).filter(Platform.tribe_id == int(tribe_id),
                                 Platform.name == name).first():
        raise HTTPException(status_code=409, detail="Une plateforme porte déjà ce nom")
    contributors = _contributor_squads(db, user, int(tribe_id), payload.get("contributor_ids"))
    p = Platform(tribe_id=int(tribe_id), name=name,
                 description=(payload.get("description") or None),
                 display_order=int(payload.get("display_order") or 0),
                 steerco_enabled=bool(payload.get("steerco_enabled", True)))
    p.contributors = contributors
    ids = [s.id for s in contributors]
    # A brand new platform with a single contributor is ready to fill: the standard
    # slide, entirely owned by that squad. With several, ownership is a decision and
    # the items start unassigned rather than arbitrarily attributed.
    # It starts from the tribe's model (Admin > Platforms and Steerco), the skeleton
    # the tribe leader imposes, unless a template is given.
    p.template = (plat.normalize_template(payload["template"], ids) if payload.get("template")
                  else plat.template_from_model(plat.get_tribe_model(db, int(tribe_id)), None, ids))
    db.add(p)
    db.flush()
    plat.sync_squad_flags(db, contributors)
    record_audit(db, user.id, "platform.create", entity="platform", entity_id=p.id,
                 detail={"name": p.name, "contributors": ids})
    db.commit()
    return _platform_out(db, user, p)


@router.put("/platforms/{platform_id}")
def update_platform(platform_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                    user: User = Depends(require_admin_tab("platforms"))):
    """Rename a platform, change its contributors, its order, its template. Audited."""
    p = _platform_in_scope(db, user, platform_id)
    before = [s for s in p.contributors]
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="La plateforme doit avoir un nom")
        clash = db.query(Platform).filter(Platform.tribe_id == p.tribe_id, Platform.name == name,
                                          Platform.id != p.id).first()
        if clash:
            raise HTTPException(status_code=409, detail="Une plateforme porte déjà ce nom")
        p.name = name
    if "description" in payload:
        p.description = payload.get("description") or None
    if "display_order" in payload:
        p.display_order = int(payload.get("display_order") or 0)
    if "steerco_enabled" in payload:
        p.steerco_enabled = bool(payload.get("steerco_enabled"))
    if "contributor_ids" in payload:
        p.contributors = _contributor_squads(db, user, p.tribe_id, payload.get("contributor_ids"))
    ids = [s.id for s in p.contributors]
    # Re-normalized even when the template is not in the payload: dropping a
    # contributor must drop the items it owned back to unassigned, or they would be
    # editable by nobody.
    new_tpl = plat.normalize_template(payload.get("template", p.template), ids)
    _relayout(p, new_tpl)
    db.flush()
    plat.sync_squad_flags(db, {s.id: s for s in (before + list(p.contributors))}.values())
    record_audit(db, user.id, "platform.update", entity="platform", entity_id=p.id,
                 detail={"name": p.name, "contributors": ids})
    db.commit()
    return _platform_out(db, user, p)


def _relayout(p: Platform, new_tpl: dict) -> None:
    """Set a new template and move every stored month onto it, by label: without
    this, removing or reordering an item shifted the figures of the others."""
    old = p.template or {}
    labels = lambda t: ([k.get("label") for k in t.get("kpis") or []],
                        [x.get("label") for x in t.get("sla") or []],
                        [tuple(k.get("sub") or []) for k in t.get("kpis") or []])
    if labels(old) != labels(new_tpl):
        for e in p.entries:
            e.data = plat.remap_data(e.data, new_tpl)
    p.template = new_tpl


def _model_tribe(db: Session, user: User, tribe_id: int | None) -> int:
    """The tribe whose model is read or written: the admin names it, anyone else
    works on their own tribe."""
    if user.role == "admin":
        tid = tribe_id
    else:
        tid = user.tribe_id
    if tid is None or db.get(Tribe, tid) is None:
        raise HTTPException(status_code=400, detail="Précisez la tribe")
    return tid


@router.get("/model")
def read_tribe_model(tribe_id: int | None = Query(None), db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """GET /api/steerco/model: the tribe's model, the Steerco skeleton its tribe
    leader imposes (KPI, sub-metrics, SLA services; no owners)."""
    tid = _model_tribe(db, user, tribe_id)
    return {"tribe_id": tid, **plat.get_tribe_model(db, tid)}


@router.put("/model")
def update_tribe_model(payload: dict = Body(...), tribe_id: int | None = Query(None),
                       db: Session = Depends(get_db),
                       user: User = Depends(require_admin_tab("platforms"))):
    """PUT /api/steerco/model: set the tribe's model. New platforms start from it;
    existing ones follow it with "apply the tribe model". Audited."""
    tid = _model_tribe(db, user, tribe_id)
    model = plat.set_tribe_model(db, tid, payload)
    record_audit(db, user.id, "steerco.model", entity="tribe", entity_id=tid,
                 detail={"kpis": len(model["kpis"]), "sla": len(model["sla"])})
    db.commit()
    return {"tribe_id": tid, **model}


@router.post("/platforms/{platform_id}/apply-model")
def apply_tribe_model(platform_id: int, db: Session = Depends(get_db),
                      user: User = Depends(require_admin_tab("platforms"))):
    """POST /api/steerco/platforms/{id}/apply-model: bring a platform back to its
    tribe's model. Items that stay keep their owner and their figures (matched by
    label); new ones go to the single contributor, else stay unassigned. Audited."""
    p = _platform_in_scope(db, user, platform_id)
    ids = [s.id for s in p.contributors]
    _relayout(p, plat.template_from_model(plat.get_tribe_model(db, p.tribe_id), p.template, ids))
    record_audit(db, user.id, "platform.apply_model", entity="platform", entity_id=p.id)
    db.commit()
    return _platform_out(db, user, p)


@router.delete("/platforms/{platform_id}", status_code=204)
def delete_platform(platform_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_admin_tab("platforms"))):
    """Delete a platform and its monthly snapshots. Tribe leader or admin. Audited."""
    p = _platform_in_scope(db, user, platform_id)
    contributors = list(p.contributors)
    record_audit(db, user.id, "platform.delete", entity="platform", entity_id=p.id,
                 detail={"name": p.name})
    db.delete(p)
    db.flush()
    plat.sync_squad_flags(db, contributors)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------
# A period is one month, "YYYY-MM". Anything else failed later as a 500 (in the
# month arithmetic) or was stored as a period no chart would ever read.
PERIOD_RE = r"^\d{4}-(0[1-9]|1[0-2])$"
PERIOD = Query(..., pattern=PERIOD_RE)


# Data access (one monthly snapshot per platform+period)
# --------------------------------------------------------------------------


def _clamp_pct(v):
    """SLA cells are percentages: keep them inside 0 to 100 (a typo like 994 -> 100).
    Non-numeric text is returned untouched."""
    n = _num(v)
    if n is None or 0 <= n <= 100:
        return v
    c = min(max(n, 0.0), 100.0)
    return f"{c:.0f}%" if str(v).strip().endswith("%") else f"{c:.0f}"


def _sanitized(payload: dict) -> dict:
    """A snapshot as it is stored: SLA percentages capped at 100."""
    sla = (payload or {}).get("sla")
    if not isinstance(sla, dict) or not isinstance(sla.get("cells"), list):
        return payload or {}
    cells = [({**c, "v": _clamp_pct(c.get("v"))} if isinstance(c, dict) else c)
             for c in sla["cells"]]
    return {**payload, "sla": {**sla, "cells": cells}}


def _entry(db: Session, platform_id: int, period: str) -> SteercoEntry | None:
    return (db.query(SteercoEntry)
            .filter(SteercoEntry.platform_id == platform_id, SteercoEntry.period == period)
            .one_or_none())


def _write_scope(db: Session, user: User, platform: Platform) -> tuple[list[int], bool]:
    """(contributing squads the caller may fill for, may-fill-everything).

    A tribe leader or an admin writes the whole slide, including items nobody has
    been assigned yet. A squad leader writes its own items and is refused outright
    when it contributes nothing to this platform.
    """
    if _may_manage(db, user) and tribe_in_scope(user, platform.tribe_id):
        return [s.id for s in platform.contributors], True
    ids = _editable_squad_ids(db, user, platform)
    if not ids:
        raise HTTPException(status_code=403,
                            detail="Vous ne contribuez pas à cette plateforme")
    return ids, False


@router.get("/entries")
def list_entries(period: str = PERIOD, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Every steerco platform of the caller's tribe for a period (the dashboard's
    Steerco tab). The whole tribe reads it: a platform's dashboard is the tribe's.
    The ``missing`` list names the contributors still owing an item, which is the
    whole point of tracking a slide filled by several people."""
    out = []
    for p in _platforms_in_scope(db, user):
        if not p.steerco_enabled:
            continue
        e = _entry(db, p.id, period)
        tpl = plat.normalize_template(p.template, [s.id for s in p.contributors])
        names = {s.id: s.name for s in p.contributors}
        out.append({
            "platform_id": p.id, "platform_name": p.name, "tribe_id": p.tribe_id,
            "data": (e.data if e else {}),
            "filled": bool(e and e.data),
            "updated_at": (e.updated_at if e else None),
            "contributors": [{"id": i, "name": n} for i, n in sorted(names.items(),
                                                                     key=lambda kv: kv[1])],
            "missing": [names[i] for i in _missing_owners(tpl, e.data if e else {})
                        if i in names],
            "unassigned": _unassigned_count(tpl),
        })
    return out


def _missing_owners(tpl: dict, data: dict) -> list[int]:
    """Contributor ids that own at least one item still empty this month."""
    late = []
    kpis = (data or {}).get("kpis") or []
    for i, item in enumerate(tpl.get("kpis") or []):
        value = kpis[i].get("value") if i < len(kpis) and isinstance(kpis[i], dict) else ""
        if not str(value or "").strip() and item.get("owner_squad_id"):
            late.append(item["owner_squad_id"])
    cells = ((data or {}).get("sla") or {}).get("cells") or []
    for i, item in enumerate(tpl.get("sla") or []):
        value = cells[i].get("v") if i < len(cells) and isinstance(cells[i], dict) else ""
        if not str(value or "").strip() and item.get("owner_squad_id"):
            late.append(item["owner_squad_id"])
    inc_owner = (tpl.get("incidents") or {}).get("owner_squad_id")
    if inc_owner and not str((data or {}).get("incidents") or "").strip():
        late.append(inc_owner)
    return list(dict.fromkeys(late))


def _unassigned_count(tpl: dict) -> int:
    """Items nobody owns yet: they are nobody's job and stay empty forever."""
    n = sum(1 for k in tpl.get("kpis") or [] if not k.get("owner_squad_id"))
    n += sum(1 for x in tpl.get("sla") or [] if not x.get("owner_squad_id"))
    n += 0 if (tpl.get("incidents") or {}).get("owner_squad_id") else 1
    return n


@router.get("/platform/{platform_id}")
def get_platform_entry(platform_id: int, period: str = PERIOD, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """One platform's monthly snapshot, with the template and what the caller owns.

    The payload carries the whole slide, not only the caller's share: a contributor
    should see the columns it does not own, greyed out and attributed, rather than a
    form that pretends the rest does not exist."""
    p = _platform_in_scope(db, user, platform_id)
    e = _entry(db, platform_id, period)
    out = _platform_out(db, user, p)
    data = e.data if e else plat.blank_data(out["template"])
    return {
        "platform_id": platform_id, "platform_name": p.name, "period": period,
        "template": out["template"], "contributors": out["contributors"],
        "editable": out["editable"], "can_manage": out["can_manage"],
        "editable_squad_ids": out["editable_squad_ids"],
        "data": data,
        "filled": bool(e and e.data),
        "missing": [c["name"] for c in out["contributors"]
                    if c["id"] in _missing_owners(out["template"], data)],
        "updated_at": e.updated_at.isoformat() if (e and e.updated_at) else None,
        "updated_by": (e.updated_by.display_name if (e and e.updated_by) else None),
    }


@router.put("/platform/{platform_id}")
def upsert_platform_entry(platform_id: int, period: str = PERIOD,
                          data: dict = Body(default=None), db: Session = Depends(get_db),
                          user: User = Depends(require_writer)):
    """Write the caller's share of a platform's month (writer + contributor rights).

    The payload may carry the whole slide; only the items the caller owns are taken
    from it, the rest is kept as stored. That is what lets two squad leaders fill
    one slide at the same time without either of them erasing the other."""
    p = _platform_in_scope(db, user, platform_id)
    squad_ids, all_owned = _write_scope(db, user, p)
    tpl = plat.normalize_template(p.template, [s.id for s in p.contributors])
    e = _entry(db, platform_id, period)
    merged = _sanitized(plat.merge_owned(e.data if e else {}, data or {}, tpl,
                                         squad_ids, all_owned))
    if e is None:
        e = SteercoEntry(platform_id=platform_id, period=period, data=merged,
                         updated_by_user_id=user.id)
        db.add(e)
    else:
        e.data = merged
        e.updated_by_user_id = user.id
    db.flush()
    record_audit(db, user.id, "steerco.upsert", entity="steerco", entity_id=e.id,
                 detail={"platform_id": platform_id, "period": period, "squads": squad_ids})
    db.commit()
    return {"platform_id": platform_id, "period": period, "data": e.data}


# --------------------------------------------------------------------------
# Calendar-year history (backfill + read), for the auto-built charts
# --------------------------------------------------------------------------

def month_keys(period: str, n: int = 12) -> list[str]:
    """The n month keys ("YYYY-MM") ending at ``period`` (oldest first)."""
    y, m = (int(x) for x in period.split("-")[:2])
    keys = []
    for i in range(n - 1, -1, -1):
        mm, yy = m - i, y
        while mm <= 0:
            mm += 12
            yy -= 1
        keys.append(f"{yy:04d}-{mm:02d}")
    return keys


def year_months(period: str) -> list[str]:
    """The 12 month keys of ``period``'s calendar year, January to December.

    This is the window the whole Steerco feature works on: the charts, the SLA
    average, the backfill grid, the wizard columns and the Excel columns all cover
    January to December of the report's year, so the one-pager charts always start in
    January and the months you enter line up with the months you see charted."""
    y = int(period.split("-")[0])
    return [f"{y:04d}-{m:02d}" for m in range(1, 13)]


def _month_short(key: str) -> str:
    y, m = key.split("-")[:2]
    return f"{m}/{y[2:]}"


def _period_long(period: str, L: dict) -> str:
    """"2026-07" -> "July 2026" / "juillet 2026" (spelled-out month, per language)."""
    try:
        y, m = period.split("-")[:2]
        return f"{L['months'][int(m) - 1]} {y}"
    except (ValueError, IndexError, KeyError):
        return period


@router.get("/platform/{platform_id}/history")
def get_history(platform_id: int, period: str = PERIOD, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """The report year's 12 monthly snapshots, January to December (backfill grid)."""
    _platform_in_scope(db, user, platform_id)
    keys = year_months(period)
    by_period = {e.period: (e.data or {}) for e in db.query(SteercoEntry)
                 .filter(SteercoEntry.platform_id == platform_id,
                         SteercoEntry.period.in_(keys)).all()}
    return {"platform_id": platform_id, "period": period,
            "months": [{"period": k, "data": by_period.get(k, {})} for k in keys]}


@router.put("/platform/{platform_id}/history")
def upsert_history(platform_id: int, months: dict = Body(..., embed=True),
                   db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Backfill several months at once. Body: ``{"months": {"2026-06": {...}, ...}}``.

    Each month goes through the same ownership merge as a single save, so a
    contributor pasting a year of its own figures cannot overwrite a colleague's
    column in any of those months."""
    p = _platform_in_scope(db, user, platform_id)
    squad_ids, all_owned = _write_scope(db, user, p)
    tpl = plat.normalize_template(p.template, [s.id for s in p.contributors])
    bad = [k for k in (months or {}) if not re.match(PERIOD_RE, str(k))]
    if bad:
        raise HTTPException(status_code=422, detail=f"Période invalide : {bad[0]} (attendu AAAA-MM)")
    for period, snap in (months or {}).items():
        e = _entry(db, platform_id, period)
        merged = _sanitized(plat.merge_owned(e.data if e else {}, snap or {}, tpl,
                                             squad_ids, all_owned))
        if e is None:
            db.add(SteercoEntry(platform_id=platform_id, period=period, data=merged,
                                updated_by_user_id=user.id))
        else:
            e.data = merged
            e.updated_by_user_id = user.id
    record_audit(db, user.id, "steerco.history", entity="steerco", entity_id=platform_id,
                 detail={"platform_id": platform_id, "months": list((months or {}).keys())})
    db.commit()
    return {"platform_id": platform_id, "count": len(months or {})}


# --------------------------------------------------------------------------
# Aggregation: build the render-data (charts + year-average SLA) from the year
# --------------------------------------------------------------------------

def _num(v) -> float | None:
    try:
        return float(str(v).replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _round_up(x: float) -> int:
    x = max(x, 1.0)
    mag = 10 ** (len(str(int(x))) - 1)
    return int(math.ceil(x / mag) * mag)


# A Software Factory counting its builds in thousands and a DBaaS counting its
# instances in tens do not belong on the same graduation: the second is a flat line
# lying on the axis. Past this ratio between two groups of curves, the big ones move
# to a scale of their own, read on the right edge.
SECONDARY_AXIS_RATIO = 5.0


def _split_axes(series: list[dict]) -> None:
    """Flag the high-magnitude series so they are plotted against a right-hand axis.

    The cut is found, not configured: series are ordered by their peak value and split
    at the widest multiplicative gap, when that gap reaches SECONDARY_AXIS_RATIO. Below
    it the curves already share a readable scale and a second axis would only add a
    column of numbers to read. Series that stay flat at zero never open a gap, since a
    zero peak has no scale of its own and would send everything else to the right."""
    peaks = []
    for s in series:
        vals = [abs(v) for v in (s.get("data") or []) if v is not None]
        if vals:
            peaks.append((max(vals), s))
    if len(peaks) < 2:
        return
    peaks.sort(key=lambda p: p[0])
    cut, widest = 0, 1.0
    for i in range(1, len(peaks)):
        low = peaks[i - 1][0]
        if low <= 0:
            continue
        ratio = peaks[i][0] / low
        if ratio > widest:
            cut, widest = i, ratio
    if not cut or widest < SECONDARY_AXIS_RATIO:
        return
    for _, s in peaks[cut:]:
        s["axis"] = "right"


def _axis_max(series: list[dict]) -> int:
    """Top graduation of one axis: the highest point of its series, rounded up."""
    vals = [v for s in series for v in (s.get("data") or []) if v is not None]
    return _round_up(max(vals + [10]))


# --- Auto-computed indicators (never entered by the squad leader) -------------
# SLA colour: above 90% green, 80 to 90% amber, below 80% red.
SLA_GREEN, SLA_AMBER = 90.0, 80.0


def _sla_status(v) -> str | None:
    """RAG status of an SLA value, derived from the number itself (None when empty)."""
    n = _num(v)
    if n is None:
        return None
    return "ok" if n > SLA_GREEN else "warn" if n >= SLA_AMBER else "ko"


def _fmt_delta(d: float) -> str:
    r = round(d, 1)
    if r == 0:
        return "0"
    return (f"{r:+.10g}").replace(".", ",")


def _kpi_change(cur, prev) -> tuple[str, str]:
    """A KPI's (trend, delta) vs the previous month, computed from both values."""
    c, p = _num(cur), _num(prev)
    if c is None or p is None:
        return "flat", ""
    d = c - p
    return ("up" if d > 0 else "down" if d < 0 else "flat"), _fmt_delta(d)


def _kpi_value(snap: dict, label: str):
    """That month's value for a KPI label (case-insensitive), None when absent."""
    target = (label or "").strip().lower()
    for k in (snap.get("kpis") or []):
        if (k.get("label") or "").strip().lower() == target:
            return k.get("value")
    return None


def _aggregate(db: Session, platform_id: int, period: str, override: dict | None = None) -> dict:
    """Assemble the one-pager render-data for a platform+month over the report's calendar
    year (January to December): KPI cards + events from the current month; SLA table
    (current row + year-average row); KPI and incident charts as the Jan-to-Dec series,
    so the charts always start in January.

    ``override`` (optional) replaces the current month's snapshot in memory only (never
    persisted) so the wizard can preview unsaved edits before submitting."""
    keys = year_months(period)
    # The vs-M-1 delta needs the month right before the report month, which for a
    # January report is December of the previous year (outside the calendar window).
    prev_key = month_keys(period, 2)[0]
    load = set(keys) | {prev_key, period}
    by_period = {e.period: (e.data or {}) for e in db.query(SteercoEntry)
                 .filter(SteercoEntry.platform_id == platform_id,
                         SteercoEntry.period.in_(load)).all()}
    if override is not None:
        by_period[period] = _sanitized(override)
    cur = by_period.get(period, {}) or {}
    prev = by_period.get(prev_key, {}) or {}
    # Le mois le plus recent qui porte des KPI (ou des colonnes SLA): un mois pas
    # encore saisi n'efface pas les courbes de janvier a aout, il leur manque
    # seulement leur dernier point.
    def latest(pick):
        if pick(cur):
            return cur
        return next((by_period[k] for k in reversed(keys)
                     if k <= period and pick(by_period.get(k) or {})), {})
    ref_kpis = latest(lambda d: d.get("kpis"))
    ref_sla = latest(lambda d: (d.get("sla") or {}).get("services"))

    # KPI change vs M-1: computed here from the two snapshots, so the squad leader
    # never types a variation and it can never go stale.
    kpis = []
    for k in (cur.get("kpis") or []):
        trend, delta = _kpi_change(k.get("value"), _kpi_value(prev, k.get("label") or ""))
        kpis.append({**k, "trend": trend, "delta": delta})

    sla_cur = cur.get("sla") or {}
    services = sla_cur.get("services") or (ref_sla.get("sla") or {}).get("services") or []
    # SLA colour: computed from each value (see _sla_status), never chosen by hand.
    cur_cells = [{**(c or {}), "v": _clamp_pct((c or {}).get("v")),
                  "s": _sla_status(_clamp_pct((c or {}).get("v")))}
                 for c in (sla_cur.get("cells") or [])]
    avg_cells = []
    for i in range(len(services)):
        vals = []
        for k in keys:
            if k > period:  # the months after the report are not in its average
                continue
            cells = (by_period.get(k, {}).get("sla") or {}).get("cells") or []
            if i < len(cells):
                pv = _num(cells[i].get("v"))
                if pv is not None:
                    vals.append(min(max(pv, 0.0), 100.0))
        if vals:
            a = sum(vals) / len(vals)
            avg_cells.append({"v": f"{a:.1f}".replace(".", ",") + "%", "s": _sla_status(a)})
        else:
            avg_cells.append({"v": "-", "s": None})
    sla = {"services": services, "rows": [
        {"period": "__current__", "cells": cur_cells},
        {"period": "__trailing__", "cells": avg_cells},
    ]}

    labels = [_month_short(k) for k in keys]
    kpi_series = []
    for idx, k in enumerate(kpis or (ref_kpis.get("kpis") or [])):
        label = k.get("label")
        # Plot the RAW monthly values (case-insensitive label match, same as the vs-M-1
        # delta so a KPI typed "K8aaS" then "K8AAS" stays one series). These are the exact
        # figures shown on the KPI cards. We deliberately do NOT index to base 100: a metric
        # ramping up from zero (e.g. DBaaS 1 -> 5) would explode to 100 -> 500 and dominate
        # the shared axis, and each series would be indexed off a different first month, so
        # the curves were not even comparable.
        data = [_num(_kpi_value(by_period.get(key, {}), label or "")) if key <= period else None
                for key in keys]
        kpi_series.append({"name": label, "color": SERIES_COLORS[idx % len(SERIES_COLORS)], "data": data})
    # Two orders of magnitude on one axis flatten the small curves; the big ones get
    # their own graduation on the right (see _split_axes).
    _split_axes(kpi_series)
    right = [s for s in kpi_series if s.get("axis") == "right"]
    kpi_chart = {"labels": labels, "y_min": 0, "series": kpi_series,
                 "y_max": _axis_max([s for s in kpi_series if s.get("axis") != "right"])}
    if right:
        kpi_chart["y2_min"], kpi_chart["y2_max"] = 0, _axis_max(right)

    inc_data = [_num(by_period.get(k, {}).get("incidents")) if k <= period else None for k in keys]
    inc_ymax = _round_up(max([v for v in inc_data if v is not None] + [10]))

    # Qui doit encore sa part ce mois-ci: la slide d'un mois vide le dit, au lieu
    # de montrer des cadres blancs.
    missing: list[str] = []
    p = db.get(Platform, platform_id)
    if p is not None:
        tpl = plat.normalize_template(p.template, [x.id for x in p.contributors])
        names = {x.id: x.name for x in p.contributors}
        missing = [names[i] for i in _missing_owners(tpl, cur) if i in names]

    return {
        "kpis": kpis,
        "filled": bool(cur),
        "missing": missing,
        "sla": sla,
        "kpi_chart": kpi_chart,
        "incidents_chart": {"labels": labels, "y_max": inc_ymax, "y_min": 0,
                            "series": [{"name": "Incidents", "color": "#D24545", "data": inc_data}]},
        "last_events": cur.get("last_events") or [],
        "next_events": cur.get("next_events") or [],
    }


# --------------------------------------------------------------------------
# One-pager rendering (HTML + PPTX), language-aware (default English)
# --------------------------------------------------------------------------

_PAGE_CSS = """
/* Palette aligned on the app theme (theme.css) so the in-app view feels native.
   The PPTX export keeps its own colours (rendered in _render_pptx). */
:root{--navy:#1E2761;--navy2:#141B47;--ice:#CADCFC;--ice-light:#E8F0FE;--ice-line:#CADCFC;
--bg:#F5F7FA;--card:#FFFFFF;--line:#E2E8F0;--txt:#1E293B;--muted:#64748B;--green:#027A48;--amber:#B54708;--red:#B42318;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:Calibri,"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--txt);padding:22px;font-size:14px;}
.page{max-width:1280px;margin:0 auto;}
.page + .page{margin-top:26px;}
/* Compact, discreet header (no heavy band). */
.hdr{display:flex;align-items:baseline;justify-content:space-between;margin:2px 2px 12px;}
.hdr h1{font-size:19px;font-weight:700;letter-spacing:.3px;color:var(--navy);}
.hdr .date{color:var(--muted);font-size:12px;font-weight:600;}
/* 2x2 grid + events row: identical 16px gutters so every column lines up. */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;align-items:stretch;}
.events-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
/* Every block is the same panel: tinted header strip + body. */
.panel{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:0 1px 2px rgba(16,37,66,.05);}
.panel .hd{display:flex;align-items:center;gap:8px;background:var(--ice-light);color:var(--navy);font-size:13.5px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding:10px 14px;border-bottom:1px solid var(--ice-line);}
.panel .hd::before{content:"";width:8px;height:8px;border-radius:2px;background:var(--navy);flex:0 0 auto;}
.panel .hd .sub{color:var(--muted);text-transform:none;letter-spacing:0;font-weight:400;font-size:11px;}
.panel .bd{padding:12px 14px;flex:1;display:flex;flex-direction:column;min-height:0;}
/* Users alone and wider on top; the 4 others in a row below. */
.kpi-wrap{display:flex;flex-direction:column;gap:10px;height:100%;}
.kpi-hero-row{display:flex;justify-content:center;}
.kpi-row{flex:1;display:grid;grid-template-columns:repeat(4,1fr);gap:10px;}
/* 3 lines: number, name (single line), trend at the bottom-left. */
.kpi{background:#fff;border:1px solid #AFC0D6;border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;}
.kpi.hero{width:44%;min-width:190px;padding:14px;}
.kpi .num{font-size:21px;font-weight:800;color:var(--navy);line-height:1.05;}
.kpi.hero .num{font-size:32px;}
.kpi .num .unit{font-size:12px;font-weight:400;color:var(--muted);margin-left:1px;}
.kpi .lbl{font-size:10px;font-weight:700;color:var(--navy2);text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px;}
.kpi.hero .lbl{font-size:14px;}
.kpi .t{font-size:11px;font-weight:600;margin-top:auto;padding-top:8px;}
.kpi-sub{display:flex;flex-wrap:wrap;gap:2px 8px;font-size:9px;color:var(--muted);margin-top:6px;line-height:1.3;}
.kpi-sub b{color:var(--navy);font-weight:700;}
.up{color:var(--green);}.down{color:var(--red);}.flat{color:var(--muted);}
/* SLA table fills the whole panel body; rows share the height evenly. */
table{width:100%;border-collapse:collapse;font-size:13px;height:100%;}
.bd > table{flex:1;}
th,td{padding:8px 10px;text-align:center;border:1px solid var(--line);vertical-align:middle;}
thead th{background:var(--navy);color:#fff;font-weight:600;}
tbody th{background:var(--ice-light);color:var(--navy);font-weight:700;text-align:left;}
/* Whole SLA cell is filled with the status colour, computed from the value (matches the PPTX). */
td.b-ok,td.b-warn,td.b-ko{font-weight:700;}
.b-ok{background:#E4F3EA;color:var(--green);}
.b-warn{background:#FBF0D9;color:#9c7212;}
.b-ko{background:#F7E0E0;color:var(--red);}
.b-none{color:var(--muted);}
.chart{flex:1;min-height:0;display:flex;}
.chart svg{width:100%;height:100%;display:block;}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;font-size:11px;color:var(--muted);}
.legend span{display:flex;align-items:center;gap:5px;}
/* Le nom d'une echelle, en tete de son groupe de courbes. */
.legend .legend-grp{font-weight:700;color:var(--navy2);margin-left:4px;}
.legend .legend-grp:first-child{margin-left:0;}
.legend i{width:14px;height:3px;border-radius:2px;display:inline-block;}
/* Uniform event row: date / type (colour chip) / description. */
.ev-list{list-style:none;}
.ev-list li{display:flex;align-items:center;gap:10px;padding:9px 2px;border-bottom:1px solid var(--line);}
.ev-list li:last-child{border-bottom:none;}
.ev-date{color:var(--muted);font-size:12px;font-weight:700;width:52px;flex:0 0 auto;}
.ev-type{font-size:11.5px;font-weight:700;color:var(--navy2);background:var(--ice-light);border:1px solid var(--ice-line);padding:2px 9px;border-radius:5px;flex:0 0 auto;min-width:52px;text-align:center;white-space:nowrap;}
.ev-desc{flex:1;font-size:13px;color:var(--txt);}
.muted{color:var(--muted);}
.empty{color:var(--muted);font-size:12px;font-style:italic;padding:6px 2px;}
"""


def _svg_line_chart(chart: dict, empty: str) -> str:
    """Server-render a multi-series line chart as SVG. Missing points (None) are gaps.

    A chart carrying ``y2_max`` has two scales: the series flagged ``axis: "right"``
    are plotted against it and its graduations are written along the right edge. The
    grid stays shared, so both scales are cut in the same four steps and the curves
    keep a common horizontal reference."""
    series = [s for s in (chart.get("series") or []) if any(v is not None for v in (s.get("data") or []))]
    labels = chart.get("labels") or []
    y_max = float(chart.get("y_max") or 100) or 100
    y_min = float(chart.get("y_min") or 0)
    span = (y_max - y_min) or 1
    if not series:
        return f"<div class='empty'>{escape(empty)}</div>"
    two = bool(chart.get("y2_max")) and any(s.get("axis") == "right" for s in series)
    y2_max = float(chart.get("y2_max") or 100) or 100
    y2_min = float(chart.get("y2_min") or 0)
    span2 = (y2_max - y2_min) or 1
    # The right graduations need their own margin, otherwise they would sit on the curves.
    W, H, pl, pt, pb = 560, 190, 34, 12, 24
    pr = 34 if two else 14
    iw, ih = W - pl - pr, H - pt - pb
    n = max(len(labels), max((len(s["data"]) for s in series), default=0), 2)

    def x(i):
        return pl + (iw * i / (n - 1))

    def y(v, right=False):
        if right:
            return pt + ih - (ih * (float(v) - y2_min) / span2)
        return pt + ih - (ih * (float(v) - y_min) / span)

    out = []
    for g in range(5):
        yy = pt + ih * g / 4
        out.append(f'<line x1="{pl}" y1="{yy:.1f}" x2="{W-pr}" y2="{yy:.1f}" stroke="#E7ECF2" stroke-width="1"/>')
        out.append(f'<text x="{pl-6}" y="{yy+3:.1f}" font-size="9" fill="#6B7C90" text-anchor="end">{round(y_max - span*g/4)}</text>')
        if two:
            out.append(f'<text x="{W-pr+6}" y="{yy+3:.1f}" font-size="9" fill="#6B7C90" text-anchor="start">{round(y2_max - span2*g/4)}</text>')
    out.append(f'<line x1="{pl}" y1="{pt}" x2="{pl}" y2="{pt+ih}" stroke="#B7C2CF" stroke-width="1"/>')
    out.append(f'<line x1="{pl}" y1="{pt+ih}" x2="{W-pr}" y2="{pt+ih}" stroke="#B7C2CF" stroke-width="1"/>')
    if two:
        out.append(f'<line x1="{W-pr}" y1="{pt}" x2="{W-pr}" y2="{pt+ih}" stroke="#B7C2CF" stroke-width="1"/>')
    for i, m in enumerate(labels):
        out.append(f'<text x="{x(i):.1f}" y="{H-8}" font-size="9" fill="#6B7C90" text-anchor="middle">{escape(str(m))}</text>')
    for s in series:
        color = escape(str(s.get("color") or NAVY))
        right = two and s.get("axis") == "right"
        pts = [(i, v) for i, v in enumerate(s["data"]) if v is not None]
        if pts:
            # Line only (no point markers).
            d = " ".join(("M" if j == 0 else "L") + f"{x(i):.1f} {y(v, right):.1f}" for j, (i, v) in enumerate(pts))
            out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
    return f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" width="100%">{"".join(out)}</svg>'


def _series_name(s: dict, right_note: str) -> str:
    """A series name, telling which scale reads it when the chart has two.

    Sert au PPTX, dont la legende est celle de PowerPoint: on n'y range rien, la
    seule place pour le dire est le nom de la serie. C'est aussi l'usage d'Excel."""
    name = str(s.get("name") or "")
    return f"{name} ({right_note})" if right_note and s.get("axis") == "right" else name


def _legend(series: list[dict], L: dict | None = None) -> str:
    """La legende d'un graphe, en HTML.

    A deux echelles, elle se **range en deux groupes nommes** au lieu de repeter
    « axe droit » derriere chaque courbe concernee: avec deux courbes a droite la
    mention etait ecrite deux fois pour dire une seule chose, et la legende passait
    a trois lignes en rognant d'autant la hauteur du graphe."""
    drawn = [s for s in (series or []) if any(v is not None for v in (s.get("data") or []))]

    def chip(s: dict) -> str:
        return (f'<span><i style="background:{escape(str(s.get("color") or NAVY))}"></i>'
                f'{escape(str(s.get("name") or ""))}</span>')

    if not L or not any(s.get("axis") == "right" for s in drawn):
        return "".join(chip(s) for s in drawn)
    out = []
    for key, on_right in (("axis_left", False), ("axis_right", True)):
        group = [s for s in drawn if (s.get("axis") == "right") is on_right]
        if group:
            out.append(f'<span class="legend-grp">{escape(L[key])}</span>'
                       + "".join(chip(s) for s in group))
    return "".join(out)


def _kpi_card_html(k: dict, hero: bool = False) -> str:
    """3 lines: (1) the number, (2) the name on a single line, (3) the trend at the
    bottom-left. Software Factory additionally shows its sub-metrics small."""
    trend = k.get("trend") or "flat"
    arrow = TREND_ARROW.get(trend, "▬")
    unit = f"<span class='unit'>{escape(str(k.get('unit')))}</span>" if k.get("unit") else ""
    delta = f"{arrow} {escape(str(k.get('delta')))}" if k.get("delta") else ""
    label = escape(str(k.get("label") or "-").upper())
    val = escape(str(k.get("value") or "-"))
    trend_html = f"<div class='t {TREND_CLASS.get(trend, 'flat')}'>{delta}</div>" if delta else ""
    sub = k.get("sub") or []
    sub_html = ""
    if sub:
        parts = "".join(
            f"<span>{escape(str(s.get('label') or ''))} <b>{escape(str(s.get('value') or '-'))}</b></span>"
            for s in sub
        )
        sub_html = f"<div class='kpi-sub'>{parts}</div>"
    return (f"<div class='kpi{' hero' if hero else ''}'>"
            f"<div class='num'>{val}{unit}</div>"
            f"<div class='lbl'>{label}</div>"
            f"{sub_html}{trend_html}</div>")


def _kpi_cards(kpis: list[dict], L: dict) -> str:
    """First KPI (Users) on its own, centred and wider at the top; the rest in a row
    below (Landing Zone / K8aaS / DBaaS / Software Factory, the last with sub-metrics)."""
    if not kpis:
        return f"<div class='empty'>{escape(L['no_kpi'])}</div>"
    hero = _kpi_card_html(kpis[0], hero=True)
    rest = "".join(_kpi_card_html(k) for k in kpis[1:])
    return (f"<div class='kpi-wrap'>"
            f"<div class='kpi-hero-row'>{hero}</div>"
            f"<div class='kpi-row'>{rest}</div></div>")


def _row_label(period: str, L: dict) -> str:
    return {"__current__": L["current"], "__trailing__": L["trailing"]}.get(period, period)


def _sla_table(sla: dict, L: dict) -> str:
    services = (sla or {}).get("services") or []
    rows = (sla or {}).get("rows") or []
    if not services or not rows:
        return f"<div class='empty'>{escape(L['no_sla'])}</div>"
    head = "".join(f"<th>{escape(str(s))}</th>" for s in services)
    body = []
    for r in rows:
        cells = r.get("cells") or []
        tds = []
        for i in range(len(services)):
            c = cells[i] if i < len(cells) else {}
            v = escape(str((c or {}).get("v") or "-"))
            cls = SLA_CLASS.get((c or {}).get("s"), "b-none")
            tds.append(f'<td class="{cls}">{v}</td>')
        body.append(f"<tr><th>{escape(_row_label(str(r.get('period') or '-'), L))}</th>{''.join(tds)}</tr>")
    return (f"<table><thead><tr><th>{escape(L['period'])}</th>{head}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table>")


def _as_event(e) -> dict:
    """Ramener un evenement a la forme que les rendus attendent.

    Le relevé est un blob sans schema: on peut y trouver une chaine la ou l'ecran
    ecrit un dictionnaire (un import, un appel d'API, une version anterieure). La
    lire comme un texte sans date ni type rend un document incomplet; refuser de la
    lire n'en rend aucun.
    """
    if isinstance(e, dict):
        return e
    return {"text": "" if e is None else str(e)}


def _events_list(events: list, L: dict) -> str:
    """Uniform event row: date / type (colour chip) / description. The chip is tinted
    with the event's severity (the "Gravité" entered in the wizard / the Excel)."""
    if not events:
        return f"<div class='empty'>{escape(L['no_event'])}</div>"
    items = []
    for raw in events:
        e = _as_event(raw)
        typ = escape(str(e.get("tag") or "-"))
        sev = e.get("sev") if e.get("sev") in SEV_FG else None
        chip = (f' style="background:{SEV_BG[sev]};color:{SEV_FG[sev]};border-color:{SEV_FG[sev]}"'
                if sev else "")
        items.append(
            f'<li><span class="ev-date">{escape(str(e.get("date") or ""))}</span>'
            f'<span class="ev-type"{chip}>{typ}</span>'
            f'<span class="ev-desc">{escape(str(e.get("text") or ""))}</span></li>'
        )
    return f'<ul class="ev-list">{"".join(items)}</ul>'


def _panel(title: str, sub: str, body: str) -> str:
    subhtml = f' <span class="sub">{sub}</span>' if sub else ""
    return f'<div class="panel"><div class="hd">{title}{subhtml}</div><div class="bd">{body}</div></div>'


def _chart_body(chart: dict, L: dict) -> str:
    # Deux echelles sans marque, et un lecteur n'a aucun moyen de savoir ce que
    # vaut une ligne: la legende dit donc quelle courbe se lit de quel cote.
    return (f'<div class="chart">{_svg_line_chart(chart, L["no_data"])}</div>'
            f'<div class="legend">{_legend(chart.get("series") or [], L)}</div>')


def _onepager(squad_name: str, period: str, data: dict, L: dict) -> str:
    """One squad's KPI one-pager: header band, then a 2x2 panel grid (row 1 = KPIs |
    KPI chart, row 2 = SLA | incidents chart) with identical panels/gutters, then the
    last/next events row - every column and row edge lines up."""
    d = data or {}
    # The charts span the report's calendar year: their sub-labels show that year.
    year = period.split("-")[0]
    kpi_sub = L["kpi_chart_sub"].format(year=year)
    inc_sub = L["inc_chart_sub"].format(year=year)
    return (
        '<div class="page">'
        f'<div class="hdr"><h1>{escape(squad_name)}</h1><div class="date">{escape(_period_long(period, L))}</div></div>'
        '<div class="grid">'
        + _panel(escape(L["key_figures"]), "", _kpi_cards(d.get("kpis") or [], L))
        + _panel(escape(L["kpi_chart"]), escape(kpi_sub), _chart_body(d.get("kpi_chart") or {}, L))
        + _panel(L["sla"], "", _sla_table(d.get("sla") or {}, L))
        + _panel(escape(L["inc_chart"]), escape(inc_sub), _chart_body(d.get("incidents_chart") or {}, L))
        + '</div>'
        '<div class="events-grid">'
        + _panel(escape(L["last_events"]), "", _events_list(d.get("last_events") or [], L))
        + _panel(escape(L["next_events"]), "", _events_list(d.get("next_events") or [], L))
        + '</div>'
        '</div>'
    )


def _document(title: str, body: str, lang: str) -> str:
    return (f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
            f"<title>{escape(title)}</title><style>{_PAGE_CSS}</style></head><body>{body}</body></html>")


def _footer_reserve(prs) -> float:
    """Inches to keep free at the bottom of each slide for the template's footer band
    (logo, page number, legal line). Zero for the plain default deck. Read from the
    master's own non-placeholder shapes that sit in the lower part of the slide, so the
    dense Steerco one-pager does not paint over the uploaded template's branding."""
    h = (prs.slide_height or 0) / 914400.0 or 7.5
    reserve = 0.0
    try:
        for sh in prs.slide_masters[0].shapes:
            if sh.is_placeholder:      # placeholders are not rendered on a blank layout
                continue
            top = (sh.top or 0) / 914400.0
            if top > h * 0.6:          # a shape anchored in the bottom 40% = footer zone
                reserve = max(reserve, h - top)
    except Exception:                  # pragma: no cover - defensive
        pass
    return min(reserve, h * 0.2)       # cap so a pathological template can't eat the slide


# Axis ids of the secondary pair. Any value works as long as it is unique inside the
# chart part; python-pptx draws its own from a range that never reaches these.
_AX_CAT2, _AX_VAL2 = "424242003", "424242004"


def _pptx_second_axis(ch, on_right: list[bool], chart: dict) -> None:
    """Replot the flagged series against a second value axis, drawn on the right.

    python-pptx exposes no secondary axis, so the chart part is edited directly: the
    series marked ``axis: "right"`` move into a second line group pointing at a fresh
    axis pair. That pair's value axis is drawn on the right edge with the y2 scale, and
    its category axis is hidden, the months being already written under the first one.
    The chart is cosmetic, so a template python-pptx lays out differently than expected
    loses the second axis rather than the export."""
    from copy import deepcopy
    from pptx.oxml.ns import qn

    def setval(parent, tag, value):
        el = parent.find(qn(tag))
        if el is not None:
            el.set("val", str(value))

    try:
        plot = ch._chartSpace.find(qn("c:chart")).find(qn("c:plotArea"))
        grp, cat_ax, val_ax = (plot.find(qn(t)) for t in ("c:lineChart", "c:catAx", "c:valAx"))
        if grp is None or cat_ax is None or val_ax is None:  # pragma: no cover - defensive
            return
        grp2, cat_ax2, val_ax2 = deepcopy(grp), deepcopy(cat_ax), deepcopy(val_ax)
        # Split the series: the left group keeps its own, the copy keeps the others.
        for group, wanted in ((grp, False), (grp2, True)):
            for i, ser in enumerate(group.findall(qn("c:ser"))):
                if on_right[i] is not wanted:
                    group.remove(ser)
        # The copied group is read by the new axis pair (cat first, val second).
        for el, axid in zip(grp2.findall(qn("c:axId")), (_AX_CAT2, _AX_VAL2)):
            el.set("val", axid)
        setval(cat_ax2, "c:axId", _AX_CAT2)
        setval(cat_ax2, "c:crossAx", _AX_VAL2)
        setval(cat_ax2, "c:delete", 1)          # the months are already under the first axis
        setval(val_ax2, "c:axId", _AX_VAL2)
        setval(val_ax2, "c:crossAx", _AX_CAT2)
        setval(val_ax2, "c:axPos", "r")
        setval(val_ax2, "c:crosses", "max")     # what puts it on the right edge
        gridlines = val_ax2.find(qn("c:majorGridlines"))
        if gridlines is not None:
            val_ax2.remove(gridlines)           # one grid is enough, the two scales share it
        scaling = val_ax2.find(qn("c:scaling"))
        for tag, value in (("c:max", chart.get("y2_max")), ("c:min", chart.get("y2_min") or 0)):
            el = scaling.find(qn(tag))
            if el is None:                      # pragma: no cover - set just above by python-pptx
                el = scaling.makeelement(qn(tag), {})
                scaling.append(el)
            el.set("val", str(float(value or 0)))
        grp.addnext(grp2)
        val_ax.addnext(cat_ax2)
        cat_ax2.addnext(val_ax2)
    except Exception:  # pragma: no cover - defensive
        pass


def _render_pptx(squads: list[dict], period: str, L: dict) -> bytes:
    """Native PPTX: one 16:9 slide per squad, same layout as the HTML (left KPIs+SLA,
    right KPI chart over incidents chart, bottom events). Built on the uploaded export
    template when one is configured (Admin), so slides carry the org's branding."""
    from .. import pptxtpl
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Inches, Pt

    def rgb(h):
        h = (h or "#000000").lstrip("#")
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def add_text(slide, x, y, w, h, text, size=12, bold=False, color="#1B2A3D"):
        tf = slide.shapes.add_textbox(x, y, w, h).text_frame
        tf.word_wrap = True
        r = tf.paragraphs[0].add_run(); r.text = text
        r.font.size = Pt(_fs(size)); r.font.bold = bold; r.font.color.rgb = rgb(color)
        return tf

    def no_shadow(s):
        s.shadow.inherit = False

    def panel(slide, x, y, w, h):
        p = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        p.fill.solid(); p.fill.fore_color.rgb = rgb("#FFFFFF")
        p.line.color.rgb = rgb("#E1E7EF"); p.line.width = Pt(0.75); no_shadow(p)
        return p

    def titled_panel(slide, x, y, w, h, title, sub=""):
        """Panel + tinted header strip (navy title). x/y/w/h are inches; returns the
        inner body box (bx, by, bw, bh) in inches."""
        panel(slide, Inches(x), Inches(y), Inches(w), Inches(h))
        strip = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.34))
        strip.fill.solid(); strip.fill.fore_color.rgb = rgb("#EDF2F8")
        strip.line.fill.background(); no_shadow(strip)
        tf = strip.text_frame; tf.word_wrap = True
        tf.margin_left = Inches(0.14); tf.margin_top = Inches(0.03); tf.margin_bottom = Inches(0.02)
        r = tf.paragraphs[0].add_run(); r.text = title.upper()
        r.font.size = Pt(_fs(12)); r.font.bold = True; r.font.color.rgb = rgb(NAVY)
        if sub:
            rs = tf.paragraphs[0].add_run(); rs.text = "  " + sub.replace("&amp;", "&")
            rs.font.size = Pt(_fs(10)); rs.font.color.rgb = rgb("#6B7C90")
        return x + 0.14, y + 0.44, w - 0.28, h - 0.56

    def kpi_card(slide, x, y, w, h, k, hero=False):
        """3 lines: (1) number, (2) name on one line, (3) trend at the bottom-left.
        Software Factory also shows its sub-metrics small. x/y/w/h in EMU."""
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        card.fill.solid(); card.fill.fore_color.rgb = rgb("#FFFFFF")
        card.line.color.rgb = rgb("#AFC0D6"); card.line.width = Pt(1.0); no_shadow(card)
        num_sz = 24 if hero else 19
        lbl_sz = 13 if hero else 9
        pad = Inches(0.1)
        iw = w - Inches(0.16)
        unit = str(k.get("unit")) if k.get("unit") else ""
        trend = k.get("trend") if k.get("trend") in ("up", "down", "flat") else "flat"
        tcolor = {"up": "#2E9E5B", "down": "#D24545", "flat": "#6B7C90"}[trend]

        def box(yy, hh, wrap=False):
            tf = slide.shapes.add_textbox(x + pad, yy, iw, hh).text_frame
            tf.word_wrap = wrap
            tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = Emu(9000); tf.margin_bottom = Emu(9000)
            return tf

        yy = y + Inches(0.07)
        num_h = Inches(0.36 if hero else 0.28)
        nbox = box(yy, num_h)
        rn = nbox.paragraphs[0].add_run(); rn.text = f"{k.get('value') or '-'}{unit}"
        rn.font.size = Pt(_fs(num_sz)); rn.font.bold = True; rn.font.color.rgb = rgb(NAVY)
        yy += num_h
        # Name: dedicated box, no wrap -> always a single line.
        lbox = box(yy, Inches(0.2))
        # La casse saisie est gardee: en majuscules, « K8aaS » devenait « K8AAS ».
        rl = lbox.paragraphs[0].add_run(); rl.text = str(k.get("label") or "-")
        rl.font.size = Pt(_fs(lbl_sz)); rl.font.bold = True; rl.font.color.rgb = rgb("#141B47")
        yy += Inches(0.2)
        sub = k.get("sub") or []
        if sub:
            # Un libelle et sa valeur ne se separent jamais (espace insecable):
            # coupes par le retour a la ligne, on lisait « Artifactory » puis
            # « 730 SonarQube 878 », la valeur sous le mauvais nom. La boite
            # s'arrete au bord de la carte.
            sbox = box(yy, max(Inches(0.2), y + h - yy - Inches(0.06)), wrap=True)
            p = sbox.paragraphs[0]
            for i, s in enumerate(sub):
                label = str(s.get("label") or "").replace(" ", "\u00a0")
                rl2 = p.add_run(); rl2.text = ("  " if i else "") + f"{label}\u00a0"
                rl2.font.size = Pt(_fs(7)); rl2.font.color.rgb = rgb("#64748B")
                rv2 = p.add_run(); rv2.text = f"{s.get('value') or '-'}"
                rv2.font.size = Pt(_fs(7)); rv2.font.bold = True; rv2.font.color.rgb = rgb(NAVY)
        # Trend: inline for the hero (right under the name), bottom-left otherwise.
        # A card with sub-metrics has them at the bottom: its trend goes on the
        # number's line, at the right, instead of over « GitLab 325 ».
        if k.get("delta"):
            ty = yy if hero else (y + h - Inches(0.26))
            if sub and not hero:
                ty = y + Inches(0.1)
            tbox = box(ty, Inches(0.22))
            if sub and not hero:
                tbox.paragraphs[0].alignment = PP_ALIGN.RIGHT
            rt = tbox.paragraphs[0].add_run(); rt.text = f"{TREND_ARROW.get(trend, '▬')} {k.get('delta')}".strip()
            rt.font.size = Pt(_fs(10 if hero else 9)); rt.font.bold = True; rt.font.color.rgb = rgb(tcolor)

    def set_cell(cell, fill, color, size=10, bold=False):
        cell.fill.solid(); cell.fill.fore_color.rgb = rgb(fill)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_top = Emu(14000); cell.margin_bottom = Emu(14000)
        for p in cell.text_frame.paragraphs:
            p.alignment = PP_ALIGN.CENTER
            for r in p.runs:
                r.font.size = Pt(_fs(size)); r.font.bold = bold; r.font.color.rgb = rgb(color)

    def sla_table(slide, x, y, w, h, sla):
        services = sla.get("services") or []
        rows = sla.get("rows") or []
        if not services or not rows:
            return
        nrows, ncols = len(rows) + 1, len(services) + 1
        tbl = slide.shapes.add_table(nrows, ncols, x, y, w, Inches(h)).table
        # Header a touch shorter, data rows share the rest so the table fills the box.
        head_h = min(0.42, h / nrows)
        data_h = (h - head_h) / (nrows - 1) if nrows > 1 else head_h
        tbl.rows[0].height = Inches(head_h)
        for i in range(1, nrows):
            tbl.rows[i].height = Inches(data_h)
        for j, txt in enumerate([L["period"]] + [str(s) for s in services]):
            tbl.cell(0, j).text = txt
            set_cell(tbl.cell(0, j), NAVY, "#FFFFFF", bold=True)
        fills = {"ok": "#E4F3EA", "warn": "#FBF0D9", "ko": "#F7E0E0"}
        texts = {"ok": "#2E9E5B", "warn": "#9C7212", "ko": "#D24545"}
        for i, r in enumerate(rows):
            tbl.cell(i + 1, 0).text = _row_label(str(r.get("period", "-")), L)
            set_cell(tbl.cell(i + 1, 0), "#EEF4F8", NAVY, bold=True)
            cells = r.get("cells") or []
            for j in range(len(services)):
                cell = cells[j] if j < len(cells) else {}
                s = (cell or {}).get("s")
                v = str((cell or {}).get("v", "-"))
                if L is I18N["en"]:
                    v = v.replace(",", ".")   # 99.1%, not the French 99,1%
                tbl.cell(i + 1, j + 1).text = v
                set_cell(tbl.cell(i + 1, j + 1), fills.get(s, "#FFFFFF"), texts.get(s, "#6B7C90"), bold=True)

    def line_chart(slide, x, y, w, h, chart):
        series = [s for s in (chart.get("series") or []) if any(v is not None for v in (s.get("data") or []))]
        if not series:
            add_text(slide, x, y, w, Inches(0.3), L["no_data"], size=10, color="#98A2B3")
            return
        on_right = [s.get("axis") == "right" for s in series]
        two = bool(chart.get("y2_max")) and any(on_right) and not all(on_right)
        note = L["axis_right"] if two else ""
        cd = CategoryChartData()
        cd.categories = chart.get("labels") or [str(i + 1) for i in range(max(len(s["data"]) for s in series))]
        for s in series:
            cd.add_series(_series_name(s, note), [None if v is None else float(v) for v in s["data"]])
        gf = slide.shapes.add_chart(XL_CHART_TYPE.LINE, x, y, w, h, cd)
        ch = gf.chart
        ch.has_title = False
        ch.has_legend = True
        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
        ch.legend.include_in_layout = False
        ch.legend.font.size = Pt(_fs(8))
        for i, ps in enumerate(ch.series):
            ps.format.line.color.rgb = rgb(series[i].get("color") or NAVY)
            ps.format.line.width = Pt(2)
        try:
            # The primary scale only has to hold the series that stayed on the left.
            ch.value_axis.maximum_scale = float(chart.get("y_max") or 100)
            ch.value_axis.minimum_scale = float(chart.get("y_min") or 0)
            ch.value_axis.tick_labels.font.size = Pt(_fs(8))
            ch.category_axis.tick_labels.font.size = Pt(_fs(8))
        except Exception:  # pragma: no cover
            pass
        if two:
            _pptx_second_axis(ch, on_right, chart)

    def events(slide, x, y, w, h, evs):
        """One event per line, as many as the panel holds, the rest counted.

        Written in one text box without a limit, the list ran out of its card
        and off the slide: two events of four were visible, cut by the edge."""
        tf = slide.shapes.add_textbox(x, y, w, h).text_frame
        tf.word_wrap = False
        tf.margin_top = Emu(0)
        size = 11
        line_h = _fs(size) * 1.2 / 72 + 2 / 72          # the line and its space_after
        room = max(1, int((h / 914400 + 0.06) / line_h))
        cpl = int((w / 914400 - 0.2) / (0.0060 * _fs(size)))
        if not evs:
            re = tf.paragraphs[0].add_run(); re.text = L["no_event"]
            re.font.size = Pt(_fs(size)); re.font.italic = True; re.font.color.rgb = rgb("#6B7C90")
            return
        shown = evs if len(evs) <= room else evs[:room - 1]
        for i, raw in enumerate(shown):
            e = _as_event(raw)
            pe = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            pe.space_after = Pt(2)
            date = str(e.get("date") or "")
            tag = str(e.get("tag") or "")
            rd = pe.add_run(); rd.text = f"{date}   " if date else ""
            rd.font.size = Pt(_fs(size)); rd.font.bold = True; rd.font.color.rgb = rgb("#6B7C90")
            if tag:
                # Type coloured by the event's severity, like the HTML chip.
                rtp = pe.add_run(); rtp.text = f"{tag}   "
                rtp.font.size = Pt(_fs(size)); rtp.font.bold = True
                rtp.font.color.rgb = rgb(SEV_FG.get(e.get("sev"), "#13315C"))
            left = max(10, cpl - len(date) - len(tag) - 6)
            rt = pe.add_run(); rt.text = _cut(str(e.get("text", "")), left)
            rt.font.size = Pt(_fs(size)); rt.font.color.rgb = rgb("#1B2A3D")
        if len(shown) < len(evs):
            extra = len(evs) - len(shown)
            pm = tf.add_paragraph()
            rm = pm.add_run()
            rm.text = L["more_events_one"] if extra == 1 else L["more_events"].format(n=extra)
            rm.font.size = Pt(_fs(size)); rm.font.color.rgb = rgb("#6B7C90")

    def not_filled(slide, x, y, w, d):
        """An empty month says so, and who still owes their part."""
        tf = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.8)).text_frame
        tf.word_wrap = True
        r = tf.paragraphs[0].add_run()
        r.text = L["not_filled"].format(month=_period_long(period, L))
        r.font.size = Pt(_fs(11)); r.font.italic = True; r.font.color.rgb = rgb("#6B7C90")
        if d.get("missing"):
            p2 = tf.add_paragraph(); r2 = p2.add_run()
            r2.text = L["expected_from"].format(names=", ".join(d["missing"]))
            r2.font.size = Pt(_fs(11)); r2.font.bold = True; r2.font.color.rgb = rgb("#9C7212")

    prs = pptxtpl.new_presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    # Leave the uploaded template's footer band (logo, page number) uncovered so it
    # actually shows through the one-pager. 0 for the plain default deck (full slide).
    foot = _footer_reserve(prs)

    # Symmetric grid geometry (inches): equal columns, equal gutters, aligned rows.
    LM = 0.45
    GUT = 0.22
    COLW = (13.333 - 2 * LM - GUT) / 2          # left/right column width
    LX, RX = LM, LM + COLW + GUT
    year = period.split("-")[0]
    kpi_sub = L["kpi_chart_sub"].format(year=year)
    inc_sub = L["inc_chart_sub"].format(year=year)
    for s in squads:
        slide = pptxtpl.add_slide(prs)
        d = s["data"] or {}
        # Compact, discreet header: navy name (left) + muted period (right).
        # Le corps descend d'un cran pour un nom long avant de le couper: la
        # place existe, le nom etait coupe vers 50 caracteres.
        pname = s["squad_name"] or ""
        for t_fs in (19, 17, 15):
            t_cpl = int(8.8 / (0.0068 * _fs(t_fs)))
            if len(pname) <= t_cpl:
                break
        add_text(slide, Inches(LM), Inches(0.26), Inches(8.8), Inches(0.4),
                 _cut(pname, t_cpl), size=t_fs, bold=True, color=NAVY)
        pmeta = slide.shapes.add_textbox(Inches(13.333 - LM - 4), Inches(0.32), Inches(4), Inches(0.3)).text_frame
        pp = pmeta.paragraphs[0]; pp.alignment = PP_ALIGN.RIGHT
        rp = pp.add_run(); rp.text = _period_long(period, L); rp.font.size = Pt(_fs(12)); rp.font.bold = True; rp.font.color.rgb = rgb("#6B7C90")

        # 2x2 grid: row 1 = KPIs | KPI chart, row 2 = SLA | incidents chart. When a
        # template reserves a footer, compress the grid + events to sit above it.
        gy, vg = 0.92, 0.18
        if foot:
            eh = 1.15
            ey = 7.5 - foot - 0.08 - eh
            gb = ey - 0.16
        else:
            gb, ey, eh = 5.9, 6.06, 1.28
        row_h = (gb - gy - vg) / 2
        r1y, r2y = gy, gy + row_h + vg

        # Row 1 left: KPI panel. Users (hero) centred on top, the rest in a row below.
        bx, by, bw, bh = titled_panel(slide, LX, r1y, COLW, row_h, L["key_figures"])
        kpis = d.get("kpis") or []
        if not kpis:
            not_filled(slide, bx, by, bw, d)
        if kpis:
            cg = 0.1
            hero_h = min(0.92, bh * 0.48)
            hero_w = bw * 0.46
            kpi_card(slide, Inches(bx + (bw - hero_w) / 2), Inches(by), Inches(hero_w), Inches(hero_h), kpis[0], hero=True)
            rest = kpis[1:5]
            if rest:
                ry = by + hero_h + cg
                rh = bh - hero_h - cg
                cw = (bw - cg * (len(rest) - 1)) / len(rest)
                for i, k in enumerate(rest):
                    kpi_card(slide, Inches(bx + i * (cw + cg)), Inches(ry), Inches(cw), Inches(rh), k)
        # Row 1 right: KPI chart.
        bx, by, bw, bh = titled_panel(slide, RX, r1y, COLW, row_h, L["kpi_chart"], kpi_sub)
        line_chart(slide, Inches(bx), Inches(by), Inches(bw), Inches(bh), d.get("kpi_chart") or {})

        # Row 2 left: SLA table.
        bx, by, bw, bh = titled_panel(slide, LX, r2y, COLW, row_h, L["sla"])
        if (d.get("sla") or {}).get("services"):
            sla_table(slide, Inches(bx), Inches(by), Inches(bw), bh, d.get("sla") or {})
        else:
            add_text(slide, Inches(bx), Inches(by), Inches(bw), Inches(0.3), L["no_sla"], size=11,
                     color="#6B7C90")
        # Row 2 right: incidents chart.
        bx, by, bw, bh = titled_panel(slide, RX, r2y, COLW, row_h, L["inc_chart"], inc_sub)
        line_chart(slide, Inches(bx), Inches(by), Inches(bw), Inches(bh), d.get("incidents_chart") or {})

        # Bottom: events row, same two columns (ey/eh set above with the footer reserve).
        bx, by, bw, bh = titled_panel(slide, LX, ey, COLW, eh, L["last_events"])
        events(slide, Inches(bx), Inches(by), Inches(bw), Inches(bh), d.get("last_events") or [])
        bx, by, bw, bh = titled_panel(slide, RX, ey, COLW, eh, L["next_events"])
        events(slide, Inches(bx), Inches(by), Inches(bw), Inches(bh), d.get("next_events") or [])

    if not squads:
        slide = pptxtpl.add_slide(prs)
        add_text(slide, Inches(0.5), Inches(0.5), Inches(9), Inches(0.6), f"Steerco {_period_long(period, L)}",
                 size=24, bold=True, color=NAVY)
        add_text(slide, Inches(0.5), Inches(1.3), Inches(9), Inches(0.5), L["no_squads"], size=12, color="#6B7C90")

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Document endpoints
# --------------------------------------------------------------------------

def _enabled_platforms(db: Session, user: User) -> list[Platform]:
    return [p for p in _platforms_in_scope(db, user) if p.steerco_enabled]


@router.get("/onepager.html", response_class=HTMLResponse)
def onepager_html(platform_id: int = Query(...), period: str = PERIOD,
                  lang: str | None = Query(None), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """One platform's KPI one-pager (auto-built from the year's monthly snapshots)."""
    p = _platform_in_scope(db, user, platform_id)
    L = I18N[_lang(lang)]
    body = _onepager(p.name, period, _aggregate(db, platform_id, period), L)
    return HTMLResponse(_document(f"Steerco {p.name} {period}", body, _lang(lang)))


@router.post("/platform/{platform_id}/preview.html", response_class=HTMLResponse)
def preview_html(platform_id: int, period: str = PERIOD, data: dict = Body(...),
                 lang: str | None = Query(None), db: Session = Depends(get_db),
                 user: User = Depends(require_writer)):
    """Live preview of the one-pager for the wizard, using the still-unsaved snapshot
    (``data``) as the current month. Nothing is persisted. Open to any contributor of
    the platform (they are the ones filling the report)."""
    p = _platform_in_scope(db, user, platform_id)
    _write_scope(db, user, p)
    L = I18N[_lang(lang)]
    body = _onepager(p.name, period, _aggregate(db, platform_id, period, override=data), L)
    return HTMLResponse(_document(f"Steerco {p.name} {period}", body, _lang(lang)))


@router.get("/document.html", response_class=HTMLResponse)
def document_html(period: str = PERIOD, lang: str | None = Query(None), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Consolidated steerco (all enabled platforms) as HTML one-pagers."""
    L = I18N[_lang(lang)]
    pages = "".join(_onepager(p.name, period, _aggregate(db, p.id, period), L)
                    for p in _enabled_platforms(db, user))
    if not pages:
        pages = f"<div class='page'><p class='empty'>{escape(L['no_squads'])}</p></div>"
    return HTMLResponse(_document(f"Steerco {period}", pages, _lang(lang)))


def _fname(name: str) -> str:
    """A file-name-safe platform name."""
    import re as _re
    import unicodedata as _ud
    flat = _ud.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return _re.sub(r"[^A-Za-z0-9]+", "_", flat).strip("_") or "plateforme"


@router.get("/document.pptx")
def document_pptx(period: str = PERIOD, lang: str | None = Query(None),
                  platform_id: int | None = Query(None), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Consolidated steerco as PPTX, one slide per platform (or only the chosen
    one, as the HTML one-pager). 501 without python-pptx."""
    from .. import pptxtpl
    L = I18N[_lang(lang)]
    squads = [{"squad_name": p.name, "data": _aggregate(db, p.id, period)}
              for p in _enabled_platforms(db, user)
              if platform_id is None or p.id == platform_id]
    pptxtpl.use(pptxtpl.get(db))
    try:
        payload = _render_pptx(squads, period, L)
    except ModuleNotFoundError:
        raise HTTPException(status_code=501, detail="Generation PPTX indisponible (python-pptx non installe)")
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="steerco_{}{}.pptx"'.format(
            period, f"_{_fname(squads[0]['squad_name'])}" if platform_id is not None and squads else "")},
    )
