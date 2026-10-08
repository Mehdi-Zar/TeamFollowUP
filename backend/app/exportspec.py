"""Studio des exports: what a document template may say, and how templates inherit.

A template's **specification** is a JSON document: an ordered list of *sections*
(one slide, or one per squad / per platform), each made of *blocks* that can be
switched off or tuned, plus the document's own settings. This module is pure (no
database, no python-pptx): it holds the catalogue, the shipped "Standard"
templates, the validation of a specification and the inheritance arithmetic.

Inheritance is by **difference**. A derived template stores only what it changes
relative to its parent's effective specification, keyed by the stable ids of
sections and blocks (never by position). The editor always works on the full,
effective specification; :func:`diff` turns it back into a patch on save, and
:func:`apply` replays a patch on the parent. A parent may lock parts of itself:
a locked part of a patch is ignored, and reported, never applied.
"""
from __future__ import annotations

import copy
import re

# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------
DOC_KINDS = ("dashboard", "weekly", "roadmap", "dependencies", "initiatives", "steerco", "org")

# Where each document gets its data. A section reads the family of its document.
DOC_DATA = {"dashboard": "report", "weekly": "report", "roadmap": "report",
            "dependencies": "dependencies", "initiatives": "initiatives",
            "steerco": "steerco", "org": "org"}

GRID_COLS, GRID_ROWS = 12, 8

# Param kinds understood by the editor and by :func:`_coerce`.
#   bool, int (min/max), enum (options), multi (options, ordered subset),
#   text (max), longtext (max), color (#rrggbb or ""), asset (int id or None)

FILTERS = ["all", "attention", "reported", "stale"]
SORTS = ["order", "severity", "name", "progress"]

