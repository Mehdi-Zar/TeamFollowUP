"""PowerPoint rendering: the four decks the product exports.

Dashboard, roadmap swimlane, initiatives and cross-team dependencies. Kept apart
from ``report`` because it is 900 lines that share almost nothing with the HTML
path - eight names, all of which now live in ``reportcommon`` - and because the
python-pptx machinery reads very differently from string templating.

The public names stay importable from ``report`` as before: it re-exports them,
so nothing that used ``from .report import render_pptx`` had to change.
"""
from __future__ import annotations

import html
import io
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import pptxtpl
from . import status as st
from .generalconfig import get_general
from .models import Squad, Tribe, utcnow
from .serializers import annual_progress, budget_out, dependency_label
from .reportcommon import (MOOD_CLOUD, MOOD_COLOR, OTD_SCOPE_COLOR, STAGE_COLOR, _DEP_T,
                           _INIT_T, _MONTHS, _lang, _status_label, _status_rag,
                           group_by_theme, mood_label, pack_otds, rt, timeline_rows)


# ----- PPTX rendering -------------------------------------------------------------

# Brand palette (mirrors the app theme): navy / accent + RAG.
_BRAND = {
    "navy": "#1E2761", "navy_deep": "#141B47", "accent": "#175CD3",
    "green": "#027A48", "orange": "#B54708", "red": "#B42318",
    # Une encre presque noire: sur un videoprojecteur fatigue, un gris anthracite
    # perd la moitie de son contraste et le texte se devine au lieu de se lire.
    "ink": "#111827", "muted": "#55606E", "card": "#F1F5F9",
    "line": "#E2E8F0", "white": "#FFFFFF", "zebra": "#F8FAFC",
}


_RAG_BRAND = {"red": "#B42318", "amber": "#B54708", "green": "#027A48", "grey": "#6B7280"}


# Runaway guard on per-squad detail slides. Set well above any realistic squad
# count so an explicit export never silently drops the squads the user picked;
# if it is ever exceeded, render_pptx adds a visible "N more squads" notice slide
# rather than dropping them without a trace.
_MAX_DETAIL_SLIDES = 300


def _pptx_toolkit():
    """Import python-pptx lazily and return the bits used to build a deck."""
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.enum.shapes import MSO_SHAPE
    return Presentation, Inches, Pt, Emu, RGBColor, PP_ALIGN, MSO_ANCHOR, MSO_SHAPE


