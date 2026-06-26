"""Personas & permissions: who can access which app sections.

A *persona* is a role key (the four built-ins admin/tribe_leader/squad_leader/member,
plus any number of admin-created custom personas). Each persona carries a set of
*capabilities* - section-access toggles - that the SPA and a few endpoints enforce.

Stored as one JSON blob in app_settings['personas']. Defaults for the built-ins
mirror the historical hard-coded navigation so behaviour is unchanged out of the box.
"""
import json
import re

from sqlalchemy.orm import Session

from .models import AppSetting

PERSONAS_KEY = "personas"

# Section-access capabilities (the catalog shown in the admin matrix).
CAPABILITIES = ["dashboard", "roadmap", "org", "feed", "reporting", "review", "mysquads"]
_CAP_SET = set(CAPABILITIES)

BUILTINS = ["admin", "tribe_leader", "squad_leader", "member"]


def _default_caps(key: str) -> dict:
    """Capabilities matching the legacy navigation for a built-in role."""
    if key == "admin":
        return {c: True for c in CAPABILITIES}
    caps = {c: False for c in CAPABILITIES}
    if key == "tribe_leader":
        caps.update(dashboard=True, roadmap=True, org=True, feed=True, review=True, mysquads=True)
    elif key == "squad_leader":
        caps.update(dashboard=True, roadmap=True, org=True, feed=True, reporting=True, mysquads=True)
    elif key == "member":
        caps.update(dashboard=True, roadmap=True, org=True, feed=True)
    return caps


def _normalize_caps(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {c: bool(raw.get(c, False)) for c in CAPABILITIES}


def _builtin_personas() -> list[dict]:
    return [{"key": k, "label": k, "builtin": True, "caps": _default_caps(k)} for k in BUILTINS]


def get_personas(db: Session) -> list[dict]:
    """All personas (built-ins first, then custom), with stored overrides applied."""
    personas = _builtin_personas()
    by_key = {p["key"]: p for p in personas}
    row = db.get(AppSetting, PERSONAS_KEY)
    if row:
        try:
            stored = json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            stored = []
        for sp in stored if isinstance(stored, list) else []:
            if not isinstance(sp, dict) or not sp.get("key"):
                continue
            key = sp["key"]
            raw = sp.get("caps") if isinstance(sp.get("caps"), dict) else {}
            if key in by_key:
                # Built-in: start from defaults so a newly-added capability keeps
                # its sensible default instead of silently turning off.
                merged = _default_caps(key)
                merged.update({c: bool(v) for c, v in raw.items() if c in _CAP_SET})
                by_key[key]["caps"] = merged
                if sp.get("label"):
                    by_key[key]["label"] = sp["label"]
            else:  # custom persona: unknown/missing caps default to off (safe)
                personas.append({"key": key, "label": sp.get("label") or key,
                                 "builtin": False, "caps": _normalize_caps(raw)})
    return personas


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower()).strip("_")
    return s or "persona"


def set_personas(db: Session, payload: list[dict]) -> list[dict]:
    """Persist personas. Built-ins are kept (caps/label only); custom ones replace.

    payload is the full list of personas as edited in the admin matrix.
    """
    incoming = {p.get("key"): p for p in payload if isinstance(p, dict) and p.get("key")}
    out: list[dict] = []
    seen: set[str] = set()

    # Built-ins always present; take their caps/label from the payload if provided.
    for k in BUILTINS:
        src = incoming.get(k, {})
        out.append({"key": k, "label": src.get("label") or k, "builtin": True,
                    "caps": _normalize_caps(src.get("caps")) if src else _default_caps(k)})
        seen.add(k)

    # Custom personas: validate/unique-ify keys.
    for p in payload if isinstance(payload, list) else []:
        key = p.get("key") if isinstance(p, dict) else None
        if not key or key in BUILTINS or key in seen:
            continue
        key = _slug(key)
        base = key
        i = 2
        while key in seen:
            key = f"{base}_{i}"; i += 1
        seen.add(key)
        out.append({"key": key, "label": (p.get("label") or key), "builtin": False,
                    "caps": _normalize_caps(p.get("caps"))})

    row = db.get(AppSetting, PERSONAS_KEY)
    value = json.dumps(out)
    if row is None:
        db.add(AppSetting(key=PERSONAS_KEY, value=value))
    else:
        row.value = value
    return out


def persona_caps(db: Session, role_key: str) -> dict:
    for p in get_personas(db):
        if p["key"] == role_key:
            return p["caps"]
    return {c: False for c in CAPABILITIES}  # unknown/deleted persona → no access


def can(db: Session, user, capability: str) -> bool:
    return bool(persona_caps(db, user.role).get(capability, False))


def valid_role_keys(db: Session) -> set[str]:
    return {p["key"] for p in get_personas(db)}
