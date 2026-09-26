"""Report snapshots: frozen point-in-time captures of a squad's reporting cycle.

Submitting a cycle ("Saisie") serializes the squad's current milestones, OTD, key
messages, mood, quarterly progress and KPIs into an immutable ReportSnapshot; the
read routes expose a squad's snapshot history and let two snapshots be diffed, on
the same six sections the reporting counts as "changed". The router is gated by the
`reporting` module; submission additionally needs the `reporting` capability and to
lead the squad (or be admin), while reads follow the squad-visibility rules.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import status as st
from ..database import get_db
from ..generalconfig import reference_year
from ..deps import (assert_can_read_squad, get_current_user, record_audit,
                    require_capability, require_module, require_writer)
from ..models import ReportSnapshot, Squad, User, utcnow
from ..serializers import annual_progress, dependency_label
from ..schemas import SnapshotMeta, SnapshotOut, SubmitCycleIn

router = APIRouter(prefix="/api/squads/{squad_id}/snapshots", tags=["snapshots"],
                   dependencies=[Depends(require_module("reporting"))])


def build_payload(db: Session, squad: Squad, year: int) -> dict:
    """Serialize the squad's current state for `year` into the snapshot payload dict.

    Deux lectures en tirent deux choses differentes, et le payload doit servir les
    deux. L'historique d'une squad compare deux soumissions, champ par champ:
    jalons, engagements, messages, moral, avancement, KPI. Un **export date** (`reportasof`) reprend,
    lui, le document entier tel qu'il partait ce jour-la, ce qui demande aussi les
    engagements OTD, les initiatives, les messages cles, le moral et le detail des
    jalons: sans eux, une version passee du dashboard se serait reconstruite avec
    les liens et les dates d'aujourd'hui, c'est a dire faux.

    Le budget n'y est pas, et c'est delibere: une saisie figee se lit par tout
    utilisateur qui voit la squad, alors que ses chiffres de budget ne se montrent
    qu'a ses responsables. Un export date reprend donc le budget du jour, filtre
    comme il l'a toujours ete.
    """
    progress = st.year_progress(squad, year)
    comments = st.quarter_comments(squad, year)
    # Les engagements de la squad, lus exactement comme le rapport les lit.
    from ..report import otd_rows_for_tribes, otds_of_squad
    from ..models import Initiative
    otds = otds_of_squad(squad, otd_rows_for_tribes(db, {squad.tribe_id}, year),
                         year, utcnow())
    initiatives = db.scalars(
        select(Initiative).where(Initiative.year == year, Initiative.squad_id == squad.id)
        .order_by(Initiative.display_order, Initiative.id)).all()
    return {
        "year": year,
        "roadmap_items": [
            {"id": r.id, "title": r.title, "quarter": r.quarter, "status": r.status,
             "release_stage": r.release_stage, "owner": r.owner, "theme": r.theme,
             "initiative_id": r.initiative_id,
             # Les deux rattachements d'engagement: c'est ce qui pose un jalon sous
             # le mois de la promesse qu'il tient, sur la frise.
             "otd_id": r.otd_id, "squad_otd_id": r.squad_otd_id,
             "dependency": dependency_label(r)}
            for r in sorted(squad.roadmap_items, key=lambda x: (x.quarter, x.display_order, x.id))
            if r.year == year
        ],
        # L'etat de la squad au moment de la soumission: son nom et son responsable
        # sont des etiquettes, mais son avancement, son statut et son moral sont ce
        # que le document disait, et aucun calcul d'aujourd'hui ne les retrouve.
        "squad": {
            "name": squad.name,
            "leader": squad.leader.display_name if squad.leader else "",
            "status": st.squad_status(squad, year),
            "annual_pct": annual_progress(squad, year),
            "mood": squad.mood,
            "mood_at": squad.mood_at.date().isoformat() if squad.mood_at else None,
            "mood_comment": squad.mood_comment,
        },
        "otds": otds,
        "initiatives": [
            {"id": i.id, "title": i.title, "owner": i.owner,
             "deadline": i.deadline.date().isoformat() if i.deadline else None}
            for i in initiatives
        ],
        "key_messages": [
            {"kind": m.kind, "text": m.text,
             "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else None}
            for m in sorted(squad.key_messages, key=lambda x: (x.display_order, x.id))
            if m.year == year
        ],
        "quarter_progress": {str(q): {"progress_pct": progress[q], "comment": comments[q]} for q in (1, 2, 3, 4)},
        "kpis": [
            {"id": k.id, "name": k.name, "unit": k.unit,
             "current_value": float(k.current_value) if k.current_value is not None else None,
             "target_value": float(k.target_value) if k.target_value is not None else None,
             "trend_status": k.trend_status, "comment": k.comment}
            for k in sorted(squad.kpis, key=lambda x: x.id)
        ],
    }


# Submitting a cycle is the "Saisie" section (SPA route /saisie, capability
# "reporting"). The reads below are the squad's history, shown on the squad page
# to anyone who may see the squad - they stay on the existing scope rules.
@router.post("", response_model=SnapshotOut, status_code=201,
             dependencies=[Depends(require_capability("reporting"))])
def submit_cycle(squad_id: int, payload: SubmitCycleIn, db: Session = Depends(get_db),
                 user: User = Depends(require_writer)):
    """Freeze the squad's current reporting cycle into a new snapshot.

    POST /api/squads/{squad_id}/snapshots
    Access: writer role + edit rights on the squad; additionally gated by the
    `reporting` capability. Business rules: defaults to the current year, and
    auto-labels the cycle "<year>-W<week>" when no label is provided.
    Side effects: writes a "cycle.submit" audit entry.
    """
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    # The squad's own leadership submits (admin included): a tribe leader reading
    # the reporting may correct some figures, not submit on the squad's behalf.
    from ..deps import assert_reports_for_squad
    assert_reports_for_squad(db, user, squad_id)
    year = payload.year or reference_year(db)

    # A default label both languages read: the reporting year and the ISO week of
    # the submission ("2026-W39"), with "(2)" for a second one in the same week.
    # It was "Soumission N", in French for everyone, counting every year together.
    label = payload.cycle_label
    if not label:
        week = utcnow().isocalendar()[1]
        base = f"{year}-W{week:02d}"
        taken = set(db.scalars(select(ReportSnapshot.cycle_label)
                               .where(ReportSnapshot.squad_id == squad_id)).all())
        label, n = base, 2
        while label in taken:
            label, n = f"{base} ({n})", n + 1

    snap = ReportSnapshot(
        squad_id=squad_id, submitted_by_user_id=user.id, submitted_at=utcnow(),
        payload=build_payload(db, squad, year), cycle_label=label,
    )
    db.add(snap)
    db.flush()
    record_audit(db, user.id, "cycle.submit", entity="snapshot", entity_id=snap.id,
                 detail={"squad_id": squad_id, "year": year, "cycle_label": label})
    db.commit()
    db.refresh(snap)
    # The moment the squad says its reporting is ready: the change notice
    # (when configured) leaves now, with the document as submitted.
    from ..changenotify import notify_change
    notify_change(squad_id, "submission", user, year)
    return snap


def _visible_squad(db: Session, user: User, squad_id: int) -> Squad:
    """The squad, if the caller may read it: same tribe rule as GET /api/squads/{id}.
    Without it the frozen payloads of another tribe's squads were readable here."""
    squad = db.get(Squad, squad_id)
    if squad is None:
        raise HTTPException(status_code=404, detail="Squad introuvable")
    assert_can_read_squad(user, squad)
    return squad


