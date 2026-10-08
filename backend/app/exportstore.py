"""Studio des exports: templates in the database, who may change them, which one a
document uses, and the render of a document through its template.

The rules, in one place:

* **Standard templates** (``system``) are created on first use, one per kind of
  document, published, read-only. Rendering one gives the deck the product always
  made: an instance where nobody touches the Studio exports exactly as before.
* **Resolution**: a document uses the template assigned to the closest scope:
  the squad, then its tribe, then the organisation, then Standard. A platform's
  steerco slide looks at the platform first, then its tribe.
* **Inheritance**: a derived template follows its parent's *published* version
  plus its own differences; a parent's published locks bind all its descendants.
* **Rights**: the administrator designs everywhere; a tribe leader designs for
  their tribe, its squads and its platforms; a squad leader designs the template
  of a squad they lead, in simple mode only (no free layout, no new section).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import exportspec as X
from .models import (ExportAsset, ExportAssignment, ExportTemplate, ExportTemplateVersion,
                     ExportTheme, Platform, Squad, User)

SCOPE_TYPES = ("global", "tribe", "squad", "platform")
MAX_DEPTH = 8

STANDARD_NAMES = {
    "fr": "Standard", "en": "Standard",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def scope_key(scope_type: str, scope_id: int | None) -> str:
    return "global" if scope_type == "global" else f"{scope_type}:{int(scope_id)}"


# --------------------------------------------------------------------------
# Standard templates
# --------------------------------------------------------------------------
def ensure_system(db: Session) -> dict[str, ExportTemplate]:
    """The Standard template of every kind of document, created when missing."""
    have = {t.doc_kind: t for t in db.scalars(select(ExportTemplate).where(ExportTemplate.system.is_(True)))}
    for kind in X.DOC_KINDS:
        if kind in have:
            continue
        spec = X.system_spec(kind)
        t = ExportTemplate(doc_kind=kind, name="Standard", scope_type="global", scope_id=None,
                           mode="root", system=True, shared=True, draft=spec, draft_locks=[])
        db.add(t)
        db.flush()
        v = ExportTemplateVersion(template_id=t.id, number=1, spec=spec, locks=[], comment="Standard")
        db.add(v)
        db.flush()
        t.published_version_id = v.id
        have[kind] = t
    return have


def published(db: Session, tpl: ExportTemplate) -> ExportTemplateVersion | None:
    if tpl.published_version_id is None:
        return None
    return db.get(ExportTemplateVersion, tpl.published_version_id)


# --------------------------------------------------------------------------
# Effective specification
# --------------------------------------------------------------------------
def _stored(db: Session, tpl: ExportTemplate, draft: bool) -> tuple[dict, list]:
    """The stored form (full spec, or patch for a derived template) and its locks."""
    if draft:
        return tpl.draft or {}, list(tpl.draft_locks or [])
    v = published(db, tpl)
    if v is None:
        return tpl.draft or {}, list(tpl.draft_locks or [])
    return v.spec or {}, list(v.locks or [])


def inherited_locks(db: Session, tpl: ExportTemplate, _depth: int = 0) -> list[str]:
    """The locks every ancestor's published version imposes on ``tpl``."""
    out: set[str] = set()
    cur, seen = tpl, {tpl.id}
    while cur.mode == "derived" and cur.parent_id and _depth < MAX_DEPTH:
        parent = db.get(ExportTemplate, cur.parent_id)
        if parent is None or parent.id in seen:
            break
        seen.add(parent.id)
        out.update(_stored(db, parent, False)[1])
        cur, _depth = parent, _depth + 1
    return sorted(out)


