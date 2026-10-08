"""Studio des exports (docs/35): templates, themes, files, assignments,
and the preview and render of any document through a template.

Designing is scoped (see ``exportstore.can_design``): the administrator works on
every scope, a tribe leader on their tribe, its squads and its platforms, a squad
leader on a squad they lead, in simple mode. Previewing and downloading a document
is open to whoever may export it already: the data comes through the very same
module and capability gates as the export endpoints, and a template only decides
how that data is laid out.
"""
from __future__ import annotations

import base64
import json
import re

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import exportspec as X
from .. import exportstore as S
from ..database import get_db
from ..deps import get_current_user, record_audit, require_capability
from ..models import (ExportAsset, ExportAssignment, ExportTemplate, ExportTemplateVersion,
                      ExportTheme, Platform, Squad, Tribe, User)

router = APIRouter(prefix="/api/exports", tags=["exports"])

# The Studio opens per persona (capability "exports", Admin > Personas). The slides
# of a document (/document.html, the "Slides" button of the Export menu) stay open
# to whoever may export it: they are the document, not the Studio.
_studio = [Depends(require_capability("exports"))]

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _kind(doc_kind: str) -> str:
    if doc_kind not in X.DOC_KINDS:
        raise HTTPException(status_code=422, detail="Type de document inconnu")
    return doc_kind


def _scope_label(db: Session, scope_type: str, scope_id: int | None) -> str:
    if scope_type == "global":
        return ""
    model = {"tribe": Tribe, "squad": Squad, "platform": Platform}.get(scope_type)
    obj = db.get(model, scope_id) if model and scope_id else None
    return getattr(obj, "name", "") or "-"


def _parse_key(key: str) -> tuple[str, int | None]:
    if key == "global":
        return "global", None
    m = re.fullmatch(r"(tribe|squad|platform):(\d+)", key or "")
    if not m:
        raise HTTPException(status_code=422, detail="Portée invalide")
    return m.group(1), int(m.group(2))


def _check_scope(db: Session, scope_type: str, scope_id: int | None) -> None:
    if scope_type not in S.SCOPE_TYPES:
        raise HTTPException(status_code=422, detail="Portée invalide")
    if scope_type != "global":
        model = {"tribe": Tribe, "squad": Squad, "platform": Platform}[scope_type]
        if not scope_id or db.get(model, scope_id) is None:
            raise HTTPException(status_code=404, detail="Portée introuvable")


def _assert_design(db: Session, user: User, scope_type: str, scope_id: int | None) -> None:
    if not S.can_design(db, user, scope_type, scope_id):
        raise HTTPException(status_code=403, detail="Vous ne pouvez pas modifier les modèles de cette portée")


def _tpl(db: Session, user: User, tid: int, *, write: bool = False) -> ExportTemplate:
    t = db.get(ExportTemplate, tid)
    if t is None or not S.can_read(db, user, t):
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    if write:
        if t.system:
            raise HTTPException(status_code=409, detail="Le modèle Standard ne se modifie pas : dérivez-en un")
        _assert_design(db, user, t.scope_type, t.scope_id)
    return t


def _assignments_of(db: Session, tid: int) -> list[str]:
    return [a.scope_key for a in db.scalars(select(ExportAssignment).where(ExportAssignment.template_id == tid))]


