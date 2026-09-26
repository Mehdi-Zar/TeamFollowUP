"""Org-chart export: a tribe's editable org tree rendered to a printable HTML page
and a single-slide PPTX, both laid out to fit one page. Mirrors the brand palette.

A node is {id, title, person_name, squad_id, squad_status, children:[...]}. Status
colours (derived squad health) are applied when a node maps to a squad.
"""
from __future__ import annotations

import html
import io

from . import pptxtpl
from .report import _pptx_toolkit

# Le titre de la slide suit le corps commun des decks: voir pptxtpl.FONT_SCALE.
_fs = pptxtpl.font_size

_NAVY = "#1E2761"
_INK = "#1F2937"
_MUTED = "#6B7280"
_LINE = "#CBD5E1"
_CARD = "#FFFFFF"
_STATUS = {"on_track": "#027A48", "at_risk": "#B54708", "blocked": "#B42318"}
_STATUS_BG = {"on_track": "#ECFDF3", "at_risk": "#FFFAEB", "blocked": "#FEF3F2"}

_T = {
    "fr": {"org": "Organigramme", "no_org": "Aucun élément à afficher.",
           "legend": "Bordure de couleur : santé de la squad rattachée",
           "on_track": "En cours", "at_risk": "À risque", "blocked": "Bloquée",
           "gen": "Généré le {d}"},
    "en": {"org": "Org chart", "no_org": "Nothing to display.",
           "legend": "Coloured border: health of the linked squad",
           "on_track": "On track", "at_risk": "At risk", "blocked": "Blocked",
           "gen": "Generated on {d}"},
}


def _lang(lang: str | None) -> str:
    """Normalize a language hint to a supported code ('en' or, by default, 'fr')."""
    return "en" if lang == "en" else "fr"


# ----- HTML --------------------------------------------------------------------

_ORG_CSS = """<style>
.org-doc{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1F2937;
  padding:24px;background:#fff}
.org-doc h1{font-size:22px;margin:0 0 2px}
.org-doc .sub{color:#6B7280;font-size:13px;margin-bottom:18px}
.org-tree,.org-tree ul{list-style:none;margin:0;padding:0}
.org-tree,.org-tree ul{display:flex;justify-content:center}
.org-tree li{display:flex;flex-direction:column;align-items:center;position:relative;padding:18px 8px 0}
/* connector up from each child to the horizontal bar */
.org-tree li::before{content:"";position:absolute;top:0;left:50%;width:1px;height:18px;background:#CBD5E1}
/* horizontal bar between siblings */
.org-tree li::after{content:"";position:absolute;top:0;left:0;right:0;height:1px;background:#CBD5E1}
.org-tree li:first-child::after{left:50%}
.org-tree li:last-child::after{right:50%}
.org-tree li:only-child::after{display:none}
.org-tree > li::before{display:none}
.org-node{border:1px solid #CBD5E1;border-radius:10px;background:#fff;padding:8px 12px;min-width:120px;
  max-width:190px;text-align:center;box-shadow:0 1px 2px rgba(16,24,40,.06)}
.org-node .t{font-weight:700;font-size:12.5px;line-height:1.25}
.org-node .p{color:#6B7280;font-size:11px;margin-top:2px}
.org-node.has-status{border-top-width:3px}
.org-children{margin-top:18px}
</style>"""


def _node_html(node: dict, e) -> str:
    """Recursively render one org node (and its children) as a nested <li>.

    A node bound to a squad is tinted with that squad's derived status colour.
    `e` is the HTML-escaper passed down to avoid re-importing it per call."""
    status = node.get("squad_status") if node.get("squad_id") else None
    cls = "org-node" + (" has-status" if status else "")
    style = ""
    if status in _STATUS:
        style = f' style="border-top-color:{_STATUS[status]};background:{_STATUS_BG[status]}"'
    person = f'<div class="p">{e(node["person_name"])}</div>' if node.get("person_name") else ""
    box = f'<div class="{cls}"{style}><div class="t">{e(node["title"])}</div>{person}</div>'
    kids = node.get("children") or []
    if not kids:
        return f"<li>{box}</li>"
    inner = "".join(_node_html(k, e) for k in kids)
    return f'<li>{box}<ul class="org-children">{inner}</ul></li>'