def render_pptx(data: dict) -> bytes:
    """Render the weekly report as a branded deck (requires python-pptx):
    a summary one-pager (dropped for a single-squad export) followed by one slide
    per squad, each built on the year's timeline: quarters and their progress, OTD
    commitments placed on their date, then one row per commitment carrying the
    milestones that hold it, with key messages and budget along the bottom. The
    roadmap-only swimlane deck is produced separately by render_roadmap_pptx."""
    Presentation, Inches, Pt, Emu, RGBColor, PP_ALIGN, MSO_ANCHOR, MSO_SHAPE = _pptx_toolkit()

    def rgb(hexstr: str) -> RGBColor:
        return RGBColor.from_string(hexstr.lstrip("#").upper())

    B = {k: rgb(v) for k, v in _BRAND.items()}
    lang = data.get("lang", "fr")

    prs = pptxtpl.new_presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    def new_slide():
        return pptxtpl.add_slide(prs)

    def textbox(s, left, top, width, height, text, size, *, bold=False, color=None,
                align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
        box = s.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Emu(0)
        tf.margin_top = tf.margin_bottom = Emu(0)
        p = tf.paragraphs[0]
        p.alignment = align
        r = p.add_run(); r.text = text
        r.font.size = Pt(size); r.font.bold = bold
        r.font.color.rgb = color if color is not None else B["ink"]
        return box

    def rect(s, left, top, width, height, fill, line=None):
        sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
        sh.fill.solid(); sh.fill.fore_color.rgb = fill
        if line is None:
            sh.line.fill.background()
        else:
            sh.line.color.rgb = line
        sh.shadow.inherit = False
        return sh

    def place(sh, lines, *, anchor=MSO_ANCHOR.TOP, ml=0.1, mt=0.06, mr=0.1, mb=0.06):
        """Write paragraphs INTO a shape's own text frame, so the text is part of
        the shape (not a separate textbox floating on top). Each line is
        (text, size_pt, color[, bold, align, space_after_pt])."""
        tf = sh.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = Inches(ml); tf.margin_right = Inches(mr)
        tf.margin_top = Inches(mt); tf.margin_bottom = Inches(mb)
        for i, ln in enumerate(lines):
            txt, size, color = ln[0], ln[1], ln[2]
            bold = ln[3] if len(ln) > 3 else False
            align = ln[4] if len(ln) > 4 else PP_ALIGN.LEFT
            sa = ln[5] if len(ln) > 5 else 2
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            p.space_after = Pt(sa)
            r = p.add_run(); r.text = txt
            r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color
        return sh

    def bullets(s, left, top, width, height, lines, size):
        """A text box with one paragraph per (text, color, bold) line."""
        box = s.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Emu(0)
        tf.margin_top = tf.margin_bottom = Emu(0)
        for i, (txt, color, bold) in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(2)
            r = p.add_run(); r.text = txt
            r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color
        return box

    def style_cell(cell, text, size, color, *, bold=False, align=PP_ALIGN.LEFT, fill=None):
        cell.margin_left = Inches(0.06); cell.margin_right = Inches(0.04)
        cell.margin_top = Emu(0); cell.margin_bottom = Emu(0)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        if fill is not None:
            cell.fill.solid(); cell.fill.fore_color.rgb = fill
        else:
            cell.fill.background()
        cell.text = text or " "
        p = cell.text_frame.paragraphs[0]
        p.alignment = align
        if p.runs:
            r = p.runs[0]
            r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color

    # ----- app-styled primitives (rounded cards, chips, progress bars) -----------
    def rrect(s, left, top, width, height, fill, *, line=None, radius=0.08):
        sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        try:
            sh.adjustments[0] = radius
        except Exception:
            pass
        sh.fill.solid(); sh.fill.fore_color.rgb = fill
        if line is None:
            sh.line.fill.background()
        else:
            sh.line.color.rgb = line; sh.line.width = Pt(1)
        sh.shadow.inherit = False
        return sh

    def card(s, left, top, width, height, title=None):
        sh = rrect(s, left, top, width, height, B["white"], line=B["line"], radius=0.05)
        if title:
            # Title lives in the card's own text frame (top-anchored), not as an
            # overlay; body content is added by the caller as child shapes.
            place(sh, [(title, 12, B["navy"], True)], anchor=MSO_ANCHOR.TOP, ml=0.18, mt=0.12, mr=0.18)
        return sh

    def chip(s, left, top, text, fill, *, color=None, size=10):
        w = Inches(0.26 + 0.082 * len(text))
        sh = rrect(s, left, top, w, Inches(0.3), fill, radius=0.5)
        tf = sh.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = Inches(0.07)
        tf.margin_top = tf.margin_bottom = Emu(0)
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = text
        r.font.size = Pt(size); r.font.bold = True
        r.font.color.rgb = color if color is not None else B["white"]
        return Emu(int(left) + int(w))

    def chips_row(s, left, top, items, *, gap=0.1):
        x = int(left)
        for text, fill in items:
            x = int(chip(s, Emu(x), top, text, fill))
            x += int(Inches(gap))

    def pbar(s, left, top, width, pct, color):
        rrect(s, left, top, width, Inches(0.12), rgb("#E2E8F0"), radius=0.5)
        p = max(0, min(100, int(pct or 0)))
        if p > 0:
            rrect(s, left, top, Emu(int(int(width) * p / 100)), Inches(0.12), color, radius=0.5)

    gen = data["generated_at"]
    gen_str = gen.strftime("%d/%m/%Y %H:%M") if isinstance(gen, datetime) else str(gen)
    sm = data["summary"]
    squads = [r for blk in data["tribes"] for r in blk["squads"]]
    margin = Inches(0.5)

    # ---------------- Summary one-pager (report kind) -----------------------------
    def summary_slide():
        s = new_slide()
        band = rect(s, Inches(0), Inches(0), prs.slide_width, Inches(1.12), B["navy"])
        # Title + subtitle are the band's own text; the right-corner meta stays a
        # corner label (left title and right meta can't share one text frame).
        place(band, [
            (f'{data["app_name"]} - {rt(lang, "report")}', 26, B["white"], True, PP_ALIGN.LEFT, 5),
            (f'{data["scope_name"]}, {rt(lang, "year")} {data["year"]}', 13, rgb("#C7D2FE"), False, PP_ALIGN.LEFT, 0),
        ], anchor=MSO_ANCHOR.TOP, ml=0.55, mt=0.18, mr=4.2)
        textbox(s, Inches(9.3), Inches(0.3), Inches(3.5), Inches(0.6),
                f'{rt(lang, "generated_full", d=gen_str)}\n{rt(lang, "window_full", n=data["since_days"])}', 11,
                color=rgb("#C7D2FE"), align=PP_ALIGN.RIGHT)

        kpis = [
            (rt(lang, "k_squads"), str(sm["squads_total"]), B["navy"]),
            (rt(lang, "k_progress"), f'{sm["avg_progress"]}%', B["accent"]),
            (rt(lang, "k_blocked"), str(sm["blocked"]), B["red"] if sm["blocked"] else B["ink"]),
            (rt(lang, "k_atrisk"), str(sm["at_risk"]), B["orange"] if sm["at_risk"] else B["ink"]),
            (rt(lang, "k_obj_red"), str(sm["objectives_red"]), B["red"] if sm["objectives_red"] else B["ink"]),
            (rt(lang, "k_stale"), str(sm["stale"]), B["orange"] if sm["stale"] else B["ink"]),
        ]
        gap = Inches(0.14)
        n = len(kpis)
        total_w = prs.slide_width - margin * 2
        card_w = Emu(int((total_w - gap * (n - 1)) / n))
        ky, kh = Inches(1.34), Inches(1.05)
        for i, (label, val, color) in enumerate(kpis):
            left = Emu(int(margin) + i * (int(card_w) + int(gap)))
            kp = rect(s, left, ky, card_w, kh, B["card"], line=B["line"])
            # Value + label are the card's own text, vertically centered.
            place(kp, [(val, 26, color, True, PP_ALIGN.CENTER, 4),
                       (label, 10, B["muted"], False, PP_ALIGN.CENTER, 0)],
                  anchor=MSO_ANCHOR.MIDDLE, ml=0.05, mr=0.05)

        headers = [rt(lang, "h_squad"), rt(lang, "h_leader"), rt(lang, "h_status"),
                   rt(lang, "h_progress"), rt(lang, "h_delta"), rt(lang, "h_blocked"), rt(lang, "h_atrisk")]
        wfrac = [0.275, 0.21, 0.12, 0.105, 0.082, 0.103, 0.105]
        table_w = int(prs.slide_width - margin * 2)
        widths = [Emu(int(table_w * f)) for f in wfrac]

        MAX = 18
        shown = squads[:MAX]
        overflow = len(squads) - len(shown)
        nrows = len(shown) + 1 + (1 if overflow > 0 else 0)
        top = Inches(2.62)
        tbl = s.shapes.add_table(max(nrows, 2), len(headers), margin, top, Emu(table_w),
                                 Inches(0.34) + Inches(0.255) * (nrows - 1)).table
        for ci, w in enumerate(widths):
            tbl.columns[ci].width = w
        for ci, h in enumerate(headers):
            align = PP_ALIGN.LEFT if ci < 2 else PP_ALIGN.CENTER
            style_cell(tbl.cell(0, ci), h, 10, B["white"], bold=True, align=align, fill=B["navy"])
        for ri, r in enumerate(shown, start=1):
            zebra = B["zebra"] if ri % 2 == 0 else B["white"]
            delta = r["delta"]
            cells = [
                (r["name"], B["ink"], True, PP_ALIGN.LEFT),
                (r["leader"] or "-", B["muted"], False, PP_ALIGN.LEFT),
                (_status_label(r["status"], lang), rgb(_RAG_BRAND[r["status_rag"]]), True, PP_ALIGN.CENTER),
                (f'{r["annual_pct"]}%', B["ink"], False, PP_ALIGN.CENTER),
                ((f'+{delta}' if delta > 0 else str(delta)),
                 (B["green"] if delta > 0 else B["red"]) if delta else B["muted"], False, PP_ALIGN.CENTER),
                (str(r["blocked"] or "-"), B["red"] if r["blocked"] else B["muted"], r["blocked"] > 0, PP_ALIGN.CENTER),
                (str(r["at_risk"] or "-"), B["orange"] if r["at_risk"] else B["muted"], r["at_risk"] > 0, PP_ALIGN.CENTER),
            ]
            for ci, (val, color, bold, align) in enumerate(cells):
                style_cell(tbl.cell(ri, ci), val, 9.5, color, bold=bold, align=align, fill=zebra)
        if overflow > 0:
            last = len(shown) + 1
            style_cell(tbl.cell(last, 0), rt(lang, "more_squads", n=overflow), 9, B["muted"], align=PP_ALIGN.LEFT)
            for ci in range(1, len(headers)):
                style_cell(tbl.cell(last, ci), " ", 9, B["muted"])

    # ---------------- Une slide par squad: la frise de l'annee --------------------
    #
    # Meme bloc que la page d'une squad et que l'export HTML: les trimestres avec
    # leur avancement, les engagements OTD poses a leur date juste dessous, puis
    # une ligne par engagement portant les jalons qui le tiennent. Les positions
    # sont calculees en pouces sur un axe unique, donc tout s'aligne: un jalon du
    # Q3 tombe sous l'entete du Q3, sans reglage a la main.
    LBL_X, LBL_W = 0.55, 1.55          # colonne des libelles, a gauche de l'axe
    AX0, AX1 = 2.20, 12.80             # l'axe des douze mois
    MW = (AX1 - AX0) / 12.0            # largeur d'un mois
    QW = MW * 3                        # un trimestre vaut trois mois
    # Quatre bandes d'engagements superposables. Trois laissaient « +3 » sur une
    # squad qui en porte dix, alors que le bas de la frise etait vide: la place
    # existait, elle n'etait simplement pas allouee.
    OTD_ROWS = 4
    CPM = 13                           # caracteres tenant dans un mois, en 9 pt
    JALON_H = 0.46                     # hauteur d'une boite de jalon, deux lignes de 9 pt
    JALON_CPL = 30                     # caracteres sur une ligne d'une boite de jalon
    STAGE_W = 0.26                     # la phase, reservee a droite dans la boite

    def fit(text: str, chars: int) -> str:
        """Coupe a la largeur disponible. PowerPoint ne sait pas mettre de points
        de suspension: sans coupe il passe a la ligne et sort de la forme."""
        text = text or ""
        return text if len(text) <= chars else text[:max(1, chars - 1)].rstrip() + "\u2026"

    def mood_cloud(s, x, y, w, mood):
        """Le nuage du moral, dessine en formes plutot qu'en emoji.

        Un emoji depend de la police installee sur le poste qui ouvre le fichier:
        il sort en carre la ou elle manque, et change de style d'un support a
        l'autre. Trois formes suffisent a le remplacer, et elles sortent pareil
        partout. La bouche redit le niveau que la couleur donne, pour la lecture
        en noir et blanc.
        """
        pal = MOOD_CLOUD[mood]
        h = w * 0.72
        cloud = s.shapes.add_shape(MSO_SHAPE.CLOUD, Inches(x), Inches(y), Inches(w), Inches(h))
        cloud.fill.solid(); cloud.fill.fore_color.rgb = rgb(pal["fill"])
        cloud.line.color.rgb = rgb(pal["ink"]); cloud.line.width = Pt(1.25)
        cloud.shadow.inherit = False

        eye = w * 0.075
        for ex in (x + w * 0.36, x + w * 0.60):
            o = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(ex), Inches(y + h * 0.42),
                                   Inches(eye), Inches(eye))
            o.fill.solid(); o.fill.fore_color.rgb = rgb(pal["ink"])
            o.line.fill.background(); o.shadow.inherit = False

        # La bouche: un trait epais pour « moyen », un arc pour les deux autres,
        # approche par un polygone. Une forme d'arc dependrait de reglages que
        # PowerPoint interprete, un polygone se dessine tel qu'on l'ecrit.
        mx, my, mw = x + w * 0.33, y + h * 0.66, w * 0.34
        th = h * 0.055
        if mood == "mixed":
            m = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(mx), Inches(my),
                                   Inches(mw), Inches(th))
            m.fill.solid(); m.fill.fore_color.rgb = rgb(pal["ink"])
            m.line.fill.background(); m.shadow.inherit = False
            return
        depth = h * 0.16 * (1 if mood == "good" else -1)
        pts = [(mx + mw * i / 4.0, my + depth * (1 - (2 * i / 4.0 - 1) ** 2)) for i in range(5)]
        outline = pts + [(px, py - th) for px, py in reversed(pts)]
        builder = s.shapes.build_freeform(Inches(outline[0][0]), Inches(outline[0][1]))
        builder.add_line_segments([(Inches(px), Inches(py)) for px, py in outline[1:]], close=True)
        mouth = builder.convert_to_shape()
        mouth.fill.solid(); mouth.fill.fore_color.rgb = rgb(pal["ink"])
        mouth.line.fill.background(); mouth.shadow.inherit = False

    def squad_slide(r):
        det = r.get("detail") or {}
        s = new_slide()
        rect(s, Inches(0), Inches(0), prs.slide_width, prs.slide_height, rgb("#F5F7FA"))

        # ----- entete: la squad, son responsable, et le moral a droite -----
        hdr = rrect(s, Inches(0.4), Inches(0.26), Inches(10.72), Inches(0.81), B["navy"], radius=0.08)
        place(hdr, [
            (r["name"], 19, B["white"], True, PP_ALIGN.LEFT, 3),
            (f'{rt(lang, "h_leader")} : {r["leader"] or "-"}, {rt(lang, "year")} {data["year"]}, '
             f'{rt(lang, "h_progress_long")} {r["annual_pct"]}%', 11, rgb("#CDD8F5"), False, PP_ALIGN.LEFT, 0),
        ], anchor=MSO_ANCHOR.MIDDLE, ml=0.28, mr=0.28)

        # Le moral: trois niveaux, et la date qui les date. Un moral de mars
        # projete en septembre ment plus surement qu'une case vide.
        mood = r.get("mood")
        # Pas de nuage quand rien n'est declare: un nuage gris se lirait comme un
        # quatrieme niveau, alors que « non renseigne » n'en est pas un.
        mcard = rrect(s, Inches(11.20), Inches(0.26), Inches(1.73), Inches(0.81),
                      B["white"], line=B["line"], radius=0.08)
        place(mcard, [(mood_label(mood, lang), 9,
                       rgb(_RAG_BRAND[MOOD_COLOR.get(mood or "", "grey")]), True,
                       PP_ALIGN.RIGHT, 0)],
              anchor=MSO_ANCHOR.MIDDLE, ml=0.04, mr=0.12, mt=0.04, mb=0.04)
        if mood in MOOD_CLOUD:
            mood_cloud(s, 11.30, 0.40, 0.56, mood)
        # La date se range au-dessus de la carte, seule dans le coin de la slide, et
        # non dans l'encadre du visage. Elle date le moral, elle ne le dit pas: a
        # l'interieur, elle prenait le meme rang que le niveau, qui est la seule
        # chose a lire de loin.
        if r.get("mood_at"):
            textbox(s, Inches(10.90), Inches(0.10), Inches(2.03), Inches(0.14),
                    rt(lang, "mood_at", d=r["mood_at"]), 7, color=B["muted"],
                    align=PP_ALIGN.RIGHT)

        # ----- la carte de la frise -----
        card(s, Inches(0.4), Inches(1.22), Inches(12.53), Inches(4.76),
             rt(lang, "h_timeline", year=data["year"]))

        # Un trimestre, son avancement, sa barre. Rien d'autre: le commentaire du
        # trimestre s'inserait entre l'en-tete et la bande des mois, ou il coupait
        # la lecture de l'axe juste la ou elle commence. Il reste dans l'ecran et
        # dans le rapport HTML, qui n'ont pas de hauteur a tenir.
        quarters = {qd["q"]: qd for qd in det.get("quarters") or []}
        qy = 1.62
        for i, q in enumerate((1, 2, 3, 4)):
            qd = quarters.get(q) or {"pct": 0}
            pct = max(0, min(100, int(qd.get("pct") or 0)))
            x = AX0 + i * QW
            qc = rrect(s, Inches(x), Inches(qy), Inches(QW - 0.06), Inches(0.44),
                       rgb("#E8F0FE"), line=B["line"], radius=0.08)
            place(qc, [(f'Q{q}    {pct} %', 12, B["navy"], True, PP_ALIGN.LEFT, 0)],
                  anchor=MSO_ANCHOR.TOP, ml=0.08, mt=0.04, mr=0.08)
            pbar(s, Inches(x + 0.08), Inches(qy + 0.25), Inches(QW - 0.22), pct, B["accent"])

        # Les mois, qui donnent la resolution de l'axe. Sur une bande, et non sur
        # le blanc de la carte: douze mots poses dans le vide ne forment pas une
        # regle, et c'est une regle qu'on cherche quand on suit une date. Un mois
        # sur deux est legerement plus fonce, pour que l'oeil compte les colonnes
        # sans avoir a lire les noms.
        months = _MONTHS[_lang(lang)]
        rect(s, Inches(AX0), Inches(2.10), Inches(AX1 - AX0), Inches(0.24), rgb("#EEF2F7"))
        for i, m in enumerate(months):
            if i % 2:
                rect(s, Inches(AX0 + i * MW), Inches(2.10), Inches(MW), Inches(0.24), rgb("#E3E9F2"))
            textbox(s, Inches(AX0 + i * MW), Inches(2.155), Inches(MW), Inches(0.18), m, 9,
                    color=B["ink"], align=PP_ALIGN.CENTER)
        rect(s, Inches(LBL_X), Inches(2.34), Inches(AX1 - LBL_X), Inches(0.012), B["line"])

        # ----- les engagements poses sur l'axe, et leurs jalons en cartes -----
        #
        # Une carte par engagement, sous la date a laquelle il est pris: son titre,
        # sa date, puis ses jalons en puces. Un pointille relie la carte au repere
        # pose sur l'axe, et les cartes se rangent en quinconce pour qu'aucune n'en
        # recouvre une autre.
        #
        # Pourquoi des cartes et non des lignes: une ligne par engagement obligeait
        # a couper chaque titre a la largeur d'une colonne de trimestre, et un titre
        # coupe ne dit plus rien. Dans une carte, la largeur est fixe et le texte
        # passe a la ligne, donc il se lit en entier.
        from pptx.enum.dml import MSO_LINE_DASH_STYLE
        from pptx.enum.shapes import MSO_CONNECTOR

        otds = det.get("otds") or []
        by_id = {o["id"]: o for o in otds}
        rows = timeline_rows(det, lang)

        TOP, BOTTOM = 2.52, 5.86    # la bande ou les cartes se posent
        GAP_X, GAP_Y = 0.12, 0.12
        PAD = 0.09                  # marge interne d'une carte

        def wrapped(text: str, fs: float, width: float) -> int:
            """Combien de lignes ce texte prend, a cette taille, dans cette largeur.

            PowerPoint ne rend pas la hauteur d'un texte avant de l'afficher: sans
            cette estimation, une carte se dimensionne au juge et son dernier jalon
            sort du cadre."""
            per_char = 0.0068 * fs
            cpl = max(8, int((width - 2 * PAD) / per_char))
            return max(1, -(-len(text or "") // cpl))

        def cards_of(row) -> list[dict]:
            """Les cartes d'une ligne de frise: une par engagement, et une par
            trimestre pour les jalons qui ne tiennent aucun engagement (ils ont un
            trimestre, pas une date)."""
            if row["key"] == "none":
                out = []
                for q in (1, 2, 3, 4):
                    items = [it for it in row["items"] if it.get("quarter") == q]
                    if items:
                        out.append({"title": None, "scope": None, "date": None,
                                    "month": (q - 1) * 3, "items": items})
                return out
            o = by_id.get(row["key"]) or {}
            month = o.get("month")
            if month is None:
                # Sans date, la carte se pose sur le trimestre de son premier jalon:
                # un engagement hors de l'axe serait invisible, et sa liste de jalons
                # avec lui.
                qs = [it.get("quarter") for it in row["items"] if it.get("quarter")]
                month = (min(qs) - 1) * 3 if qs else 0
            return [{"title": row["title"], "scope": row.get("scope") or "management",
                     "date": o.get("date"), "month": month, "items": row["items"]}]

        cards = [c for row in rows for c in cards_of(row)]
        cards.sort(key=lambda c: (c["month"], c["title"] or ""))

        def layout(cols: int, title_fs: float, item_fs: float):
            """Range les cartes sur ``cols`` colonnes et rend (posees, debordantes).

            Une carte va dans la colonne de son mois et s'empile sous celles qui y
            sont deja. Quand cette colonne est pleine jusqu'en bas, elle prend la
            colonne la moins remplie: le pointille garde le lien avec sa date, donc
            une carte decalee reste juste, la ou une carte absente ne dit plus rien.
            """
            col_w = (AX1 - AX0) / cols
            card_w = col_w - GAP_X
            title_lh, item_lh = title_fs * 0.0200, item_fs * 0.0190
            bottoms = [TOP] * cols
            placed, spill = [], []

            for c in cards:
                h = 2 * PAD
                if c["title"]:
                    h += wrapped(c["title"], title_fs, card_w) * title_lh
                    if c["date"]:
                        h += item_lh
                for it in c["items"]:
                    label = it["title"] + (f' ({it["stage"]})' if it.get("stage") else "")
                    h += wrapped("- " + label, item_fs, card_w) * item_lh

                home = min(cols - 1, int(c["month"] * cols / 12))
                if bottoms[home] + h <= BOTTOM:
                    col = home
                else:
                    free = [(bottoms[i], abs(i - home), i) for i in range(cols)
                            if bottoms[i] + h <= BOTTOM]
                    if not free:
                        spill.append(c)
                        continue
                    col = min(free)[2]
                y = bottoms[col]
                bottoms[col] = y + h + GAP_Y
                placed.append({**c, "x": AX0 + col * col_w, "y": y, "h": h,
                               "w": card_w, "title_fs": title_fs, "item_fs": item_fs})
            return placed, spill

        # Du plus lisible au plus dense: on ne coupe pas le texte pour faire tenir
        # la slide, on ajoute une colonne puis on reduit le corps. Ce qui ne rentre
        # toujours pas est compte en clair plutot que tu.
        for cols, tfs, ifs in ((5, 9.5, 8.5), (5, 8.5, 7.5), (6, 8.5, 7.5), (6, 8, 7), (7, 7.5, 6.5)):
            placed, spill = layout(cols, tfs, ifs)
            if not spill:
                break

        for c in placed:
            ink = (rgb(OTD_SCOPE_COLOR[c["scope"]]) if c["scope"] else B["muted"])
            x, y, h, CARD_W = c["x"], c["y"], c["h"], c["w"]
            title_fs, item_fs = c["title_fs"], c["item_fs"]

            if c["title"]:
                # Le repere sur l'axe: une etoile a la date, et un pointille qui
                # descend vers la carte. Sans le trait, deux cartes voisines ne
                # disent plus laquelle repond a quelle date.
                mx = AX0 + c["month"] * MW + MW / 2
                star = s.shapes.add_shape(MSO_SHAPE.STAR_5_POINT, Inches(mx - 0.09),
                                          Inches(2.26), Inches(0.18), Inches(0.18))
                star.fill.solid(); star.fill.fore_color.rgb = ink
                star.line.fill.background(); star.shadow.inherit = False
                # Le trait ne se justifie que si la carte est proche de son etoile.
                # Quand elle a ete rangee ailleurs, un pointille en diagonale
                # traverse toute la frise et croise les autres: il coute plus en
                # bruit qu'il ne rapporte, et la date ecrite dans la carte dit deja
                # a quel repere elle repond.
                anchor = min(max(mx, x + 0.2), x + CARD_W - 0.2)
                if abs(anchor - mx) < CARD_W * 0.75:
                    link = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(mx), Inches(2.44),
                                                  Inches(anchor), Inches(y))
                    link.line.color.rgb = ink
                    link.line.width = Pt(0.75)
                    link.line.dash_style = MSO_LINE_DASH_STYLE.ROUND_DOT

            box = rrect(s, Inches(x), Inches(y), Inches(CARD_W), Inches(h),
                        B["white"], line=ink, radius=0.05)
            box.line.dash_style = MSO_LINE_DASH_STYLE.DASH

            tf = box.text_frame
            tf.word_wrap = True          # la largeur est fixe, le texte passe a la ligne
            tf.margin_left = tf.margin_right = Inches(PAD)
            tf.margin_top = Inches(PAD * 0.7); tf.margin_bottom = Inches(PAD * 0.5)
            tf.vertical_anchor = MSO_ANCHOR.TOP

            first = True

            def para():
                nonlocal first
                pp = tf.paragraphs[0] if first else tf.add_paragraph()
                first = False
                pp.space_after = Pt(0.5)
                pp.alignment = PP_ALIGN.LEFT
                return pp

            if c["title"]:
                pt_ = para()
                run = pt_.add_run(); run.text = c["title"]
                run.font.size = Pt(title_fs); run.font.bold = True; run.font.color.rgb = ink
                if c["date"]:
                    pd = para()
                    rd = pd.add_run()
                    rd.text = f'{rt(lang, "otd_commit")} {c["date"]}'
                    rd.font.size = Pt(item_fs - 0.5); rd.font.color.rgb = B["muted"]

            for it in c["items"]:
                pi = para()
                # La puce porte le statut, la legende du bas la traduit. Un mot de
                # statut par jalon prendrait une ligne sur deux dans la carte.
                rb = pi.add_run(); rb.text = "\u2022 "
                rb.font.size = Pt(item_fs)
                rb.font.color.rgb = rgb(_RAG_BRAND[_status_rag(it["status"])])
                rr = pi.add_run(); rr.text = it["title"]
                rr.font.size = Pt(item_fs); rr.font.color.rgb = B["ink"]
                if it.get("stage"):
                    rs = pi.add_run(); rs.text = f' ({it["stage"]})'
                    rs.font.size = Pt(item_fs - 0.5); rs.font.color.rgb = B["muted"]

        # Ce qui n'a pas trouve de place est dit, pas tu: une carte absente d'un
        # export se lit comme un engagement qui n'existe pas.
        notes = []
        undated = [o["title"] for o in otds if o.get("month") is None]
        if undated:
            notes.append(f'{rt(lang, "tl_no_date")} : {", ".join(undated)}')
        if spill:
            notes.append(f'+{len(spill)}')
        if not cards:
            notes.append(rt(lang, "tl_empty"))
        if notes:
            textbox(s, Inches(AX0), Inches(BOTTOM + 0.02), Inches(AX1 - AX0), Inches(0.18),
                    ", ".join(notes)[:170], 8, color=B["muted"])

        # ----- bas de slide: messages cles et budget -----
        def list_card(x, y2, w, h, title, lines, empty):
            sh = rrect(s, x, y2, w, h, B["white"], line=B["line"], radius=0.05)
            paras = [(title, 12, B["navy"], True, PP_ALIGN.LEFT, 4)]
            if lines:
                paras += [(txt, 10, color, bold, PP_ALIGN.LEFT, 2) for (txt, color, bold) in lines]
            else:
                paras.append((empty, 10, B["muted"], False, PP_ALIGN.LEFT, 0))
            place(sh, paras, anchor=MSO_ANCHOR.TOP, ml=0.16, mt=0.08, mr=0.16, mb=0.06)

        kms = det.get("key_messages") or []
        klines = []
        for m in kms[:3]:
            rag = {"success": "green", "alert": "amber", "risk": "red"}.get(m["kind"], "grey")
            klines.append((f'{rt(lang, "km_" + m["kind"])} : {m["text"]}', rgb(_RAG_BRAND[rag]), False))
        if len(kms) > 3:
            klines.append((f'+{len(kms) - 3}', B["muted"], False))
        list_card(Inches(0.4), Inches(6.08), Inches(8.02), Inches(1.18),
                  rt(lang, "h_key_messages"), klines, rt(lang, "no_key_message"))

        bsh = rrect(s, Inches(8.61), Inches(6.08), Inches(4.32), Inches(1.18),
                    B["white"], line=B["line"], radius=0.05)
        place(bsh, [(rt(lang, "h_budget"), 12, B["navy"], True, PP_ALIGN.LEFT, 4)],
              anchor=MSO_ANCHOR.TOP, ml=0.16, mt=0.08, mr=0.16)
        bud = det.get("budget")
        btf = bsh.text_frame
        if bud is None:
            p = btf.add_paragraph(); rr = p.add_run(); rr.text = rt(lang, "no_budget")
            rr.font.size = Pt(10); rr.font.color.rgb = B["muted"]
        else:
            f = lambda v: "-" if v is None else f"{v:,.0f} €"
            st_color = {"on_track": "green", "at_risk": "amber", "over": "red"}[bud["status"]]
            st_lbl = rt(lang, {"on_track": "b_on_track", "at_risk": "b_at_risk",
                               "over": "b_over"}[bud["status"]])
            rows_b = [
                (rt(lang, "b_total"), f(bud["total"])),
                (rt(lang, "b_spent"), f(bud["spent"]) +
                 (f' ({bud["spent_pct"]}%)' if bud.get("spent_pct") is not None else "")),
                (rt(lang, "b_forecast"), f(bud["forecast"]) +
                 (f' ({bud["forecast_pct"]}%)' if bud.get("forecast_pct") is not None else "")),
            ]
            for label, val in rows_b:
                p = btf.add_paragraph(); p.space_after = Pt(1)
                r1 = p.add_run(); r1.text = f'{label} : '
                r1.font.size = Pt(10); r1.font.color.rgb = B["muted"]
                r2 = p.add_run(); r2.text = val
                r2.font.size = Pt(10); r2.font.bold = True; r2.font.color.rgb = B["ink"]
            cw = Inches(0.26 + 0.082 * len(st_lbl))
            chip(s, Emu(int(Inches(8.61)) + int(Inches(4.32)) - int(cw) - int(Inches(0.14))),
                 Inches(6.14), st_lbl, rgb(_RAG_BRAND[st_color]))

        # La legende, tout en bas: les couleurs de statut, puis les deux phases.
        # Elle se lit une fois et sert pour toute la frise, donc elle tient sur une
        # ligne discrete plutot que de repeter dans chaque boite ce qu'une couleur
        # et deux lettres suffisent a dire.
        LEG_CW = 0.048                 # largeur d'un caractere en 7 pt
        lx = 0.4
        # D'abord les deux portees d'engagement: c'est la distinction nouvelle, et
        # une couleur sans legende se devine, mal, en reunion. Le meme repere que
        # sur l'axe, sinon la legende explique un signe qui ne s'y trouve pas.
        for scope in ("management", "squad"):
            mk = s.shapes.add_shape(MSO_SHAPE.STAR_5_POINT, Inches(lx), Inches(7.30),
                                    Inches(0.13), Inches(0.13))
            mk.fill.solid(); mk.fill.fore_color.rgb = rgb(OTD_SCOPE_COLOR[scope])
            mk.line.fill.background(); mk.shadow.inherit = False
            leg = rt(lang, "otd_scope_" + scope)
            textbox(s, Inches(lx + 0.13), Inches(7.31), Inches(LEG_CW * len(leg) + 0.06),
                    Inches(0.14), leg, 7, color=B["muted"])
            lx += 0.26 + LEG_CW * len(leg)
        for rag, codes in (("green", ("on_track", "done")), ("amber", ("at_risk",)),
                           ("red", ("blocked",))):
            rect(s, Inches(lx), Inches(7.33), Inches(0.09), Inches(0.09), rgb(_RAG_BRAND[rag]))
            leg = ", ".join(_status_label(c, lang) for c in codes)
            textbox(s, Inches(lx + 0.13), Inches(7.31), Inches(LEG_CW * len(leg) + 0.06),
                    Inches(0.14), leg, 7, color=B["muted"])
            lx += 0.26 + LEG_CW * len(leg)
        # EA et GA sont dans les boites: deux lettres qui ne veulent rien dire pour
        # qui decouvre le document, et tout pour qui sait, d'ou la legende.
        for code in ("ea", "ga"):
            leg = f'{code.upper()} {rt(lang, "stage_" + code)}'
            textbox(s, Inches(lx), Inches(7.31), Inches(LEG_CW * len(leg) + 0.06),
                    Inches(0.14), leg, 7, color=B["muted"])
            lx += 0.20 + LEG_CW * len(leg)

    # --- Assemble the deck. Une squad, une slide, la meme dans les deux cas: un
    # export d'une seule squad n'est que ce deck sans sa page de synthese.
    if not data.get("squad_scoped"):
        summary_slide()
    for r in squads[:_MAX_DETAIL_SLIDES]:
        if r.get("detail"):
            squad_slide(r)
    # Never silently drop squads the user explicitly selected: if the runaway
    # guard is ever hit, say how many were omitted instead of losing them.
    omitted = len(squads) - _MAX_DETAIL_SLIDES
    if omitted > 0:
        s = new_slide()
        rect(s, Inches(0), Inches(0), prs.slide_width, Inches(0.92), B["navy"])
        textbox(s, margin, Inches(3.2), prs.slide_width - margin * 2, Inches(1),
                rt(lang, "more_squads", n=omitted), 24, bold=True,
                color=B["navy"], align=PP_ALIGN.CENTER)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# Roadmap deck palette (mirrors the reference "Global Roadmap" deck).
_RM = {
    "dark": "#304957",   # quarter headers + swimlane labels
    "sub": "#97A3AA",    # month sub-headers
    "card": "#F2F2F2",   # milestone cards
    "card_ink": "#002060",
    "muted": "#6B7280",
    "white": "#FFFFFF",
}




def render_roadmap_pptx(data: dict) -> bytes:
    """Roadmap swimlane deck (mirrors the reference layout): quarters in columns
    with month sub-headers, squads as swimlane rows, and one milestone card per
    (squad, quarter) with status-coloured bullets."""
    Presentation, Inches, Pt, Emu, RGBColor, PP_ALIGN, MSO_ANCHOR, MSO_SHAPE = _pptx_toolkit()

    def rgb(hexstr: str) -> RGBColor:
        return RGBColor.from_string(hexstr.lstrip("#").upper())

    C = {k: rgb(v) for k, v in _RM.items()}
    STAGE = {k: rgb(v) for k, v in STAGE_COLOR.items()}  # EA=gold, GA=green
    lang = _lang(data.get("lang", "fr"))
    year = data["year"]
    gen = data["generated_at"]
    gen_str = gen.strftime("%d/%m/%Y %H:%M") if isinstance(gen, datetime) else str(gen)
    months = _MONTHS[lang]

    SLIDE_W, SLIDE_H = 13.333, 7.5
    prs = pptxtpl.new_presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)

    # Column geometry (4 quarters).
    MARGIN, GAP = 0.5, 0.08
    COL_W = (SLIDE_W - 2 * MARGIN - GAP * 3) / 4
    def col_x(i): return MARGIN + i * (COL_W + GAP)
    Y_Q, H_Q = 0.92, 0.34          # quarter header
    Y_M, H_M = 1.30, 0.28          # month sub-headers
    # Pas de fleche de temps sous les mois: les quatre trimestres et leurs mois
    # disent deja le sens de lecture, et la bande rendait un demi-pouce de hauteur
    # a une decoration. Recupere, ce demi-pouce va aux cartes de jalons, qui sont
    # ce que la slide doit faire tenir.
    Y_TOP, Y_BOTTOM = 1.72, 7.18   # swimlane content band

    squads = [r for blk in data["tribes"] for r in blk["squads"]]

    def shape(s, kind, x, y, w, h, fill, *, line=None, rot=0, round_adj=None):
        sh = s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
        sh.fill.solid(); sh.fill.fore_color.rgb = fill
        if line is None:
            sh.line.fill.background()
        else:
            sh.line.color.rgb = line; sh.line.width = Pt(0.75)
        sh.shadow.inherit = False
        if rot:
            sh.rotation = rot
        if round_adj is not None:
            try:
                sh.adjustments[0] = round_adj
            except Exception:
                pass
        return sh

    def set_text(holder, text, size, color, *, bold=False, align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE):
        tf = holder.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.04)
        tf.margin_top = tf.margin_bottom = Emu(0)
        tf.vertical_anchor = anchor
        p = tf.paragraphs[0]; p.alignment = align
        r = p.add_run(); r.text = text
        r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color

    def textbox(s, x, y, w, h, runs, size, *, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
        box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Emu(0); tf.margin_top = tf.margin_bottom = Emu(0)
        tf.vertical_anchor = anchor
        p = tf.paragraphs[0]; p.alignment = align
        for txt, color, bold in runs:
            r = p.add_run(); r.text = txt
            r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color
        return box

    def draw_header(s):
        textbox(s, MARGIN, 0.22, 8.6, 0.5,
                [(f'{rt(lang, "roadmap_report")} - {data["scope_name"]}', C["dark"], True)], 22)
        textbox(s, MARGIN, 0.66, 8.6, 0.25,
                [(f'{rt(lang, "year")} {year}, {rt(lang, "generated_full", d=gen_str)}', C["muted"], False)], 10.5)
        legend = [("EA  ", STAGE["EA"], True), (rt(lang, "stage_ea") + "      ", C["dark"], False),
                  ("GA  ", STAGE["GA"], True), (rt(lang, "stage_ga"), C["dark"], False)]
        textbox(s, SLIDE_W - 5.9, 0.34, 5.4, 0.3, legend, 10, align=PP_ALIGN.RIGHT)
        for i, q in enumerate((1, 2, 3, 4)):
            x = col_x(i)
            set_text(shape(s, MSO_SHAPE.RECTANGLE, x, Y_Q, COL_W, H_Q, C["dark"]),
                     f'Q{q} {year}', 15, C["white"], bold=True)
            mw = (COL_W - 2 * 0.05) / 3
            for mi in range(3):
                mx = x + mi * (mw + 0.05)
                set_text(shape(s, MSO_SHAPE.RECTANGLE, mx, Y_M, mw, H_M, C["sub"]),
                         months[i * 3 + mi], 10, C["white"])

    def draw_card(s, x, y, w, h, items, fs, line_h):
        card = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, C["card"], round_adj=0.06)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.07); tf.margin_right = Inches(0.04)
        tf.margin_top = Inches(0.04); tf.margin_bottom = Inches(0.03)
        tf.vertical_anchor = MSO_ANCHOR.TOP
        if not items:
            return
        # Flatten into ordered paragraphs: a bold theme header then its milestones.
        specs: list[tuple[str, object]] = []
        for theme, group in group_by_theme(items):
            if theme:
                specs.append(("theme", theme))
            for it in group:
                specs.append(("item", it))
        item_fs = max(7, fs - 1.5)  # milestone lines a touch smaller than the theme header
        max_lines = max(1, int((h - 0.08) / line_h))
        shown = specs[:max_lines]
        for li, (kind, val) in enumerate(shown):
            p = tf.paragraphs[0] if li == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT  # themes + milestones are left-aligned, never centred
            p.space_after = Pt(0.5)
            if kind == "theme":
                r = p.add_run(); r.text = val
                r.font.size = Pt(fs); r.font.bold = True; r.font.color.rgb = C["card_ink"]
                continue
            it = val
            r1 = p.add_run(); r1.text = it["title"]
            r1.font.size = Pt(item_fs); r1.font.color.rgb = C["card_ink"]
            stage = it.get("stage")
            if stage:
                ro = p.add_run(); ro.text = " ("
                ro.font.size = Pt(item_fs); ro.font.color.rgb = C["card_ink"]
                rs = p.add_run(); rs.text = stage
                rs.font.size = Pt(item_fs); rs.font.bold = True
                rs.font.color.rgb = STAGE.get(stage, C["card_ink"])
                rc = p.add_run(); rc.text = ")"
                rc.font.size = Pt(item_fs); rc.font.color.rgb = C["card_ink"]
        if len(specs) > max_lines:
            p = tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            r = p.add_run(); r.text = f'+{len(specs) - max_lines}…'
            r.font.size = Pt(max(6, item_fs - 0.5)); r.font.color.rgb = C["muted"]

    def draw_swimlanes(s, lanes):
        # Everything fits on ONE slide: band height + fonts scale with the count,
        # but with a readable floor (small decks get a comfortably large font).
        n = max(1, len(lanes))
        band_h = (Y_BOTTOM - Y_TOP) / n
        card_fs = (13 if band_h >= 1.05 else 12 if band_h >= 0.85 else 11 if band_h >= 0.68
                   else 10 if band_h >= 0.52 else 9 if band_h >= 0.40 else 8)
        line_h = card_fs * 0.020
        label_fs = max(8.5, min(13, band_h * 12))
        lbl_h = min(0.36, band_h * 0.6)
        for ri, sq in enumerate(lanes):
            by = Y_TOP + ri * band_h
            bcy = by + band_h / 2
            lbl_len = max(0.35, min(band_h - 0.08, 1.7))
            lbl = shape(s, MSO_SHAPE.RECTANGLE, 0.24 - lbl_len / 2, bcy - lbl_h / 2,
                        lbl_len, lbl_h, C["dark"], rot=270)
            set_text(lbl, sq["name"], label_fs, C["white"], bold=True)
            qmap = {qd["q"]: qd["items"] for qd in (sq.get("detail") or {}).get("quarters", [])}
            for i, q in enumerate((1, 2, 3, 4)):
                draw_card(s, col_x(i), by + 0.04, COL_W, band_h - 0.08, qmap.get(q, []), card_fs, line_h)

    s = pptxtpl.add_slide(prs)  # single page, always
    draw_header(s)
    draw_swimlanes(s, squads)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def render_initiatives_pptx(data: dict, *, lang: str = "fr") -> bytes:
    """Render the initiatives list as a single branded table slide (max 18 rows)."""
    Presentation, Inches, Pt, Emu, RGBColor, PP_ALIGN, MSO_ANCHOR, MSO_SHAPE = _pptx_toolkit()

    def rgb(h):
        return RGBColor.from_string(h.lstrip("#").upper())

    B = {k: rgb(v) for k, v in _BRAND.items()}
    lang = _lang(lang)
    T = _INIT_T[lang]
    prs = pptxtpl.new_presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    margin = Inches(0.5)
    s = pptxtpl.add_slide(prs)
    head = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, Inches(0.92))
    head.fill.solid(); head.fill.fore_color.rgb = B["navy"]; head.line.fill.background(); head.shadow.inherit = False
    tf = head.text_frame; tf.margin_left = Inches(0.5); tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; r = p.add_run(); r.text = f'{T["title"]} - {data["scope_name"]}'
    r.font.size = Pt(22); r.font.bold = True; r.font.color.rgb = B["white"]

    headers = [T["h_init"], T["h_owner"], T["h_squad"], T["h_deadline"]]
    wfrac = [0.40, 0.24, 0.22, 0.14]
    items = data["items"][:18]
    nrows = max(2, len(items) + 1)
    table_w = int(prs.slide_width - margin * 2)
    tbl = s.shapes.add_table(nrows, 4, margin, Inches(1.2), Emu(table_w),
                             Inches(0.34) + Inches(0.3) * (nrows - 1)).table
    for ci, f in enumerate(wfrac):
        tbl.columns[ci].width = Emu(int(table_w * f))

    def cell(c, text, size, color, *, bold=False, align=PP_ALIGN.LEFT, fill=None):
        c.margin_left = Inches(0.06); c.margin_right = Inches(0.04); c.margin_top = Emu(0); c.margin_bottom = Emu(0)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        if fill is not None:
            c.fill.solid(); c.fill.fore_color.rgb = fill
        else:
            c.fill.background()
        c.text = text or " "
        pp = c.text_frame.paragraphs[0]; pp.alignment = align
        if pp.runs:
            rr = pp.runs[0]; rr.font.size = Pt(size); rr.font.bold = bold; rr.font.color.rgb = color

    for ci, h in enumerate(headers):
        cell(tbl.cell(0, ci), h, 11, B["white"], bold=True, fill=B["navy"])
    if not items:
        cell(tbl.cell(1, 0), T["none"], 10, B["muted"])
        for ci in range(1, 4):
            cell(tbl.cell(1, ci), " ", 10, B["muted"])
    for ri, it in enumerate(items, start=1):
        zebra = B["zebra"] if ri % 2 == 0 else B["white"]
        cells = [(it["title"], B["ink"], True), (it["owner"] or "-", B["ink"], False),
                 (it["squad_name"] or "-", B["ink"], False), (it["deadline"], B["ink"], False)]
        for ci, (val, color, bold) in enumerate(cells):
            cell(tbl.cell(ri, ci), val, 10, color, bold=bold, fill=zebra)
    buf = io.BytesIO(); prs.save(buf); return buf.getvalue()