def effective(db: Session, tpl: ExportTemplate, *, draft: bool = False, _depth: int = 0,
              _seen: frozenset = frozenset()) -> tuple[dict, list[dict]]:
    """The full specification ``tpl`` stands for, and what of its patch was not
    applied (locked or orphaned). A parent is always read at its published version."""
    stored, _locks = _stored(db, tpl, draft)
    if tpl.mode == "derived" and tpl.parent_id and _depth < MAX_DEPTH and tpl.parent_id not in _seen:
        parent = db.get(ExportTemplate, tpl.parent_id)
        if parent is not None:
            base, _sk = effective(db, parent, draft=False, _depth=_depth + 1, _seen=_seen | {tpl.id})
            return X.apply(base, stored, inherited_locks(db, tpl), tpl.doc_kind)
    return X.normalize(stored, tpl.doc_kind), []


def parent_effective(db: Session, tpl: ExportTemplate) -> dict | None:
    if tpl.mode != "derived" or not tpl.parent_id:
        return None
    parent = db.get(ExportTemplate, tpl.parent_id)
    return effective(db, parent)[0] if parent is not None else None


def save_draft(db: Session, tpl: ExportTemplate, spec: dict, locks, user: User | None) -> dict:
    """Store the editor's full specification as the draft: its difference with the
    parent for a derived template, the specification itself otherwise."""
    eff = X.normalize(spec, tpl.doc_kind)
    if tpl.mode == "derived":
        base = parent_effective(db, tpl)
        tpl.draft = X.diff(base, eff) if base is not None else eff
    else:
        tpl.draft = eff
    tpl.draft_locks = X.clean_locks(locks, eff)
    tpl.updated_at = now()
    tpl.updated_by_user_id = user.id if user else None
    return eff


def publish(db: Session, tpl: ExportTemplate, user: User | None, comment: str = "") -> ExportTemplateVersion:
    last = max((v.number for v in tpl.versions), default=0)
    v = ExportTemplateVersion(template_id=tpl.id, number=last + 1, spec=tpl.draft or {},
                              locks=list(tpl.draft_locks or []), comment=X._clean_text(comment, 300),
                              created_by_user_id=user.id if user else None)
    db.add(v)
    db.flush()
    tpl.published_version_id = v.id
    tpl.updated_at = now()
    return v


def has_unpublished(db: Session, tpl: ExportTemplate) -> bool:
    v = published(db, tpl)
    return v is None or (v.spec or {}) != (tpl.draft or {}) or list(v.locks or []) != list(tpl.draft_locks or [])


def descendants(db: Session, tpl: ExportTemplate) -> list[ExportTemplate]:
    out, todo = [], [tpl.id]
    while todo:
        kids = db.scalars(select(ExportTemplate).where(ExportTemplate.parent_id.in_(todo))).all()
        todo = [k.id for k in kids if k.id not in {o.id for o in out}]
        out.extend(kids)
        if len(out) > 500:
            break
    return out


# --------------------------------------------------------------------------
# Rights
# --------------------------------------------------------------------------
def scope_tribe(db: Session, scope_type: str, scope_id: int | None) -> int | None:
    """The tribe a scope belongs to (None for the organisation)."""
    if scope_type == "tribe":
        return scope_id
    if scope_type == "squad":
        sq = db.get(Squad, scope_id) if scope_id else None
        return sq.tribe_id if sq else None
    if scope_type == "platform":
        p = db.get(Platform, scope_id) if scope_id else None
        return p.tribe_id if p else None
    return None


def _studio_open(db: Session, user: User) -> bool:
    """The persona opens the Studio (capability "exports", Admin > Personas)."""
    from .personasconfig import can
    return user.role == "admin" or can(db, user, "exports")


def can_design(db: Session, user: User, scope_type: str, scope_id: int | None) -> bool:
    """May ``user`` create, edit or assign templates at this scope: the persona opens
    the Studio, and the role covers the scope."""
    if not _studio_open(db, user):
        return False
    if user.role == "admin":
        return True
    if scope_type == "global":
        return False
    if user.role == "tribe_leader" and user.tribe_id is not None:
        if scope_tribe(db, scope_type, scope_id) == user.tribe_id:
            return True
    if scope_type == "squad" and scope_id:
        from .deps import leads_squad
        return leads_squad(db, user, scope_id)
    return False


