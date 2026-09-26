"""Les documents tels qu'ils partaient a une date passee.

Une squad fige sa saisie a chaque soumission de cycle (``ReportSnapshot``), et
cette photo etait jusqu'ici lisible d'un seul endroit: l'historique de la page
d'une squad, une soumission a la fois. Personne ne pouvait donc repondre a la
question qu'on pose apres coup, en comite ou en audit: « montre-moi le dashboard
tel qu'il etait le 12 septembre ». Le seul recours etait de restaurer une
sauvegarde de la base entiere, c'est a dire de faire reculer l'application pour
tout le monde.

Ce module rejoue un document a une date. Il ne recalcule rien: il prend le
rapport du jour, deja assemble et deja filtre pour ce lecteur, et remplace le
contenu de chaque squad par celui de sa derniere soumission anterieure a la date
demandee. Ce qui n'a pas ete soumis ce jour-la n'est pas invente: la squad sort
du document et son nom est cite, parce qu'une squad absente d'une version se lit
comme une squad qui n'existait pas.

Deux choses restent celles du jour, et c'est dit sur le document:

- **Le budget.** Ses chiffres ne se montrent qu'aux responsables de la squad,
  alors qu'une saisie figee se lit par tout utilisateur qui voit la squad: les
  geler dans le payload les aurait ouverts a tout le monde. Le budget affiche est
  donc celui d'aujourd'hui, filtre comme il l'a toujours ete.
- **Le nom de la squad et de son responsable**, qui sont des etiquettes. Une
  squad renommee depuis garde son nom actuel, sans quoi personne ne la
  reconnaitrait dans la liste.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ReportSnapshot
from .reportcommon import _status_rag


def parse_as_of(value: str | date | datetime | None) -> datetime | None:
    """La borne haute d'une version, en UTC.

    Une date seule vaut la fin de cette journee: demander « la version du 12 »
    inclut ce qui a ete soumis ce jour-la, ce qui est la seule lecture a laquelle
    personne n'a besoin de reflechir.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.max, tzinfo=timezone.utc)
    text = str(value).strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.max, tzinfo=timezone.utc)
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Date de version illisible : {value}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Une date de base sans fuseau est une date UTC: SQLite les rend nues."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def list_versions(db: Session, squad_ids: list[int], year: int) -> list[dict]:
    """Les versions disponibles pour ces squads, de la plus recente a la plus ancienne.

    Une version est une journee, pas une soumission: treize squads soumettent le
    meme lundi et le lecteur choisit « le 12 septembre », pas « la soumission 4 de
    telle squad ». Le nombre de squads qui ont soumis ce jour-la accompagne la
    date, parce que c'est ce qui dit si la version est complete.
    """
    if not squad_ids:
        return []
    # The year is read in the database, and only the dates and labels come back:
    # the frozen payloads (tens of KB each) stay where they are.
    rows = db.execute(
        select(ReportSnapshot.squad_id, ReportSnapshot.submitted_at, ReportSnapshot.cycle_label)
        .where(ReportSnapshot.squad_id.in_(squad_ids),
               ReportSnapshot.payload["year"].as_integer() == year)
        .order_by(ReportSnapshot.submitted_at.desc())).all()
    days: dict[str, dict] = {}
    for sn in rows:
        day = _aware(sn.submitted_at).date().isoformat()
        entry = days.setdefault(day, {"date": day, "squads": set(), "labels": []})
        entry["squads"].add(sn.squad_id)
        if sn.cycle_label and sn.cycle_label not in entry["labels"]:
            entry["labels"].append(sn.cycle_label)
    out = [{"date": d["date"], "squads": len(d["squads"]), "labels": d["labels"][:4]}
           for d in days.values()]
    out.sort(key=lambda d: d["date"], reverse=True)
    return out


def _latest_snapshot(db: Session, squad_id: int, cutoff: datetime, year: int):
    """La derniere saisie de cette squad pour cette annee, avant la date demandee."""
    snaps = db.scalars(
        select(ReportSnapshot)
        .where(ReportSnapshot.squad_id == squad_id, ReportSnapshot.submitted_at <= cutoff)
        .order_by(ReportSnapshot.submitted_at.desc())).all()
    for sn in snaps:
        if (sn.payload or {}).get("year") == year:
            return sn
    return None


def _detail_from_payload(payload: dict, year: int, live_detail: dict) -> dict:
    """Le bloc « detail » d'une squad, reconstruit depuis sa saisie figee.

    Les jalons reprennent leurs rattachements d'engagement, sans quoi la frise les
    rangerait sous les dates d'aujourd'hui et la version mentirait sur ce qu'on
    avait promis.
    """
    by_quarter: dict[int, list[dict]] = {q: [] for q in (1, 2, 3, 4)}
    for it in payload.get("roadmap_items") or []:
        q = it.get("quarter") or 1
        by_quarter.setdefault(q, []).append({
            "id": it.get("id"), "title": it.get("title"), "status": it.get("status"),
            "owner": it.get("owner"), "stage": it.get("release_stage"),
            "theme": it.get("theme"), "objective_id": it.get("objective_id"),
            "initiative_id": it.get("initiative_id"),
            "otd_id": it.get("otd_id"), "squad_otd_id": it.get("squad_otd_id"),
            "dependency": it.get("dependency"),
        })
    progress = payload.get("quarter_progress") or {}
    return {
        "year": year,
        "initiatives": payload.get("initiatives") or [],
        "objectives": [
            {"id": o.get("id"), "title": o.get("title"), "rag": o.get("rag_status"),
             "initiative_id": o.get("initiative_id"), "target_date": o.get("target_date")}
            for o in payload.get("objectives") or [] if o.get("is_active", True)
        ],
        "otds": payload.get("otds") or [],
        "quarters": [
            {"q": q,
             "pct": int((progress.get(str(q)) or {}).get("progress_pct") or 0),
             "comment": (progress.get(str(q)) or {}).get("comment"),
             "items": by_quarter.get(q) or []}
            for q in (1, 2, 3, 4)
        ],
        "key_messages": payload.get("key_messages") or [],
        # Le budget du jour, filtre pour ce lecteur: voir l'en-tete du module.
        "budget": (live_detail or {}).get("budget"),
    }


