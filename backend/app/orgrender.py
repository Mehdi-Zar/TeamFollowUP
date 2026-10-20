"""Org-chart export: a tribe's editable org tree rendered to a printable HTML page
and a PPTX: one slide while its cards read, an overview and one slide per branch
beyond. Mirrors the brand palette.

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
#
# Un organigramme tient sur une slide tant que ses cartes se lisent. Au-dela, il
# passe sur plusieurs: une vue d'ensemble (la racine et ses branches, chacune avec
# le nombre de ses elements), puis une slide par branche, coupee en « (suite) » si
# une branche est elle-meme trop large. Une slide unique a quarante equipes
# donnait des cartes d'un demi-pouce et des noms reduits a une lettre (« P… »).

_SLIDE_W = 13.333
_TOP, _BOTTOM = 1.2, 7.0
_LEFT_M = _RIGHT_M = 0.4
_CHAR_W = 0.0080            # largeur d'un caractere gras, par point de corps

# Le seuil de lisibilite d'une carte: en dessous, l'arbre change de slide.
_MIN_W = 1.2                # plus etroite, une carte coupait chaque titre
_MIN_H = 0.42               # un titre et un nom a 9 points, marges comprises
_MIN_TITLE_FS = 9.0
_MIN_PERSON_FS = 8.5
_HEADER_CHARS = 78          # ce que le bandeau du haut tient a 22 points

_T_MORE = {
    "fr": {"one": "1 élément", "many": "{n} éléments", "cont": "suite", "sep": " : ",
           "and_one": " et 1 autre", "and_more": " et {n} autres"},
    "en": {"one": "1 item", "many": "{n} items", "cont": "cont.", "sep": ": ",
           "and_one": " and 1 more", "and_more": " and {n} more"},
}


def _clone(node: dict, depth: int | None = None) -> dict:
    """Une copie de l'arbre, coupee sous ``depth`` niveaux: la mise en page ecrit
    sa position dans les noeuds, et chaque essai doit partir d'un arbre propre."""
    kids = node.get("children") or []
    out = {k: v for k, v in node.items()
           if (not k.startswith("_") or k == "_note") and k != "children"}
    out["children"] = [] if depth == 0 else [_clone(k, None if depth is None else depth - 1) for k in kids]
    return out


def _count(node: dict) -> int:
    """Le nombre d'elements sous un noeud, a tous les niveaux."""
    return sum(1 + _count(k) for k in node.get("children") or [])


