"""Platform steerco: the slide template, who owns each item, and the merge on save.

A platform's slide is fed by one or more squads. The template says what the slide
contains and, for every single item, which contributing squad is responsible for
it. That per-item ownership is the whole point: with it, a slide assembled from n
contributors never needs a merge rule, because no two people can write the same
number. Without it, two squads filling the same SLA column leaves the renderer
choosing between two values and the reader with a figure nobody signed.

Template shape (the authority is here, not in the frontend)::

    {"kpis": [{"label": "K8aaS", "owner_squad_id": 9, "sub": ["GitLab", "Nexus"]}],
     "sla":  [{"label": "Gitlab", "owner_squad_id": 8}],
     "incidents": {"owner_squad_id": 8}}

Snapshot shape (``SteercoEntry.data``) is unchanged from the per-squad era, and is
POSITIONAL against the template: ``data["kpis"][i]`` holds the value of
``template["kpis"][i]``. Keeping that shape is deliberate, the one-pager renderer
(HTML and PPTX, some 600 lines) reads it as-is and did not have to move.

Labels are never taken from the client: :func:`merge_owned` rebuilds the skeleton
from the template and copies only *values* out of the payload, so the stored blob
cannot drift from the template it is rendered against.
"""
from sqlalchemy.orm import Session

# The structure a platform starts with, matching what squads were reporting before
# platforms existed (frontend/src/steerco.ts holds the same defaults for the UI).
DEFAULT_KPI_LABELS = ["Cloud Users", "Landing Zone", "K8aaS", "DBaaS", "Software Factory"]
DEFAULT_SWF_SUB = ["GitLab", "Artifactory", "SonarQube"]
DEFAULT_SLA_SERVICES = ["Incidents", "Gitlab", "Artifactory", "Sonarqube"]


def default_template(owner_squad_id: int | None = None) -> dict:
    """The standard slide, every item owned by ``owner_squad_id`` (may be None).

    Used when a platform is created and by the migration that turned each
    steerco-enabled squad into a platform of its own.
    """
    return {
        "kpis": [{"label": label, "owner_squad_id": owner_squad_id,
                  "sub": (list(DEFAULT_SWF_SUB) if label == "Software Factory" else [])}
                 for label in DEFAULT_KPI_LABELS],
        "sla": [{"label": s, "owner_squad_id": owner_squad_id} for s in DEFAULT_SLA_SERVICES],
        "incidents": {"owner_squad_id": owner_squad_id},
    }


def _owner(value, allowed: set[int] | None) -> int | None:
    """Coerce an owner id, dropping anyone who is not a contributor.

    A squad removed from the platform must not keep owning an item: the item would
    be editable by nobody and silently frozen. It falls back to unassigned, which
    the UI reports as an item to attribute.
    """
    try:
        oid = int(value)
    except (TypeError, ValueError):
        return None
    if allowed is not None and oid not in allowed:
        return None
    return oid


def normalize_template(raw: dict | None, contributor_ids=None) -> dict:
    """Clean a template as submitted: known keys only, owners limited to contributors.

    Items without a label are dropped (an unnamed KPI card is not a card), and an
    empty template falls back to the default structure so a platform is never a
    blank slide nobody can fill.
    """
    allowed = set(contributor_ids) if contributor_ids is not None else None
    raw = raw if isinstance(raw, dict) else {}
    kpis = []
    for item in raw.get("kpis") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        sub = [str(s).strip() for s in (item.get("sub") or []) if str(s).strip()]
        kpis.append({"label": label, "owner_squad_id": _owner(item.get("owner_squad_id"), allowed),
                     "sub": sub})
    sla = []
    for item in raw.get("sla") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        sla.append({"label": label, "owner_squad_id": _owner(item.get("owner_squad_id"), allowed)})
    incidents = raw.get("incidents") if isinstance(raw.get("incidents"), dict) else {}
    tpl = {"kpis": kpis, "sla": sla,
           "incidents": {"owner_squad_id": _owner(incidents.get("owner_squad_id"), allowed)}}
    if not tpl["kpis"] and not tpl["sla"]:
        only = next(iter(allowed)) if allowed and len(allowed) == 1 else None
        return default_template(only)
    return tpl


def blank_data(tpl: dict) -> dict:
    """The empty snapshot matching ``tpl``: labels in place, every value empty."""
    return {
        "kpis": [{"label": k["label"], "value": "",
                  **({"sub": [{"label": s, "value": ""} for s in k.get("sub") or []]}
                     if k.get("sub") else {})}
                 for k in tpl.get("kpis") or []],
        "sla": {"services": [s["label"] for s in tpl.get("sla") or []],
                "cells": [{"v": "", "s": None} for _ in tpl.get("sla") or []]},
        "incidents": "",
        "last_events": [],
        "next_events": [],
    }


