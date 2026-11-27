"""Platform steerco: the slide template, the snapshot built on it, the tribe model.

A platform's slide is described by its template: which KPI cards (and their
sub-metrics), which SLA columns. Since 4.0 (ADR 0018) the figures are entered by
the tribe's Steerco leaders only, so the template no longer assigns an owner to
each item, and a save simply takes the values of every item.

Template shape (the authority is here, not in the frontend)::

    {"kpis": [{"label": "K8aaS", "sub": ["GitLab", "Nexus"]}],
     "sla":  [{"label": "Gitlab"}],
     "display": {"kpi_chart": "auto", "chart_kpis": []}}

Snapshot shape (``SteercoEntry.data``) is POSITIONAL against the template:
``data["kpis"][i]`` holds the value of ``template["kpis"][i]``. The one-pager
renderer (HTML and PPTX) reads it as-is.

Labels are never taken from the client: :func:`merge_values` rebuilds the skeleton
from the template and copies only *values* out of the payload, so the stored blob
cannot drift from the template it is rendered against.
"""
from sqlalchemy.orm import Session

# The structure a platform starts with, matching what squads were reporting before
# platforms existed (frontend/src/steerco.ts holds the same defaults for the UI).
DEFAULT_KPI_LABELS = ["Cloud Users", "Landing Zone", "K8aaS", "DBaaS", "Software Factory"]
DEFAULT_SWF_SUB = ["GitLab", "Artifactory", "SonarQube"]
DEFAULT_SLA_SERVICES = ["Incidents", "Gitlab", "Artifactory", "Sonarqube"]


def default_template() -> dict:
    """The standard slide: used when a platform is created without a model."""
    return {
        "kpis": [{"label": label,
                  "sub": (list(DEFAULT_SWF_SUB) if label == "Software Factory" else [])}
                 for label in DEFAULT_KPI_LABELS],
        "sla": [{"label": s} for s in DEFAULT_SLA_SERVICES],
    }


# How the KPI chart of the slide is drawn. "auto" draws curves up to
# LINES_MAX_SERIES KPIs and one small chart per KPI beyond: a dozen curves on one
# plot, or on two scales, cannot be told apart.
CHART_MODES = ("auto", "lines", "small_multiples", "table")
LINES_MAX_SERIES = 5


def normalize_display(raw, labels) -> dict:
    """The slide's rendering choices: the KPI chart mode, and which KPIs the chart
    shows (empty: all of them). A KPI that left the template leaves the list."""
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get("kpi_chart") if raw.get("kpi_chart") in CHART_MODES else "auto"
    known = set(labels)
    picked = [str(x) for x in (raw.get("chart_kpis") or []) if str(x) in known]
    return {"kpi_chart": mode, "chart_kpis": list(dict.fromkeys(picked))}


def normalize_template(raw: dict | None, _ignored=None) -> dict:
    """Clean a template as submitted: known keys only (an ``owner_squad_id`` left by
    an older client is dropped).

    Items without a label are dropped (an unnamed KPI card is not a card), and an
    empty template falls back to the default structure so a platform is never a
    blank slide nobody can fill.
    """
    raw = raw if isinstance(raw, dict) else {}
    kpis = []
    for item in raw.get("kpis") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        sub = [str(s).strip() for s in (item.get("sub") or []) if str(s).strip()]
        kpis.append({"label": label, "sub": sub})
    sla = []
    for item in raw.get("sla") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if label:
            sla.append({"label": label})
    if not kpis and not sla:
        base = default_template()
        kpis, sla = base["kpis"], base["sla"]
    return {"kpis": kpis, "sla": sla,
            "display": normalize_display(raw.get("display"), [k["label"] for k in kpis])}


def item_count(tpl: dict) -> int:
    """Items a month must fill to be complete: every KPI, every SLA column, and
    the incident count."""
    return len(tpl.get("kpis") or []) + len(tpl.get("sla") or []) + 1


def filled_count(tpl: dict, data: dict | None) -> int:
    """How many of the template's items carry a value this month."""
    data = data or {}
    kpis = data.get("kpis") or []
    cells = (data.get("sla") or {}).get("cells") or []
    n = 0
    for i in range(len(tpl.get("kpis") or [])):
        k = kpis[i] if i < len(kpis) and isinstance(kpis[i], dict) else {}
        n += bool(str(k.get("value") or "").strip())
    for i in range(len(tpl.get("sla") or [])):
        c = cells[i] if i < len(cells) and isinstance(cells[i], dict) else {}
        n += bool(str(c.get("v") or "").strip())
    n += bool(str(data.get("incidents") or "").strip())
    return n


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


def _kpi_value(data: dict, index: int) -> dict:
    items = (data or {}).get("kpis") or []
    return items[index] if index < len(items) and isinstance(items[index], dict) else {}


def _cell_value(data: dict, index: int) -> dict:
    cells = ((data or {}).get("sla") or {}).get("cells") or []
    return cells[index] if index < len(cells) and isinstance(cells[index], dict) else {}


SEVERITIES = ("red", "amber", "green", "ice")


