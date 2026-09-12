"""Admin > Data: erase what you choose, and take or restore a point-in-time copy.

Three operations, all admin-only and all audited, because each of them can lose
somebody's year of work:

* **counts** answers "what is in there" before anything is decided;
* **reset** erases the selected domains and what they drag along;
* **snapshots** take a copy, put one back, download one, upload one back.

Every destructive call requires ``confirm: true`` in the body. It is not a
substitute for the confirmation dialog: it is what stops a stray POST, a replayed
curl or a mis-clicked link from emptying a database, since these endpoints are
reachable with nothing but an admin cookie.

A reset and a restore both keep the break-glass admin alive (``ensure_breakglass``
runs after each): the one login guaranteed to work once the data that carried the
other accounts has gone.
"""
import gzip
import json

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import datareset, datasnapshots
from ..bootstrap import ensure_breakglass
from ..database import get_db
from ..deps import record_audit, require_admin
from ..models import DataSnapshot, User

router = APIRouter(prefix="/api/admin/data", tags=["admin-data"])


def _require_confirm(payload: dict | None) -> None:
    if not (payload or {}).get("confirm"):
        raise HTTPException(status_code=400,
                            detail="Confirmation manquante : cette operation efface des donnees")


def _snapshot_out(s: DataSnapshot) -> dict:
    return {
        "id": s.id, "name": s.name, "kind": s.kind,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "created_by": s.created_by.display_name if s.created_by else None,
        "size_bytes": s.size_bytes,
        "rows": sum((s.row_counts or {}).values()),
        "row_counts": s.row_counts or {},
    }


# --------------------------------------------------------------------------
# What is in there, and erasing part of it
# --------------------------------------------------------------------------