def _layout(roots: list[dict], compact: bool = False,
            per_col: int | None = None) -> tuple[list[dict], int, int]:
    """Tidy top-down layout. Returns (placed_nodes, n_leaf_slots, max_depth).
    Each placed node gets x (leaf-slot centre, float) and depth (int).

    ``compact``: the leaves of one parent are stacked in a single column under it
    (``_stack`` = their rank) instead of taking one slot each. With twenty leaves
    side by side, each card was half an inch wide and every title read « Plate… ».
    ``per_col`` caps a stack: past it, the leaves continue in a second column, a
    third, so that forty leaves do not shrink to forty slivers of a column."""
    placed: list[dict] = []
    counter = {"leaf": 0}

    def walk(node: dict, depth: int) -> float:
        kids = node.get("children") or []
        node["_stack"] = None
        if compact and len(kids) > 1 and all(not (k.get("children") or []) for k in kids):
            cols = 1 if not per_col else -(-len(kids) // per_col)
            size = -(-len(kids) // cols)
            xs = []
            for c in range(cols):
                x = counter["leaf"] + 0.5
                counter["leaf"] += 1
                xs.append(x)
                for i, k in enumerate(kids[c * size:(c + 1) * size]):
                    k["_x"], k["_depth"], k["_stack"] = x, depth + 1, i
                    placed.append({"node": k, "x": x, "depth": depth + 1, "parent_x": None})
            x = sum(xs) / len(xs)
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


# Le texte suit la carte. PowerPoint passe un titre a la ligne, mais il ne coupe
# pas un mot: « Management » plus large que sa carte en sortait des deux cotes et
# s'ecrivait sur la voisine. On descend donc d'un demi-point tant que le mot le
# plus long ne rentre pas, et on coupe en dernier ressort plutot que de deborder.
def _fit_size(text: str, base: float, width: float, floor: float = 8.0) -> float:
    inner = width - 0.12      # la largeur utile, marges deduites
    longest = max((len(w) for w in (text or "").split()), default=1)
    size = base
    while size > floor and longest * _CHAR_W * size > inner:
        size -= 0.5
    return size


def _fit_text(text: str, size: float, lines: int, width: float) -> str:
    """Le titre entier tient sur ses lignes, coupe a la fin avec « … » et non
    plus mot par mot (« Platefo… de moderni… » ne se lisait plus)."""
    chars = max(3, int((width - 0.12) / (_CHAR_W * size)))
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


def _fit_person(name: str, size: float, width: float) -> str:
    """Un nom sur une ligne: entier s'il tient, sinon l'initiale du prenom et
    le nom (« C. Dubois »), et non plus le seul prenom (« Camille… »)."""
    chars = max(3, int((width - 0.12) / (_CHAR_W * size)))
    name = (name or "").strip()
    if len(name) <= chars:
        return name
    parts = name.split()
    if len(parts) > 1:
        short = f"{parts[0][0]}. {' '.join(parts[1:])}"
        if len(short) <= chars:
            return short
        return _fit_text(short, size, 1, width)
    return _fit_text(name, size, 1, width)


def _geometry(roots: list[dict], compact: bool = False, per_col: int | None = None,
              pack: bool = False) -> dict | None:
    """Ou va chaque carte, a quelle taille, en quel corps: tout ce que le dessin
    lit, calcule sur une copie de l'arbre. None pour un arbre vide."""
    roots = [_clone(r) for r in roots]
    placed, n_leaf, max_depth = _layout(roots, compact, per_col)
    if not placed:
        return None
    avail_w = _SLIDE_W - _LEFT_M - _RIGHT_M
    col_w = avail_w / n_leaf                       # width per leaf slot
    # Peu de colonnes: elles se resserrent au centre au lieu de partager toute la
    # largeur, ou deux piles se regardaient d'un bord a l'autre de la slide.
    x0 = _LEFT_M
    if pack and col_w > 2.6:
        col_w = 2.6
        x0 = _LEFT_M + (avail_w - col_w * n_leaf) / 2
    row_h = (_BOTTOM - _TOP) / (max_depth + 1)
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
    widths = {}
    for d, xs_ in xs_by_depth.items():
        xs = sorted(xs_)
        gap = min((b - a for a, b in zip(xs, xs[1:])), default=n_leaf)
        widths[d] = min(2.2, gap * col_w * 0.92)
        # Seule sur sa rangee, une carte au bord de l'arbre debordait de la slide:
        # elle ne s'etend pas plus loin que le bord.
        edge = min(min(x0 + x * col_w - 0.2, _SLIDE_W - 0.2 - (x0 + x * col_w)) for x in xs)
        widths[d] = min(widths[d], 2 * edge)

    box_h = min(0.8, max(0.5, row_h * 0.62))
    # Stacked leaves share the space from their row down to the bottom.
    max_stack = 1 + max((it["node"].get("_stack") or 0 for it in placed), default=0)
    stack_top = {it["depth"] for it in placed if it["node"].get("_stack") is not None}
    if max_stack > 1:
        d0 = min(stack_top)
        room = _BOTTOM - (_TOP + d0 * row_h + 0.1)
        stack_h = min(box_h, room / max_stack - 0.08)
    else:
        stack_h = box_h

    # Un meme corps pour toutes les cartes d'un meme niveau: d'une carte a sa
    # voisine, le titre changeait de taille selon la longueur de ses mots.
    fs1: dict[int, float] = {}
    fs2: dict[int, float] = {}
    for item in placed:
        n_, d_ = item["node"], item["depth"]
        fs1[d_] = min(fs1.get(d_, 99), _fit_size(n_["title"], 10.5 if max_depth <= 3 else 9, widths[d_]))
        if n_.get("person_name"):
            fs2[d_] = min(fs2.get(d_, 99), _fit_size(n_["person_name"], 8.5, widths[d_]))
    return {"roots": roots, "placed": placed, "n_leaf": n_leaf, "max_depth": max_depth,
            "row_h": row_h, "box_h": box_h, "stack_h": stack_h, "max_stack": max_stack,
            "widths": widths, "fs1": fs1, "fs2": fs2, "col_w": col_w, "x0": x0}


def _card_text(g: dict, item: dict) -> tuple[str, str | None, str | None, float]:
    """Ce qu'une carte ecrit, deja ajuste a sa taille: titre, nom, note (le
    nombre d'elements d'une branche de la vue d'ensemble), et sa hauteur."""
    node, depth = item["node"], item["depth"]
    stacked = node.get("_stack") is not None
    bh_ = g["stack_h"] if stacked else g["box_h"]
    width = g["widths"][depth]
    fs1 = g["fs1"][depth]
    extra = (0.16 if node.get("person_name") else 0.02) + (0.15 if node.get("_note") else 0)
    lines1 = max(1, int((bh_ - extra) / (fs1 * 1.2 / 72)))
    title = _fit_text(node["title"], fs1, lines1, width)
    person = (_fit_person(node["person_name"], g["fs2"].get(depth, 8.5), width)
              if node.get("person_name") else None)
    return title, person, node.get("_note"), bh_


def _legible(g: dict) -> bool:
    """Toutes les cartes se lisent: assez larges, assez hautes, un corps d'au
    moins neuf points, et aucun titre ni nom ampute de sa fin."""
    if min(g["widths"].values()) < _MIN_W:
        return False
    if min(g["box_h"], g["stack_h"] if g["max_stack"] > 1 else g["box_h"]) < _MIN_H:
        return False
    # Une rangee doit laisser passer ses traits entre deux cartes.
    if g["max_depth"] and g["box_h"] > g["row_h"] - 0.2:
        return False
    if min(g["fs1"].values()) < _MIN_TITLE_FS or min(g["fs2"].values(), default=99) < _MIN_PERSON_FS:
        return False
    for item in g["placed"]:
        title, person, note, bh_ = _card_text(g, item)
        if title.endswith("…") and not item["node"]["title"].rstrip().endswith("…"):
            return False
        if person is not None and person.endswith("…"):
            return False
        lines = (1 if person else 0) + (1 if note else 0)
        if bh_ < 0.18 + lines * 0.15:
            return False
    return True


def _fit(roots: list[dict], pack: bool = False) -> tuple[dict | None, bool]:
    """La mise en page d'un arbre sur une slide, et si elle se lit.

    D'abord celle d'avant (une colonne par feuille, ou une pile par parent des
    qu'il y a plus de dix feuilles): un organigramme qui se lisait ne change pas.
    Ensuite des piles plus courtes, sur plusieurs colonnes."""
    g = _geometry(roots, pack=pack)
    if g is None:
        return None, True
    if g["n_leaf"] > 10:
        g = _geometry(roots, compact=True, pack=pack)
    if _legible(g):
        return g, True
    groups = []

    def leaf_groups(n):
        kids = n.get("children") or []
        if len(kids) > 1 and all(not (k.get("children") or []) for k in kids):
            groups.append(len(kids))
        for k in kids:
            leaf_groups(k)
    for r in roots:
        leaf_groups(r)
    last = g
    for per_col in range(max(groups, default=1) - 1, 0, -1):
        g2 = _geometry(roots, compact=True, per_col=per_col, pack=pack)
        last = g2
        if _legible(g2):
            return g2, True
    return last, False


def _pages(node: dict, path: list[str]) -> list[tuple[list[str], dict, bool]]:
    """Les slides d'une branche: (chemin, mise en page, suite?). Une branche qui
    ne tient pas est coupee en groupes d'enfants, chacun sous son parent, et un
    enfant trop grand a lui seul prend ses propres slides."""
    g, ok = _fit([node], pack=True)
    if ok:
        return [(path, g, False)]
    kids = node.get("children") or []
    for size in range(len(kids) - 1, 0, -1):
        chunks = [kids[i:i + size] for i in range(0, len(kids), size)]
        fits = [_fit([{**node, "children": c}], pack=True) for c in chunks]
        if all(ok_ for _, ok_ in fits):
            return [(path, g_, i > 0) for i, (g_, _) in enumerate(fits)]
    # Un enfant a la fois ne tient toujours pas: la branche est montree sans
    # ses petits-enfants, et chaque enfant trop large a ses slides.
    out = []
    head = _clone(node, 1)
    g, _ = _fit([head], pack=True)
    out.append((path, g, False))
    for k in kids:
        if k.get("children"):
            out += _pages(k, path + [k["title"]])
    return out


def render_org_pptx(roots: list[dict], scope_name: str, *, lang: str = "fr") -> bytes:
    """Render the org tree as a PPTX: one slide while the cards read, an overview
    and one slide per branch beyond.

    Uses _layout to assign each node a leaf-slot x and a depth, then scales box
    size / row height to fit everything on one 13.33x7.5in slide. Connectors are
    drawn first so the boxes sit on top; squad-bound boxes are status-coloured."""
    prs = pptxtpl.new_deck()
    org_deck(prs, roots, scope_name, lang=lang)["org"](None)
    return pptxtpl.save_deck(prs)


def org_deck(prs, roots: list[dict], scope_name: str, *, lang: str = "fr") -> dict:
    """The org-chart section drawer bound to one deck."""
    from .exportspec import block_on

    def org_section(sec):
        _org_slides(prs, roots, scope_name, lang, block_on(sec, "legend"), block_on(sec, "stamp"))

    return {"org": org_section, "parts": {}}


def _org_slides(prs, roots, scope_name, lang, legend_on=True, stamp_on=True):
    """Les slides de l'organigramme: une seule tant que l'arbre se lit, sinon une
    vue d'ensemble puis une slide par branche."""
    lang = _lang(lang)
    M = _T_MORE[lang]
    base = f'{_T[lang]["org"]} | {scope_name}'
    g, ok = _fit(roots)
    if g is None or ok:
        _org_slide(prs, g, base, lang, legend_on, stamp_on)
        return
    # La vue d'ensemble: la racine et ses branches, chacune avec ce qu'elle porte.
    overview = []
    for r in roots:
        top = _clone(r, 1)
        for k, src in zip(top["children"], r.get("children") or []):
            n = _count(src)
            if n:
                k["_note"] = M["one"] if n == 1 else M["many"].format(n=n)
        overview.append(top)
    slides: list[tuple[list[str], dict, bool]] = []
    g_over, ok_over = _fit(overview, pack=True)
    if ok_over:
        slides.append(([], g_over, False))
    else:
        for top in overview:
            slides += [([], g_, cont) for _, g_, cont in _pages(top, [])]
    # Une slide par branche, mais les petites branches voisines partagent la leur
    # tant qu'elles s'y lisent: quarante branches de deux equipes ne font pas
    # quarante slides presque vides.
    group: list[dict] = []

    def group_title(names: list[str]) -> str:
        """« A, B et 4 autres »: les premieres branches nommees, les suivantes
        comptees, dans la place que le bandeau laisse."""
        room = _HEADER_CHARS - len(base) - len(M["sep"])
        for k in range(len(names), 0, -1):
            rest = len(names) - k
            tail = "" if not rest else (M["and_one"] if rest == 1 else M["and_more"].format(n=rest))
            text = ", ".join(names[:k]) + tail
            if len(text) <= room:
                return text
        return names[0]

    def flush():
        if group:
            g_, _ = _fit(group, pack=True)
            slides.append(([group_title([b["title"] for b in group])], g_, False))
            group.clear()
    for r in roots:
        for k in r.get("children") or []:
            if not k.get("children"):
                continue
            pages = _pages(k, [k["title"]])
            if len(pages) > 1:
                flush()
                slides += pages
                continue
            if group and not _fit(group + [k], pack=True)[1]:
                flush()
            group.append(k)
    flush()
    for path, g_, cont in slides:
        title = base
        if path:
            room = _HEADER_CHARS - len(base) - len(M["sep"])
            tail = " / ".join(path)
            if len(tail) > room:
                tail = tail[:max(8, room - 1)].rstrip() + "…"
            title += M["sep"] + tail
        if cont:
            title += f' ({M["cont"]})'
        _org_slide(prs, g_, title, lang, legend_on, stamp_on)


def _org_slide(prs, g, title, lang, legend_on=True, stamp_on=True):
    Presentation, Inches, Pt, Emu, RGBColor, PP_ALIGN, MSO_ANCHOR, MSO_SHAPE = _pptx_toolkit()
    from pptx.enum.shapes import MSO_CONNECTOR
    _NAVY = pptxtpl.color("primary", globals()["_NAVY"])

    def rgb(h):
        return RGBColor.from_string(h.lstrip("#").upper())

    SLIDE_W = _SLIDE_W
    s = pptxtpl.add_slide(prs)

    # Header band
    head = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(SLIDE_W), Inches(0.9))
    head.fill.solid(); head.fill.fore_color.rgb = rgb(_NAVY); head.line.fill.background(); head.shadow.inherit = False
    tf = head.text_frame; tf.margin_left = Inches(0.5); tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; r = p.add_run(); r.text = title
    r.font.size = Pt(_fs(22)); r.font.bold = True; r.font.color.rgb = rgb("#FFFFFF")

    if g is None:
        # Une slide avec son seul titre se lisait comme un export rate.
        box = s.shapes.add_textbox(Inches(0.5), Inches(3.3), Inches(SLIDE_W - 1), Inches(0.6))
        pe = box.text_frame.paragraphs[0]; pe.alignment = PP_ALIGN.CENTER
        re_ = pe.add_run(); re_.text = _T[lang]["no_org"]
        re_.font.size = Pt(_fs(16)); re_.font.color.rgb = rgb(_MUTED)
        return

    # La legende et la date, en bas: une bordure verte ou orange ne s'explique
    # pas d'elle-meme, et une slide d'organigramme circule seule.
    from datetime import datetime, timezone
    from .reportcommon import fmt_datetime
    T = _T[lang]
    ly = 7.14
    lx = 0.4
    if legend_on:
        lg = s.shapes.add_textbox(Inches(lx), Inches(ly), Inches(4.2), Inches(0.22))
        lr = lg.text_frame.paragraphs[0].add_run(); lr.text = T["legend"]
        lr.font.size = Pt(9); lr.font.color.rgb = rgb(_MUTED)
        lx += 3.9
    for st in (("on_track", "at_risk", "blocked") if legend_on else ()):
        sw = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(lx), Inches(ly + 0.03),
                                Inches(0.26), Inches(0.15))
        sw.fill.solid(); sw.fill.fore_color.rgb = rgb(_STATUS_BG[st])
        sw.line.color.rgb = rgb(_STATUS[st]); sw.line.width = Pt(1.5); sw.shadow.inherit = False
        tb = s.shapes.add_textbox(Inches(lx + 0.32), Inches(ly), Inches(1.2), Inches(0.22))
        tr = tb.text_frame.paragraphs[0].add_run(); tr.text = T[st]
        tr.font.size = Pt(9); tr.font.color.rgb = rgb(_MUTED)
        lx += 0.4 + 0.075 * len(T[st]) + 0.3
    if stamp_on:
        gb = s.shapes.add_textbox(Inches(SLIDE_W - 4.4), Inches(ly), Inches(4.0), Inches(0.22))
        gp = gb.text_frame.paragraphs[0]; gp.alignment = PP_ALIGN.RIGHT
        gr = gp.add_run(); gr.text = T["gen"].format(d=fmt_datetime(datetime.now(timezone.utc), lang))
        gr.font.size = Pt(9); gr.font.color.rgb = rgb(_MUTED)

    top = _TOP
    col_w, x0 = g["col_w"], g["x0"]
    row_h, box_h, stack_h = g["row_h"], g["box_h"], g["stack_h"]

    def width_at(d: int) -> float:
        return g["widths"][d]

    def cx(x):  # leaf-slot centre → inches
        return x0 + x * col_w

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
            # A stack: one spine down the left edge of each column, a tick into
            # each card, and one bar above the columns when there are several.
            x1, y1 = cx(node["_x"]), cy(node["_depth"], node.get("_stack")) + box_h
            first_y = cy(kids[0]["_depth"], 0)
            cols = sorted({k["_x"] for k in kids})
            half = width_at(kids[0]["_depth"]) / 2 + 0.06
            spines = [cx(c) - half for c in cols]
            line(x1, y1, x1, first_y - 0.05)
            if len(cols) == 1:
                line(spines[0], first_y - 0.05, x1, first_y - 0.05)
            else:
                line(min(spines + [x1]), first_y - 0.05, max(spines + [x1]), first_y - 0.05)
            for c, sx in zip(cols, spines):
                col = [k for k in kids if k["_x"] == c]
                last_mid = cy(col[-1]["_depth"], col[-1]["_stack"]) + stack_h / 2
                line(sx, first_y - 0.05, sx, last_mid)
                for k in col:
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
    for r0 in g["roots"]:
        draw_connectors(r0)

    for item in g["placed"]:
        node = item["node"]
        title_txt, person, note, bh_ = _card_text(g, item)
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
        fs1 = g["fs1"][item["depth"]]
        r1 = p.add_run(); r1.text = title_txt
        r1.font.size = Pt(fs1); r1.font.bold = True; r1.font.color.rgb = rgb(_INK)
        fs2 = g["fs2"].get(item["depth"], 8.5)
        if person is not None:
            p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
            r2 = p2.add_run(); r2.text = person
            r2.font.size = Pt(fs2); r2.font.color.rgb = rgb(_MUTED)
        if note:
            p3 = tf.add_paragraph(); p3.alignment = PP_ALIGN.CENTER
            r3 = p3.add_run(); r3.text = note
            r3.font.size = Pt(fs2); r3.font.italic = True; r3.font.color.rgb = rgb(_MUTED)