def _events(raw) -> list:
    out = []
    for e in raw or []:
        if not isinstance(e, dict):
            continue
        out.append({"date": str(e.get("date") or ""), "text": str(e.get("text") or ""),
                    "tag": str(e.get("tag") or ""),
                    "sev": e.get("sev") if e.get("sev") in SEVERITIES else "ice"})
    return out


def merge_values(incoming: dict | None, tpl: dict) -> dict:
    """The snapshot to store: the template's skeleton, every value from ``incoming``.

    Labels come from the template, so a stale form cannot rename a line of the
    slide; anything the template does not describe is dropped.
    """
    incoming = incoming or {}
    out = blank_data(tpl)
    for i, card in enumerate(out["kpis"]):
        src = _kpi_value(incoming, i)
        card["value"] = "" if src.get("value") is None else str(src.get("value", ""))
        if card.get("sub"):
            src_sub = {str(s.get("label")): s.get("value") for s in (src.get("sub") or [])
                       if isinstance(s, dict)}
            for entry in card["sub"]:
                entry["value"] = str(src_sub.get(entry["label"], "") or "")
    for i, cell in enumerate(out["sla"]["cells"]):
        src = _cell_value(incoming, i)
        cell["v"] = "" if src.get("v") is None else str(src.get("v", ""))
    out["incidents"] = "" if incoming.get("incidents") is None else str(incoming.get("incidents", ""))
    out["last_events"] = _events(incoming.get("last_events"))
    out["next_events"] = _events(incoming.get("next_events"))
    return out


# --------------------------------------------------------------------------
# The tribe's model: the skeleton its tribe leader imposes on every platform
# --------------------------------------------------------------------------
#
# One model per tribe, stored in app_settings['steerco_model:tribe:<id>']. It holds
# the structure only (KPI and their sub-metrics, SLA services). A new platform
# starts from it, and "apply the tribe model" brings an existing platform back to
# it while keeping the figures of the items that stay.

MODEL_PREFIX = "steerco_model:tribe:"


def _model_key(tribe_id: int) -> str:
    return f"{MODEL_PREFIX}{int(tribe_id)}"


def normalize_model(raw) -> dict:
    """The tribe model as stored: labels and sub-metrics."""
    tpl = normalize_template(raw)
    return {"kpis": [{"label": k["label"], "sub": list(k.get("sub") or [])} for k in tpl["kpis"]],
            "sla": [{"label": s["label"]} for s in tpl["sla"]]}


def get_tribe_model(db: Session, tribe_id: int) -> dict:
    """The tribe's model, or the standard structure when none was set."""
    import json
    from .models import AppSetting
    row = db.get(AppSetting, _model_key(tribe_id))
    if row:
        try:
            return normalize_model(json.loads(row.value))
        except (ValueError, TypeError):
            pass
    return normalize_model(default_template())


def set_tribe_model(db: Session, tribe_id: int, raw) -> dict:
    """Store the tribe's model (no commit)."""
    import json
    from .models import AppSetting
    model = normalize_model(raw)
    key = _model_key(tribe_id)
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=json.dumps(model)))
    else:
        row.value = json.dumps(model)
    return model


def template_from_model(model: dict, current: dict | None, _ignored=None) -> dict:
    """A platform template shaped like ``model``, keeping how this platform's slide
    is drawn (``display``)."""
    cur = current if isinstance(current, dict) else {}
    raw = {
        "kpis": [{"label": k["label"], "sub": k.get("sub") or []} for k in model.get("kpis") or []],
        "sla": [{"label": s["label"]} for s in model.get("sla") or []],
        "display": cur.get("display"),
    }
    return normalize_template(raw)


def remap_data(data: dict | None, new_tpl: dict) -> dict:
    """A stored snapshot re-laid on a changed template, matched by label.

    Snapshots are positional (``data["kpis"][i]`` is ``template["kpis"][i]``): when
    items were removed or reordered, the figures shifted onto the neighbouring
    items at the next save. Here each figure follows its label; an item that left
    the template takes its figures with it, a new one starts empty.
    """
    data = data if isinstance(data, dict) else {}
    out = blank_data(new_tpl)
    by_label = {str(k.get("label")): k for k in data.get("kpis") or [] if isinstance(k, dict)}
    for card in out["kpis"]:
        src = by_label.get(card["label"]) or {}
        card["value"] = "" if src.get("value") is None else str(src.get("value", ""))
        if card.get("sub"):
            src_sub = {str(s.get("label")): s.get("value") for s in (src.get("sub") or [])
                       if isinstance(s, dict)}
            for entry in card["sub"]:
                entry["value"] = str(src_sub.get(entry["label"], "") or "")
    sla = data.get("sla") or {}
    cells = {str(lbl): (sla.get("cells") or [])[i]
             for i, lbl in enumerate(sla.get("services") or [])
             if i < len(sla.get("cells") or []) and isinstance((sla.get("cells") or [])[i], dict)}
    out["sla"]["cells"] = [dict(cells.get(lbl) or {"v": "", "s": None}) for lbl in out["sla"]["services"]]
    for key in ("incidents", "last_events", "next_events"):
        if key in data:
            out[key] = data[key]
    # Anything else the snapshot carries (older keys) is kept as is.
    for key, value in data.items():
        if key not in out:
            out[key] = value
    return out