def render_dependencies_pptx(data: dict) -> bytes:
    """Paginated table deck of milestone dependencies, grouped by the entity waited
    on. Rows flow across slides so no dependency is ever dropped."""
    Presentation, Inches, Pt, Emu, RGBColor, PP_ALIGN, MSO_ANCHOR, MSO_SHAPE = _pptx_toolkit()

    def rgb(hexstr: str) -> RGBColor:
        return RGBColor.from_string(hexstr.lstrip("#").upper())

    B = {k: rgb(v) for k, v in _BRAND.items()}
    lang = _lang(data.get("lang", "fr"))
    T = _DEP_T[lang]

    prs = pptxtpl.new_presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    SW = prs.slide_width
    margin = int(Inches(0.5))
    content_w = int(SW) - 2 * margin
    fracs = [0.405, 0.225, 0.075, 0.18, 0.115]
    aligns = [PP_ALIGN.LEFT, PP_ALIGN.LEFT, PP_ALIGN.CENTER, PP_ALIGN.LEFT, PP_ALIGN.CENTER]
    colw = [int(content_w * f) for f in fracs]
    colx, acc = [], margin
    for w in colw:
        colx.append(acc); acc += w
    ROW_H, HDR_H, GRP_H = int(Inches(0.30)), int(Inches(0.32)), int(Inches(0.46))
    TOP0, BOTTOM = int(Inches(1.25)), int(Inches(7.22))

    gen = data["generated_at"]
    gen_str = gen.strftime("%d/%m/%Y %H:%M") if isinstance(gen, datetime) else str(gen)

    def new_slide():
        return pptxtpl.add_slide(prs)

    def textbox(s, left, top, width, height, text, size, *, bold=False, color=None,
                align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE):
        box = s.shapes.add_textbox(Emu(int(left)), Emu(int(top)), Emu(int(width)), Emu(int(height)))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = Inches(0.05); tf.margin_right = Inches(0.05)
        tf.margin_top = Emu(0); tf.margin_bottom = Emu(0)
        p = tf.paragraphs[0]; p.alignment = align
        r = p.add_run(); r.text = text
        r.font.size = Pt(size); r.font.bold = bold
        r.font.color.rgb = color if color is not None else B["ink"]
        return box

    def rect(s, left, top, width, height, fill):
        sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(int(left)), Emu(int(top)), Emu(int(width)), Emu(int(height)))
        sh.fill.solid(); sh.fill.fore_color.rgb = fill
        sh.line.fill.background(); sh.shadow.inherit = False
        return sh

    def band(s, cont):
        rect(s, 0, 0, SW, Inches(1.05), B["navy"])
        textbox(s, margin, Inches(0.14), Inches(9.2), Inches(0.5),
                T["title"] + (T["suite"] if cont else ""), 22, bold=True, color=B["white"], anchor=MSO_ANCHOR.TOP)
        textbox(s, margin, Inches(0.64), Inches(9.2), Inches(0.3),
                f'{data["scope_name"]}, {rt(lang, "year")} {data["year"]}, '
                f'{T["total"].format(n=data["total"])}'
                # Un deck filtre doit le dire, sinon son compte se lit comme le
                # total et « aucune dependance » repond a une autre question.
                + (f', {T["cross_only"]}' if data.get("mode") == "cross_tribe" else ""),
                12, color=rgb("#C7D2FE"), anchor=MSO_ANCHOR.TOP)
        textbox(s, int(SW) - int(Inches(4.3)), Inches(0.32), Inches(3.8), Inches(0.4),
                rt(lang, "generated_full", d=gen_str), 10, color=rgb("#C7D2FE"), align=PP_ALIGN.RIGHT)

    def col_headers(s, y):
        rect(s, margin, y, content_w, HDR_H, B["navy"])
        for i, key in enumerate(("c_jalon", "c_squad", "c_trim", "c_owner", "c_status")):
            textbox(s, colx[i], y, colw[i], HDR_H, T[key], 9.5, bold=True, color=B["white"], align=aligns[i])
        return y + HDR_H

    def group_header(s, y, g, cont):
        rect(s, margin, y, content_w, GRP_H, rgb("#EEF2FF"))
        tlbl = {"tribe": T["t_tribe"], "squad": T["t_squad"], "text": T["t_text"]}.get(g["target_type"], "")
        if g["target_type"] == "squad" and g.get("target_tribe"):
            tlbl = f'{tlbl}, {g["target_tribe"]}'
        txt = f'▶  {g["target_label"]}   ({tlbl})' + (T["suite"] if cont else "")
        textbox(s, colx[0], y, content_w - int(Inches(2.4)), GRP_H, txt, 13, bold=True, color=B["navy"])
        textbox(s, margin + content_w - int(Inches(2.4)), y, Inches(2.3), GRP_H,
                T["gcount"].format(n=len(g["items"])), 10, color=B["muted"], align=PP_ALIGN.RIGHT)
        return y + GRP_H

    def trunc(x, n):
        x = x or ""
        return x if len(x) <= n else x[:n - 1] + "…"

    def data_row(s, y, it, zebra):
        if zebra:
            rect(s, margin, y, content_w, ROW_H, rgb("#F8FAFC"))
        vals = [trunc(it["jalon"], 62),
                trunc(f'{it["squad_name"]} ({it["tribe_name"]})', 34),
                f'Q{it["quarter"]} {str(it["year"])[2:]}',
                trunc(it["owner"] or "-", 24),
                _status_label(it["status"], lang)]
        colors = [B["ink"], B["muted"], B["ink"], B["ink"], rgb(_RAG_BRAND[_status_rag(it["status"])])]
        bolds = [True, False, False, False, True]
        for i, v in enumerate(vals):
            textbox(s, colx[i], y, colw[i], ROW_H, v, 9, bold=bolds[i], color=colors[i], align=aligns[i])
        return y + ROW_H

    if data["total"] == 0:
        s = new_slide(); band(s, False)
        textbox(s, margin, Inches(3.2), content_w, Inches(0.6), T["none"], 18, bold=True,
                color=B["muted"], align=PP_ALIGN.CENTER)
        buf = io.BytesIO(); prs.save(buf); return buf.getvalue()

    state = {"s": None, "y": 0}

    def open_slide(cont):
        s = new_slide(); band(s, cont)
        state["s"] = s; state["y"] = TOP0

    open_slide(False)
    for g in data["groups"]:
        if state["y"] + GRP_H + HDR_H + ROW_H > BOTTOM:
            open_slide(True)
        state["y"] = group_header(state["s"], state["y"], g, False)
        state["y"] = col_headers(state["s"], state["y"])
        for idx, it in enumerate(g["items"]):
            if state["y"] + ROW_H > BOTTOM:
                open_slide(True)
                state["y"] = group_header(state["s"], state["y"], g, True)
                state["y"] = col_headers(state["s"], state["y"])
            state["y"] = data_row(state["s"], state["y"], it, idx % 2 == 1)

    buf = io.BytesIO(); prs.save(buf); return buf.getvalue()