def _meta(db: Session, user: User, t: ExportTemplate) -> dict:
    v = S.published(db, t)
    parent = db.get(ExportTemplate, t.parent_id) if t.parent_id else None
    return {
        "id": t.id, "doc_kind": t.doc_kind, "name": t.name, "scope_type": t.scope_type,
        "scope_id": t.scope_id, "scope_label": _scope_label(db, t.scope_type, t.scope_id),
        "parent_id": t.parent_id, "parent_name": parent.name if parent else None,
        "parent_scope_label": _scope_label(db, parent.scope_type, parent.scope_id) if parent else None,
        "mode": t.mode, "system": t.system, "shared": t.shared,
        "published_number": v.number if v else None,
        "unpublished_changes": (not t.system) and S.has_unpublished(db, t),
        "can_edit": (not t.system) and S.can_design(db, user, t.scope_type, t.scope_id),
        "simple_only": S.simple_only(db, user, t.scope_type, t.scope_id),
        "assigned": _assignments_of(db, t.id),
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _designable_scopes(db: Session, user: User) -> dict:
    """Where this person may design, for the editor's pickers."""
    from ..deps import led_squad_ids
    out = {"global": user.role == "admin", "tribes": [], "squads": [], "platforms": []}
    tribes = db.scalars(select(Tribe).order_by(Tribe.display_order, Tribe.id)).all()
    if user.role == "admin":
        tids = {t.id for t in tribes}
    elif user.role == "tribe_leader" and user.tribe_id:
        tids = {user.tribe_id}
    else:
        tids = set()
    out["tribes"] = [{"id": t.id, "name": t.name} for t in tribes if t.id in tids]
    led = set(db.scalars(led_squad_ids(db, user)).all())
    for sq in db.scalars(select(Squad).order_by(Squad.display_order, Squad.id)):
        if sq.tribe_id in tids or sq.id in led:
            out["squads"].append({"id": sq.id, "name": sq.name, "tribe_id": sq.tribe_id,
                                  "simple": S.simple_only(db, user, "squad", sq.id)})
    for p in db.scalars(select(Platform).order_by(Platform.display_order, Platform.name)):
        if p.tribe_id in tids:
            out["platforms"].append({"id": p.id, "name": p.name, "tribe_id": p.tribe_id})
    return out


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------
@router.get("/catalog", dependencies=_studio)
def catalog(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/exports/catalog: sections, blocks, widgets, parameters, fonts, and
    where the caller may design."""
    S.ensure_system(db)
    db.commit()
    return {**X.catalogue(), "fonts": list(S.FONTS), "designer": S.is_designer(db, user),
            "scopes": _designable_scopes(db, user)}


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------
@router.get("/templates", dependencies=_studio)
def list_templates(doc_kind: str | None = Query(None), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """GET /api/exports/templates: the templates the caller can read (Standard,
    shared ones, and those of their scopes), newest first within each kind."""
    S.ensure_system(db)
    db.commit()
    q = select(ExportTemplate)
    if doc_kind:
        q = q.where(ExportTemplate.doc_kind == _kind(doc_kind))
    rows = [t for t in db.scalars(q.order_by(ExportTemplate.doc_kind, ExportTemplate.system.desc(),
                                             ExportTemplate.name)) if S.can_read(db, user, t)]
    return [_meta(db, user, t) for t in rows]


@router.post("/templates", status_code=201, dependencies=_studio)
def create_template(payload: dict = Body(...), db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """POST /api/exports/templates: a new template at a scope, derived from (or
    copied from) an existing one, or from Standard. A squad leader may only derive."""
    kind = _kind(payload.get("doc_kind") or "")
    stype, sid = payload.get("scope_type") or "global", payload.get("scope_id")
    sid = int(sid) if sid not in (None, "") else None
    _check_scope(db, stype, sid)
    _assert_design(db, user, stype, sid)
    mode = payload.get("mode") if payload.get("mode") in ("derived", "detached", "root") else "derived"
    if S.simple_only(db, user, stype, sid):
        mode = "derived"
    src_id = payload.get("from_template_id")
    src = _tpl(db, user, int(src_id)) if src_id else S.ensure_system(db)[kind]
    if src.doc_kind != kind:
        raise HTTPException(status_code=422, detail="Le modèle source est d'un autre type de document")
    name = X._clean_text(payload.get("name") or "", 120).strip() or "Nouveau modele"
    base = S.effective(db, src)[0]
    t = ExportTemplate(doc_kind=kind, name=name, scope_type=stype, scope_id=sid, mode=mode,
                       parent_id=src.id if mode in ("derived", "detached") else None,
                       shared=bool(payload.get("shared", True)), draft={}, draft_locks=[],
                       created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(t)
    db.flush()
    t.draft = {} if mode == "derived" else base
    record_audit(db, user.id, "export_template.create", entity="export_template", entity_id=t.id,
                 detail={"doc_kind": kind, "scope": S.scope_key(stype, sid), "mode": mode, "from": src.id})
    db.commit()
    return _meta(db, user, t)


def _detail(db: Session, user: User, t: ExportTemplate) -> dict:
    draft_eff, skipped = S.effective(db, t, draft=True)
    pub_eff = S.effective(db, t)[0]
    parent = S.parent_effective(db, t)
    versions = [{"id": v.id, "number": v.number, "comment": v.comment,
                 "created_at": v.created_at.isoformat() if v.created_at else None,
                 "author": (db.get(User, v.created_by_user_id).display_name
                            if v.created_by_user_id and db.get(User, v.created_by_user_id) else None),
                 "current": v.id == t.published_version_id}
                for v in sorted(t.versions, key=lambda v: -v.number)]
    return {**_meta(db, user, t), "spec": draft_eff, "published_spec": pub_eff, "parent_spec": parent,
            "skipped": skipped, "inherited_locks": S.inherited_locks(db, t),
            "locks": list(t.draft_locks or []), "lock_paths": X.lock_paths(draft_eff),
            "versions": versions, "children": [c.id for c in S.descendants(db, t)][:50]}


@router.get("/templates/{tid}", dependencies=_studio)
def get_template(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/exports/templates/{id}: the template, its draft and published
    specifications, its parent's, what of it is locked or orphaned, its versions."""
    return _detail(db, user, _tpl(db, user, tid))


@router.put("/templates/{tid}", dependencies=_studio)
def save_template(tid: int, payload: dict = Body(...), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """PUT /api/exports/templates/{id}: save the draft (the full specification; a
    derived template keeps only its differences). Exports keep the published version."""
    t = _tpl(db, user, tid, write=True)
    if "name" in payload:
        t.name = X._clean_text(payload.get("name") or "", 120).strip() or t.name
    if "shared" in payload:
        t.shared = bool(payload.get("shared"))
    if "spec" in payload:
        spec = X.normalize(payload.get("spec"), t.doc_kind)
        if S.simple_only(db, user, t.scope_type, t.scope_id):
            base = S.parent_effective(db, t) or S.effective(db, t)[0]
            if not S.check_simple(base, spec):
                raise HTTPException(status_code=403,
                                    detail="En mode simple, on règle et on masque, on n'ajoute rien")
            payload["locks"] = []
        S.save_draft(db, t, spec, payload.get("locks", t.draft_locks), user)
    record_audit(db, user.id, "export_template.save", entity="export_template", entity_id=t.id)
    db.commit()
    return _detail(db, user, t)


@router.post("/templates/{tid}/publish", dependencies=_studio)
def publish_template(tid: int, payload: dict = Body(default={}), db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """POST /api/exports/templates/{id}/publish: the draft becomes the version the
    exports use, and the templates derived from this one follow it."""
    t = _tpl(db, user, tid, write=True)
    v = S.publish(db, t, user, (payload or {}).get("comment") or "")
    record_audit(db, user.id, "export_template.publish", entity="export_template", entity_id=t.id,
                 detail={"version": v.number})
    db.commit()
    return _detail(db, user, t)


@router.post("/templates/{tid}/detach", dependencies=_studio)
def detach_template(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """POST /api/exports/templates/{id}/detach: stop following the parent; the
    template keeps its current look as a full copy."""
    t = _tpl(db, user, tid, write=True)
    if S.simple_only(db, user, t.scope_type, t.scope_id):
        raise HTTPException(status_code=403, detail="Un modèle de squad suit toujours son parent")
    if t.mode == "derived":
        draft_eff = S.effective(db, t, draft=True)[0]
        had_version = S.published(db, t) is not None
        pub_eff = S.effective(db, t)[0]
        t.mode = "detached"
        # The published version was a patch on the parent: publish its full copy
        # so the exports keep exactly what they had and stop following the parent.
        # The draft, with any unpublished change, stays a draft.
        if had_version:
            t.draft = pub_eff
            S.publish(db, t, user, "detach")
        t.draft = draft_eff
    record_audit(db, user.id, "export_template.detach", entity="export_template", entity_id=t.id)
    db.commit()
    return _detail(db, user, t)


@router.post("/templates/{tid}/restore", dependencies=_studio)
def restore_version(tid: int, payload: dict = Body(...), db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """POST /api/exports/templates/{id}/restore {version_id}: the draft goes back to
    that version (publish it to make it the exported one)."""
    t = _tpl(db, user, tid, write=True)
    v = db.get(ExportTemplateVersion, int(payload.get("version_id") or 0))
    if v is None or v.template_id != t.id:
        raise HTTPException(status_code=404, detail="Version introuvable")
    t.draft = v.spec
    t.draft_locks = list(v.locks or [])
    t.updated_at = S.now()
    record_audit(db, user.id, "export_template.restore", entity="export_template", entity_id=t.id,
                 detail={"version": v.number})
    db.commit()
    return _detail(db, user, t)


def _spec_of(db: Session, t: ExportTemplate, which: str) -> dict:
    if which == "draft":
        return S.effective(db, t, draft=True)[0]
    if which == "published":
        return S.effective(db, t)[0]
    if which == "parent":
        p = S.parent_effective(db, t)
        if p is None:
            raise HTTPException(status_code=404, detail="Pas de modèle parent")
        return p
    if which.isdigit():
        v = db.get(ExportTemplateVersion, int(which))
        if v is None or v.template_id != t.id:
            raise HTTPException(status_code=404, detail="Version introuvable")
        if t.mode == "derived":
            base = S.parent_effective(db, t)
            return X.apply(base, v.spec, S.inherited_locks(db, t), t.doc_kind)[0] if base else \
                X.normalize(v.spec, t.doc_kind)
        return X.normalize(v.spec, t.doc_kind)
    raise HTTPException(status_code=422, detail="Comparaison invalide")


def changes(a: dict, b: dict) -> list[dict]:
    """What changes from ``a`` to ``b``, said path by path, for people."""
    out = []
    if a.get("theme_id") != b.get("theme_id"):
        out.append({"path": "theme", "before": a.get("theme_id"), "after": b.get("theme_id")})
    for k in b["doc"]:
        if a["doc"].get(k) != b["doc"][k]:
            out.append({"path": f"doc/{k}", "before": a["doc"].get(k), "after": b["doc"][k]})
    am = {s["id"]: s for s in a["sections"]}
    bm = {s["id"]: s for s in b["sections"]}
    for sid in am:
        if sid not in bm:
            out.append({"path": f"section/{sid}", "before": am[sid]["type"], "after": None})
    for sid, s in bm.items():
        if sid not in am:
            out.append({"path": f"section/{sid}", "before": None, "after": s["type"]})
            continue
        p = am[sid]
        if p["enabled"] != s["enabled"]:
            out.append({"path": f"section/{sid}/enabled", "before": p["enabled"], "after": s["enabled"]})
        for k, v in s["params"].items():
            if p["params"].get(k) != v:
                out.append({"path": f"section/{sid}/{k}", "before": p["params"].get(k), "after": v})
        for bid, blk in s["blocks"].items():
            pb = p["blocks"].get(bid) or {"enabled": True, "params": {}}
            if pb["enabled"] != blk["enabled"]:
                out.append({"path": f"section/{sid}/block/{bid}", "before": pb["enabled"], "after": blk["enabled"]})
            for k, v in blk["params"].items():
                if (pb.get("params") or {}).get(k) != v:
                    out.append({"path": f"section/{sid}/block/{bid}/{k}",
                                "before": (pb.get("params") or {}).get(k), "after": v})
        if s.get("items") != p.get("items"):
            out.append({"path": f"section/{sid}/items", "before": len(p.get("items") or []),
                        "after": len(s.get("items") or [])})
    if [x for x in (s["id"] for s in a["sections"]) if x in bm] != [x for x in (s["id"] for s in b["sections"]) if x in am]:
        out.append({"path": "order", "before": [s["id"] for s in a["sections"]],
                    "after": [s["id"] for s in b["sections"]]})
    return out


@router.get("/templates/{tid}/compare", dependencies=_studio)
def compare(tid: int, a: str = Query("published"), b: str = Query("draft"), db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """GET /api/exports/templates/{id}/compare?a=&b=: two states of a template
    (``draft``, ``published``, ``parent`` or a version id) and what differs."""
    t = _tpl(db, user, tid)
    sa, sb = _spec_of(db, t, a), _spec_of(db, t, b)
    return {"a": sa, "b": sb, "changes": changes(sa, sb)}


@router.delete("/templates/{tid}", status_code=204, dependencies=_studio)
def delete_template(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """DELETE /api/exports/templates/{id}: refused while other templates derive from
    it; its assignments go with it (those scopes fall back to the next one)."""
    t = _tpl(db, user, tid, write=True)
    kids = [c for c in S.descendants(db, t) if c.mode == "derived"]
    if kids:
        raise HTTPException(status_code=409, detail="D'autres modèles en dérivent : " +
                            ", ".join(sorted({k.name for k in kids}))[:300])
    for a in db.scalars(select(ExportAssignment).where(ExportAssignment.template_id == t.id)):
        db.delete(a)
    record_audit(db, user.id, "export_template.delete", entity="export_template", entity_id=t.id,
                 detail={"name": t.name})
    db.delete(t)
    db.commit()


# --------------------------------------------------------------------------
# Import / export of a template as a file
# --------------------------------------------------------------------------
FILE_FORMAT = "teamfollowup-export-template"


@router.get("/templates/{tid}/file", dependencies=_studio)
def export_template_file(tid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/exports/templates/{id}/file: the published template as one JSON file
    (its specification, its theme and every file it uses), to load in another
    instance (test, then production)."""
    t = _tpl(db, user, tid)
    spec = S.effective(db, t)[0]
    assets = {}
    theme = None
    if spec.get("theme_id"):
        th = db.get(ExportTheme, spec["theme_id"])
        if th is not None:
            theme = {"name": th.name, "config": S.clean_theme_config(th.config), "master": th.master_asset_id}
            if th.master_asset_id:
                assets[str(th.master_asset_id)] = None
    for sec in spec["sections"]:
        for k in ("image", "asset"):
            if sec["params"].get(k):
                assets[str(sec["params"][k])] = None
        for it in sec.get("items") or []:
            if it["params"].get("asset"):
                assets[str(it["params"]["asset"])] = None
    for aid in list(assets):
        a = db.get(ExportAsset, int(aid))
        assets[aid] = ({"filename": a.filename, "data": base64.b64encode(a.data).decode("ascii")}
                       if a is not None else None)
    body = {"format": FILE_FORMAT, "version": 1, "doc_kind": t.doc_kind, "name": t.name, "spec": spec,
            "theme": theme, "assets": {k: v for k, v in assets.items() if v}}
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", t.name).strip("_") or "modele"
    return Response(content=json.dumps(body, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="modele_{t.doc_kind}_{name}.json"'})


@router.post("/templates/import", status_code=201, dependencies=_studio)
def import_template_file(payload: dict = Body(...), db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """POST /api/exports/templates/import {scope_type, scope_id, file}: create a
    template (and its theme and files) from an exported file. Everything is
    validated as if typed in the editor."""
    stype, sid = payload.get("scope_type") or "global", payload.get("scope_id")
    sid = int(sid) if sid not in (None, "") else None
    _check_scope(db, stype, sid)
    _assert_design(db, user, stype, sid)
    if S.simple_only(db, user, stype, sid):
        raise HTTPException(status_code=403, detail="Importer un modèle est réservé aux tribe leaders")
    f = payload.get("file") or {}
    if f.get("format") != FILE_FORMAT:
        raise HTTPException(status_code=422, detail="Ce fichier n'est pas un modèle d'export")
    kind = _kind(f.get("doc_kind") or "")
    tribe = S.scope_tribe(db, stype, sid)
    ids = {}
    try:
        for old, a in (f.get("assets") or {}).items():
            raw = base64.b64decode((a or {}).get("data") or "", validate=True)
            ids[str(old)] = S.store_asset(db, a.get("filename") or "fichier", raw, "", tribe, user).id
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Fichier joint refusé ({exc})")
    spec = X.normalize(f.get("spec"), kind)

    def remap(v):
        return ids.get(str(v)) if v else None
    for sec in spec["sections"]:
        for k in ("image", "asset"):
            if k in sec["params"] and sec["params"][k]:
                sec["params"][k] = remap(sec["params"][k])
        for it in sec.get("items") or []:
            if it["params"].get("asset"):
                it["params"]["asset"] = remap(it["params"]["asset"])
    spec["theme_id"] = None
    th = f.get("theme")
    if isinstance(th, dict):
        theme = ExportTheme(name=X._clean_text(th.get("name") or "Theme", 120), tribe_id=tribe,
                            config=S.clean_theme_config(th.get("config")),
                            master_asset_id=remap(th.get("master")), created_by_user_id=user.id)
        db.add(theme)
        db.flush()
        spec["theme_id"] = theme.id
    t = ExportTemplate(doc_kind=kind, name=X._clean_text(f.get("name") or "Modele importe", 120),
                       scope_type=stype, scope_id=sid, mode="root", shared=True, draft=spec, draft_locks=[],
                       created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(t)
    db.flush()
    record_audit(db, user.id, "export_template.import", entity="export_template", entity_id=t.id,
                 detail={"doc_kind": kind, "scope": S.scope_key(stype, sid)})
    db.commit()
    return _meta(db, user, t)


# --------------------------------------------------------------------------
# Assignments
# --------------------------------------------------------------------------
@router.get("/assignments", dependencies=_studio)
def list_assignments(doc_kind: str | None = Query(None), db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """GET /api/exports/assignments: which template each scope uses."""
    q = select(ExportAssignment)
    if doc_kind:
        q = q.where(ExportAssignment.doc_kind == _kind(doc_kind))
    out = []
    for a in db.scalars(q):
        stype, sid = _parse_key(a.scope_key)
        t = db.get(ExportTemplate, a.template_id)
        out.append({"doc_kind": a.doc_kind, "scope_key": a.scope_key, "scope_type": stype, "scope_id": sid,
                    "scope_label": _scope_label(db, stype, sid), "template_id": a.template_id,
                    "template_name": t.name if t else None,
                    "can_edit": S.can_design(db, user, stype, sid)})
    return out


@router.put("/assignments", dependencies=_studio)
def set_assignment(payload: dict = Body(...), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """PUT /api/exports/assignments {doc_kind, scope_type, scope_id, template_id|null}:
    the template a scope uses (null: back to the next scope up)."""
    kind = _kind(payload.get("doc_kind") or "")
    stype, sid = payload.get("scope_type") or "global", payload.get("scope_id")
    sid = int(sid) if sid not in (None, "") else None
    _check_scope(db, stype, sid)
    _assert_design(db, user, stype, sid)
    tid = payload.get("template_id")
    if tid is not None:
        t = _tpl(db, user, int(tid))
        if t.doc_kind != kind:
            raise HTTPException(status_code=422, detail="Ce modèle est d'un autre type de document")
        if S.published(db, t) is None:
            raise HTTPException(status_code=409, detail="Publiez le modèle avant de l'assigner")
        tid = t.id
    S.assign(db, kind, S.scope_key(stype, sid), tid, user)
    record_audit(db, user.id, "export_assignment.set", entity="export_assignment",
                 detail={"doc_kind": kind, "scope": S.scope_key(stype, sid), "template_id": tid})
    db.commit()
    return {"ok": True}


@router.get("/effective", dependencies=_studio)
def effective_spec(doc_kind: str = Query(...), tribe_id: int | None = Query(None),
                   squad_id: int | None = Query(None), platform_id: int | None = Query(None),
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/exports/effective: the layout a document of this scope uses (the
    published specification of its template), the starting point of a one-off
    adjustment from the Export menu. A layout, never data: open to everyone."""
    from ..deps import scoped_tribe_id
    kind = _kind(doc_kind)
    if squad_id is None and platform_id is None:
        tribe_id = scoped_tribe_id(user, tribe_id)
    t, where = S.resolve(db, kind, S.chain_for(db, squad_id=squad_id, tribe_id=tribe_id,
                                               platform_id=platform_id))
    spec = S.effective(db, t)[0]
    db.commit()
    return {"template_id": t.id, "name": t.name, "source": where, "spec": spec}


# --------------------------------------------------------------------------
# Themes
# --------------------------------------------------------------------------
def _theme_out(db: Session, user: User, th: ExportTheme) -> dict:
    stype, sid = ("tribe", th.tribe_id) if th.tribe_id else ("global", None)
    return {"id": th.id, "name": th.name, "config": S.clean_theme_config(th.config),
            "master_asset_id": th.master_asset_id, "tribe_id": th.tribe_id,
            "can_edit": S.can_design(db, user, stype, sid) and (th.tribe_id is not None or user.role == "admin")}


@router.get("/themes", dependencies=_studio)
def list_themes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/exports/themes: the organisation's themes and the caller's tribe's."""
    rows = db.scalars(select(ExportTheme).order_by(ExportTheme.name)).all()
    if user.role != "admin":
        rows = [t for t in rows if t.tribe_id in (None, user.tribe_id)]
    return [_theme_out(db, user, t) for t in rows]


def _theme_scope(db: Session, user: User, tribe_id) -> int | None:
    tribe_id = int(tribe_id) if tribe_id not in (None, "") else None
    if tribe_id is None:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Un thème commun à toute l'organisation est réservé à l'administrateur")
        return None
    _check_scope(db, "tribe", tribe_id)
    _assert_design(db, user, "tribe", tribe_id)
    if S.simple_only(db, user, "tribe", tribe_id):
        raise HTTPException(status_code=403, detail="Les thèmes se gèrent au niveau de la tribe")
    return tribe_id


@router.post("/themes", status_code=201, dependencies=_studio)
def create_theme(payload: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tid = _theme_scope(db, user, payload.get("tribe_id"))
    th = ExportTheme(name=X._clean_text(payload.get("name") or "Theme", 120).strip() or "Theme",
                     config=S.clean_theme_config(payload.get("config")), tribe_id=tid,
                     master_asset_id=_asset_ref(db, user, payload.get("master_asset_id"), "pptx"),
                     created_by_user_id=user.id)
    db.add(th)
    db.flush()
    record_audit(db, user.id, "export_theme.create", entity="export_theme", entity_id=th.id)
    db.commit()
    return _theme_out(db, user, th)


@router.put("/themes/{theme_id}", dependencies=_studio)
def update_theme(theme_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    th = db.get(ExportTheme, theme_id)
    if th is None:
        raise HTTPException(status_code=404, detail="Thème introuvable")
    _theme_scope(db, user, th.tribe_id)
    if "name" in payload:
        th.name = X._clean_text(payload.get("name") or "", 120).strip() or th.name
    if "config" in payload:
        th.config = S.clean_theme_config(payload.get("config"))
    if "master_asset_id" in payload:
        th.master_asset_id = _asset_ref(db, user, payload.get("master_asset_id"), "pptx")
    th.updated_at = S.now()
    record_audit(db, user.id, "export_theme.update", entity="export_theme", entity_id=th.id)
    db.commit()
    return _theme_out(db, user, th)


@router.delete("/themes/{theme_id}", status_code=204, dependencies=_studio)
def delete_theme(theme_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    th = db.get(ExportTheme, theme_id)
    if th is None:
        raise HTTPException(status_code=404, detail="Thème introuvable")
    _theme_scope(db, user, th.tribe_id)
    used = [t.name for t in db.scalars(select(ExportTemplate))
            if (t.draft or {}).get("theme_id") == th.id
            or any((v.spec or {}).get("theme_id") == th.id for v in t.versions)]
    if used:
        raise HTTPException(status_code=409, detail="Thème utilisé par : " + ", ".join(sorted(set(used)))[:300])
    record_audit(db, user.id, "export_theme.delete", entity="export_theme", entity_id=th.id)
    db.delete(th)
    db.commit()


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------
def _asset_visible(user: User, a: ExportAsset) -> bool:
    return user.role == "admin" or a.tribe_id in (None, user.tribe_id)


def _asset_ref(db: Session, user: User, aid, kind: str | None = None) -> int | None:
    if aid in (None, "", 0):
        return None
    a = db.get(ExportAsset, int(aid))
    if a is None or not _asset_visible(user, a) or (kind and a.kind != kind):
        raise HTTPException(status_code=422, detail="Fichier introuvable")
    return a.id


def _asset_out(a: ExportAsset) -> dict:
    return {"id": a.id, "kind": a.kind, "filename": a.filename, "mime": a.mime, "size": a.size,
            "tribe_id": a.tribe_id, "created_at": a.created_at.isoformat() if a.created_at else None}


@router.get("/assets", dependencies=_studio)
def list_assets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/exports/assets: the files the caller's templates may use."""
    rows = db.scalars(select(ExportAsset).order_by(ExportAsset.created_at.desc())).all()
    return [_asset_out(a) for a in rows if _asset_visible(user, a)]


@router.post("/assets", status_code=201, dependencies=_studio)
async def upload_asset(file: UploadFile = File(...), tribe_id: str | None = Form(None),
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """POST /api/exports/assets: a PowerPoint (master or slide to import) or an
    image (PNG, JPEG, GIF), 12 MB at most, checked by content not by name."""
    if not S.is_designer(db, user):
        raise HTTPException(status_code=403, detail="Accès non autorisé pour votre rôle")
    tid = int(tribe_id) if tribe_id not in (None, "", "null") else None
    if tid is None and user.role != "admin":
        tid = user.tribe_id
    if tid is not None and user.role != "admin" and tid != user.tribe_id:
        raise HTTPException(status_code=403, detail="Accès non autorisé pour votre rôle")
    data = await file.read(S.MAX_ASSET + 1)
    try:
        a = S.store_asset(db, file.filename or "fichier", data, file.content_type or "", tid, user)
    except ValueError as exc:
        msg = {"too_large": "Fichier trop volumineux (12 Mo au plus)",
               "macros": "Les présentations avec macros sont refusées",
               "bad_archive": "Archive refusée (trop d'entrées ou trop compressée)"}.get(
            str(exc), "Format refusé : PowerPoint .pptx, PNG, JPEG ou GIF")
        raise HTTPException(status_code=422, detail=msg)
    record_audit(db, user.id, "export_asset.upload", entity="export_asset", entity_id=a.id,
                 detail={"filename": a.filename, "kind": a.kind, "size": a.size})
    db.commit()
    return _asset_out(a)


@router.get("/assets/{asset_id}/raw", dependencies=_studio)
def asset_raw(asset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.get(ExportAsset, asset_id)
    if a is None or not _asset_visible(user, a):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return Response(content=a.data, media_type=a.mime,
                    headers={"Content-Disposition": f'inline; filename="{re.sub(r"[^A-Za-z0-9._-]+", "_", a.filename)}"',
                             "X-Content-Type-Options": "nosniff"})


@router.get("/assets/{asset_id}/slides", dependencies=_studio)
def asset_slides(asset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/exports/assets/{id}/slides: the slides of a PowerPoint file, with
    their first words, to pick the one a template imports."""
    import io
    a = db.get(ExportAsset, asset_id)
    if a is None or not _asset_visible(user, a) or a.kind != "pptx":
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    from pptx import Presentation
    prs = Presentation(io.BytesIO(a.data))
    out = []
    for i, sl in enumerate(prs.slides, start=1):
        words = " ".join(sh.text_frame.text for sh in sl.shapes if sh.has_text_frame).split()
        out.append({"index": i, "text": " ".join(words)[:120]})
    return {"slides": out, "layouts": len(prs.slide_layouts)}


@router.delete("/assets/{asset_id}", status_code=204, dependencies=_studio)
def delete_asset(asset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = db.get(ExportAsset, asset_id)
    if a is None or not _asset_visible(user, a):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    stype, sid = ("tribe", a.tribe_id) if a.tribe_id else ("global", None)
    _assert_design(db, user, stype, sid)
    if db.scalar(select(ExportTheme).where(ExportTheme.master_asset_id == a.id)) is not None:
        raise HTTPException(status_code=409, detail="Ce fichier est le masque d'un thème")
    record_audit(db, user.id, "export_asset.delete", entity="export_asset", entity_id=a.id,
                 detail={"filename": a.filename})
    db.delete(a)
    db.commit()


# --------------------------------------------------------------------------
# Data of a document, behind the gates of its export endpoint
# --------------------------------------------------------------------------
def _gate(db: Session, user: User, module: str, feature: str | None, capability: str | None) -> None:
    from ..modulesconfig import get_modules, is_active
    from ..personasconfig import can
    if not is_active(get_modules(db), module, feature):
        raise HTTPException(status_code=404, detail="Service désactivé")
    if capability and not can(db, user, capability):
        raise HTTPException(status_code=403, detail="Accès non autorisé pour votre rôle")


def document_context(request: Request, db: Session, user: User, doc_kind: str, q: dict) -> dict:
    """The providers, scope chain and labels of a document, built exactly as its
    export endpoint builds them (same gates, same scope, same budget filtering)."""
    from ..generalconfig import get_general, reference_year
    q = q or {}

    def ival(k):
        v = q.get(k)
        try:
            return int(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"Paramètre invalide : {k}")
    tribe_id, squad_id, platform_id, year = ival("tribe_id"), ival("squad_id"), ival("platform_id"), ival("year")
    squad_ids = [int(x) for x in (q.get("squad_ids") or []) if str(x).isdigit()] or None
    lang = q.get("lang") or None
    as_of = q.get("as_of") or None
    kind = _kind(doc_kind)
    if kind in ("dashboard", "weekly", "roadmap"):
        from .reports import _data
        gate = {"dashboard": ("dashboard", None, "dashboard"), "weekly": ("review", "weekly_report", "dashboard"),
                "roadmap": ("squad_content", "roadmap", "roadmap")}[kind]
        _gate(db, user, *gate)
        data = _data(request, db, user, tribe_id, year, int(q.get("since_days") or 7), squad_id, lang,
                     squad_ids, as_of)
        if kind == "dashboard":
            data["doc"] = "dashboard"
        return {"providers": {"report": lambda: data}, "chain": S.report_chain(db, data),
                "lang": data.get("lang", "fr"), "scope_name": data.get("scope_name", ""),
                "year": data.get("year"), "period": ""}
    if kind == "dependencies":
        from .reports import _dep_data
        _gate(db, user, "squad_content", "roadmap", "roadmap")
        mode = q.get("mode") if q.get("mode") in ("all", "cross_tribe") else "all"
        data = _dep_data(request, db, user, tribe_id, year, squad_ids, lang, mode)
        from ..deps import scoped_tribe_id
        return {"providers": {"dependencies": lambda: data},
                "chain": S.chain_for(db, tribe_id=scoped_tribe_id(user, tribe_id)),
                "lang": data.get("lang", "fr"), "scope_name": data.get("scope_name", ""),
                "year": data.get("year"), "period": ""}
    if kind == "initiatives":
        from ..deps import visible_tribe_id
        from ..report import build_initiative_list
        year = year or reference_year(db)
        scope = tribe_id if user.role == "admin" else visible_tribe_id(user)
        lang = lang or get_general(db).get("default_lang") or "fr"
        data = build_initiative_list(db, scope, year, lang)
        return {"providers": {"initiatives": lambda: data}, "chain": S.chain_for(db, tribe_id=scope),
                "lang": lang, "scope_name": data.get("scope_name", ""), "year": year, "period": ""}
    if kind == "steerco":
        from .steerco import I18N, _aggregate, _enabled_platforms, _lang
        _gate(db, user, "steerco", None, None)
        period = str(q.get("period") or "")
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
            from datetime import date
            d = date.today()
            period = f"{d.year}-{d.month:02d}"
        L = I18N[_lang(lang)]
        plats = [p for p in _enabled_platforms(db, user) if platform_id is None or p.id == platform_id]
        rows = [{"squad_name": p.name, "platform_id": p.id, "data": _aggregate(db, p.id, period)}
                for p in plats]
        from ..deps import visible_tribe_id
        return {"providers": {"steerco": lambda: (rows, period, L)},
                "chain": S.chain_for(db, platform_id=platform_id, tribe_id=visible_tribe_id(user)),
                "lang": _lang(lang), "scope_name": plats[0].name if platform_id and plats else "Steerco",
                "year": int(period[:4]), "period": period}
    # org
    from .org import _resolve_tribe
    from .orgexport import _prune, _tree_dicts
    _gate(db, user, "org", None, "org")
    tid = _resolve_tribe(user, tribe_id, db)
    roots, name = _tree_dicts(db, tid) if tid is not None else ([], "-")
    node_ids = {int(x) for x in (q.get("node_ids") or []) if str(x).isdigit()}
    roots = _prune(roots, node_ids)
    return {"providers": {"org": lambda: (roots, name)}, "chain": S.chain_for(db, tribe_id=tid),
            "lang": lang or "fr", "scope_name": name, "year": None, "period": ""}


def _asset_reader_for(db: Session, user: User):
    def read(aid):
        a = db.get(ExportAsset, int(aid)) if aid else None
        return a.data if a is not None and _asset_visible(user, a) else None
    return read


def _build(request: Request, db: Session, user: User, payload: dict):
    """The presentation and context of a preview or a one-off render."""
    from .. import exportengine as E
    from ..generalconfig import get_general
    kind = _kind(payload.get("doc_kind") or "")
    dc = document_context(request, db, user, kind, payload.get("context") or {})
    if payload.get("spec") is not None:
        spec, tpl = X.normalize(payload.get("spec"), kind), None
        if payload.get("template_id"):
            tpl = _tpl(db, user, int(payload["template_id"]))
    else:
        try:
            spec, tpl, _w = S.pick_spec(db, user, kind, dc["chain"],
                                        template_id=int(payload["template_id"]) if payload.get("template_id") else None,
                                        draft=bool(payload.get("draft")))
        except LookupError:
            raise HTTPException(status_code=404, detail="Modèle introuvable")
    theme, master = S.theme_for(db, spec.get("theme_id"))
    ctx = E.Context(doc_kind=kind, lang=dc["lang"], scope_name=dc["scope_name"], year=dc["year"],
                    period=dc["period"], app_name=get_general(db).get("app_name") or "TeamFollowUP",
                    providers=dc["providers"], theme=theme, master=master,
                    asset=_asset_reader_for(db, user),
                    variant=S.variant_fn(db, kind, tpl) if tpl is not None else (lambda k, e: None))
    return spec, ctx


@router.post("/preview", dependencies=_studio)
def preview(request: Request, payload: dict = Body(...), db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """POST /api/exports/preview {doc_kind, context, spec | template_id [+draft]}: the document as HTML slides, drawn from the very deck the export
    would save, with the readability checks and what the render had to say."""
    from .. import exportengine as E
    from .. import pptxhtml
    spec, ctx = _build(request, db, user, payload)
    try:
        prs = E.build_presentation(spec, ctx)
    finally:
        from .. import pptxtpl
        pptxtpl.use_theme(None)
    html, lints, n = pptxhtml.render(prs, standalone=False)
    db.commit()
    return {"html": html, "css": pptxhtml.CSS, "slides": n, "lints": lints, "warnings": ctx.warnings,
            "filename": E.filename(spec, ctx), "width": round(prs.slide_width / 9525.0, 2),
            "height": round(prs.slide_height / 9525.0, 2)}


@router.post("/render", dependencies=_studio)
def render_document(request: Request, payload: dict = Body(...), fmt: str = Query("pptx"),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """POST /api/exports/render?fmt=pptx|html: the document itself, laid out by the
    given specification or template."""
    from .. import exportengine as E
    from .. import pptxhtml
    spec, ctx = _build(request, db, user, payload)
    if fmt == "html":
        try:
            prs = E.build_presentation(spec, ctx)
        finally:
            from .. import pptxtpl
            pptxtpl.use_theme(None)
        doc, _l, _n = pptxhtml.render(prs, title=E.filename(spec, ctx)[:-5])
        return HTMLResponse(doc)
    blob = E.render(spec, ctx)
    return Response(content=blob, media_type=PPTX_MIME,
                    headers={"Content-Disposition": f'attachment; filename="{E.filename(spec, ctx)}"'})


@router.get("/document.html", response_class=HTMLResponse)
def document_html(request: Request, doc_kind: str = Query(...), template_id: int | None = Query(None),
                  tribe_id: int | None = Query(None),
                  squad_id: int | None = Query(None), squad_ids: list[int] | None = Query(None),
                  platform_id: int | None = Query(None), year: int | None = Query(None),
                  lang: str | None = Query(None), as_of: str | None = Query(None),
                  period: str | None = Query(None), mode: str | None = Query(None),
                  node_ids: list[int] | None = Query(None),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """GET /api/exports/document.html: the document's slides as a web page (the
    same deck as the PowerPoint, drawn in the browser), through its template."""
    from .. import exportengine as E
    from .. import pptxhtml
    payload = {"doc_kind": doc_kind, "template_id": template_id,
               "context": {"tribe_id": tribe_id, "squad_id": squad_id, "squad_ids": squad_ids,
                           "platform_id": platform_id, "year": year, "lang": lang, "as_of": as_of,
                           "period": period, "mode": mode, "node_ids": node_ids}}
    spec, ctx = _build(request, db, user, payload)
    try:
        prs = E.build_presentation(spec, ctx)
    finally:
        from .. import pptxtpl
        pptxtpl.use_theme(None)
    doc, _l, _n = pptxhtml.render(prs, title=E.filename(spec, ctx)[:-5])
    db.commit()
    return HTMLResponse(doc)