# What "changed since the last submission" compares, per step of the reporting.
# Each reads a slice of the payload; the OTD slice leaves out their status, which
# moves with the calendar (a commitment turns late by itself) and is not an edit.
def _slices(payload: dict) -> dict:
    squad = payload.get("squad") or {}
    return {
        "roadmap": [{k: v for k, v in (r or {}).items() if k not in ("otd_id", "initiative_id", "dependency")}
                    for r in payload.get("roadmap_items") or []],
        "otds": [(o.get("id"), o.get("title"), o.get("date")) for o in payload.get("otds") or []
                 if o.get("scope", "squad") == "squad"],
        "key_messages": [(m.get("kind"), m.get("text")) for m in payload.get("key_messages") or []],
        "mood": (squad.get("mood"), squad.get("mood_comment")),
        "kpis": payload.get("kpis") or [],
        "progress": {q: (v or {}).get("comment") for q, v in (payload.get("quarter_progress") or {}).items()},
    }


@router.get("/pending")
def pending_changes(squad_id: int, year: int | None = None, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """GET /api/squads/{squad_id}/snapshots/pending?year=

    What changed since the squad's last submission for that year, step by step:
    ``{"last": {cycle_label, submitted_at} | null, "changed": {roadmap, otds,
    key_messages, mood, kpis, progress}, "any": bool}``. Drives the state of each
    step of the reporting and the "unsubmitted changes" badge. Never submitted:
    every step with content counts as changed.
    """
    squad = _visible_squad(db, user, squad_id)
    year = year or reference_year(db)
    last = next((sn for sn in db.scalars(
        select(ReportSnapshot).where(ReportSnapshot.squad_id == squad_id)
        .order_by(ReportSnapshot.submitted_at.desc())).all()
        if (sn.payload or {}).get("year") == year), None)
    now = _slices(build_payload(db, squad, year))
    if last is None:
        def has(v):
            if isinstance(v, dict):
                return any(v.values())
            if isinstance(v, tuple):
                return any(x for x in v)
            return bool(v)
        changed = {k: has(v) for k, v in now.items()}
    else:
        before = _slices(last.payload or {})
        changed = {k: now[k] != before.get(k) for k in now}
    return {
        "last": None if last is None else {"cycle_label": last.cycle_label,
                                           "submitted_at": last.submitted_at},
        "changed": changed,
        "any": any(changed.values()),
    }


@router.get("", response_model=list[SnapshotMeta])
def list_snapshots(squad_id: int, year: int | None = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """List a squad's snapshots (metadata only), newest first.

    GET /api/squads/{squad_id}/snapshots?year=
    With ``year``, only the submissions of that year (the history of a squad page
    follows the year on screen instead of mixing them all).
    Access: any user who can see the squad. 404 if the squad is unknown.
    """
    _visible_squad(db, user, squad_id)
    q = select(ReportSnapshot).where(ReportSnapshot.squad_id == squad_id)
    if year is not None:
        q = q.where(ReportSnapshot.payload["year"].as_integer() == year)
    # Only the header columns: the payload is a whole report each.
    from sqlalchemy.orm import load_only
    rows = db.scalars(q.options(load_only(ReportSnapshot.id, ReportSnapshot.squad_id,
                                          ReportSnapshot.submitted_by_user_id,
                                          ReportSnapshot.submitted_at, ReportSnapshot.cycle_label))
                      .order_by(ReportSnapshot.submitted_at.desc())).all()
    ids = {r.submitted_by_user_id for r in rows if r.submitted_by_user_id}
    names = {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(ids))).all()} if ids else {}
    return [{"id": r.id, "squad_id": r.squad_id, "submitted_by_user_id": r.submitted_by_user_id,
             "submitted_by_name": names.get(r.submitted_by_user_id), "submitted_at": r.submitted_at,
             "cycle_label": r.cycle_label} for r in rows]