def editable_items(tpl: dict, squad_ids) -> dict:
    """Which items of ``tpl`` a caller owning ``squad_ids`` may write.

    Returned as index lists so the UI can grey out what belongs to somebody else
    rather than hiding it: a contributor should see the whole slide and know who
    owes the rest.
    """
    ids = set(squad_ids or [])
    return {
        "kpis": [i for i, k in enumerate(tpl.get("kpis") or []) if k.get("owner_squad_id") in ids],
        "sla": [i for i, s in enumerate(tpl.get("sla") or []) if s.get("owner_squad_id") in ids],
        "incidents": (tpl.get("incidents") or {}).get("owner_squad_id") in ids,
        "events": bool(ids),  # every contributor may add its own events
    }


def _kpi_value(data: dict, index: int) -> dict:
    items = (data or {}).get("kpis") or []
    return items[index] if index < len(items) and isinstance(items[index], dict) else {}


def _cell_value(data: dict, index: int) -> dict:
    cells = ((data or {}).get("sla") or {}).get("cells") or []
    return cells[index] if index < len(cells) and isinstance(cells[index], dict) else {}


def merge_owned(stored: dict | None, incoming: dict | None, tpl: dict, squad_ids,
                all_owned: bool = False) -> dict:
    """Next stored snapshot: owned items from ``incoming``, the rest from ``stored``.

    ``all_owned`` is for a tribe leader or an admin, who may write the whole slide.
    The skeleton is rebuilt from the template, so labels always match what will be
    rendered even when the caller posts a stale form.
    """
    editable = editable_items(tpl, squad_ids)
    own_kpis = set(range(len(tpl.get("kpis") or []))) if all_owned else set(editable["kpis"])
    own_sla = set(range(len(tpl.get("sla") or []))) if all_owned else set(editable["sla"])
    own_inc = all_owned or editable["incidents"]

    out = blank_data(tpl)
    for i, card in enumerate(out["kpis"]):
        src = _kpi_value(incoming if i in own_kpis else stored, i)
        card["value"] = "" if src.get("value") is None else str(src.get("value", ""))
        if card.get("sub"):
            src_sub = {str(s.get("label")): s.get("value") for s in (src.get("sub") or [])
                       if isinstance(s, dict)}
            for entry in card["sub"]:
                entry["value"] = str(src_sub.get(entry["label"], "") or "")
    for i, cell in enumerate(out["sla"]["cells"]):
        src = _cell_value(incoming if i in own_sla else stored, i)
        cell["v"] = "" if src.get("v") is None else str(src.get("v", ""))
    src_inc = (incoming if own_inc else stored) or {}
    out["incidents"] = "" if src_inc.get("incidents") is None else str(src_inc.get("incidents", ""))
    out["last_events"] = merge_events((stored or {}).get("last_events"),
                                      (incoming or {}).get("last_events"), squad_ids, all_owned)
    out["next_events"] = merge_events((stored or {}).get("next_events"),
                                      (incoming or {}).get("next_events"), squad_ids, all_owned)
    return out


def merge_events(stored, incoming, squad_ids, all_owned: bool = False) -> list:
    """Events are the one shared section, so they merge by author rather than by item.

    Each event carries the squad that wrote it. A contributor replaces its own
    events and cannot touch anyone else's, which keeps a shared timeline editable
    by everybody without anyone being able to erase a colleague's line.
    """
    ids = set(squad_ids or [])
    mine = str(next(iter(sorted(ids)))) if ids else None
    kept = [e for e in (stored or []) if isinstance(e, dict)
            and not (all_owned or str(e.get("squad_id")) in {str(i) for i in ids})]
    added = []
    for e in (incoming or []):
        if not isinstance(e, dict):
            continue
        squad_id = e.get("squad_id") if all_owned else mine
        added.append({"date": str(e.get("date") or ""), "text": str(e.get("text") or ""),
                      "tag": str(e.get("tag") or ""), "sev": e.get("sev") or "ice",
                      "squad_id": squad_id})
    return kept + added


def sync_squad_flags(db: Session, squads=None) -> None:
    """Recompute ``Squad.steerco_enabled`` from platform membership.

    The flag is a cache of "this squad contributes somewhere", read by the
    reporting screen to show its Steerco step. Recomputed rather than toggled by
    hand so it cannot drift from the link table.
    """
    from .models import Squad

    targets = squads if squads is not None else db.query(Squad).all()
    for squad in targets:
        squad.steerco_enabled = bool(squad.platforms)