def simple_only(db: Session, user: User, scope_type: str, scope_id: int | None) -> bool:
    """A squad leader designs in simple mode: switches and settings, nothing added."""
    if user.role == "admin":
        return False
    if user.role == "tribe_leader" and scope_tribe(db, scope_type, scope_id) == user.tribe_id:
        return False
    return True


def is_designer(db: Session, user: User) -> bool:
    """Does the Studio have anything for this person at all."""
    if not _studio_open(db, user):
        return False
    if user.role in ("admin", "tribe_leader"):
        return True
    from .deps import led_squad_ids
    return bool(db.scalars(led_squad_ids(db, user)).first())


def can_read(db: Session, user: User, tpl: ExportTemplate) -> bool:
    """A template is read to derive from it (library) or to export with it."""
    if tpl.system or tpl.shared:
        return True
    return can_design(db, user, tpl.scope_type, tpl.scope_id)


def check_simple(spec_before: dict | None, spec_after: dict) -> bool:
    """True when ``spec_after`` only switches and tunes what ``spec_before`` has:
    the same sections (some may be off or reordered), no free layout changed."""
    if spec_before is None:
        return False
    before = {s["id"]: s for s in spec_before["sections"]}
    for s in spec_after["sections"]:
        b = before.get(s["id"])
        if b is None or b["type"] != s["type"]:
            return False
        if s["type"] in ("custom", "imported", "cover", "text") and \
                (s.get("items") != b.get("items") or s["params"] != b["params"]):
            return False
    return len(spec_after["sections"]) == len(spec_before["sections"])


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------
def chain_for(db: Session, *, squad_id: int | None = None, tribe_id: int | None = None,
              platform_id: int | None = None) -> list[str]:
    """The scopes a document looks at, the closest first."""
    keys = []
    if platform_id:
        keys.append(scope_key("platform", platform_id))
        p = db.get(Platform, platform_id)
        if p is not None and tribe_id is None:
            tribe_id = p.tribe_id
    if squad_id:
        keys.append(scope_key("squad", squad_id))
        sq = db.get(Squad, squad_id)
        if sq is not None and tribe_id is None:
            tribe_id = sq.tribe_id
    if tribe_id:
        keys.append(scope_key("tribe", tribe_id))
    keys.append("global")
    return keys


def resolve(db: Session, doc_kind: str, chain: list[str]) -> tuple[ExportTemplate, str]:
    """The template a document uses, and the scope it was assigned at
    (``standard`` when nobody assigned one)."""
    rows = {a.scope_key: a for a in db.scalars(select(ExportAssignment).where(
        ExportAssignment.doc_kind == doc_kind, ExportAssignment.scope_key.in_(chain)))}
    for key in chain:
        a = rows.get(key)
        if a is not None:
            t = db.get(ExportTemplate, a.template_id)
            if t is not None and t.doc_kind == doc_kind:
                return t, key
    return ensure_system(db)[doc_kind], "standard"


def assign(db: Session, doc_kind: str, key: str, template_id: int | None, user: User | None) -> None:
    row = db.scalar(select(ExportAssignment).where(ExportAssignment.doc_kind == doc_kind,
                                                   ExportAssignment.scope_key == key))
    if template_id is None:
        if row is not None:
            db.delete(row)
        return
    if row is None:
        row = ExportAssignment(doc_kind=doc_kind, scope_key=key, template_id=template_id)
        db.add(row)
    row.template_id = template_id
    row.updated_by_user_id = user.id if user else None
    row.updated_at = now()


# --------------------------------------------------------------------------
# Theme, master, files
# --------------------------------------------------------------------------
THEME_LIMITS = {"font_scale": (0.8, 1.5)}
FONTS = ("", "Calibri", "Arial", "Segoe UI", "Helvetica", "Verdana", "Tahoma", "Trebuchet MS",
         "Georgia", "Aptos", "Roboto", "Open Sans", "Lato", "Source Sans Pro")


