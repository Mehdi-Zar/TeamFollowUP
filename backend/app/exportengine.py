"""Studio des exports: build a PowerPoint document from a template specification.

The engine walks the sections of an effective specification (see ``exportspec``)
and hands each one to the renderer that owns it: the report family (summary,
squad slides, attention points, roadmap) to ``reportpptx``, the dependencies and
initiatives to theirs, the steerco one-pager to ``routers.steerco``, the org chart
to ``orgrender``, and the generic sections (cover, free text, free layout,
imported slide) to ``exportblocks``. Every renderer draws on the same deck.

The engine is database-free: what it needs comes in a :class:`Context`, whose data
providers are built by the export endpoints with exactly the scope and the rights
they already apply. A section whose data is not available is skipped and reported.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from . import exportblocks, pptxtpl
from .exportspec import DOC_DATA, SECTION_TYPES, WIDGETS, fill, sparam

DOC_LABELS = {
    "fr": {"dashboard": "Tableau de bord", "weekly": "Rapport hebdomadaire", "roadmap": "Roadmap",
           "dependencies": "Dépendances", "initiatives": "Initiatives", "steerco": "Steerco",
           "org": "Organigramme"},
    "en": {"dashboard": "Dashboard", "weekly": "Weekly report", "roadmap": "Roadmap",
           "dependencies": "Dependencies", "initiatives": "Initiatives", "steerco": "Steerco",
           "org": "Org chart"},
}

WIDGET_LABELS = {
    "fr": {"no_data": "Pas de donnée pour ce bloc dans ce document"},
    "en": {"no_data": "No data for this block in this document"},
}


@dataclass
class Context:
    """Everything a render needs besides the specification."""
    doc_kind: str
    lang: str = "fr"
    scope_name: str = ""
    year: int | None = None
    app_name: str = ""
    period: str = ""
    # Data providers, called at most once each: report -> dict (build_report_data),
    # dependencies -> dict, initiatives -> dict, steerco -> (platforms, period, L),
    # org -> (roots, scope_name).
    providers: dict[str, Callable[[], object]] = field(default_factory=dict)
    theme: dict = field(default_factory=dict)          # palette, font_scale, font
    master: bytes | None = None                       # the .pptx whose masters to use
    asset: Callable[[int], bytes | None] = lambda _id: None
    # The variant of one squad's (or platform's) slide, when its own template has one.
    variant: Callable[[str, dict], dict | None] = lambda _kind, _entity: None
    now: object = None
    warnings: list[dict] = field(default_factory=list)
    _cache: dict = field(default_factory=dict)

    def data(self, family: str):
        if family not in self._cache:
            fn = self.providers.get(family)
            self._cache[family] = fn() if fn else None
        return self._cache[family]

    def warn(self, kind: str, section: str = "", **extra) -> None:
        self.warnings.append({"kind": kind, "section": section, **extra})


def _values(ctx: Context) -> dict:
    """The ``{fields}`` a template's text can use."""
    from datetime import datetime, timezone
    from .reportcommon import fmt_date
    now = ctx.now or datetime.now(timezone.utc)
    lang = "en" if ctx.lang == "en" else "fr"
    rep = ctx._cache.get("report") or {}
    version = ""
    if rep.get("as_of"):
        version = fmt_date(rep["as_of"], lang)
    return {"doc": DOC_LABELS[lang].get(ctx.doc_kind, ctx.doc_kind), "scope": ctx.scope_name,
            "year": ctx.year or "", "date": fmt_date(now.date() if hasattr(now, "date") else now, lang),
            "app": ctx.app_name, "period": ctx.period, "version": version,
            "squad": "", "leader": "", "platform": "", "page": ""}


def filename(spec: dict, ctx: Context) -> str:
    """The document's file name, from the template's pattern."""
    raw = fill(spec["doc"].get("filename") or "{doc}_{scope}_{date}", _values(ctx))
    flat = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    flat = re.sub(r"[^A-Za-z0-9._-]+", "_", flat).strip("._") or ctx.doc_kind
    return flat[:120] + ".pptx"