def render_org_html(roots: list[dict], scope_name: str, *, lang: str = "fr",
                    standalone: bool = True) -> str:
    """Render an org tree as a printable HTML page (CSS-drawn connectors between
    boxes). standalone wraps the fragment in a full <html> document."""
    e = html.escape
    lang = _lang(lang)
    title = _T[lang]["org"]
    body = [f'<div class="org-doc"><h1>{e(title)} | {e(scope_name)}</h1>',
            f'<div class="sub">{e(scope_name)}</div>']
    if not roots:
        body.append(f'<div class="sub">{e(_T[lang]["no_org"])}</div>')
    else:
        body.append('<ul class="org-tree">')
        body.append("".join(_node_html(r, e) for r in roots))
        body.append('</ul>')
    body.append('</div>')
    inner = _ORG_CSS + "".join(body)
    if not standalone:
        return inner
    return (f'<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">'
            f'<title>{e(title)} | {e(scope_name)}</title></head><body>{inner}</body></html>')


# ----- PPTX --------------------------------------------------------------------

def _layout(roots: list[dict], compact: bool = False) -> tuple[list[dict], int, int]:
    """Tidy top-down layout. Returns (placed_nodes, n_leaf_slots, max_depth).
    Each placed node gets x (leaf-slot centre, float) and depth (int).

    ``compact``: the leaves of one parent are stacked in a single column under it
    (``_stack`` = their rank) instead of taking one slot each. With twenty leaves
    side by side, each card was half an inch wide and every title read « Plate… »."""
    placed: list[dict] = []
    counter = {"leaf": 0}

    def walk(node: dict, depth: int) -> float:
        kids = node.get("children") or []
        node["_stack"] = None
        if compact and len(kids) > 1 and all(not (k.get("children") or []) for k in kids):
            x = counter["leaf"] + 0.5
            counter["leaf"] += 1
            for i, k in enumerate(kids):
                k["_x"], k["_depth"], k["_stack"] = x, depth + 1, i
                placed.append({"node": k, "x": x, "depth": depth + 1, "parent_x": None})
        elif not kids:
            x = counter["leaf"] + 0.5
            counter["leaf"] += 1
        else:
            xs = [walk(k, depth + 1) for k in kids]
            x = sum(xs) / len(xs)
        placed.append({"node": node, "x": x, "depth": depth,
                       "parent_x": None})  # parent_x filled by caller
        node["_x"] = x
        node["_depth"] = depth
        return x

    max_depth = 0

    def depth_of(node, d=0):
        nonlocal max_depth
        max_depth = max(max_depth, d)
        for k in (node.get("children") or []):
            depth_of(k, d + 1)

    for r in roots:
        walk(r, 0)
        depth_of(r, 0)
    return placed, max(1, counter["leaf"]), max_depth