def clean_theme_config(raw) -> dict:
    """A theme's settings, validated by shape: colours are #rrggbb, the font comes
    from a closed list, the scale is bounded."""
    import re
    raw = raw if isinstance(raw, dict) else {}
    pal = {}
    for k, v in (raw.get("palette") or {}).items():
        if k in X.catalogue()["theme_keys"] and isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            pal[k] = v.upper()
    font = raw.get("font") if raw.get("font") in FONTS else ""
    try:
        scale = float(raw.get("font_scale") or 1.15)
    except (TypeError, ValueError):
        scale = 1.15
    lo, hi = THEME_LIMITS["font_scale"]
    return {"palette": pal, "font": font, "font_scale": round(max(lo, min(hi, scale)), 2)}


def theme_for(db: Session, theme_id: int | None) -> tuple[dict, bytes | None]:
    """The render theme and the master bytes of a template's theme. No theme: the
    rendering the product always made, on the PowerPoint template of
    Administration > Import when there is one."""
    from . import pptxtpl
    if not theme_id:
        return {}, pptxtpl.get(db)
    th = db.get(ExportTheme, theme_id)
    if th is None:
        return {}, pptxtpl.get(db)
    cfg = clean_theme_config(th.config)
    theme = {"palette": cfg["palette"], "font": cfg["font"] or None, "font_scale": cfg["font_scale"]}
    master = None
    if th.master_asset_id:
        a = db.get(ExportAsset, th.master_asset_id)
        master = a.data if a is not None and a.kind == "pptx" else None
    return theme, master if master is not None else pptxtpl.get(db)


def asset_reader(db: Session):
    def read(asset_id: int) -> bytes | None:
        a = db.get(ExportAsset, int(asset_id)) if asset_id else None
        return a.data if a is not None else None
    return read


MAX_ASSET = 12 * 1024 * 1024
IMAGE_MIMES = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif"}


def store_asset(db: Session, filename: str, data: bytes, mime: str, tribe_id: int | None,
                user: User | None) -> ExportAsset:
    """Validate then store a file. Images: PNG, JPEG, GIF, recognised by their
    bytes. PowerPoint: a real ``.pptx`` (no macros), checked as an archive first so
    a compression bomb is refused before python-pptx opens it."""
    if len(data) > MAX_ASSET:
        raise ValueError("too_large")
    kind = None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        kind, mime = "image", "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        kind, mime = "image", "image/jpeg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        kind, mime = "image", "image/gif"
    elif data[:4] == b"PK\x03\x04":
        _check_pptx(data)
        kind, mime = "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if kind is None:
        raise ValueError("bad_type")
    a = ExportAsset(kind=kind, filename=X._clean_text(filename or "fichier", 255) or "fichier", mime=mime,
                    size=len(data), sha256=hashlib.sha256(data).hexdigest(), data=data, tribe_id=tribe_id,
                    created_by_user_id=user.id if user else None)
    db.add(a)
    db.flush()
    return a


def _check_pptx(data: bytes) -> None:
    import io
    import zipfile
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("bad_type")
    infos = z.infolist()
    if len(infos) > 3000:
        raise ValueError("bad_archive")
    total = sum(i.file_size for i in infos)
    if total > 200 * 1024 * 1024 or total > 60 * max(1, len(data)):
        raise ValueError("bad_archive")
    names = {i.filename for i in infos}
    if "ppt/presentation.xml" not in names:
        raise ValueError("bad_type")
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise ValueError("macros")
    from pptx import Presentation
    try:
        Presentation(io.BytesIO(data))
    except Exception:
        raise ValueError("bad_type")


