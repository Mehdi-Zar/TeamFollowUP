"""A tribe's Customer Success settings (ADR 0020, docs/37).

Stored as one JSON value per tribe in ``app_settings['cs:<tribe_id>']``:

    {"stages": [{"key", "label", "color", "closed"}],  # in order
     "offers": [str],                                  # the offer picklist
     "stale_days": 14,                                 # "no news since" threshold
     "access_warn_days": 30,                           # "access ends soon" threshold
     "recap_intro": str,                               # the recap's opening text
     "recap_marked_at": "YYYY-MM-DDTHH:MM:SS+00:00"}   # entries after it read "New"

Stages are keyed so that renaming one keeps its projects. ``closed`` stages
(Delivered, Closed by default) count as done: no "no news" badge on them, and
the dashboard counts them apart.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from .models import AppSetting

DEFAULT_STAGES = [
    {"key": "request", "label": "Demande", "color": "#667085", "closed": False},
    {"key": "scoping", "label": "Cadrage", "color": "#175CD3", "closed": False},
    {"key": "proposal", "label": "Proposition", "color": "#7C41AE", "closed": False},
    {"key": "agreement", "label": "Accord client", "color": "#B6770B", "closed": False},
    {"key": "build", "label": "Build", "color": "#248FCC", "closed": False},
    {"key": "delivered", "label": "Livré", "color": "#199E6E", "closed": True},
    {"key": "closed", "label": "Clos", "color": "#475467", "closed": True},
]
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _key(tribe_id: int) -> str:
    return f"cs:{int(tribe_id)}"


def defaults() -> dict:
    return {"stages": [dict(s) for s in DEFAULT_STAGES], "offers": [], "stale_days": 14,
            "access_warn_days": 30, "recap_intro": "", "recap_marked_at": None}


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower()).strip("_")
    return s[:40] or "stage"


def _clean_stages(raw) -> list[dict]:
    out, seen = [], set()
    for s in raw if isinstance(raw, list) else []:
        if not isinstance(s, dict):
            continue
        label = str(s.get("label") or "").strip()[:80]
        if not label:
            continue
        key = str(s.get("key") or "").strip()[:40] or _slug(label)
        base, n = key, 2
        while key in seen:
            key = f"{base[:36]}_{n}"
            n += 1
        seen.add(key)
        color = s.get("color") if isinstance(s.get("color"), str) and _HEX.match(s["color"]) else "#667085"
        out.append({"key": key, "label": label, "color": color, "closed": bool(s.get("closed"))})
    return out


def _int(v, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def normalize(raw: dict | None) -> dict:
    cfg = defaults()
    raw = raw if isinstance(raw, dict) else {}
    stages = _clean_stages(raw.get("stages"))
    if stages:
        cfg["stages"] = stages
    offers = raw.get("offers")
    if isinstance(offers, list):
        seen, clean = set(), []
        for o in offers:
            o = str(o or "").strip()[:255]
            if o and o.lower() not in seen:
                seen.add(o.lower())
                clean.append(o)
        cfg["offers"] = clean
    cfg["stale_days"] = _int(raw.get("stale_days"), 14, 1, 365)
    cfg["access_warn_days"] = _int(raw.get("access_warn_days"), 30, 1, 365)
    cfg["recap_intro"] = str(raw.get("recap_intro") or "")[:20000]
    m = raw.get("recap_marked_at")
    cfg["recap_marked_at"] = m if isinstance(m, str) and m else None
    return cfg


def get(db: Session, tribe_id: int) -> dict:
    row = db.get(AppSetting, _key(tribe_id))
    if row is None:
        return defaults()
    try:
        return normalize(json.loads(row.value))
    except (json.JSONDecodeError, TypeError):
        return defaults()


def save(db: Session, tribe_id: int, patch: dict) -> dict:
    """Merge ``patch`` into the tribe's settings and persist (no commit)."""
    cur = get(db, tribe_id)
    if isinstance(patch, dict):
        cur.update({k: v for k, v in patch.items() if k in cur})
    cfg = normalize(cur)
    row = db.get(AppSetting, _key(tribe_id))
    payload = json.dumps(cfg, ensure_ascii=False)
    if row is None:
        db.add(AppSetting(key=_key(tribe_id), value=payload))
    else:
        row.value = payload
    return cfg


def stage_keys(cfg: dict) -> list[str]:
    return [s["key"] for s in cfg["stages"]]


def closed_keys(cfg: dict) -> set[str]:
    return {s["key"] for s in cfg["stages"] if s["closed"]}
