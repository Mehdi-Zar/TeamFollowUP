"""Customer Success as a document: the projects of a tribe, as on screen (docs/37).

One data set (:func:`build_cs_list`) drawn twice: as an HTML page (the in-app
preview, and the JPG made from it) and as a PowerPoint section drawer
(:func:`cs_deck`) that the export engine places in a deck, with the tribe's
template, master and theme like every other document (``doc_kind`` "cs").

Every amount is the net price, after the discount. The figures on top are the four the screen shows by default: open projects,
blocked ones, the price still to invoice and the price waiting for its payment.
The table keeps one line per project, the blocked ones first, then the open
ones by stage, the delivered and closed ones last.
"""
from __future__ import annotations

import html
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from . import csconfig
from .models import Tribe, User

L = {
    "fr": {
        "title": "Customer Success", "generated": "Généré le {d}", "none": "Aucun projet dans ce périmètre.",
        "suite": " (suite)",
        "k_open": "Projets ouverts", "k_blocked": "Bloqués", "k_todo": "À facturer", "k_invoiced": "En attente de paiement",
        "h_project": "Projet", "h_requesters": "Demandeurs", "h_stage": "Étape", "h_status": "Statut",
        "h_follow": "Blocage ou prochaine action", "h_contact": "Dernier échange", "h_price": "Prix",
        "blocked": "Bloqué : {label}",
        "health": {"green": "En bonne voie", "amber": "À surveiller", "red": "En difficulté"},
        "billing": {"todo": "à facturer", "invoiced": "facturé", "paid": "payé"},
    },
    "en": {
        "title": "Customer Success", "generated": "Generated on {d}", "none": "No project in this scope.",
        "suite": " (continued)",
        "k_open": "Open projects", "k_blocked": "Blocked", "k_todo": "Not invoiced yet", "k_invoiced": "Awaiting payment",
        "h_project": "Project", "h_requesters": "Requesters", "h_stage": "Stage", "h_status": "Status",
        "h_follow": "Blocker or next action", "h_contact": "Last contact", "h_price": "Price",
        "blocked": "Blocked: {label}",
        "health": {"green": "On track", "amber": "At risk", "red": "In trouble"},
        "billing": {"todo": "not invoiced yet", "invoiced": "awaiting payment", "paid": "paid"},
    },
}

_TONE = {"green": "#027A48", "amber": "#B54708", "red": "#B42318"}


def _money(v: float, lang: str) -> str:
    n = f"{v:,.0f}"
    return f"{n.replace(',', ' ')} €" if lang == "fr" else f"€{n}"


def build_cs_list(db: Session, user: User, tid: int, lang: str = "fr", *, closed: bool = True) -> dict:
    """The tribe's projects the caller sees, ready to draw. ``closed=False`` leaves
    out the delivered and closed ones."""
    from .reportcommon import fmt_date
    from .routers.cs import BILLING, _visible_projects, facts, _today
    lang = "en" if lang == "en" else "fr"
    T = L[lang]
    cfg = csconfig.get(db, tid)
    today = _today()
    order = {s["key"]: i for i, s in enumerate(cfg["stages"])}
    labels = {s["key"]: csconfig.stage_label(s, lang) for s in cfg["stages"]}
    rows, totals = [], {b: 0.0 for b in BILLING}
    n_open = n_blocked = 0
    for p in _visible_projects(db, user, tid):
        f = facts(p, cfg, today)
        if p.net_amount is not None:
            totals[p.billing] = totals.get(p.billing, 0.0) + float(p.net_amount)
        if not f["closed"]:
            n_open += 1
        if f["blocked"]:
            n_blocked += 1
        if f["closed"] and not closed:
            continue
        if f["blocker"]:
            follow, alert = T["blocked"].format(label=f["blocker"]["label"]), "red"
        elif f["next_action"]:
            a = f["next_action"]
            follow = a["label"] + (f", {fmt_date(a['due'], lang)}" if a["due"] else "")
            alert = "red" if a["overdue"] else None
        else:
            follow, alert = "", None
        rows.append({
            "title": p.title, "client": p.client or "", "requesters": p.requesters or "",
            "stage": labels.get(p.stage, p.stage), "closed": f["closed"],
            "health": p.health, "health_label": T["health"].get(p.health or "", ""),
            "follow": follow, "follow_alert": alert,
            "last_contact": fmt_date(f["last_contact"], lang) if f["last_contact"] else "",
            "stale": f["stale"],
            "price": _money(float(p.net_amount), lang) if p.net_amount is not None else "",
            "billing": p.billing, "billing_label": T["billing"].get(p.billing, p.billing),
            "_rank": (0 if f["blocked"] else 2 if f["closed"] else 1, order.get(p.stage, 99), p.title.lower()),
        })
    rows.sort(key=lambda r: r.pop("_rank"))
    tribe = db.get(Tribe, tid)
    kpis = [
        {"label": T["k_open"], "value": str(n_open), "tone": None},
        {"label": T["k_blocked"], "value": str(n_blocked), "tone": "red" if n_blocked else None},
        {"label": T["k_todo"], "value": _money(totals.get("todo", 0.0), lang), "tone": "amber" if totals.get("todo") else None},
        {"label": T["k_invoiced"], "value": _money(totals.get("invoiced", 0.0), lang),
         "tone": "amber" if totals.get("invoiced") else None},
    ]
    return {"lang": lang, "scope_name": tribe.name if tribe else "", "year": today.year,
            "generated": datetime.now(timezone.utc).isoformat(), "kpis": kpis, "rows": rows}


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