# --------------------------------------------------------------------------
# Rendering a document through its template
# --------------------------------------------------------------------------
def variant_fn(db: Session, doc_kind: str, base: ExportTemplate):
    """For a consolidated document: the squad's (or platform's) own slide, when that
    squad has a template of its own assigned."""
    cache: dict = {}

    def variant(kind: str, entity: dict):
        if kind == "squad":
            sid = entity.get("squad_id")
            key = scope_key("squad", sid) if sid else None
            stype = "squad"
        else:
            pid = entity.get("platform_id")
            key = scope_key("platform", pid) if pid else None
            stype = "platform"
        if key is None:
            return None
        if key not in cache:
            row = db.scalar(select(ExportAssignment).where(ExportAssignment.doc_kind == doc_kind,
                                                           ExportAssignment.scope_key == key))
            sec = None
            if row is not None and row.template_id != base.id:
                t = db.get(ExportTemplate, row.template_id)
                if t is not None:
                    spec = effective(db, t)[0]
                    sec = next((s for s in spec["sections"] if s["type"] == stype and s["enabled"]), None)
            cache[key] = sec
        return cache[key]
    return variant


def pick_spec(db: Session, user: User | None, doc_kind: str, chain: list[str], *,
              template_id: int | None = None,
              draft: bool = False) -> tuple[dict, ExportTemplate | None, str]:
    """The specification an export uses: an explicitly chosen template, or the one
    assigned to the closest scope."""
    if template_id is not None:
        t = db.get(ExportTemplate, template_id)
        if t is None or t.doc_kind != doc_kind or (user is not None and not can_read(db, user, t)):
            raise LookupError("template")
        if draft and (user is None or not can_design(db, user, t.scope_type, t.scope_id)):
            draft = False
        return effective(db, t, draft=draft)[0], t, "chosen"
    t, where = resolve(db, doc_kind, chain)
    return effective(db, t)[0], t, where


def render(db: Session, user: User | None, doc_kind: str, providers: dict, *, chain: list[str],
           lang: str = "fr", scope_name: str = "", year: int | None = None, period: str = "",
           template_id: int | None = None, draft: bool = False,
           legacy_name: str | None = None) -> tuple[bytes, str, dict]:
    """Render a document for an export endpoint. Returns the bytes, the file name and
    what the render had to say (warnings)."""
    from . import exportengine as E
    from .generalconfig import get_general
    spec, tpl, where = pick_spec(db, user, doc_kind, chain, template_id=template_id, draft=draft)
    theme, master = theme_for(db, spec.get("theme_id"))
    ctx = E.Context(doc_kind=doc_kind, lang=lang, scope_name=scope_name, year=year, period=period,
                    app_name=(get_general(db).get("app_name") or "TeamFollowUP"),
                    providers=providers, theme=theme, master=master, asset=asset_reader(db),
                    variant=variant_fn(db, doc_kind, tpl) if tpl is not None else (lambda k, e: None))
    blob = E.render(spec, ctx)
    name = legacy_name if (tpl is not None and tpl.system and legacy_name) else E.filename(spec, ctx)
    return blob, name, {"warnings": ctx.warnings, "template_id": tpl.id if tpl else None, "source": where}


def report_chain(db: Session, data: dict) -> list[str]:
    """The scopes of a report data set: its squad when it is about one, its tribe
    when it covers one, the organisation otherwise."""
    rows = [(blk.get("tribe_id"), r.get("squad_id")) for blk in data.get("tribes") or []
            for r in blk.get("squads") or []]
    tribes = {t for t, _s in rows if t}
    if data.get("squad_scoped") and rows:
        return chain_for(db, squad_id=rows[0][1], tribe_id=rows[0][0])
    if len(tribes) == 1:
        return chain_for(db, tribe_id=next(iter(tribes)))
    return chain_for(db)


def render_report(db: Session, data: dict, doc_kind: str | None = None, user: User | None = None,
                  **kw) -> bytes:
    """The PowerPoint of a report data set through its scope's template: what the
    scheduled mails and the change notifications attach."""
    kind = doc_kind or ("dashboard" if data.get("doc") == "dashboard" else "weekly")
    blob, _name, _meta = render(db, user, kind, {"report": lambda: data}, chain=report_chain(db, data),
                                lang=data.get("lang", "fr"), scope_name=data.get("scope_name", ""),
                                year=data.get("year"), **kw)
    return blob