@router.get("/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(squad_id: int, snapshot_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Return one full snapshot (frozen payload included).

    GET /api/squads/{squad_id}/snapshots/{snapshot_id}
    Access: any user who can see the squad. 404 if the snapshot is missing or does
    not belong to this squad (the squad_id/snapshot_id pairing is verified).
    """
    _visible_squad(db, user, squad_id)
    snap = db.get(ReportSnapshot, snapshot_id)
    if snap is None or snap.squad_id != squad_id:
        raise HTTPException(status_code=404, detail="Snapshot introuvable")
    return snap


@router.get("/{snapshot_id}/compare", response_model=dict)
def compare_to_previous(squad_id: int, snapshot_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Diff a snapshot against the squad's immediately preceding one.

    GET /api/squads/{squad_id}/snapshots/{snapshot_id}/compare
    Access: any user who can see the squad. Returns the current and previous
    payloads plus a per-section diff (added/changed/removed). When there is no
    earlier snapshot, `previous` is null and everything reads as "added".
    """
    _visible_squad(db, user, squad_id)
    snap = db.get(ReportSnapshot, snapshot_id)
    if snap is None or snap.squad_id != squad_id:
        raise HTTPException(status_code=404, detail="Snapshot introuvable")
    # The previous submission OF THE SAME YEAR: a 2027 plan compared with a 2026
    # report listed every milestone as added and removed.
    year = (snap.payload or {}).get("year")
    previous = next((sn for sn in db.scalars(
        select(ReportSnapshot)
        .where(ReportSnapshot.squad_id == squad_id, ReportSnapshot.submitted_at < snap.submitted_at)
        .order_by(ReportSnapshot.submitted_at.desc())).all()
        if (sn.payload or {}).get("year") == year), None)
    return {
        "current": SnapshotOut.model_validate(snap).model_dump(),
        "previous": SnapshotOut.model_validate(previous).model_dump() if previous else None,
        "diff": _diff(previous.payload if previous else None, snap.payload),
    }


def _index(items):
    """Index a list of snapshot items by their `id` for O(1) prev/cur matching."""
    return {it["id"]: it for it in (items or [])}


def _keyed(payload: dict | None) -> dict:
    """The six compared sections of a payload, each as a list of items with an id.

    Milestones and KPIs carry their own id. An OTD is compared on what the squad
    writes (title, date, scope), not on its status, which moves with the calendar.
    A key message has no id: its kind and text are its identity. The mood and each
    quarter's progress comment are single values, under a fixed id.
    """
    p = payload or {}
    squad = p.get("squad") or {}
    return {
        "roadmap_items": p.get("roadmap_items") or [],
        "otds": [{"id": o.get("id"), "title": o.get("title"), "date": o.get("date"),
                  "scope": o.get("scope")} for o in p.get("otds") or []],
        "key_messages": [{"id": f"{m.get('kind')}:{m.get('text')}", "kind": m.get("kind"),
                          "text": m.get("text")} for m in p.get("key_messages") or []],
        "mood": ([{"id": "mood", "mood": squad.get("mood"), "mood_comment": squad.get("mood_comment")}]
                 if squad.get("mood") or squad.get("mood_comment") else []),
        "progress": [{"id": f"Q{q}", "comment": (v or {}).get("comment")}
                     for q, v in sorted((p.get("quarter_progress") or {}).items())
                     if (v or {}).get("comment")],
        "kpis": p.get("kpis") or [],
    }


def _diff(prev: dict | None, cur: dict) -> dict:
    """Compute a per-section diff between two snapshot payloads.

    For each of the six sections the reporting submits (milestones, OTD, key
    messages, mood, progress comments, KPIs), classify every item as added (only
    in cur), removed (only in prev) or changed (field-level from/to deltas). A
    None `prev` yields an all-"added" diff.
    """
    result = {}
    kp, kc = _keyed(prev), _keyed(cur)
    for section in kc:
        prev_idx = _index(kp[section] if prev is not None else [])
        cur_idx = _index(kc[section])
        changes = []
        for cid, citem in cur_idx.items():
            pitem = prev_idx.get(cid)
            if pitem is None:
                changes.append({"id": cid, "type": "added", "item": citem})
            else:
                fields = {k: {"from": pitem.get(k), "to": v} for k, v in citem.items() if pitem.get(k) != v}
                if fields:
                    changes.append({"id": cid, "type": "changed", "fields": fields, "item": citem})
        for pid, pitem in prev_idx.items():
            if pid not in cur_idx:
                changes.append({"id": pid, "type": "removed", "item": pitem})
        result[section] = changes
    return result