_CSS = """<style>
body{margin:0;background:#F5F7FA}
.cs-doc{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111827;max-width:1120px;
  margin:0 auto;padding:24px;line-height:1.4;background:#fff}
.cs-doc h1{font-size:22px;margin:0 0 4px}
.cs-doc .sub{color:#6b7280;font-size:13px}
.cs-doc .kpis{display:flex;gap:10px;margin:16px 0}
.cs-doc .kpi{flex:1;min-width:0;border:1px solid #e5e7eb;border-radius:10px;padding:10px 14px}
.cs-doc .kpi .v{font-size:20px;font-weight:700;color:#1E2761}
.cs-doc .kpi .l{font-size:12px;color:#6b7280}
.cs-doc table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px}
.cs-doc th{text-align:left;color:#6b7280;font-weight:600;font-size:12px;border-bottom:1px solid #e5e7eb;padding:8px 6px}
.cs-doc td{border-bottom:1px solid #e5e7eb;padding:9px 6px;vertical-align:top;overflow-wrap:anywhere}
.cs-doc td .c{color:#6b7280;font-size:12px}
.cs-doc tr.closed td{color:#9ca3af}
.cs-doc .r{text-align:right}
</style>"""


def render_cs_html(data: dict) -> str:
    """The projects as a standalone HTML page."""
    from .reportcommon import fmt_datetime
    e = html.escape
    lang = data["lang"]
    T = L[lang]
    parts = [f'<h1>{e(T["title"])} | {e(data["scope_name"])}</h1>',
             f'<div class="sub">{e(T["generated"].format(d=fmt_datetime(data["generated"], lang)))}</div>',
             '<div class="kpis">']
    for k in data["kpis"]:
        style = f' style="color:{_TONE[k["tone"]]}"' if k["tone"] else ""
        parts.append(f'<div class="kpi"><div class="v"{style}>{e(k["value"])}</div><div class="l">{e(k["label"])}</div></div>')
    parts.append('</div>')
    if not data["rows"]:
        parts.append(f'<p class="sub">{e(T["none"])}</p>')
    else:
        parts.append('<table><colgroup><col style="width:24%"><col style="width:14%"><col style="width:11%">'
                     '<col style="width:11%"><col style="width:22%"><col style="width:9%"><col style="width:9%">'
                     '</colgroup><thead><tr>'
                     + "".join(f'<th{" class=r" if h == "h_price" else ""}>{e(T[h])}</th>' for h in
                               ("h_project", "h_requesters", "h_stage", "h_status", "h_follow", "h_contact", "h_price"))
                     + '</tr></thead><tbody>')
        for r in data["rows"]:
            hl = (f'<span style="color:{_TONE[r["health"]]}">{e(r["health_label"])}</span>'
                  if r["health"] in _TONE else "-")
            fl = (f'<span style="color:{_TONE[r["follow_alert"]]}">{e(r["follow"])}</span>'
                  if r["follow_alert"] else e(r["follow"] or "-"))
            ct = (f'<span style="color:{_TONE["amber"]}">{e(r["last_contact"])}</span>'
                  if r["stale"] and r["last_contact"] else e(r["last_contact"] or "-"))
            pr = "-"
            if r["price"]:
                tone = "" if r["billing"] == "paid" else f' style="color:{_TONE["amber"]}"'
                pr = f'<span{tone}>{e(r["price"])}</span><div class="c">{e(r["billing_label"])}</div>'
            client = f'<div class="c">{e(r["client"])}</div>' if r["client"] else ""
            parts.append(f'<tr{" class=closed" if r["closed"] else ""}><td><strong>{e(r["title"])}</strong>{client}</td>'
                         f'<td>{e(r["requesters"] or "-")}</td><td>{e(r["stage"])}</td><td>{hl}</td>'
                         f'<td>{fl}</td><td>{ct}</td><td class="r">{pr}</td></tr>')
        parts.append('</tbody></table>')
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            f'<title>{e(T["title"])} | {e(data["scope_name"])}</title>{_CSS}</head>'
            f'<body><div class="cs-doc">{"".join(parts)}</div></body></html>')