SECTION_TYPES: dict[str, dict] = {
    # ---- report family (dashboard, weekly report, roadmap) ----------------------
    "summary": {
        "data": "report", "repeat": "once",
        "params": {
            "filter": {"kind": "enum", "options": FILTERS[:3], "default": "all"},
            "sort": {"kind": "enum", "options": SORTS, "default": "order"},
            "skip_when_single_squad": {"kind": "bool", "default": True},
            "rows_first": {"kind": "int", "min": 4, "max": 20, "default": 14},
            "rows_next": {"kind": "int", "min": 6, "max": 24, "default": 20},
        },
        "blocks": {
            "header": {},
            "kpis": {"params": {"items": {"kind": "multi", "default": [
                "squads", "progress", "blocked", "at_risk", "otd_late", "stale"],
                "options": ["squads", "progress", "blocked", "at_risk", "otd_late", "stale"]}}},
            "version": {},
            "table": {"params": {"columns": {"kind": "multi", "default": [
                "name", "leader", "status", "progress", "blocked", "at_risk", "last"],
                "options": ["name", "leader", "status", "progress", "blocked", "at_risk", "last"]}}},
        },
    },
    "squad": {
        "data": "report", "repeat": "per_squad",
        "params": {
            "filter": {"kind": "enum", "options": FILTERS, "default": "all"},
            "sort": {"kind": "enum", "options": SORTS, "default": "order"},
            "use_squad_variant": {"kind": "bool", "default": False},
        },
        "blocks": {
            "header": {"params": {
                "show_leader": {"kind": "bool", "default": True},
                "show_progress": {"kind": "bool", "default": True},
                "show_last_update": {"kind": "bool", "default": True},
                "show_people": {"kind": "bool", "default": True}}},
            "mood": {},
            "timeline": {"params": {
                "show_done": {"kind": "bool", "default": True},
                "show_otds": {"kind": "bool", "default": True},
                "show_quarter_progress": {"kind": "bool", "default": True},
                "show_notes": {"kind": "bool", "default": True}}},
            "status_legend": {},
            "key_messages": {"params": {"max": {"kind": "int", "min": 1, "max": 4, "default": 4}}},
            "kpis": {},
            "budget": {},
            "legend": {},
            "stamp": {},
        },
    },
    "attention": {
        "data": "report", "repeat": "once",
        "params": {
            "skip_when_dated": {"kind": "bool", "default": True},
            "skip_when_single_squad": {"kind": "bool", "default": True},
        },
        "blocks": {"header": {}, "attention": {}, "tribe_otds": {}, "leaves": {}},
    },
    "roadmap": {
        "data": "report", "repeat": "once",
        "params": {
            "filter": {"kind": "enum", "options": FILTERS, "default": "all"},
            "sort": {"kind": "enum", "options": SORTS, "default": "order"},
            "show_themes": {"kind": "enum", "options": ["auto", "always", "never"], "default": "auto"},
            "show_done": {"kind": "bool", "default": True},
        },
        "blocks": {"header": {}, "legend": {}},
    },
    # ---- the other documents ------------------------------------------------------
    "dependencies": {
        "data": "dependencies", "repeat": "once",
        "params": {"hide_done": {"kind": "bool", "default": False}},
        "blocks": {"header": {}},
    },
    "initiatives": {
        "data": "initiatives", "repeat": "once",
        "params": {
            "rows_per_slide": {"kind": "int", "min": 6, "max": 20, "default": 16},
            "hide_past": {"kind": "bool", "default": False},
            "columns": {"kind": "multi", "default": ["owner", "squad", "deadline"],
                        "options": ["owner", "squad", "deadline"]},
        },
        "blocks": {"header": {}},
    },
    "platform": {
        "data": "steerco", "repeat": "per_platform",
        "params": {"swap_columns": {"kind": "bool", "default": False},
                   "use_platform_variant": {"kind": "bool", "default": False}},
        "blocks": {"header": {}, "kpis": {}, "kpi_chart": {}, "sla": {}, "incidents": {},
                   "last_events": {}, "next_events": {}},
    },
    "org": {
        "data": "org", "repeat": "once",
        "params": {},
        "blocks": {"legend": {}, "stamp": {}},
    },
    # ---- generic sections, valid in every document ---------------------------------
    "cover": {
        "data": None, "repeat": "once",
        "params": {
            "title": {"kind": "text", "max": 160, "default": "{doc} | {scope}"},
            "subtitle": {"kind": "text", "max": 200, "default": "{year}, {date}"},
            "background": {"kind": "color", "default": ""},
            "image": {"kind": "asset", "default": None},
        },
        "blocks": {},
    },
    "text": {
        "data": None, "repeat": "once",
        "params": {
            "title": {"kind": "text", "max": 160, "default": ""},
            "body": {"kind": "longtext", "max": 4000, "default": ""},
        },
        "blocks": {},
    },
    "custom": {
        "data": None, "repeat": "once",
        "params": {
            "title": {"kind": "text", "max": 160, "default": ""},
            "repeat": {"kind": "enum", "options": ["once", "per_squad", "per_platform"], "default": "once"},
            "filter": {"kind": "enum", "options": FILTERS, "default": "all"},
        },
        "blocks": {},
    },
    "imported": {
        "data": None, "repeat": "once",
        "params": {
            "asset": {"kind": "asset", "default": None},
            "slide": {"kind": "int", "min": 1, "max": 200, "default": 1},
        },
        "blocks": {},
    },
}

GENERIC_SECTIONS = ("cover", "text", "custom", "imported")

# The widgets a custom (grid) section can place, and what each needs.
#   needs: None (anywhere), "report", "squad" (per-squad slide), "steerco", "platform"
WIDGETS: dict[str, dict] = {
    "text": {"needs": None, "params": {
        "text": {"kind": "longtext", "max": 2000, "default": ""},
        "size": {"kind": "int", "min": 8, "max": 44, "default": 14},
        "bold": {"kind": "bool", "default": False},
        "align": {"kind": "enum", "options": ["left", "center", "right"], "default": "left"},
        "color": {"kind": "color", "default": ""},
        "fill": {"kind": "color", "default": ""}}},
    "image": {"needs": None, "params": {"asset": {"kind": "asset", "default": None}}},
    "kpi_tiles": {"needs": "report", "params": {"items": SECTION_TYPES["summary"]["blocks"]["kpis"]["params"]["items"]}},
    "squad_table": {"needs": "report", "params": {
        "columns": SECTION_TYPES["summary"]["blocks"]["table"]["params"]["columns"],
        "filter": {"kind": "enum", "options": FILTERS[:3], "default": "all"},
        "sort": {"kind": "enum", "options": SORTS, "default": "order"}}},
    "attention_list": {"needs": "report", "params": {}},
    "tribe_otds": {"needs": "report", "params": {}},
    "roadmap": {"needs": "report", "params": {
        "show_themes": {"kind": "enum", "options": ["auto", "always", "never"], "default": "auto"}}},
    "squad_header": {"needs": "squad", "params": {}},
    "squad_mood": {"needs": "squad", "params": {}},
    "squad_timeline": {"needs": "squad", "params": {}},
    "squad_key_messages": {"needs": "squad", "params": {}},
    "squad_kpis": {"needs": "squad", "params": {}},
    "squad_budget": {"needs": "squad", "params": {}},
    "platform_kpis": {"needs": "platform", "params": {}},
    "platform_kpi_chart": {"needs": "platform", "params": {}},
    "platform_sla": {"needs": "platform", "params": {}},
    "platform_incidents": {"needs": "platform", "params": {}},
    "platform_last_events": {"needs": "platform", "params": {}},
    "platform_next_events": {"needs": "platform", "params": {}},
}

