"""Org-chart export endpoints: HTML + single-slide PPTX, with optional selection of
which top-level branches to include. Same module/capability gate as the org view."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_capability, require_module
from ..models import OrgNode, Tribe, User
from ..orgrender import render_org_html, render_org_pptx
from ..serializers import build_org_tree
from .org import _resolve_tribe, _squad_status_map

router = APIRouter(prefix="/api/org", tags=["org-export"],
                   dependencies=[Depends(require_module("org")),
                                 Depends(require_capability("org"))])


def _tree_dicts(db: Session, tid: int) -> tuple[list[dict], str]:
    nodes = list(db.scalars(select(OrgNode).where(OrgNode.tribe_id == tid)).all())
    roots = [r.model_dump() for r in build_org_tree(nodes, _squad_status_map(db))]
    tribe = db.get(Tribe, tid)
    return roots, (tribe.name if tribe else "-")


def _prune(roots: list[dict], keep: set[int]) -> list[dict]:
    """Keep only the selected top-level branches (children of each root)."""
    if not keep:
        return roots
    out = []
    for r in roots:
        kids = [k for k in (r.get("children") or []) if k["id"] in keep]
        if kids or r["id"] in keep:
            out.append({**r, "children": kids})
    return out


@router.get("/export/branches")
def export_branches(tribe_id: int | None = Query(default=None),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Selectable top-level branches (the root's direct children) for the picker."""
    tid = _resolve_tribe(user, tribe_id, db)
    if tid is None:
        return []
    roots, _ = _tree_dicts(db, tid)
    out = []
    for r in roots:
        for k in (r.get("children") or []):
            out.append({"id": k["id"], "title": k["title"],
                        "count": len(k.get("children") or [])})
    return out


@router.get("/export.html", response_class=HTMLResponse)
def export_html(tribe_id: int | None = Query(default=None),
                node_ids: list[int] | None = Query(default=None),
                lang: str | None = Query(default=None),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tid = _resolve_tribe(user, tribe_id, db)
    roots, name = _tree_dicts(db, tid) if tid is not None else ([], "-")
    roots = _prune(roots, set(node_ids or []))
    return HTMLResponse(render_org_html(roots, name, lang=lang or "fr", standalone=True))


@router.get("/export.pptx")
def export_pptx(tribe_id: int | None = Query(default=None),
                node_ids: list[int] | None = Query(default=None),
                lang: str | None = Query(default=None),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tid = _resolve_tribe(user, tribe_id, db)
    roots, name = _tree_dicts(db, tid) if tid is not None else ([], "-")
    roots = _prune(roots, set(node_ids or []))
    payload = render_org_pptx(roots, name, lang=lang or "fr")
    # Buffered artifact → plain Response so Content-Length is set (not chunked).
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="organigramme_{name}.pptx"'},
    )