# --------------------------------------------------------------------------
# PowerPoint
# --------------------------------------------------------------------------

def cs_deck(prs, data: dict, *, lang: str = "fr") -> dict:
    """The Customer Success section drawer bound to one deck: a band, the four
    figures on the first slide, then the projects in a table across slides."""
    from . import pptxtpl
    from .exportspec import block_on, sparam
    from .reportcommon import fmt_datetime
    from .reportpptx import _BRAND, _cut, _fs, _pptx_toolkit
    Presentation, Inches, Pt, Emu, RGBColor, PP_ALIGN, MSO_ANCHOR, MSO_SHAPE = _pptx_toolkit()

    def rgb(h):
        return RGBColor.from_string(h.lstrip("#").upper())

    B = {k: rgb(v) for k, v in pptxtpl.palette(_BRAND, pptxtpl.BRAND_MAP).items()}
    tone = {"green": B["green"], "amber": B["orange"], "red": B["red"]}
    lang = "en" if lang == "en" else "fr"
    T = L[lang]
    margin = Inches(0.5)
    width = prs.slide_width - margin * 2
    keys = ("project", "requesters", "stage", "status", "follow", "contact", "price")
    frac = (0.24, 0.14, 0.11, 0.11, 0.22, 0.09, 0.09)
    heads = (T["h_project"], T["h_requesters"], T["h_stage"], T["h_status"], T["h_follow"], T["h_contact"], T["h_price"])

    def text(c, value, size, color, *, bold=False, align=PP_ALIGN.LEFT, fill=None, sub=None, sub_color=None):
        c.margin_left = Inches(0.06); c.margin_right = Inches(0.04); c.margin_top = Emu(0); c.margin_bottom = Emu(0)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        if fill is not None:
            c.fill.solid(); c.fill.fore_color.rgb = fill
        else:
            c.fill.background()
        c.text = value or " "
        p = c.text_frame.paragraphs[0]; p.alignment = align
        if p.runs:
            r = p.runs[0]; r.font.size = Pt(_fs(size)); r.font.bold = bold; r.font.color.rgb = color
        if sub:
            p2 = c.text_frame.add_paragraph(); p2.alignment = align
            r2 = p2.add_run(); r2.text = sub
            r2.font.size = Pt(_fs(size - 1.5)); r2.font.color.rgb = sub_color or B["muted"]

    def band(s, cont):
        head = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, Inches(1.05))
        head.fill.solid(); head.fill.fore_color.rgb = B["navy"]; head.line.fill.background(); head.shadow.inherit = False
        tf = head.text_frame; tf.margin_left = Inches(0.5); tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
        r = p.add_run(); r.text = f'{T["title"]} | {data["scope_name"]}' + (T["suite"] if cont else "")
        r.font.size = Pt(_fs(22)); r.font.bold = True; r.font.color.rgb = B["white"]
        p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.LEFT
        r2 = p2.add_run(); r2.text = T["generated"].format(d=fmt_datetime(data["generated"], lang))
        r2.font.size = Pt(_fs(11)); r2.font.color.rgb = rgb("#C7D2FE")

    def figures(s, top):
        n = len(data["kpis"])
        gap = Inches(0.15)
        w = int((width - gap * (n - 1)) / n)
        for i, k in enumerate(data["kpis"]):
            box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, margin + i * (w + gap), top, w, Inches(0.8))
            box.adjustments[0] = 0.12
            box.fill.solid(); box.fill.fore_color.rgb = B["card"]; box.line.color.rgb = B["line"]; box.shadow.inherit = False
            tf = box.text_frame; tf.margin_left = Inches(0.15); tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
            r = p.add_run(); r.text = k["value"]
            r.font.size = Pt(_fs(18)); r.font.bold = True; r.font.color.rgb = tone.get(k["tone"], B["navy"])
            p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.LEFT
            r2 = p2.add_run(); r2.text = k["label"]
            r2.font.size = Pt(_fs(10)); r2.font.color.rgb = B["muted"]

    def table(s, rows, top):
        tbl = s.shapes.add_table(max(2, len(rows) + 1), len(keys), margin, top, Emu(int(width)),
                                 Inches(0.34 + 0.44 * max(1, len(rows)))).table
        for ci, f in enumerate(frac):
            tbl.columns[ci].width = Emu(int(width * f))
        for ri in range(1, max(2, len(rows) + 1)):
            tbl.rows[ri].height = Inches(0.44)
        for ci, h in enumerate(heads):
            text(tbl.cell(0, ci), h, 10, B["white"], bold=True, fill=B["navy"],
                 align=PP_ALIGN.RIGHT if keys[ci] == "price" else PP_ALIGN.LEFT)
        if not rows:
            text(tbl.cell(1, 0), T["none"], 10, B["muted"])
            for ci in range(1, len(keys)):
                text(tbl.cell(1, ci), " ", 10, B["muted"])
        for ri, r in enumerate(rows, start=1):
            fill = B["zebra"] if ri % 2 == 0 else B["white"]
            ink = B["muted"] if r["closed"] else B["ink"]
            text(tbl.cell(ri, 0), _cut(r["title"], 40), 10, ink, bold=True, fill=fill, sub=_cut(r["client"], 40) or None)
            text(tbl.cell(ri, 1), _cut(r["requesters"] or "-", 44), 9, ink, fill=fill)
            text(tbl.cell(ri, 2), r["stage"], 9, ink, fill=fill)
            text(tbl.cell(ri, 3), r["health_label"] or "-", 9, tone.get(r["health"], ink), fill=fill)
            text(tbl.cell(ri, 4), _cut(r["follow"] or "-", 70), 9, tone.get(r["follow_alert"], ink), fill=fill)
            text(tbl.cell(ri, 5), r["last_contact"] or "-", 9, B["orange"] if r["stale"] else ink, fill=fill)
            text(tbl.cell(ri, 6), r["price"] or "-", 9, ink if r["billing"] == "paid" else B["orange"], fill=fill,
                 align=PP_ALIGN.RIGHT, sub=r["billing_label"] if r["price"] else None)

    def cs_section(sec):
        per = int(sparam(sec, "rows_per_slide", 10) or 10)
        rows = [r for r in data["rows"] if not (sparam(sec, "hide_closed", False) and r["closed"])]
        head_on = block_on(sec, "header")
        # The first slide carries the figures, so it holds a few lines less.
        first = max(3, per - 3)
        pages = [rows[:first]] + [rows[i:i + per] for i in range(first, len(rows), per)]
        for k, chunk in enumerate(pages):
            s = pptxtpl.add_slide(prs)
            top = Inches(1.3) if head_on else Inches(0.5)
            if head_on:
                band(s, k > 0)
            if k == 0:
                figures(s, top)
                top = top + Inches(1.0)
            table(s, chunk, top)

    return {"cs": cs_section, "parts": {}}