DOC_PARAMS = {
    "filename": {"kind": "text", "max": 120, "default": "{doc}_{scope}_{date}"},
    "footer": {"kind": "text", "max": 200, "default": ""},
    "page_numbers": {"kind": "bool", "default": False},
}

# The text fields a template may write: anything else between braces stays as typed.
TOKENS = ("doc", "scope", "year", "date", "app", "squad", "leader", "platform", "period",
          "version", "page")

# Characters the repository never prints (see CLAUDE.md): the Studio refuses them in a
# template's text, so a template cannot reintroduce them in a generated document.
BANNED_CHARS = ("\u2014", "\u00b7")


def sections_for(doc_kind: str) -> list[str]:
    """The section types a document of this kind may contain."""
    fam = DOC_DATA.get(doc_kind)
    return [t for t, d in SECTION_TYPES.items() if d["data"] == fam] + list(GENERIC_SECTIONS)


def widgets_for(doc_kind: str, repeat: str) -> list[str]:
    """The widgets a custom section of this document and repetition may place."""
    fam = DOC_DATA.get(doc_kind)
    out = []
    for name, w in WIDGETS.items():
        need = w["needs"]
        if need is None or (need == "report" and fam == "report") \
                or (need == "squad" and fam == "report" and repeat == "per_squad") \
                or (need == "platform" and fam == "steerco" and repeat == "per_platform"):
            out.append(name)
    return out


def catalogue() -> dict:
    """Everything the editor needs to build its panels, as plain JSON."""
    return {
        "doc_kinds": list(DOC_KINDS),
        "doc_data": DOC_DATA,
        "sections": SECTION_TYPES,
        "widgets": WIDGETS,
        "doc_params": DOC_PARAMS,
        "sections_for": {k: sections_for(k) for k in DOC_KINDS},
        "grid": {"cols": GRID_COLS, "rows": GRID_ROWS},
        "tokens": list(TOKENS),
        "theme_keys": ["primary", "primary_deep", "accent", "green", "orange", "red",
                       "ink", "muted", "line", "card", "background", "zebra"],
    }


# --------------------------------------------------------------------------
# The shipped templates ("Standard"): exactly the decks the product always made
# --------------------------------------------------------------------------
def _section(sid: str, stype: str, **params) -> dict:
    return {"id": sid, "type": stype, "enabled": True, "params": params, "blocks": {}}


def system_spec(doc_kind: str) -> dict:
    """The Standard template of a document: rendering it gives, to the byte, the deck
    the application produced before templates existed."""
    if doc_kind == "dashboard":
        secs = [_section("summary", "summary"), _section("squads", "squad")]
    elif doc_kind == "weekly":
        secs = [_section("summary", "summary"), _section("squads", "squad"),
                _section("attention", "attention")]
    elif doc_kind == "roadmap":
        secs = [_section("roadmap", "roadmap")]
    elif doc_kind == "dependencies":
        secs = [_section("dependencies", "dependencies")]
    elif doc_kind == "initiatives":
        secs = [_section("initiatives", "initiatives")]
    elif doc_kind == "steerco":
        secs = [_section("platforms", "platform")]
    elif doc_kind == "org":
        secs = [_section("org", "org")]
    else:
        raise ValueError(f"unknown document kind: {doc_kind}")
    return normalize({"doc_kind": doc_kind, "sections": secs}, doc_kind)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _clean_text(v, limit: int) -> str:
    s = str(v if v is not None else "")
    for ch in BANNED_CHARS:
        s = s.replace(ch, ",")
    # No control characters but line breaks: the value ends up in XML.
    s = "".join(c for c in s if c in "\n\t" or ord(c) >= 32)
    return s[:limit]