def render_org_pptx(roots: list[dict], scope_name: str, *, lang: str = "fr") -> bytes:
    """Render the org tree as a single-slide PPTX.

    Uses _layout to assign each node a leaf-slot x and a depth, then scales box
    size / row height to fit everything on one 13.33x7.5in slide. Connectors are
    drawn first so the boxes sit on top; squad-bound boxes are status-coloured."""
    Presentation, Inches, Pt, Emu, RGBColor, PP_ALIGN, MSO_ANCHOR, MSO_SHAPE = _pptx_toolkit()
    from pptx.enum.shapes import MSO_CONNECTOR

    def rgb(h):
        return RGBColor.from_string(h.lstrip("#").upper())

    lang = _lang(lang)
    SLIDE_W, SLIDE_H = 13.333, 7.5
    prs = pptxtpl.new_presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    s = pptxtpl.add_slide(prs)

    # Header band
    head = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(SLIDE_W), Inches(0.9))
    head.fill.solid(); head.fill.fore_color.rgb = rgb(_NAVY); head.line.fill.background(); head.shadow.inherit = False
    tf = head.text_frame; tf.margin_left = Inches(0.5); tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; r = p.add_run(); r.text = f'{_T[lang]["org"]} | {scope_name}'
    r.font.size = Pt(_fs(22)); r.font.bold = True; r.font.color.rgb = rgb("#FFFFFF")

    placed, n_leaf, max_depth = _layout(roots)
    if n_leaf > 10:
        placed, n_leaf, max_depth = _layout(roots, compact=True)
    if not placed:
        # Une slide avec son seul titre se lisait comme un export rate.
        box = s.shapes.add_textbox(Inches(0.5), Inches(3.3), Inches(SLIDE_W - 1), Inches(0.6))
        pe = box.text_frame.paragraphs[0]; pe.alignment = PP_ALIGN.CENTER
        re_ = pe.add_run(); re_.text = _T[lang]["no_org"]
        re_.font.size = Pt(_fs(16)); re_.font.color.rgb = rgb(_MUTED)
        buf = io.BytesIO(); prs.save(buf); return buf.getvalue()

    # La legende et la date, en bas: une bordure verte ou orange ne s'explique
    # pas d'elle-meme, et une slide d'organigramme circule seule.
    from datetime import datetime, timezone
    from .reportcommon import fmt_datetime
    T = _T[lang]
    ly = 7.14
    lx = 0.4
    lg = s.shapes.add_textbox(Inches(lx), Inches(ly), Inches(4.2), Inches(0.22))
    lr = lg.text_frame.paragraphs[0].add_run(); lr.text = T["legend"]
    lr.font.size = Pt(9); lr.font.color.rgb = rgb(_MUTED)
    lx += 3.9
    for st in ("on_track", "at_risk", "blocked"):
        sw = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(lx), Inches(ly + 0.03),
                                Inches(0.26), Inches(0.15))
        sw.fill.solid(); sw.fill.fore_color.rgb = rgb(_STATUS_BG[st])
        sw.line.color.rgb = rgb(_STATUS[st]); sw.line.width = Pt(1.5); sw.shadow.inherit = False
        tb = s.shapes.add_textbox(Inches(lx + 0.32), Inches(ly), Inches(1.2), Inches(0.22))
        tr = tb.text_frame.paragraphs[0].add_run(); tr.text = T[st]
        tr.font.size = Pt(9); tr.font.color.rgb = rgb(_MUTED)
        lx += 0.4 + 0.075 * len(T[st]) + 0.3
    gb = s.shapes.add_textbox(Inches(SLIDE_W - 4.4), Inches(ly), Inches(4.0), Inches(0.22))
    gp = gb.text_frame.paragraphs[0]; gp.alignment = PP_ALIGN.RIGHT
    gr = gp.add_run(); gr.text = T["gen"].format(d=fmt_datetime(datetime.now(timezone.utc), lang))
    gr.font.size = Pt(9); gr.font.color.rgb = rgb(_MUTED)

    top, bottom = 1.2, 7.0
    left_m, right_m = 0.4, 0.4
    avail_w = SLIDE_W - left_m - right_m
    col_w = avail_w / n_leaf                       # width per leaf slot
    row_h = (bottom - top) / (max_depth + 1)
    if any(it["node"].get("_stack") is not None for it in placed):
        # The rows above a stack give it their spare height.
        row_h = min(row_h, 1.3)
    # Une carte ne depasse jamais son emplacement. Un plancher de 1,1 pouce la
    # gardait large quand la tribu compte quatorze feuilles: l'emplacement n'en
    # fait plus que 0,9, et les cartes se chevauchaient deux a deux, chacune
    # mordant sur sa voisine.
    # A card is as wide as the gap to its nearest neighbour on the same row
    # allows: the root, alone on its row, no longer shrinks to a leaf's width.
    xs_by_depth: dict[int, set] = {}
    for it in placed:
        xs_by_depth.setdefault(it["depth"], set()).add(it["x"])

    def width_at(d: int) -> float:
        xs = sorted(xs_by_depth.get(d, ()))
        gap = min((b - a for a, b in zip(xs, xs[1:])), default=n_leaf)
        return min(2.2, gap * col_w * 0.92)

    box_h = min(0.8, max(0.5, row_h * 0.62))
    # Stacked leaves share the space from their row down to the bottom.
    max_stack = 1 + max((it["node"].get("_stack") or 0 for it in placed), default=0)
    stack_top = {it["depth"] for it in placed if it["node"].get("_stack") is not None}
    if max_stack > 1:
        d0 = min(stack_top)
        room = bottom - (top + d0 * row_h + 0.1)
        stack_h = min(box_h, room / max_stack - 0.08)
    else:
        stack_h = box_h

    # Le texte suit la carte. PowerPoint passe un titre a la ligne, mais il ne coupe
    # pas un mot: « Management » plus large que sa carte en sortait des deux cotes et
    # s'ecrivait sur la voisine. On descend donc d'un demi-point tant que le mot le
    # plus long ne rentre pas, et on coupe en dernier ressort plutot que de deborder.
    CHAR_W = 0.0080            # largeur d'un caractere gras, par point de corps

    def fit_size(text: str, base: float, d: int, floor: float = 8.0) -> float:
        inner = width_at(d) - 0.12      # la largeur utile, marges deduites
        longest = max((len(w) for w in (text or "").split()), default=1)
        size = base
        while size > floor and longest * CHAR_W * size > inner:
            size -= 0.5
        return size

    def fit_text(text: str, size: float, lines: int, d: int) -> str:
        """Le titre entier tient sur ses lignes, coupe a la fin avec « … » et non
        plus mot par mot (« Platefo… de moderni… » ne se lisait plus)."""
        chars = max(3, int((width_at(d) - 0.12) / (CHAR_W * size)))
        words = (text or "").split()
        out, cur, used = [], "", 0
        for w in words:
            if len(w) > chars:
                w = w[:max(1, chars - 1)] + "…"
            cand = f"{cur} {w}" if cur else w
            if len(cand) <= chars:
                cur = cand
                continue
            out.append(cur)
            used += 1
            cur = w
            if used >= lines:
                break
        else:
            out.append(cur)
            return " ".join(x for x in out if x)
        kept = " ".join(x for x in out if x).rstrip(" ,;:.")
        return (kept[:-1] if kept.endswith("…") else kept) + "…"

    def fit_person(name: str, size: float, d: int) -> str:
        """Un nom sur une ligne: entier s'il tient, sinon l'initiale du prenom et
        le nom (« C. Dubois »), et non plus le seul prenom (« Camille… »)."""
        chars = max(3, int((width_at(d) - 0.12) / (CHAR_W * size)))
        name = (name or "").strip()
        if len(name) <= chars:
            return name
        parts = name.split()
        if len(parts) > 1:
            short = f"{parts[0][0]}. {' '.join(parts[1:])}"
            if len(short) <= chars:
                return short
            return fit_text(short, size, 1, d)
        return fit_text(name, size, 1, d)

    # Un meme corps pour toutes les cartes d'un meme niveau: d'une carte a sa
    # voisine, le titre changeait de taille selon la longueur de ses mots.
    level_fs1: dict[int, float] = {}
    level_fs2: dict[int, float] = {}
    for item in placed:
        n_, d_ = item["node"], item["depth"]
        level_fs1[d_] = min(level_fs1.get(d_, 99), fit_size(n_["title"], 10.5 if max_depth <= 3 else 9, d_))
        if n_.get("person_name"):
            level_fs2[d_] = min(level_fs2.get(d_, 99), fit_size(n_["person_name"], 8.5, d_))

    def cx(x):  # leaf-slot centre → inches
        return left_m + (x / n_leaf) * avail_w
    def cy(depth, stack=None):
        if stack is not None:
            return top + depth * row_h + 0.1 + stack * (stack_h + 0.08)
        return top + depth * row_h + (row_h - box_h) / 2

    # Connectors first (so boxes sit on top).
    def line(x1, y1, x2, y2):
        cn = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                    Inches(x1), Inches(y1), Inches(x2), Inches(y2))
        cn.line.color.rgb = rgb(_LINE); cn.line.width = Pt(1)
        # Sans ombre: PowerPoint en pose une par defaut, qui doublait chaque trait.
        cn.shadow.inherit = False

    def draw_connectors(node):
        kids = node.get("children") or []
        if kids and kids[0].get("_stack") is not None:
            # A stack: one spine down the left edge, a tick into each card.
            x1, y1 = cx(node["_x"]), cy(node["_depth"], node.get("_stack")) + box_h
            sx = cx(kids[0]["_x"]) - width_at(kids[0]["_depth"]) / 2 - 0.06
            first_y = cy(kids[0]["_depth"], 0)
            line(x1, y1, x1, first_y - 0.05)
            line(sx, first_y - 0.05, x1, first_y - 0.05)
            last_mid = cy(kids[-1]["_depth"], kids[-1]["_stack"]) + stack_h / 2
            line(sx, first_y - 0.05, sx, last_mid)
            for k in kids:
                ym = cy(k["_depth"], k["_stack"]) + stack_h / 2
                line(sx, ym, sx + 0.06, ym)
            return
        if not kids:
            return
        # Des traits a angle droit (un tronc, une barre, une descente par
        # enfant), comme un organigramme se dessine: l'eventail de diagonales
        # partait d'un seul point et se croisait sous le parent.
        x1, y1 = cx(node["_x"]), cy(node["_depth"], node.get("_stack")) + box_h
        top_y = min(cy(k["_depth"], k.get("_stack")) for k in kids)
        ym = (y1 + top_y) / 2
        xs = [cx(k["_x"]) for k in kids]
        line(x1, y1, x1, ym)
        if len(kids) > 1 or abs(xs[0] - x1) > 0.004:
            line(min(xs + [x1]), ym, max(xs + [x1]), ym)
        for k, x2 in zip(kids, xs):
            line(x2, ym, x2, cy(k["_depth"], k.get("_stack")))
            draw_connectors(k)
    for r0 in roots:
        draw_connectors(r0)

    for item in placed:
        node = item["node"]
        stacked = node.get("_stack") is not None
        bh_ = stack_h if stacked else box_h
        box_w = width_at(item["depth"])
        x, depth = cx(item["x"]) - box_w / 2, cy(item["depth"], node.get("_stack"))
        status = node.get("squad_status") if node.get("squad_id") else None
        box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(depth),
                                 Inches(box_w), Inches(bh_))
        box.fill.solid()
        box.fill.fore_color.rgb = rgb(_STATUS_BG[status]) if status in _STATUS_BG else rgb(_CARD)
        box.line.color.rgb = rgb(_STATUS[status]) if status in _STATUS else rgb(_LINE)
        box.line.width = Pt(2 if status in _STATUS else 1)
        box.shadow.inherit = False
        try:
            box.adjustments[0] = 0.12
        except Exception:
            pass
        tf = box.text_frame; tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.05)
        tf.margin_top = tf.margin_bottom = Emu(0)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        # Le texte d'une carte est calibre sur la largeur de la carte, elle-meme
        # donnee par le nombre de branches: il ne suit donc pas FONT_SCALE, qui ne
        # ferait que pousser les noms hors de leur cadre sans rien rendre plus
        # lisible. Seul le titre de la slide, qui a toute la largeur pour lui,
        # profite de l'agrandissement.
        fs1 = level_fs1[item["depth"]]
        lines1 = max(1, int((bh_ - (0.16 if node.get("person_name") else 0.02)) / (fs1 * 1.2 / 72)))
        r1 = p.add_run(); r1.text = fit_text(node["title"], fs1, lines1, item["depth"])
        r1.font.size = Pt(fs1); r1.font.bold = True; r1.font.color.rgb = rgb(_INK)
        if node.get("person_name"):
            fs2 = level_fs2.get(item["depth"], 8.5)
            p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
            r2 = p2.add_run(); r2.text = fit_person(node["person_name"], fs2, item["depth"])
            r2.font.size = Pt(fs2); r2.font.color.rgb = rgb(_MUTED)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