def render(spec: dict, ctx: Context) -> bytes:
    """The PowerPoint document of ``spec`` on ``ctx``'s data, theme and master."""
    pptxtpl.use(ctx.master)
    pptxtpl.use_theme(ctx.theme)
    try:
        prs = pptxtpl.new_deck()
        _build(prs, spec, ctx)
        return pptxtpl.save_deck(prs)
    finally:
        pptxtpl.use_theme(None)


def build_presentation(spec: dict, ctx: Context):
    """The python-pptx presentation itself (the preview reads it without saving)."""
    pptxtpl.use(ctx.master)
    pptxtpl.use_theme(ctx.theme)
    prs = pptxtpl.new_deck()
    _build(prs, spec, ctx)
    pptxtpl.apply_font(prs, pptxtpl.font_name())
    return prs


def _build(prs, spec: dict, ctx: Context) -> None:
    decks: dict[str, dict] = {}
    values = _values(ctx)
    lang = "en" if ctx.lang == "en" else "fr"

    def deck(kind: str):
        """The section drawers of a family, created on first use, on this deck."""
        if kind in decks:
            return decks[kind]
        d = None
        if kind == "report":
            data = ctx.data("report")
            if data is not None:
                from .reportpptx import report_deck
                d = report_deck(prs, data)
        elif kind == "roadmap":
            data = ctx.data("report")
            if data is not None:
                from .reportpptx import roadmap_deck
                d = roadmap_deck(prs, data)
        elif kind == "dependencies":
            data = ctx.data("dependencies")
            if data is not None:
                from .reportpptx import dependencies_deck
                d = dependencies_deck(prs, data)
        elif kind == "initiatives":
            data = ctx.data("initiatives")
            if data is not None:
                from .reportpptx import initiatives_deck
                d = initiatives_deck(prs, data, lang=lang)
        elif kind == "steerco":
            got = ctx.data("steerco")
            if got is not None:
                from .routers.steerco import steerco_deck
                platforms, period, L = got
                d = steerco_deck(prs, platforms, period, L)
        elif kind == "org":
            got = ctx.data("org")
            if got is not None:
                from .orgrender import org_deck
                roots, scope = got
                d = org_deck(prs, roots, scope, lang=lang)
        decks[kind] = d
        return d

    family_of = {"summary": "report", "squad": "report", "attention": "report", "roadmap": "roadmap",
                 "dependencies": "dependencies", "initiatives": "initiatives",
                 "platform": "steerco", "org": "org"}

    for sec in spec["sections"]:
        if not sec.get("enabled", True):
            continue
        stype = sec["type"]
        if stype in family_of:
            d = deck(family_of[stype])
            if d is None:
                ctx.warn("no_data", sec["id"])
                continue
            if stype == "squad" and sparam(sec, "use_squad_variant", False):
                d["squad"](sec, variant=lambda r: ctx.variant("squad", r))
            elif stype == "platform":
                d["platform"](sec, variant=(lambda p: ctx.variant("platform", p))
                              if sparam(sec, "use_platform_variant", False) else None)
            else:
                d[stype](sec)
        elif stype == "cover":
            p = sec["params"]
            img = ctx.asset(p["image"]) if p.get("image") else None
            exportblocks.cover_slide(prs, p, values, img)
        elif stype == "text":
            exportblocks.text_slide(prs, sec["params"], values)
        elif stype == "imported":
            p = sec["params"]
            blob = ctx.asset(p["asset"]) if p.get("asset") else None
            if not blob:
                ctx.warn("imported_missing", sec["id"])
                continue
            _slide, warns = exportblocks.import_slide(prs, blob, p.get("slide") or 1, values)
            for w in warns:
                ctx.warn(w, sec["id"])
        elif stype == "custom":
            _custom(prs, sec, ctx, deck, values, lang)
    rep = decks.get("report")
    if rep:
        rep["finish"]()
    doc = spec.get("doc") or {}
    if doc.get("footer") or doc.get("page_numbers"):
        exportblocks.footer(prs, doc.get("footer") or "", bool(doc.get("page_numbers")), values)