@router.get("/domains")
def list_domains(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/data/domains: row counts per erasable domain. Admin only.

    Read before every reset: the confirmation shows real numbers rather than a
    promise, and a domain with nothing in it is still listed because "0" answers
    the question too."""
    return {"domains": datareset.counts(db), "never_erased": sorted(datareset.NEVER_ERASED)}


@router.post("/reset")
def reset(payload: dict = Body(...), db: Session = Depends(get_db),
          admin: User = Depends(require_admin)):
    """POST /api/admin/data/reset: erase the selected domains. Admin only. Audited.

    Body: ``{"domains": [...], "confirm": true, "snapshot_first": true}``. The
    snapshot is taken in the SAME transaction as the deletion, so a reset either
    leaves a copy behind or does not happen at all."""
    _require_confirm(payload)
    keys = [k for k in (payload.get("domains") or []) if k in datareset.DOMAINS]
    if not keys:
        raise HTTPException(status_code=400, detail="Choisissez au moins un domaine a effacer")
    snapshot_id = None
    if payload.get("snapshot_first", True):
        snap = datasnapshots.create(db, payload.get("snapshot_name") or "Avant remise a zero",
                                    kind="manual", user_id=admin.id)
        snapshot_id = snap.id
    erased = datareset.erase(db, keys)
    ensure_breakglass(db)
    record_audit(db, admin.id, "data.reset", entity="data",
                 detail={"domains": datareset.expand(keys), "erased": erased,
                         "snapshot_id": snapshot_id})
    db.commit()
    return {"erased": erased, "domains": datareset.expand(keys), "snapshot_id": snapshot_id}


# --------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------

@router.get("/snapshots")
def list_snapshots(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/data/snapshots: the copies on file, newest first. Admin only."""
    rows = db.scalars(select(DataSnapshot).order_by(DataSnapshot.created_at.desc())).all()
    return [_snapshot_out(s) for s in rows]


@router.post("/snapshots", status_code=201)
def create_snapshot(payload: dict = Body(default=None), db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """POST /api/admin/data/snapshots: take a copy now. Admin only. Audited."""
    snap = datasnapshots.create(db, (payload or {}).get("name") or "", kind="manual",
                                user_id=admin.id)
    record_audit(db, admin.id, "data.snapshot", entity="snapshot", entity_id=snap.id,
                 detail={"name": snap.name, "size": snap.size_bytes})
    db.commit()
    return _snapshot_out(snap)


@router.post("/snapshots/{snapshot_id}/restore")
def restore_snapshot(snapshot_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                     admin: User = Depends(require_admin)):
    """POST /api/admin/data/snapshots/{id}/restore: rewind to that copy. Audited.

    Everything the snapshot covers is emptied and rewritten, ids included. A
    safety copy of the CURRENT state is taken first unless the caller says not to,
    so a restore aimed at the wrong line is itself undoable."""
    _require_confirm(payload)
    snap = db.get(DataSnapshot, snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Sauvegarde introuvable")
    safety = None
    if payload.get("snapshot_first", True):
        safety = datasnapshots.create(db, f"Avant restauration de {snap.name}",
                                      kind="manual", user_id=admin.id).id
    written = datasnapshots.restore(db, snap)
    ensure_breakglass(db)
    record_audit(db, admin.id, "data.restore", entity="snapshot", entity_id=snap.id,
                 detail={"name": snap.name, "written": written, "safety_snapshot_id": safety})
    db.commit()
    return {"restored": written, "snapshot": _snapshot_out(snap), "safety_snapshot_id": safety}


@router.delete("/snapshots/{snapshot_id}", status_code=204)
def delete_snapshot(snapshot_id: int, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """DELETE /api/admin/data/snapshots/{id}: remove a copy. Admin only. Audited."""
    snap = db.get(DataSnapshot, snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Sauvegarde introuvable")
    record_audit(db, admin.id, "data.snapshot.delete", entity="snapshot", entity_id=snap.id,
                 detail={"name": snap.name})
    db.delete(snap)
    db.commit()
    return Response(status_code=204)


@router.get("/snapshots/{snapshot_id}/download")
def download_snapshot(snapshot_id: int, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    """GET /api/admin/data/snapshots/{id}/download: the copy as a .json.gz file.

    The same bytes that are stored, so a file downloaded today can be uploaded
    back tomorrow, into this instance or another one."""
    snap = db.get(DataSnapshot, snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Sauvegarde introuvable")
    slug = "".join(c if c.isalnum() else "-" for c in snap.name).strip("-").lower() or "snapshot"
    return Response(
        content=snap.payload,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="teamfollowup.{slug}.json.gz"'},
    )


@router.post("/snapshots/import", status_code=201)
def import_snapshot(file: UploadFile = File(...), db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """POST /api/admin/data/snapshots/import: upload a .json.gz back as a snapshot.

    Stored, not applied: importing a file and restoring it are two decisions, and
    only the second one erases anything. The payload is parsed here so a truncated
    or foreign file is refused now rather than halfway through a restore."""
    raw = file.file.read()
    try:
        data = json.loads(gzip.decompress(raw).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("racine JSON inattendue")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Fichier illisible : {exc}")
    known = {t.name for t in datasnapshots.covered_tables()}
    if not (set(data) & known):
        raise HTTPException(status_code=400,
                            detail="Ce fichier ne contient aucune table de l'application")
    counts = {k: len(v) for k, v in data.items() if isinstance(v, list) and v}
    snap = DataSnapshot(name=(file.filename or "Import")[:datasnapshots.MAX_NAME], kind="manual",
                        created_by_user_id=admin.id, size_bytes=len(raw), row_counts=counts,
                        payload=raw)
    db.add(snap)
    db.flush()
    record_audit(db, admin.id, "data.snapshot.import", entity="snapshot", entity_id=snap.id,
                 detail={"name": snap.name, "size": snap.size_bytes})
    db.commit()
    return _snapshot_out(snap)


# --------------------------------------------------------------------------
# Automatic snapshots
# --------------------------------------------------------------------------

@router.get("/snapshot-config")
def read_snapshot_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """GET /api/admin/data/snapshot-config: automatic snapshot settings. Admin only."""
    return datasnapshots.get_config(db)


@router.put("/snapshot-config")
def update_snapshot_config(payload: dict = Body(...), db: Session = Depends(get_db),
                           admin: User = Depends(require_admin)):
    """PUT /api/admin/data/snapshot-config: schedule (or stop) automatic copies.

    ``{"enabled": true, "interval_days": 7, "keep": 8}``. The hourly scheduler
    takes one when the last automatic copy is older than the interval, and prunes
    automatic copies past ``keep``. Manual copies are never pruned. Audited."""
    cfg = datasnapshots.set_config(db, payload)
    record_audit(db, admin.id, "data.snapshot_config", entity="settings", detail=cfg)
    db.commit()
    return cfg