def _row_from_snapshot(row: dict, snap, year: int) -> dict:
    """La ligne d'une squad, telle que sa saisie figee la disait.

    Les compteurs sont recalcules sur les jalons figes et non repris du jour: un
    jalon debloque depuis ferait etat de zero bloqueur dans une version qui en
    comptait trois, ce qui est exactement le mensonge qu'on vient eviter ici.
    """
    payload = snap.payload or {}
    detail = _detail_from_payload(payload, year, row.get("detail") or {})
    items = [it for qd in detail["quarters"] for it in qd["items"]]
    blocked = sum(1 for it in items if it.get("status") == "blocked")
    at_risk = sum(1 for it in items if it.get("status") == "at_risk")
    late = sum(1 for o in detail["otds"] if isinstance(o, dict) and o.get("status") == "late")

    # Les saisies d'avant cette version ne portaient pas l'etat de la squad. Plutot
    # que de reprendre celui d'aujourd'hui, qui serait faux sans le dire, il se
    # deduit de ce qui est fige.
    meta = payload.get("squad") or {}
    annual = meta.get("annual_pct")
    if annual is None:
        # Same rule as status.annual_mean: only the quarters that had milestones.
        planned = [qd["pct"] for qd in detail["quarters"] if qd["items"]]
        annual = round(sum(planned) / len(planned)) if planned else 0
    status = meta.get("status") or ("red" if blocked else "amber" if at_risk else "green")

    return {**row,
            "status": status,
            "status_rag": _status_rag(status),
            "mood": meta.get("mood"),
            "mood_at": meta.get("mood_at"),
            "mood_comment": meta.get("mood_comment"),
            "annual_pct": annual,
            "quarters": {q: detail["quarters"][q - 1]["pct"] for q in (1, 2, 3, 4)},
            "blocked": blocked,
            "at_risk": at_risk,
            "otd_late": late,
            # Une saisie est fraiche par definition le jour ou elle est soumise:
            # la peremption se mesure a partir d'aujourd'hui et n'a pas de sens ici.
            "age_days": 0, "is_stale": False, "delta": 0, "changes": [],
            "cycle_label": snap.cycle_label,
            "submitted_at": _aware(snap.submitted_at).isoformat(),
            "detail": detail}


def freeze_report_data(db: Session, data: dict, as_of) -> dict:
    """Rejoue ``data`` a la date demandee, en place.

    Rend le meme dictionnaire, aux memes clefs, pour que les quatre rendus (HTML,
    JPG, PPTX, courriel) n'aient rien a savoir des versions: un document date est
    le meme document, avec d'autres chiffres dedans.
    """
    cutoff = parse_as_of(as_of)
    if cutoff is None:
        return data
    year = data["year"]
    missing: list[str] = []
    totals = {"squads": 0, "blocked": 0, "at_risk": 0, "otd_late": 0, "progress": 0}
    late_ids: set = set()

    for blk in data.get("tribes") or []:
        kept = []
        for row in blk["squads"]:
            snap = _latest_snapshot(db, row["squad_id"], cutoff, year)
            if snap is None:
                missing.append(row["name"])
                continue
            frozen = _row_from_snapshot(row, snap, year)
            kept.append(frozen)
            totals["squads"] += 1
            totals["blocked"] += frozen["blocked"]
            totals["at_risk"] += frozen["at_risk"]
            # A commitment shared by several squads counts once, as in the live
            # document (it was added squad by squad: 67 instead of 26).
            ids = [o.get("id") for o in (frozen.get("detail") or {}).get("otds") or []
                   if o.get("status") == "late"]
            if ids and all(i is not None for i in ids):
                late_ids.update(ids)
            else:
                totals["otd_late"] += frozen["otd_late"]
            totals["progress"] += frozen["annual_pct"]
        from .report import severity_key
        kept.sort(key=severity_key)
        blk["squads"] = kept
    data["tribes"] = [b for b in (data.get("tribes") or []) if b["squads"]]

    data["summary"] = {
        "squads_total": totals["squads"],
        "blocked": totals["blocked"],
        "at_risk": totals["at_risk"],
        "otd_late": totals["otd_late"] + len(late_ids),
        # Rien n'est perime dans une version: chaque squad y est a sa date de saisie.
        "stale": 0,
        "avg_progress": round(totals["progress"] / totals["squads"]) if totals["squads"] else 0,
    }
    from .report import is_attention, severity_key
    attention = [r for blk in data["tribes"] for r in blk["squads"] if is_attention(r)]
    attention.sort(key=severity_key)
    data["attention"] = attention
    # Les absences a venir sont une projection depuis aujourd'hui: elles n'ont pas
    # de sens dans un document date, et une liste d'hier lue comme « a venir »
    # tromperait plus surement qu'une liste vide.
    data["leaves_upcoming"] = []
    data["as_of"] = cutoff.date().isoformat()
    data["as_of_missing"] = missing
    return data