def _custom(prs, sec: dict, ctx: Context, deck, values: dict, lang: str) -> None:
    """A free layout: once, once per squad, or once per platform."""
    from .reportpptx import select_squads
    repeat = sparam(sec, "repeat", "once")
    fam = DOC_DATA.get(ctx.doc_kind)
    no_data = WIDGET_LABELS[lang]["no_data"]

    def draw(entity=None, kind=None):
        vals = dict(values)
        if kind == "squad":
            vals.update(squad=entity.get("name") or "", leader=entity.get("leader") or "")
        elif kind == "platform":
            vals.update(platform=entity.get("squad_name") or "")

        def widget(slide, item, x, y, w, h):
            name, params = item["widget"], item.get("params") or {}
            need = WIDGETS[name]["needs"]
            if name == "text":
                exportblocks.widget_text(slide, params, vals, x, y, w, h)
                return
            if name == "image":
                blob = ctx.asset(params["asset"]) if params.get("asset") else None
                if blob:
                    exportblocks.picture_in(slide, blob, x, y, w, h)
                else:
                    exportblocks.widget_placeholder(slide, no_data, x, y, w, h)
                return
            from pptx.util import Inches
            if need == "report" and name == "roadmap":
                d = deck("roadmap")
                if d:
                    d["parts"]["roadmap"](slide, x, y, w, h, params)
                    return
            elif need in ("report", "squad"):
                d = deck("report")
                if d:
                    parts = d["parts"]
                    if name == "kpi_tiles":
                        parts["kpi_tiles"](slide, Inches(x), Inches(y), Inches(w), Inches(min(h, 1.3)),
                                           params.get("items"))
                        return
                    if name == "squad_table":
                        parts["squad_table"](slide, x, y, w, h, params)
                        return
                    if name in ("attention_list", "tribe_otds"):
                        parts[name](slide, "attention" if name == "attention_list" else "tribe_otds",
                                    x, y, w, h)
                        return
                    if entity is not None and kind == "squad":
                        if name == "squad_header":
                            parts["squad_header"](slide, entity, x, y, w, min(h, 0.74))
                        elif name == "squad_mood":
                            parts["squad_mood"](slide, entity, x, y + (0.14 if h > 0.9 else 0))
                        elif name == "squad_timeline":
                            parts["squad_timeline"](slide, entity, x, y, w, h)
                        elif name == "squad_key_messages":
                            parts["squad_key_messages"](slide, entity, x, y, w, h)
                        elif name == "squad_kpis":
                            parts["squad_kpis"](slide, entity, x, y, w, h)
                        elif name == "squad_budget":
                            parts["squad_budget"](slide, entity, x, y, w, h)
                        return
            elif need == "platform" and entity is not None:
                d = deck("steerco")
                if d:
                    d["parts"][name](slide, entity, x, y, w, h)
                    return
            exportblocks.widget_placeholder(slide, no_data, x, y, w, h)

        exportblocks.grid_slide(prs, sec, vals, widget)

    if repeat == "per_squad" and fam == "report":
        data = ctx.data("report")
        if data is None:
            ctx.warn("no_data", sec["id"])
            return
        rows = [r for blk in data["tribes"] for r in blk["squads"]]
        for r in select_squads(rows, sec):
            draw(r, "squad")
    elif repeat == "per_platform" and fam == "steerco":
        got = ctx.data("steerco")
        if got is None:
            ctx.warn("no_data", sec["id"])
            return
        for p in got[0]:
            draw(p, "platform")
    else:
        draw()


def section_types_with_data() -> dict[str, str | None]:
    """Section type -> data family (None for the generic ones)."""
    return {k: v["data"] for k, v in SECTION_TYPES.items()}