def _coerce(spec: dict, value):
    kind = spec["kind"]
    default = spec.get("default")
    if kind == "bool":
        return bool(value) if isinstance(value, (bool, int)) else default
    if kind == "int":
        try:
            v = int(value)
        except (TypeError, ValueError):
            return default
        return max(spec.get("min", v), min(spec.get("max", v), v))
    if kind == "enum":
        return value if value in spec["options"] else default
    if kind == "multi":
        if not isinstance(value, list):
            return list(default)
        seen = []
        for x in value:
            if x in spec["options"] and x not in seen:
                seen.append(x)
        return seen
    if kind in ("text", "longtext"):
        return _clean_text(value if value is not None else default, spec.get("max", 500))
    if kind == "color":
        return value if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else ""
    if kind == "asset":
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
    return default


def _params(schema: dict, raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {k: _coerce(s, raw.get(k, s.get("default"))) for k, s in schema.items()}


def _zone(raw) -> list[int]:
    try:
        c0, r0, c1, r1 = (int(x) for x in raw)
    except (TypeError, ValueError):
        return [0, 0, GRID_COLS, GRID_ROWS]
    c0 = max(0, min(GRID_COLS - 1, c0)); r0 = max(0, min(GRID_ROWS - 1, r0))
    c1 = max(c0 + 1, min(GRID_COLS, c1)); r1 = max(r0 + 1, min(GRID_ROWS, r1))
    return [c0, r0, c1, r1]


def normalize_section(raw: dict, doc_kind: str) -> dict | None:
    """A clean section, or None when its type is not allowed in this document."""
    if not isinstance(raw, dict):
        return None
    stype = raw.get("type")
    if stype not in SECTION_TYPES or stype not in sections_for(doc_kind):
        return None
    cat = SECTION_TYPES[stype]
    sid = str(raw.get("id") or stype)
    if not _ID.match(sid):
        sid = stype
    out = {"id": sid, "type": stype, "enabled": bool(raw.get("enabled", True)),
           "params": _params(cat["params"], raw.get("params")), "blocks": {}}
    blocks = raw.get("blocks") if isinstance(raw.get("blocks"), dict) else {}
    for bid, bcat in cat["blocks"].items():
        b = blocks.get(bid) if isinstance(blocks.get(bid), dict) else {}
        out["blocks"][bid] = {"enabled": bool(b.get("enabled", True)),
                              "params": _params(bcat.get("params") or {}, b.get("params"))}
    if stype == "custom":
        repeat = out["params"]["repeat"]
        allowed = set(widgets_for(doc_kind, repeat))
        items, seen = [], set()
        for it in raw.get("items") or []:
            if not isinstance(it, dict) or it.get("widget") not in allowed:
                continue
            iid = str(it.get("id") or "")
            if not _ID.match(iid) or iid in seen:
                iid = f"w{len(items) + 1}"
                while iid in seen:
                    iid += "x"
            seen.add(iid)
            items.append({"id": iid, "widget": it["widget"], "zone": _zone(it.get("zone")),
                          "params": _params(WIDGETS[it["widget"]]["params"], it.get("params"))})
            if len(items) >= 24:
                break
        out["items"] = items
    return out


def normalize(raw: dict | None, doc_kind: str) -> dict:
    """A clean, complete specification: known types only, every parameter present and
    within bounds, unique section ids, at most 40 sections."""
    if doc_kind not in DOC_KINDS:
        raise ValueError(f"unknown document kind: {doc_kind}")
    raw = raw if isinstance(raw, dict) else {}
    sections, seen = [], set()
    for s in raw.get("sections") or []:
        sec = normalize_section(s, doc_kind)
        if sec is None:
            continue
        base, n = sec["id"], 2
        while sec["id"] in seen:
            sec["id"] = f"{base}{n}"[:40]
            n += 1
        seen.add(sec["id"])
        sections.append(sec)
        if len(sections) >= 40:
            break
    theme_id = raw.get("theme_id")
    try:
        theme_id = int(theme_id) if theme_id not in (None, "") else None
    except (TypeError, ValueError):
        theme_id = None
    return {"doc_kind": doc_kind, "theme_id": theme_id,
            "doc": _params(DOC_PARAMS, raw.get("doc")), "sections": sections}


# --------------------------------------------------------------------------
# Inheritance: diff / apply, with locks
# --------------------------------------------------------------------------
def _diff_params(a: dict, b: dict) -> dict:
    return {k: v for k, v in b.items() if a.get(k) != v}


def _diff_section(p: dict, c: dict) -> dict:
    out = {}
    if p["enabled"] != c["enabled"]:
        out["enabled"] = c["enabled"]
    dp = _diff_params(p["params"], c["params"])
    if dp:
        out["params"] = dp
    blocks = {}
    for bid, cb in c["blocks"].items():
        pb = p["blocks"].get(bid) or {"enabled": True, "params": {}}
        d = {}
        if pb["enabled"] != cb["enabled"]:
            d["enabled"] = cb["enabled"]
        bp = _diff_params(pb.get("params") or {}, cb["params"])
        if bp:
            d["params"] = bp
        if d:
            blocks[bid] = d
    if blocks:
        out["blocks"] = blocks
    if c.get("items") is not None and c.get("items") != p.get("items"):
        out["items"] = copy.deepcopy(c["items"])
    return out


def diff(parent: dict, child: dict) -> dict:
    """The patch that turns ``parent`` (effective) into ``child`` (effective)."""
    patch: dict = {}
    if child.get("theme_id") != parent.get("theme_id"):
        patch["theme_id"] = child.get("theme_id")
    dd = _diff_params(parent["doc"], child["doc"])
    if dd:
        patch["doc"] = dd
    pmap = {s["id"]: s for s in parent["sections"]}
    cids = [s["id"] for s in child["sections"]]
    secs, added = {}, []
    for s in child["sections"]:
        if s["id"] in pmap and pmap[s["id"]]["type"] == s["type"]:
            d = _diff_section(pmap[s["id"]], s)
            if d:
                secs[s["id"]] = d
        else:
            added.append(copy.deepcopy(s))
    if secs:
        patch["sections"] = secs
    if added:
        patch["added"] = added
    removed = [sid for sid in pmap if sid not in cids]
    if removed:
        patch["removed"] = removed
    kept_parent_order = [sid for sid in (s["id"] for s in parent["sections"]) if sid in cids]
    if [sid for sid in cids if sid in pmap] != kept_parent_order or added:
        patch["order"] = cids
    return patch


def _locked(locks: set[str], *keys: str) -> bool:
    return any(k in locks for k in keys)


def apply(parent: dict, patch: dict | None, locks=(), doc_kind: str | None = None) -> tuple[dict, list[dict]]:
    """Replay ``patch`` on ``parent`` (effective). Returns the effective specification
    and the list of patch entries that were not applied, each with its reason:
    ``locked`` (the parent forbids it) or ``orphan`` (it targets something the parent
    no longer has). Nothing is ever dropped silently: the editor shows this list."""
    doc_kind = doc_kind or parent["doc_kind"]
    locks = set(locks or ())
    patch = patch if isinstance(patch, dict) else {}
    eff = copy.deepcopy(parent)
    skipped: list[dict] = []
    if "theme_id" in patch:
        if _locked(locks, "theme"):
            skipped.append({"path": "theme", "reason": "locked"})
        else:
            eff["theme_id"] = patch["theme_id"]
    for k, v in (patch.get("doc") or {}).items():
        if _locked(locks, "doc", f"doc/{k}"):
            skipped.append({"path": f"doc/{k}", "reason": "locked"})
        elif k in eff["doc"]:
            eff["doc"][k] = v
    smap = {s["id"]: s for s in eff["sections"]}
    for sid, d in (patch.get("sections") or {}).items():
        sec = smap.get(sid)
        if sec is None:
            skipped.append({"path": f"section/{sid}", "reason": "orphan"})
            continue
        if _locked(locks, f"section/{sid}"):
            skipped.append({"path": f"section/{sid}", "reason": "locked"})
            continue
        if "enabled" in d:
            sec["enabled"] = bool(d["enabled"])
        for k, v in (d.get("params") or {}).items():
            if k in sec["params"]:
                sec["params"][k] = v
        for bid, bd in (d.get("blocks") or {}).items():
            if bid not in sec["blocks"]:
                skipped.append({"path": f"section/{sid}/block/{bid}", "reason": "orphan"})
                continue
            if _locked(locks, f"section/{sid}/block/{bid}"):
                skipped.append({"path": f"section/{sid}/block/{bid}", "reason": "locked"})
                continue
            if "enabled" in bd:
                sec["blocks"][bid]["enabled"] = bool(bd["enabled"])
            for k, v in (bd.get("params") or {}).items():
                if k in sec["blocks"][bid]["params"]:
                    sec["blocks"][bid]["params"][k] = v
        if "items" in d and sec["type"] == "custom":
            sec["items"] = copy.deepcopy(d["items"])
    for sid in patch.get("removed") or []:
        if sid not in smap:
            skipped.append({"path": f"section/{sid}", "reason": "orphan"})
        elif _locked(locks, f"section/{sid}"):
            skipped.append({"path": f"section/{sid}", "reason": "locked"})
        else:
            eff["sections"] = [s for s in eff["sections"] if s["id"] != sid]
    added = [s for s in (patch.get("added") or []) if isinstance(s, dict)]
    if added and _locked(locks, "add"):
        skipped += [{"path": f"section/{s.get('id')}", "reason": "locked"} for s in added]
        added = []
    have = {s["id"] for s in eff["sections"]}
    for s in added:
        if s.get("id") in have:
            skipped.append({"path": f"section/{s.get('id')}", "reason": "orphan"})
            continue
        eff["sections"].append(copy.deepcopy(s))
        have.add(s.get("id"))
    order = patch.get("order")
    if isinstance(order, list):
        if _locked(locks, "order"):
            skipped.append({"path": "order", "reason": "locked"})
        else:
            rank = {sid: i for i, sid in enumerate(order)}
            # Sections the patch does not know (added to the parent since) keep their
            # place relative to each other, after those it orders.
            eff["sections"].sort(key=lambda s: rank.get(s["id"], len(rank) + 1))
    return normalize(eff, doc_kind), skipped


def lock_paths(spec: dict) -> list[str]:
    """Every path that can be locked in this specification, for the editor."""
    out = ["theme", "doc", "order", "add"]
    for s in spec["sections"]:
        out.append(f"section/{s['id']}")
        out += [f"section/{s['id']}/block/{b}" for b in s["blocks"]]
    return out


def clean_locks(raw, spec: dict) -> list[str]:
    allowed = set(lock_paths(spec))
    return sorted({str(x) for x in (raw or []) if str(x) in allowed})


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------
_TOKEN = re.compile(r"\{([a-z]+)\}")


def fill(text: str, values: dict) -> str:
    """Replace the known ``{token}`` fields; anything else stays as typed."""
    def sub(m):
        k = m.group(1)
        return str(values.get(k, "")) if k in TOKENS else m.group(0)
    return _TOKEN.sub(sub, text or "")


# --------------------------------------------------------------------------
# Helpers for the renderers
# --------------------------------------------------------------------------
def block_on(sec: dict | None, bid: str) -> bool:
    """Is this block of the section switched on (True without a section)."""
    if not sec:
        return True
    b = (sec.get("blocks") or {}).get(bid)
    return True if b is None else bool(b.get("enabled", True))


def bparam(sec: dict | None, bid: str, key: str, default=None):
    """A block parameter, or ``default``."""
    if not sec:
        return default
    b = (sec.get("blocks") or {}).get(bid) or {}
    return (b.get("params") or {}).get(key, default)


def sparam(sec: dict | None, key: str, default=None):
    """A section parameter, or ``default``."""
    if not sec:
        return default
    return (sec.get("params") or {}).get(key, default)
