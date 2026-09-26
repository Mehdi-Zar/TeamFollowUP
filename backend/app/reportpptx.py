"""PowerPoint rendering: the four decks the product exports.

Dashboard, roadmap swimlane, initiatives and cross-team dependencies. Kept apart
from ``report`` because it is 900 lines that share almost nothing with the HTML
path - eight names, all of which now live in ``reportcommon`` - and because the
python-pptx machinery reads very differently from string templating.

The public names stay importable from ``report`` as before: it re-exports them,
so nothing that used ``from .report import render_pptx`` had to change.
"""
from __future__ import annotations

import io
from datetime import datetime


from . import pptxtpl
from .reportcommon import (_people_line, _sep, fmt_date, fmt_datetime, fmt_money, MOOD_CLOUD, MOOD_CLOUD_BOX, MOOD_CLOUD_EYES,
                           MOOD_CLOUD_STROKE, OTD_SCOPE_COLOR,
                           STAGE_COLOR, _DEP_T, _INIT_T, _MONTHS, _lang,
                           _status_label, _status_rag, group_by_theme,
                           mood_cloud_mouth_points, mood_cloud_outline, mood_label,
                           rt, timeline_groups,
                           wrap_lines)


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


# Libelles propres aux decks. Ils vivent ici plutot que dans reportcommon: seul le
# PowerPoint les ecrit (une colonne, une legende, une mention de bas de slide que
# le HTML dit autrement).
_PT = {
    "fr": {
        "h_last": "Dernière saisie",
        "never": "jamais",
        "last_on": "dernière saisie le {d}",
        "last_never": "aucune saisie",
        "stale_since": "périmée depuis {n} j",
        "gen_on": "Généré le {d}",
        "as_of": "Version du {d}",
        "as_of_missing_one": "1 squad sans saisie à cette date : {names}",
        "as_of_missing": "{n} squads sans saisie à cette date : {names}",
        "continued": "suite",
        "km_more_one": "+1 autre message",
        "km_more": "+{n} autres messages",
        "late_frame": "Engagement en retard",
        "budget_empty": "Montants non renseignés",
        "budget_none": "Pas de budget dans ce document",
        "budget_off": "Budget non suivi pour cette squad",
        "blocked_one": "1 jalon bloqué",
        "blocked": "{n} jalons bloqués",
        "otd_late_one": "1 OTD en retard",
        "otd_late": "{n} OTD en retard",
        "nothing": "Rien à signaler.",
        "no_leave": "Aucune absence prévue.",
        "more": "+{n} autres",
        "no_leader": "Aucun squad leader",
        "not_reported": "Non renseigné",
    },
    "en": {
        "h_last": "Last update",
        "never": "never",
        "last_on": "last update {d}",
        "last_never": "no update yet",
        "stale_since": "stale for {n} d",
        "gen_on": "Generated on {d}",
        "as_of": "Version of {d}",
        "as_of_missing_one": "1 squad with no update at that date: {names}",
        "as_of_missing": "{n} squads with no update at that date: {names}",
        "continued": "continued",
        "km_more_one": "+1 more message",
        "km_more": "+{n} more messages",
        "late_frame": "Late commitment",
        "budget_empty": "Amounts not entered",
        "budget_none": "No budget in this document",
        "budget_off": "No budget tracking for this squad",
        "blocked_one": "1 blocked milestone",
        "blocked": "{n} blocked milestones",
        "otd_late_one": "1 late OTD",
        "otd_late": "{n} late OTDs",
        "nothing": "Nothing to report.",
        "no_leave": "No absence planned.",
        "more": "+{n} more",
        "no_leader": "No squad leader",
        "not_reported": "Not reported",
    },
}


def _pt(lang: str, key: str, n: int | None = None, **kw) -> str:
    """Un libelle du deck, au singulier quand n vaut 1 (cle suffixee _one)."""
    table = _PT["en" if lang == "en" else "fr"]
    if n is not None:
        kw["n"] = n
        if n == 1 and key + "_one" in table:
            key += "_one"
    s = table.get(key, key)
    return s.format(**kw) if kw else s


def _cut(text: str, n: int) -> str:
    """Coupe a n caracteres, sur un mot quand c'est possible, avec des points de
    suspension. PowerPoint n'en met pas: sans coupe il passe a la ligne et sort
    de la forme."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    head = text[:max(1, n - 1)]
    if " " in head[n // 2:]:
        head = head.rsplit(" ", 1)[0]
    # Un mot deja abrege (« environnem… ») ne recoit pas un second signe: il en
    # sortait « …… », et le deuxieme passait seul sur une ligne de plus.
    return head.rstrip(" ,;:.…") + "…"


def _cut_middle(text: str, n: int) -> str:
    """Coupe au milieu en gardant la fin: « Squad supplementaire 12 » et « ... 13 »
    restent distincts (« Squad sup…taire 12 »), la ou une coupe a droite donnait
    trois fois le meme « Squad supplementai… »."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    tail = max(1, (n - 1) // 2)
    head = max(1, n - 1 - tail)
    return text[:head].rstrip() + "…" + text[-tail:].lstrip()


def _wrap_fit(text: str, cpl: int, lines: int, *, reserve: int = 0) -> str:
    """Le texte qui tient sur ``lines`` lignes de ``cpl`` caracteres, coupe aux
    espaces comme PowerPoint le fera, la derniere ligne finie par « … » s'il en
    reste. ``reserve`` garde de la place en fin de derniere ligne (une phase
    « (GA) » ajoutee apres). Un mot plus long qu'une ligne est seul abrege.

    Couper au nombre total de caracteres ne suffit pas: un mot qui ne tient pas en
    fin de ligne passe a la suivante, et un « … » isole finissait sur une ligne
    de plus que la forme n'en a."""
    cpl, lines = max(1, int(cpl)), max(1, int(lines))
    words = [w if len(w) <= cpl else w[:max(1, cpl - 1)] + "…" for w in (text or "").split()]
    out, cur, i = [], "", 0
    while i < len(words):
        w = words[i]
        cand = f"{cur} {w}" if cur else w
        limit = cpl - (reserve if len(out) == lines - 1 else 0)
        if len(cand) <= limit:
            cur, i = cand, i + 1
            continue
        if len(out) == lines - 1 or not cur:
            # Derniere ligne pleine: elle finit sur un mot entier suivi de « … »
            # (« certifiees… » plutot que « certi… »). Un mot seul trop long pour
            # elle est le seul cas ou l'on coupe dans un mot.
            if cur and len(cur) + 1 <= limit:
                out.append(cur.rstrip(" ,;:.…") + "…")
            else:
                rest = " ".join([cur] + words[i:]) if cur else " ".join(words[i:])
                out.append(_cut(rest, max(2, limit)))
            return " ".join(out)
        out.append(cur)
        cur = ""
    if cur:
        out.append(cur)
    return " ".join(out)


def _pct(n, lang: str) -> str:
    """Un pourcentage comme on l'ecrit: « 48 % » (espace fine insecable) en
    francais, « 48% » en anglais. Le deck melangeait « 33 % » et « 48% »."""
    return f"{n}\u202f%" if lang != "en" else f"{n}%"


def _short_words(text: str, cpl: int) -> str:
    """Abrege les mots plus longs qu'une ligne (« environnem… »): PowerPoint les
    couperait au milieu, sans signe, et « deploiemen / t » se lit plus mal."""
    return " ".join(w if len(w) <= cpl else w[:max(1, cpl - 1)] + "…"
                    for w in (text or "").split())


def _version_line(data: dict, lang: str) -> str:
    """La mention d'une version passee, datee comme on l'ecrit et nommant les
    squads qui n'avaient rien soumis (et non plus « version du 2026-08-22 »)."""
    if not data.get("as_of"):
        return ""
    out = _pt(lang, "as_of", d=fmt_date(data["as_of"], lang))
    missing = data.get("as_of_missing") or []
    if missing:
        names = [m if isinstance(m, str) else (m.get("name") or "") for m in missing]
        out += ", " + _pt(lang, "as_of_missing", n=len(names), names=_cut(", ".join(names), 90))
    return out


def _last_update(r: dict, gen, lang: str) -> tuple[str, bool]:
    """La date de la derniere saisie d'une squad et si elle est perimee.

    Le rapport donne l'age en jours a la generation: la date s'en deduit, et c'est
    elle qu'on lit en comite (« il y a 13 jours » ne dit rien une semaine apres)."""
    from datetime import timedelta
    age = r.get("age_days")
    if age is None:
        return _pt(lang, "never"), True
    when = gen - timedelta(days=int(age)) if isinstance(gen, datetime) else None
    return (fmt_date(when.date(), lang) if when else f"J-{age}"), bool(r.get("is_stale"))


# Le corps du texte des decks: voir pptxtpl.FONT_SCALE. Les deux noms sont repris ici
# parce que la largeur d'une pastille se calcule au caractere, donc a partir du meme
# facteur que la police qu'elle entoure.
FONT_SCALE = pptxtpl.FONT_SCALE
_fs = pptxtpl.font_size


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
                align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, wrap=True):
        box = s.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = wrap
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Emu(0)
        tf.margin_top = tf.margin_bottom = Emu(0)
        p = tf.paragraphs[0]
        p.alignment = align
        r = p.add_run(); r.text = text
        r.font.size = Pt(_fs(size)); r.font.bold = bold
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
            r.font.size = Pt(_fs(size)); r.font.bold = bold; r.font.color.rgb = color
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
            r.font.size = Pt(_fs(size)); r.font.bold = bold; r.font.color.rgb = color
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
            r.font.size = Pt(_fs(size)); r.font.bold = bold; r.font.color.rgb = color

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
        w = Inches(0.26 + 0.082 * FONT_SCALE * len(text))
        sh = rrect(s, left, top, w, Inches(0.3), fill, radius=0.5)
        tf = sh.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = Inches(0.07)
        tf.margin_top = tf.margin_bottom = Emu(0)
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = text
        r.font.size = Pt(_fs(size)); r.font.bold = True
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
    gen_str = fmt_datetime(gen, lang) if isinstance(gen, datetime) else str(gen)
    # La version passee se dit a part, datee comme on l'ecrit, et non plus collee
    # a l'heure de generation en ISO.
    version = _version_line(data, lang)
    sm = data["summary"]
    squads = [r for blk in data["tribes"] for r in blk["squads"]]
    margin = Inches(0.5)

    # ---------------- Summary one-pager (report kind) -----------------------------
    # Le tableau des squads ne cache plus rien: au-dela de ce qu'une slide tient,
    # il continue sur la suivante. « +3 autres squads » faisait disparaitre une
    # squad a risque derriere des squads vertes.
    ROWS_FIRST, ROWS_NEXT = 14, 20

    def summary_header(s, cont: bool):
        band = rect(s, Inches(0), Inches(0), prs.slide_width, Inches(1.12), B["navy"])
        title = f'{data["app_name"]} | {rt(lang, "dashboard_doc" if data.get("doc") == "dashboard" else "report")}'
        if cont:
            title += f' ({_pt(lang, "continued")})'
        # Title + subtitle are the band's own text; the right-corner meta stays a
        # corner label (left title and right meta can't share one text frame).
        place(band, [
            (title, 26, B["white"], True, PP_ALIGN.LEFT, 5),
            (f'{data["scope_name"]}, {rt(lang, "year")} {data["year"]}', 13, rgb("#C7D2FE"), False, PP_ALIGN.LEFT, 0),
        ], anchor=MSO_ANCHOR.TOP, ml=0.55, mt=0.18, mr=4.2)
        meta = rt(lang, "generated_full", d=gen_str)
        if not data.get("as_of"):
            meta += "\n" + rt(lang, "window_full", n=data["since_days"])
        textbox(s, Inches(9.3), Inches(0.3), Inches(3.5), Inches(0.6), meta, 11,
                color=rgb("#C7D2FE"), align=PP_ALIGN.RIGHT)

    def squad_table(s, rows, top):
        headers = [rt(lang, "h_squad"), rt(lang, "h_leader"), rt(lang, "h_status"),
                   rt(lang, "h_progress"), rt(lang, "h_blocked"), rt(lang, "h_atrisk"),
                   _pt(lang, "h_last")]
        wfrac = [0.27, 0.20, 0.12, 0.10, 0.09, 0.09, 0.13]
        # Une version passee n'a pas de « derniere saisie » a montrer: l'age porte
        # par les donnees est celui d'aujourd'hui, pas celui de la version.
        if data.get("as_of"):
            headers, wfrac = headers[:-1], [0.30, 0.235, 0.13, 0.115, 0.11, 0.11]
        table_w = int(prs.slide_width - margin * 2)
        widths = [Emu(int(table_w * f)) for f in wfrac]
        nrows = len(rows) + 1
        tbl = s.shapes.add_table(max(nrows, 2), len(headers), margin, top, Emu(table_w),
                                 Inches(0.34) + Inches(0.255) * (nrows - 1)).table
        for ci, w in enumerate(widths):
            tbl.columns[ci].width = w
        for ci, h in enumerate(headers):
            align = PP_ALIGN.LEFT if ci < 2 else PP_ALIGN.CENTER
            style_cell(tbl.cell(0, ci), h, 10, B["white"], bold=True, align=align, fill=B["navy"])
        for ri, r in enumerate(rows, start=1):
            zebra = B["zebra"] if ri % 2 == 0 else B["white"]
            last, stale = _last_update(r, gen, lang)
            # Une squad qui n'a jamais rien saisi n'est pas « En cours » en vert:
            # rien ne le mesure. (Une version passee garde le statut de sa date.)
            if r.get("age_days") is None and not data.get("as_of"):
                st_txt, st_col = _pt(lang, "not_reported"), rgb(_RAG_BRAND["grey"])
            else:
                st_txt, st_col = _status_label(r["status"], lang), rgb(_RAG_BRAND[r["status_rag"]])
            cells = [
                (_cut(r["name"], 34), B["ink"], True, PP_ALIGN.LEFT),
                (_cut(r["leader"] or "-", 26), B["muted"], False, PP_ALIGN.LEFT),
                (st_txt, st_col, True, PP_ALIGN.CENTER),
                (_pct(r["annual_pct"], lang), B["ink"], False, PP_ALIGN.CENTER),
                (str(r["blocked"] or "-"), B["red"] if r["blocked"] else B["muted"], r["blocked"] > 0, PP_ALIGN.CENTER),
                (str(r["at_risk"] or "-"), B["orange"] if r["at_risk"] else B["muted"], r["at_risk"] > 0, PP_ALIGN.CENTER),
                # Une saisie perimee se voit sur sa ligne, pas seulement dans le
                # total de la tuile du dessus.
                (last, B["orange"] if stale else B["muted"], stale, PP_ALIGN.CENTER),
            ][:len(headers)]
            for ci, (val, color, bold, align) in enumerate(cells):
                style_cell(tbl.cell(ri, ci), val, 9.5, color, bold=bold, align=align, fill=zebra)

    def summary_slide():
        s = new_slide()
        summary_header(s, False)
        kpis = [
            (rt(lang, "k_squads"), str(sm["squads_total"]), B["navy"]),
            (rt(lang, "k_progress"), _pct(sm["avg_progress"], lang), B["accent"]),
            (rt(lang, "k_blocked"), str(sm["blocked"]), B["red"] if sm["blocked"] else B["ink"]),
            (rt(lang, "k_atrisk"), str(sm["at_risk"]), B["orange"] if sm["at_risk"] else B["ink"]),
            (rt(lang, "k_otd_late"), str(sm["otd_late"]), B["red"] if sm["otd_late"] else B["ink"]),
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
        top = 2.62
        if version:
            # Un document date qui ne se dit pas date a l'air du rapport du jour.
            textbox(s, margin, Inches(2.44), prs.slide_width - margin * 2, Inches(0.2),
                    _cut(version, 150), 10, bold=True, color=B["orange"])
            top = 2.72
        squad_table(s, squads[:ROWS_FIRST], Inches(top))
        rest = squads[ROWS_FIRST:]
        while rest:
            s = new_slide()
            summary_header(s, True)
            squad_table(s, rest[:ROWS_NEXT], Inches(1.34))
            rest = rest[ROWS_NEXT:]

    # ---------------- Points d'attention (rapport hebdo) ---------------------------
    # Le deck hebdo annoncait une fenetre de sept jours et montrait la meme chose
    # que le tableau de bord. Ce que le HTML dit en plus (les squads a regarder,
    # les engagements que personne ne porte, les absences qui arrivent) a ici sa
    # slide, juste apres la synthese.
    def attention_slide():
        s = new_slide()
        summary_header(s, False)
        cols = [
            (rt(lang, "attention"), [], _pt(lang, "nothing")),
            (rt(lang, "h_tribe_otds"), [], _pt(lang, "nothing")),
        ]
        # Les absences n'ont une colonne que si le module est actif: sinon
        # « Aucune absence prevue » affirmait ce que personne ne saisit.
        if data.get("leaves_enabled", True):
            cols.append((rt(lang, "leaves_upcoming"), [], _pt(lang, "no_leave")))
        for r in data.get("attention") or []:
            bits = []
            if r.get("blocked"):
                bits.append(_pt(lang, "blocked", n=r["blocked"]))
            # Un engagement en retard met la squad dans la liste: il se dit aussi.
            if r.get("otd_late"):
                bits.append(_pt(lang, "otd_late", n=r["otd_late"]))
            if r.get("is_stale"):
                last, _st = _last_update(r, gen, lang)
                bits.append(f'{_pt(lang, "last_on", d=last)} ({_pt(lang, "stale_since", n=r["age_days"])})'
                            if r.get("age_days") is not None else _pt(lang, "last_never"))
            cols[0][1].append((r["name"], ", ".join(bits),
                               B["red"] if r.get("blocked") or r.get("otd_late") else B["orange"]))
        for o in data.get("tribe_otds") or []:
            late = o.get("status") == "late"
            when = fmt_date(o["date"], lang) if o.get("date") else rt(lang, "tl_no_date_short")
            cols[1][1].append((o["title"], when + (f', {rt(lang, "otd_late").lower()}' if late else ""),
                               B["red"] if late else B["navy"]))
        for lv in (data.get("leaves_upcoming") or []) if len(cols) > 2 else []:
            extra = f' ({rt(lang, "leaves_pending")})' if lv.get("status") == "pending" else ""
            cols[2][1].append((lv["name"], f'{lv["start"]} - {lv["end"]}, {lv["days"]:g} {rt(lang, "days_short")}{extra}',
                               B["ink"]))
        nc = len(cols)
        cw = (13.333 - 1.0 - (nc - 1) * 0.2) / nc
        for i, (title, rows, empty) in enumerate(cols):
            x = 0.5 + i * (cw + 0.2)
            sh = rrect(s, Inches(x), Inches(1.34), Inches(cw), Inches(5.8), B["white"], line=B["line"], radius=0.03)
            paras = [(title, 13, B["navy"], True, PP_ALIGN.LEFT, 8)]
            # La place se compte en lignes, et chaque texte passe a la ligne
            # (deux au plus): coupee sur une seule, « dernière saisie le ... »
            # perdait justement « (périmée depuis 13 j) ».
            cpl = int((cw - 0.4) / (0.0068 * _fs(10.5)))
            line = _fs(10.5) * 1.2 / 72.0
            budget = (5.8 - 0.16 - 0.1 - _fs(13) * 1.2 / 72.0 - 8 / 72.0) - line  # garde la ligne « +N »
            used, shown = 0.0, 0
            for name, info, color in rows:
                nl, il = min(2, wrap_lines(name, cpl)), (min(2, wrap_lines(info, cpl)) if info else 0)
                need = (nl + il) * line + 6 / 72.0
                if used + need > budget:
                    break
                paras.append((_wrap_fit(name, cpl, nl), 10.5, color, True, PP_ALIGN.LEFT, 0))
                if info:
                    paras.append((_wrap_fit(info, cpl, il), 10, B["muted"], False, PP_ALIGN.LEFT, 6))
                used += need
                shown += 1
            if len(rows) > shown:
                paras.append((_pt(lang, "more", n=len(rows) - shown), 10, B["muted"], False, PP_ALIGN.LEFT, 0))
            if not rows:
                paras.append((empty, 10.5, B["muted"], False, PP_ALIGN.LEFT, 0))
            place(sh, paras, anchor=MSO_ANCHOR.TOP, ml=0.2, mt=0.16, mr=0.2)

    # ---------------- Une slide par squad: la frise de l'annee --------------------
    #
    # Trois etages, et un seul sens de lecture: les trimestres et les mois en
    # tete, les engagements poses sur leur mois, puis les boites de jalons, reliees
    # a leur date par un trait qui ne remonte jamais plus haut que les
    # engagements. C'est ce qui garantit qu'aucun trait ne traverse un titre.
    LBL_X, LBL_W = 0.50, 1.58          # colonne des libelles, a gauche de l'axe
    AX0, AX1 = 2.20, 12.80             # l'axe des douze mois
    MW = (AX1 - AX0) / 12.0            # largeur nominale d'un mois
    QW = MW * 3                        # un trimestre vaut trois mois
    # L'axe est decoupe **par trimestre**, dans les deux bandes a la fois: un
    # trimestre et ses trois mois forment un bloc, et la meme gouttiere separe deux
    # blocs en haut comme en bas. La bande des mois etait d'un seul tenant sous des
    # cartes de trimestre separees: rien ne disait ou Q1 s'arretait, et mars avait
    # l'air de deborder du trimestre qui le contient.
    Q_GAP = 0.09                       # la gouttiere entre deux blocs
    QIW = QW - Q_GAP                   # largeur utile d'un bloc de trimestre
    MIW = QIW / 3.0                    # largeur d'un mois dans son bloc

    def qx(q: int) -> float:
        """Le bord gauche du bloc du trimestre q (0 a 3)."""
        return AX0 + q * QW + Q_GAP / 2

    def mx0(m: int) -> float:
        """Le bord gauche du mois m (0 a 11), dans le bloc de son trimestre."""
        return qx(m // 3) + (m % 3) * MIW
    # La carte d'un trimestre porte une ligne de titre puis sa barre d'avancement:
    # sa hauteur se **deduit du corps du texte**, elle n'est plus un nombre pose a
    # la main. La barre etait a 0,25 pouce du haut, ce qui la mettait juste sous une
    # ligne de 13 points; le corps ayant grandi, la ligne descend plus bas et
    # « Q4  50 % » se retrouvait ecrit par-dessus sa propre barre.
    Q_FS = 13                          # le corps du titre d'un trimestre
    Q_PAD = 0.04                       # la marge interieure de la carte
    Q_LINE = _fs(Q_FS) * 1.2 / 72.0    # la hauteur d'une ligne, au corps reel
    Q_BAR_H = 0.12                     # l'epaisseur de la barre
    Q_BAR_Y = Q_PAD + Q_LINE + 0.02    # la barre, juste sous le titre
    QY, QH = 1.38, Q_BAR_Y + Q_BAR_H + Q_PAD     # la rangee des trimestres
    BAND_Y, BAND_H = QY + QH + 0.04, 0.26        # la bande des mois, juste dessous
    SEP_Y = BAND_Y + BAND_H
    OTD_Y = SEP_Y + 0.08               # la bande des engagements
    STAR_S = 0.13                      # l'etoile d'un engagement, posee sur sa date
    OTD_MAX_LINES = 6                  # un titre d'engagement tient dans la largeur
    OTD_MAX_H = 1.05                   #   d'un mois, sans jamais se couper, et la
                                       #   bande ne prend pas plus d'un pouce: au-dela
                                       #   il ne reste rien pour les jalons
    OTD_GAP = 0.07                     # entre deux engagements du meme mois
    GUTTER = 0.26                      # entre les engagements et les boites
    BOX_BOTTOM = 5.82                  # le bas des boites (autant de hauteur qu'avant)
    BOX_GAP = 0.12                     # entre deux boites
    BOX_MIN_W = 1.25                   # la largeur sous laquelle un titre de
                                       #   jalon casse ses mots en deux
    TICK = 0.15                        # la coche de statut d'un jalon: a 0,10 pouce
                                       #   elle faisait deux millimetres et ne se
                                       #   voyait pas une fois la slide projetee

    def fit(text: str, chars: int) -> str:
        """Coupe a la largeur disponible. PowerPoint ne sait pas mettre de points
        de suspension: sans coupe il passe a la ligne et sort de la forme."""
        text = text or ""
        return text if len(text) <= chars else text[:max(1, chars - 1)].rstrip() + "\u2026"

    def polygon(s, points, fill, *, line=None, width=None):
        """Un polygone ferme, dessine point par point.

        PowerPoint n'a pas de forme qui ressemble au nuage de l'application: la
        forme « nuage » du logiciel a ses propres bosses, et l'icone du document
        n'etait donc pas celle qu'on voit a l'ecran. Un polygone, lui, se dessine
        exactement comme on l'ecrit, et les deux supports peuvent lire la meme
        description.
        """
        builder = s.shapes.build_freeform(Inches(points[0][0]), Inches(points[0][1]))
        builder.add_line_segments([(Inches(px), Inches(py)) for px, py in points[1:]],
                                  close=True)
        sh = builder.convert_to_shape()
        if fill is None:
            sh.fill.background()
        else:
            sh.fill.solid(); sh.fill.fore_color.rgb = fill
        if line is None:
            sh.line.fill.background()
        else:
            sh.line.color.rgb = line
            if width is not None:
                sh.line.width = width
        sh.shadow.inherit = False
        return sh

    def mood_cloud(s, x, y, w, mood):
        """Le nuage du moral, le meme dessin que dans l'application.

        Contour, yeux et bouche viennent de la description partagee avec le HTML
        (repere de 64 x 46): un emoji dependrait de la police installee sur le
        poste qui ouvre le fichier, et la forme « nuage » de PowerPoint donnait
        une autre silhouette que celle de l'ecran, donc une autre icone.
        """
        pal = MOOD_CLOUD[mood]
        ink, fill = rgb(pal["ink"]), rgb(pal["fill"])
        bw, bh = MOOD_CLOUD_BOX
        h = w * bh / bw
        sx, sy = w / bw, h / bh

        def at(px, py):
            return (x + px * sx, y + py * sy)

        polygon(s, [at(px, py) for px, py in mood_cloud_outline()], fill,
                line=ink, width=Pt(1.6))

        for (ex, ey), r in MOOD_CLOUD_EYES:
            o = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + (ex - r) * sx),
                                   Inches(y + (ey - r) * sy),
                                   Inches(2 * r * sx), Inches(2 * r * sy))
            o.fill.solid(); o.fill.fore_color.rgb = ink
            o.line.fill.background(); o.shadow.inherit = False

        # La bouche est un trait epais: la slide ne connait que des segments, donc
        # on la dessine comme une bande, la courbe et son decalage vers le haut.
        curve = mood_cloud_mouth_points(mood)
        if not curve:
            return
        th = MOOD_CLOUD_STROKE
        band = ([at(px, py + th / 2) for px, py in curve]
                + [at(px, py - th / 2) for px, py in reversed(curve)])
        polygon(s, band, ink)

    def squad_slide(r):
        det = r.get("detail") or {}
        s = new_slide()
        rect(s, Inches(0), Inches(0), prs.slide_width, prs.slide_height, rgb("#F5F7FA"))

        # ----- entete: la squad, son responsable, et le moral a droite -----
        # Tout le haut de la slide remonte: la marge au-dessus de l'entete etait
        # plus large que tout le reste, et la legende, faute de place, finissait
        # collee au bord bas de la slide.
        hdr = rrect(s, Inches(0.4), Inches(0.14), Inches(10.72), Inches(0.74), B["navy"], radius=0.08)
        # Le nom tient sur une ligne: le corps descend d'un cran pour un nom long,
        # puis le nom se coupe. Sur deux lignes, il sortait par le haut du bandeau
        # et poussait la ligne du responsable sous la frise.
        HDR_W = 10.72 - 0.56
        name = r["name"] or ""
        for name_fs in (20, 16, 14):
            name_cpl = int(HDR_W / (0.0085 * _fs(name_fs)))
            if len(name) <= name_cpl:
                break
        name = _cut(name, name_cpl)
        # La date de la derniere saisie est dans l'en-tete: une slide d'une seule
        # squad n'avait aucune date, et une squad perimee s'y lisait comme a jour.
        last, stale = _last_update(r, gen, lang)
        when = (_pt(lang, "last_never") if r.get("age_days") is None
                else _pt(lang, "last_on", d=last))
        if stale and r.get("age_days") is not None:
            when += f' ({_pt(lang, "stale_since", n=r["age_days"])})'
        if data.get("as_of"):
            when, stale = "", False
        leader = (f'{rt(lang, "h_leader")}{_sep(lang)}{r["leader"]}' if r.get("leader")
                  else _pt(lang, "no_leader"))
        info = (f'{leader}, {rt(lang, "year")} {data["year"]}, '
                f'{rt(lang, "h_progress_long")} {_pct(r["annual_pct"], lang)}' + (", " if when else ""))
        people = _people_line(r, lang)
        info_cpl = int(HDR_W / (0.0075 * _fs(12)))
        people = _cut(people, max(0, info_cpl - len(info) - len(when) - 2)) if people else ""
        place(hdr, [(name, name_fs, B["white"], True, PP_ALIGN.LEFT, 3)],
              anchor=MSO_ANCHOR.MIDDLE, ml=0.28, mr=0.28)
        p2 = hdr.text_frame.add_paragraph()
        p2.alignment = PP_ALIGN.LEFT
        for txt, color, bold in ((info, rgb("#CDD8F5"), False),
                                 (when, rgb("#FDBA74") if stale else rgb("#CDD8F5"), stale),
                                 (people, rgb("#CDD8F5"), False)):
            if not txt:
                continue
            run = p2.add_run(); run.text = txt
            run.font.size = Pt(_fs(12)); run.font.bold = bold; run.font.color.rgb = color

        # Le moral: trois niveaux, et la date qui les date. Un moral de mars
        # projete en septembre ment plus surement qu'une case vide.
        mood = r.get("mood")
        # Pas de nuage quand rien n'est declare: un nuage gris se lirait comme un
        # quatrieme niveau, alors que « non renseigne » n'en est pas un.
        mcard = rrect(s, Inches(11.20), Inches(0.14), Inches(1.73), Inches(0.74),
                      B["white"], line=B["line"], radius=0.08)
        # « Team » au-dessus, « Mood » en dessous, le nuage a droite: le niveau se
        # lit sur le visage et sur la couleur, et l'ecrire en toutes lettres a cote
        # revenait a le dire deux fois dans deux centimetres.
        place(mcard, [(rt(lang, "mood_l1"), 12, B["navy"], True, PP_ALIGN.LEFT, 0),
                      (rt(lang, "mood_l2"), 12, B["navy"], True, PP_ALIGN.LEFT, 0)],
              anchor=MSO_ANCHOR.MIDDLE, ml=0.14, mr=0.75, mt=0.04, mb=0.04)
        if mood in MOOD_CLOUD:
            mood_cloud(s, 12.18, 0.22, 0.56, mood)
        else:
            textbox(s, Inches(11.95), Inches(0.39), Inches(0.90), Inches(0.24),
                    mood_label(mood, lang), 9, color=B["muted"], align=PP_ALIGN.CENTER)
        # La date se range au-dessus de la carte, seule dans le coin de la slide, et
        # non dans l'encadre du visage. Elle date le moral, elle ne le dit pas: a
        # l'interieur, elle prenait le meme rang que le niveau, qui est la seule
        # chose a lire de loin.
        if r.get("mood_at"):
            textbox(s, Inches(10.90), Inches(0.00), Inches(2.03), Inches(0.13),
                    rt(lang, "mood_at", d=fmt_date(r["mood_at"], lang)), 8, color=B["muted"],
                    align=PP_ALIGN.RIGHT)

        # ----- la carte de la frise -----
        card(s, Inches(0.4), Inches(0.96), Inches(12.53), Inches(5.08),
             rt(lang, "h_timeline", year=data["year"]))

        # Un trimestre, son avancement, sa barre. Rien d'autre: le commentaire du
        # trimestre s'inserait entre l'en-tete et la bande des mois, ou il coupait
        # la lecture de l'axe juste la ou elle commence. Il reste dans l'ecran et
        # dans le rapport HTML, qui n'ont pas de hauteur a tenir.
        from pptx.enum.dml import MSO_LINE_DASH_STYLE
        from pptx.enum.shapes import MSO_CONNECTOR
        from pptx.oxml.ns import qn

        months = _MONTHS[_lang(lang)]
        otds = det.get("otds") or []
        groups = timeline_groups(det)

        def marker_label(x, y, w, h, runs, fs, *, align=PP_ALIGN.LEFT,
                         anchor=MSO_ANCHOR.TOP):
            """Un libelle, sous son etoile ou a cote de sa coche."""
            box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
            tf = box.text_frame
            tf.word_wrap = True
            tf.margin_left = tf.margin_right = Emu(0)
            tf.margin_top = tf.margin_bottom = Emu(0)
            tf.vertical_anchor = anchor
            para = tf.paragraphs[0]
            para.alignment = align
            for text, color, bold in runs:
                run = para.add_run()
                run.text = text
                run.font.size = Pt(_fs(fs)); run.font.bold = bold; run.font.color.rgb = color
            return box

        # La coche d'un jalon dit les trois etats demandes par le dessin et pas
        # seulement par la couleur: **fait** = pastille pleine et cochee, **en
        # cours** = anneau avec un point au centre, **pas commence** = anneau vide.
        # Deux anneaux identiques ne distinguaient pas ce qui avance de ce qui
        # dort, et une couleur seule ne se lit pas une fois la slide projetee.
        CHECK = [(0.10, 0.50), (0.38, 0.80), (0.90, 0.18), (1.00, 0.30),
                 (0.38, 1.00), (0.00, 0.62)]

        def status_tick(x, y, status):
            ink = rgb(_RAG_BRAND[_status_rag(status)])
            ring = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y),
                                      Inches(TICK), Inches(TICK))
            ring.line.color.rgb = ink; ring.line.width = Pt(1.5)
            ring.shadow.inherit = False
            if status != "done":
                ring.fill.background()
                if status:                 # en cours, a risque, bloque
                    d = TICK * 0.40
                    dot = s.shapes.add_shape(MSO_SHAPE.OVAL,
                                             Inches(x + (TICK - d) / 2),
                                             Inches(y + (TICK - d) / 2),
                                             Inches(d), Inches(d))
                    dot.fill.solid(); dot.fill.fore_color.rgb = ink
                    dot.line.fill.background(); dot.shadow.inherit = False
                return
            ring.fill.solid(); ring.fill.fore_color.rgb = ink
            s_ = TICK * 0.62
            ox, oy = x + TICK * 0.19, y + TICK * 0.16
            pts = [(ox + px * s_, oy + py * s_) for px, py in CHECK]
            builder = s.shapes.build_freeform(Inches(pts[0][0]), Inches(pts[0][1]))
            builder.add_line_segments([(Inches(px), Inches(py)) for px, py in pts[1:]],
                                      close=True)
            mark = builder.convert_to_shape()
            mark.fill.solid(); mark.fill.fore_color.rgb = B["white"]
            mark.line.fill.background(); mark.shadow.inherit = False

        quarters = {qd["q"]: qd for qd in det.get("quarters") or []}
        for i, q in enumerate((1, 2, 3, 4)):
            qd = quarters.get(q) or {"pct": 0}
            pct = max(0, min(100, int(qd.get("pct") or 0)))
            # La carte d'un trimestre couvre **exactement ses trois mois**: elle
            # commence au bord gauche du premier et finit au bord droit du
            # troisieme, si bien que la coupure entre deux cartes tombe sur la
            # coupure entre deux mois. Elle etait plus courte d'une gouttiere prise
            # entierement a droite: Q1 s'arretait avant la fin de mars, et sa bande
            # ne se superposait a celle des mois nulle part. Le trait de la carte
            # suffit a separer deux trimestres, comme il separe deux mois dans la
            # bande du dessous.
            x = qx(i)
            qc = rrect(s, Inches(x), Inches(QY), Inches(QIW), Inches(QH),
                       rgb("#E8F0FE"), line=B["line"], radius=0.08)
            planned = bool(qd.get("items"))
            # « rien de prevu » seulement si le trimestre est vraiment vide: une
            # boite posee a la date d'un engagement de ce trimestre peut porter des
            # jalons comptes dans un autre, et la mention la contredisait.
            occupied = any((o.get("month") or 0) // 3 == i for o in otds if o.get("month") is not None)                 or any(g["month"] // 3 == i for g in groups)
            empty_lbl = "-" if occupied else rt(lang, "q_nothing")
            place(qc, [(f'Q{q}    {_pct(pct, lang)}' if planned else f'Q{q}    {empty_lbl}',
                        Q_FS, B["navy"] if planned else B["muted"], True, PP_ALIGN.LEFT, 0)],
                  anchor=MSO_ANCHOR.TOP, ml=0.08, mt=Q_PAD, mr=0.08)
            if planned:  # nothing planned: no empty bar that reads as 0 % delivered
                pbar(s, Inches(x + 0.08), Inches(QY + Q_BAR_Y), Inches(QIW - 0.16), pct, B["accent"])

        # Les mois, qui donnent la resolution de l'axe, juste sous les trimestres:
        # un trimestre et ses trois mois se lisent ensemble, et rien ne doit
        # s'inserer entre les deux. Un mois sur deux est legerement plus fonce,
        # pour que l'oeil compte les colonnes sans avoir a lire les noms.
        for i in range(4):
            rect(s, Inches(qx(i)), Inches(BAND_Y), Inches(QIW), Inches(BAND_H), rgb("#EEF2F7"))
        for i, m in enumerate(months):
            # Le mois du milieu de chaque bloc est legerement plus fonce: l'oeil
            # compte les trois colonnes d'un trimestre sans avoir a lire les noms.
            if i % 3 == 1:
                rect(s, Inches(mx0(i)), Inches(BAND_Y), Inches(MIW), Inches(BAND_H),
                     rgb("#E3E9F2"))
            textbox(s, Inches(mx0(i)), Inches(BAND_Y + 0.035), Inches(MIW), Inches(0.20),
                    m, 11, color=B["ink"], align=PP_ALIGN.CENTER)
        rect(s, Inches(LBL_X), Inches(SEP_Y), Inches(AX1 - LBL_X), Inches(0.012), B["line"])

        # ----- les engagements, chacun dans sa case de mois --------------------
        #
        # Un engagement tient dans la largeur d'un mois, pas plus: son titre passe
        # a la ligne. Etale a cote de son etoile, il courait sur trois ou quatre
        # mois et on ne savait plus a quelle colonne il repondait. Deux engagements
        # du meme mois se suivent dans la meme colonne, l'un sous l'autre.
        # La case d'un engagement laisse un couloir libre a ses deux bords: c'est
        # par la que passent les traits des boites, en ligne droite, sans jamais
        # toucher un titre.
        CELL_W = MIW - 0.14
        # Une ligne de texte fait 1,2 fois le corps, soit fs/72*1,2 pouce. Sous-
        # estimee, elle laissait le titre d'un engagement mordre sur la gouttiere.

        by_month: dict[int, list] = {}
        for o in otds:
            if o.get("month") is not None:
                by_month.setdefault(o["month"], []).append(o)

        def otd_band(fs: float, max_lines: int = OTD_MAX_LINES):
            """La hauteur de la bande a ce corps, et le nombre de lignes par titre.

            Un titre tient dans la largeur d'une case de mois. Le corps descend
            d'un cran tant que la bande depasse sa hauteur maximale: sans cela,
            deux engagements du meme mois occupent la moitie de la frise et il ne
            reste plus rien pour les jalons. Il ne se coupe pas pour autant, et
            c'est la bande des jalons qui se resserre en dernier ressort.
            """
            cpl = max(6, int(CELL_W / (0.0071 * _fs(fs))))
            line = _fs(fs) * 0.0170
            longest = max((len(w) for column in by_month.values() for o in column
                           for w in o["title"].split()), default=0)
            lines = {id(o): min(max_lines, wrap_lines(o["title"], cpl))
                     for column in by_month.values() for o in column}
            height = max((sum(STAR_S + 0.02 + lines[id(o)] * line + OTD_GAP
                              for o in column) - OTD_GAP
                          for column in by_month.values()), default=0.0)
            return height, cpl, line, lines, cpl >= longest

        # Une case de mois est etroite: deux crans de plus et « interruption » se
        # coupe en deux au milieu du titre, ce qui se lit plus mal que le meme
        # titre ecrit un point plus petit. On prend donc le plus grand corps qui
        # tienne la hauteur **sans couper un mot**, et on ne retombe sur un mot
        # coupe que si aucun corps n'y arrive.
        best = None
        # L'echelle descend deux crans plus bas que le corps le plus petit
        # qu'on veuille lire: FONT_SCALE la releve toute entiere, et sans ces
        # deux crans une frise chargee ne trouverait plus aucun corps qui tienne.
        # Le corps ne descend pas sous 7 (8 points une fois le facteur commun
        # applique): plus bas, le titre ne se lit plus projete. Si la bande ne
        # tient toujours pas, les titres perdent des lignes et finissent par « … ».
        for OTD_FS in (9, 8.5, 8, 7.5, 7):
            otd_h, OTD_CPL, OTD_LINE, otd_lines, whole = otd_band(OTD_FS)
            if otd_h <= OTD_MAX_H:
                # Sans corps qui garde tous les mots entiers, le plus petit qui
                # tient: c'est celui qui en coupe le moins.
                best = (OTD_FS, otd_h, OTD_CPL, OTD_LINE, otd_lines)
                if whole:
                    break
        else:
            if best is not None:
                OTD_FS, otd_h, OTD_CPL, OTD_LINE, otd_lines = best
            else:
                for cap in range(OTD_MAX_LINES - 1, 0, -1):
                    otd_h, OTD_CPL, OTD_LINE, otd_lines, _w = otd_band(7, cap)
                    if otd_h <= OTD_MAX_H:
                        break
                OTD_FS = 7
        otd_bottom = (OTD_Y + otd_h) if by_month else SEP_Y + 0.04

        if by_month:
            textbox(s, Inches(LBL_X), Inches(OTD_Y), Inches(LBL_W), Inches(0.18),
                    rt(lang, "h_otd_section"), 10, bold=True, color=B["navy"])
        for month, column in by_month.items():
            cy = OTD_Y
            mx = mx0(month) + MIW / 2
            for o in column:
                ink = rgb(OTD_SCOPE_COLOR.get(o.get("scope") or "management", "#1E2761"))
                star = s.shapes.add_shape(MSO_SHAPE.STAR_5_POINT, Inches(mx - STAR_S / 2),
                                          Inches(cy), Inches(STAR_S), Inches(STAR_S))
                star.fill.solid(); star.fill.fore_color.rgb = ink
                star.line.fill.background(); star.shadow.inherit = False
                lines = otd_lines[id(o)]
                textbox(s, Inches(mx - CELL_W / 2), Inches(cy + STAR_S + 0.02),
                        Inches(CELL_W), Inches(lines * OTD_LINE),
                        _wrap_fit(o["title"], OTD_CPL, lines), OTD_FS,
                        bold=True, color=ink,
                        align=PP_ALIGN.CENTER)
                cy += STAR_S + 0.02 + lines * OTD_LINE + OTD_GAP

        # ----- les boites de jalons -------------------------------------------
        #
        # Une boite par engagement (ou par theme pour les jalons qui n'en tiennent
        # aucun), titree par lui, ses jalons l'un sous l'autre. Les boites sont
        # rangees **dans l'ordre des dates**, cote a cote sur une seule rangee:
        # leurs traits ne peuvent donc pas se croiser, et aucun ne remonte plus
        # haut que la gouttiere, donc aucun ne traverse un engagement.
        BOX_TOP = otd_bottom + GUTTER

        def longest_word(g) -> int:
            """Le mot le plus long d'une boite, titre compris.

            Quand une colonne est plus etroite que ce mot, PowerPoint le coupe en
            deux (« environnement / s historiques »), ce qui se lit mal et se voit
            de loin. On prefere descendre d'un demi-point de corps.
            """
            words = (g["title"] or "").split()
            for it in g["items"]:
                words += it["title"].split()
            return max((len(w) for w in words), default=1)

        def lay_boxes(fs: float, count: int, *, whole_words: bool = True, tight: bool = False):
            """Range les boites dans leur trimestre et rend leur geometrie.

            Une boite **ne sort jamais du trimestre de sa date**: elle peut
            commencer un mois plus tot pour tenir dans les trois colonnes, mais
            elle n'en deborde pas. Une boite a cheval sur deux trimestres se lisait
            sous le mauvais, et une boite de decembre n'avait nulle part ou
            s'etendre.

            Dans un trimestre, les boites **s'empilent d'abord sur une seule
            colonne**, et on n'en ouvre une deuxieme, puis une troisieme, que
            lorsque la pile ne tient plus dans la hauteur. La frise a de la hauteur
            et peu de largeur: une boite large porte un texte plus gros et ne coupe
            pas ses mots, la ou deux boites cote a cote dans un trimestre font six
            centimetres chacune et cassent un titre tous les dix caracteres.

            Seule la premiere de chaque pile recoit son trait: un trait vers une
            boite du bas traverserait celle du haut. Les suivantes portent leur
            mois devant leur titre, ce qui dit la meme chose sans rien croiser.
            """
            shown = groups[:count]
            title_h = _fs(fs + 1) * 0.0170
            line_h = _fs(fs) * 0.0170
            by_quarter: dict[int, list] = {}
            for g in shown:
                by_quarter.setdefault(g["month"] // 3, []).append(g)

            def lay_quarter(quarter, boxes, lanes, tight=False):
                """Les boites d'un trimestre sur ce nombre de colonnes, ou None."""
                width = (QIW - (lanes - 1) * BOX_GAP) / lanes
                cpl = max(8, int((width - TICK - 0.20) / (0.0071 * _fs(fs))))
                tcpl = max(8, int((width - 0.14) / (0.0071 * _fs(fs + 1))))
                # Une ligne de moins de 14 caracteres (16 serree) coupait les
                # jalons a quatre lettres (« Durciss… ») ou empilait un mot par
                # ligne: mieux vaut une colonne de moins, ou la boite comptee dans
                # la note « non affiches ».
                if cpl < (16 if tight else 14):
                    return None
                bottoms = [BOX_TOP] * lanes
                out = []
                for rank, g in enumerate(boxes):
                    lane = rank % lanes
                    first = rank < lanes          # la tete de pile porte le trait
                    title = g["title"] or ""
                    if not first:
                        when = months[g["month"]] if g.get("dated") else f'Q{(g["month"] - 1) // 3 + 1}'
                        title = f'{when}{_sep(lang)}{title}' if title else when
                    h = 0.08
                    # Serre: une ligne par titre et par jalon, coupee avec « … ».
                    # C'est le dernier recours avant de retirer une boite.
                    tlines = (1 if tight else wrap_lines(title, tcpl)) if title else 0
                    if title:
                        h += tlines * title_h + 0.04
                    rows = []
                    for it in g["items"]:
                        label = it["title"] + (f' ({it["stage"]})' if it.get("stage") else "")
                        n = 1 if tight else wrap_lines(label, cpl)
                        rows.append((it, label, n))
                        h += n * line_h + (0.03 if tight else 0.05)
                    y = bottoms[lane]
                    if y + h > BOX_BOTTOM:
                        return None
                    if whole_words and not tight and cpl < longest_word(g):
                        return None
                    bottoms[lane] = y + h + BOX_GAP
                    out.append({**g, "title": title, "linked": first,
                                "x": qx(quarter) + lane * (width + BOX_GAP),
                                "y": y, "w": width, "h": h, "rows": rows, "fs": fs,
                                "line_h": line_h, "title_h": title_h, "cpl": cpl,
                                "tcpl": tcpl, "tlines": tlines, "tight": tight})
                return out

            laid = []
            for quarter, boxes in by_quarter.items():
                placed = None
                # Un trimestre ne se serre que s'il le faut: les autres gardent
                # leurs titres entiers sur plusieurs lignes.
                for q_tight in ((False, True) if tight else (False,)):
                    for lanes in range(1, min(3, len(boxes)) + 1):
                        placed = lay_quarter(quarter, boxes, lanes, q_tight)
                        if placed is not None:
                            break
                    if placed is not None:
                        break
                if placed is None:
                    return None
                laid.extend(placed)
            return laid

        # Du plus lisible au plus dense: on reduit le texte avant de renoncer a une
        # boite. Ce qui ne tient toujours pas est compte en clair plutot que tu.
        laid = None
        for count in range(len(groups), 0, -1):
            for whole_words, tight in ((True, False), (False, False), (False, True)):
                # Le plus grand corps qui tienne quand la slide est aeree, et on
                # descend jusqu'au plus petit qui se lise encore plutot que de
                # renoncer a une boite: un jalon ecrit petit se lit encore, un
                # jalon absent ne dit plus rien. L'echelle est donnee avant
                # FONT_SCALE, qui la releve d'un cran et demi.
                # Serre, un grand corps couperait chaque titre apres dix lettres:
                # on reste au plus petit corps lisible, qui en garde le plus.
                sizes = (8, 7.5, 7) if tight else (11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8, 7.5, 7)
                for fs in sizes:
                    laid = lay_boxes(fs, count, whole_words=whole_words, tight=tight)
                    if laid is not None:
                        break
                if laid is not None:
                    break
            if laid is not None:
                break
        laid = laid or []
        dropped = groups[len(laid):]

        # Les traits d'abord, les boites par-dessus: un trait s'arrete ainsi net au
        # bord de la boite, sans depasser a l'interieur.
        def segment(x1, y1, x2, y2, *, arrow=False):
            if abs(x1 - x2) < 0.004 and abs(y1 - y2) < 0.004:
                return
            link = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1),
                                          Inches(x2), Inches(y2))
            # Le meme ton et le meme pointille que la boite: le trait fait partie
            # du meme dessin, il ne doit pas se voir davantage qu'elle. Et sans
            # ombre: PowerPoint en pose une par defaut, qui doublait le trait d'un
            # halo gris et le rendait plus lourd que l'encadre.
            link.line.color.rgb = B["line"]
            link.line.width = Pt(0.75)
            link.line.dash_style = MSO_LINE_DASH_STYLE.DASH
            link.shadow.inherit = False
            if arrow:
                # python-pptx n'expose pas les pointes de fleche, d'ou l'element
                # pose a la main, en dernier comme le schema l'impose.
                el = link.line._get_or_add_ln()
                el.append(el.makeelement(qn("a:tailEnd"),
                                         {"type": "triangle", "w": "sm", "len": "sm"}))

        # Le trait remonte **jusqu'au mois**, tout droit, par le couloir libre qui
        # longe le bord de la case: il ne croise donc aucun titre d'engagement.
        # Quand une boite a du se decaler d'une colonne, le coude tient dans les
        # quelques millimetres juste au-dessus d'elle.
        for g in laid:
            if not g["linked"]:
                continue
            # Le trait reste sur le mois de la date; la boite, elle, peut avoir
            # recule d'un mois pour tenir dans son trimestre. Le coude tient alors
            # dans les quelques millimetres juste au-dessus d'elle.
            mx = mx0(g["month"]) + 0.03
            bx = min(max(mx, g["x"] + 0.06), g["x"] + g["w"] - 0.06)
            segment(mx, SEP_Y, mx, BOX_TOP - 0.07)
            segment(mx, BOX_TOP - 0.07, bx, BOX_TOP - 0.07)
            segment(bx, BOX_TOP - 0.07, bx, BOX_TOP, arrow=True)
            dot = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(mx - 0.035), Inches(SEP_Y - 0.035),
                                     Inches(0.07), Inches(0.07))
            dot.fill.solid(); dot.fill.fore_color.rgb = B["line"]
            dot.line.fill.background(); dot.shadow.inherit = False

        for g in laid:
            late = g.get("status") == "late"
            box = rrect(s, Inches(g["x"]), Inches(g["y"]), Inches(g["w"]), Inches(g["h"]),
                        B["white"], line=B["red"] if late else B["line"], radius=0.05)
            if late:  # late: a solid red frame, readable in a printed deck too
                box.line.width = Pt(1.5)
            else:
                box.line.dash_style = MSO_LINE_DASH_STYLE.DASH
            cy = g["y"] + 0.04
            if g["title"]:
                ink = B["red"] if late else (rgb(OTD_SCOPE_COLOR[g["scope"]]) if g["scope"] else B["navy"])
                lines = g["tlines"] or 1
                marker_label(g["x"] + 0.07, cy, g["w"] - 0.14, lines * g["title_h"],
                             [(_wrap_fit(g["title"], g["tcpl"], lines), ink, True)],
                             g["fs"] + 1,
                             anchor=MSO_ANCHOR.TOP)
                cy += lines * g["title_h"] + 0.04
            for it, label, n in g["rows"]:
                stage = it.get("stage")
                if g["tight"] and stage and len(it["title"]) + len(stage) + 3 > g["cpl"]:
                    # Une ligne serree: la phase part avant le titre. « Mise… (GA) »
                    # ne disait plus quel jalon; « Mise en production » le dit.
                    stage = None
                h = n * g["line_h"]
                # La coche est a droite: la colonne de gauche est celle des titres,
                # et un oeil qui descend une liste lit des titres alignes, pas des
                # titres decales de la largeur d'une pastille.
                status_tick(g["x"] + g["w"] - 0.07 - TICK, cy + h / 2 - TICK / 2,
                            it["status"])
                runs = [(_wrap_fit(it["title"], g["cpl"], n, reserve=len(stage) + 3 if stage else 0),
                         B["ink"], False)]
                if stage:
                    runs.append((f' ({stage})', B["muted"], False))
                marker_label(g["x"] + 0.07, cy, g["w"] - 0.19 - TICK, h,
                             runs, g["fs"], anchor=MSO_ANCHOR.TOP)
                cy += h + (0.03 if g["tight"] else 0.05)

        # Ce qui n'a pas trouve de place est dit, pas tu: une boite absente d'un
        # export se lit comme des jalons qui n'existent pas.
        notes = []
        undated = [o["title"] for o in otds if o.get("month") is None]
        if undated:
            notes.append(f'{rt(lang, "tl_no_date")}{_sep(lang)}{", ".join(undated)}')
        if dropped:
            # Not shown for lack of room: said as such, not mixed with the undated.
            notes.append(f'{rt(lang, "tl_dropped", n=len(dropped))}{_sep(lang)}'
                         + ", ".join(g["title"] or rt(lang, "h_jalons") for g in dropped))
        if not groups and not by_month:
            # Au milieu de la frise vide, et non sur le bord arrondi de la carte.
            textbox(s, Inches(LBL_X), Inches((SEP_Y + BOX_BOTTOM) / 2 - 0.15), Inches(AX1 - LBL_X),
                    Inches(0.3), rt(lang, "tl_empty"), 12, color=B["muted"], align=PP_ALIGN.CENTER)

        for k, note in enumerate(notes[:2]):
            textbox(s, Inches(LBL_X), Inches(BOX_BOTTOM + 0.01 + k * 0.2), Inches(AX1 - LBL_X),
                    Inches(0.2), _cut(note, 150), 10, color=B["muted"])

        # ----- bas de slide: messages cles et budget -----
        #
        # Les deux cartes valent une ligne de titre et trois lignes de texte, et
        # c'est la hauteur qu'on leur donne. Elles etaient plus courtes que leur
        # contenu: la derniere ligne du budget, « Prevision », sortait par le bas
        # et se lisait a moitie. La hauteur vient de la frise, qui en a de reste.
        def list_card(x, y2, w, h, title, lines, empty, extra=None):
            sh = rrect(s, x, y2, w, h, B["white"], line=B["line"], radius=0.05)
            paras = [(title, 12, B["navy"], True, PP_ALIGN.LEFT, 2)]
            if lines:
                paras += [(txt, 10, color, bold, PP_ALIGN.LEFT, 0) for (txt, color, bold) in lines]
            else:
                paras.append((empty, 10, B["muted"], False, PP_ALIGN.LEFT, 0))
            place(sh, paras, anchor=MSO_ANCHOR.TOP, ml=0.16, mt=0.06, mr=0.16, mb=0.04)
            if extra:
                # Le reste se compte a cote du titre, ou il ne prend pas de ligne.
                r_ = sh.text_frame.paragraphs[0].add_run()
                r_.text = f'   {extra}'
                r_.font.size = Pt(_fs(10)); r_.font.color.rgb = B["muted"]

        # Deux messages, pas trois: la carte fait deux centimetres de haut, et une
        # troisieme ligne passait sur la legende de la frise au lieu de rester dans
        # son encadre. Le reste est compte au bout de la deuxieme ligne, ou il ne
        # coute pas une ligne de plus.
        kms = det.get("key_messages") or []
        klines = []
        # The most serious first (risk, alert, success): a risk entered third
        # used to be cut off as "+1".
        kms = sorted(kms, key=lambda x: {"risk": 0, "alert": 1}.get(x.get("kind"), 2))
        # Un message, une ligne: deux messages longs passaient chacun sur deux
        # lignes et le dernier finissait sur la legende.
        km_cpl = int((8.02 - 0.34) / (0.0078 * _fs(10)))
        for m in kms[:2]:
            rag = {"success": "green", "alert": "amber", "risk": "red"}.get(m["kind"], "grey")
            klines.append((_cut(f'{rt(lang, "km_" + m["kind"])}{_sep(lang)}{m["text"]}', km_cpl),
                           rgb(_RAG_BRAND[rag]), False))
        more = _pt(lang, "km_more", n=len(kms) - 2) if len(kms) > 2 else None
        list_card(Inches(0.4), Inches(6.10), Inches(8.02), Inches(0.96),
                  rt(lang, "h_key_messages"), klines, rt(lang, "no_key_message"), extra=more)

        bsh = rrect(s, Inches(8.61), Inches(6.10), Inches(4.32), Inches(0.96),
                    B["white"], line=B["line"], radius=0.05)
        bud = det.get("budget")
        btf = bsh.text_frame
        f = lambda v: fmt_money(v, lang)

        def bline(label, val, *, muted=False, italic=False):
            p = btf.add_paragraph(); p.space_after = Pt(0)
            if label:
                r1 = p.add_run(); r1.text = f'{label}{_sep(lang)}'
                r1.font.size = Pt(_fs(10)); r1.font.color.rgb = B["muted"]
            r2 = p.add_run(); r2.text = val
            r2.font.size = Pt(_fs(10)); r2.font.bold = not muted
            r2.font.italic = italic
            r2.font.color.rgb = B["muted"] if muted else B["ink"]

        # Le total monte dans le titre: la ligne liberee porte le commentaire,
        # qui n'etait jamais rendu (« Arbitrage Q3 en attente »).
        has_amounts = bud is not None and bud.get("total") is not None
        title = rt(lang, "h_budget") + (f'{_sep(lang)}{f(bud["total"])}' if has_amounts else "")
        place(bsh, [(title, 12, B["navy"], True, PP_ALIGN.LEFT, 2)],
              anchor=MSO_ANCHOR.TOP, ml=0.16, mt=0.06, mr=0.16, mb=0.04)
        if bud is None:
            # Absent parce que la squad ne suit pas de budget, ou parce que ce
            # document n'en montre pas (envoi a une liste): « non renseigne »
            # laissait croire a un oubli de la squad.
            bline(None, _pt(lang, "budget_off" if det.get("budget_enabled") is False else "budget_none"),
                  muted=True)
        elif not has_amounts:
            bline(None, _pt(lang, "budget_empty"), muted=True)
        else:
            bline(rt(lang, "b_spent"), f(bud["spent"]) +
                  (f' ({_pct(bud["spent_pct"], lang)})' if bud.get("spent_pct") is not None else ""))
            bline(rt(lang, "b_forecast"), f(bud["forecast"]) +
                  (f' ({_pct(bud["forecast_pct"], lang)})' if bud.get("forecast_pct") is not None else ""))
            if bud.get("comment"):
                bline(None, _cut(bud["comment"], int((4.32 - 0.34) / (0.0078 * _fs(10)))),
                      muted=True, italic=True)
            # Pas de pastille sans montant a comparer: « Sur les rails » en vert
            # au-dessus de trois tirets affirmait ce que rien ne mesurait.
            if bud.get("spent") is not None or bud.get("forecast") is not None:
                st_color = {"on_track": "green", "at_risk": "amber", "over": "red"}[bud["status"]]
                st_lbl = rt(lang, {"on_track": "b_on_track", "at_risk": "b_at_risk",
                                   "over": "b_over"}[bud["status"]])
                cw = Inches(0.26 + 0.082 * FONT_SCALE * len(st_lbl))
                chip(s, Emu(int(Inches(8.61)) + int(Inches(4.32)) - int(cw) - int(Inches(0.14))),
                     Inches(6.16), st_lbl, rgb(_RAG_BRAND[st_color]))

        # La legende: les couleurs de statut, puis les deux phases. Elle se lit une
        # fois et sert pour toute la frise, donc elle tient sur une ligne discrete
        # plutot que de repeter dans chaque boite ce qu'une couleur et deux lettres
        # suffisent a dire. Elle est **dans la carte de la frise**, sous les boites:
        # tout en bas de slide elle occupait la ligne dont les deux cartes avaient
        # besoin, et leur texte lui passait dessus. Elle explique l'axe, sa place
        # est avec lui.
        # Le corps 7 etait illisible et la largeur estimee d'un caractere trop
        # courte: le libelle revenait a la ligne et sa deuxieme ligne tombait hors
        # de la slide. On estime large, et on interdit le retour a la ligne plutot
        # que d'esperer que la police du modele soit etroite.
        LEG_Y = 7.14                   # sous les cartes, avec une marge au bord bas
        scope_legs = [rt(lang, "otd_scope_" + sc) for sc in ("management", "squad")]
        stage_legs = [f'{c.upper()} {rt(lang, "stage_" + c)}' for c in ("ea", "ga")]
        # Chaque slide porte sa date (et sa version quand elle rejoue le passe):
        # une slide sortie du deck et collee ailleurs doit encore dire de quand
        # elle date.
        stamp = _pt(lang, "gen_on", d=gen_str)
        if data.get("as_of"):
            stamp = (f'{_pt(lang, "as_of", d=fmt_date(data["as_of"], lang))}, '
                     f'{stamp[0].lower()}{stamp[1:]}')

        def leg_row(cw):
            """La largeur de la rangee entiere a cette largeur de caractere."""
            return (sum(0.28 + cw * len(t) for t in scope_legs)
                    + sum(0.22 + cw * len(t) for t in stage_legs)
                    + 0.3 + 0.075 * _fs(9) / 10 * len(stamp))

        # La rangee tient sur une ligne et ne sort pas de la slide: son corps suit le
        # facteur commun tant qu'elle rentre, et redescend sinon.
        LEG_W = prs.slide_width / 914400.0 - 0.8
        for LEG_FS in (10, 9.5, 9, 8.5, 8, 7.5, 7):
            LEG_CW = 0.088 * _fs(LEG_FS) / 10   # largeur d'un caractere a ce corps, majoree
            if leg_row(LEG_CW) <= LEG_W:
                break
        lx = 0.4
        # D'abord les deux portees d'engagement: le meme repere que sur l'axe,
        # sinon la legende explique un signe qui ne s'y trouve pas.
        for scope, leg in zip(("management", "squad"), scope_legs):
            mk = s.shapes.add_shape(MSO_SHAPE.STAR_5_POINT, Inches(lx), Inches(LEG_Y),
                                    Inches(0.17), Inches(0.17))
            mk.fill.solid(); mk.fill.fore_color.rgb = rgb(OTD_SCOPE_COLOR[scope])
            mk.line.fill.background(); mk.shadow.inherit = False
            textbox(s, Inches(lx + 0.20), Inches(LEG_Y), Inches(LEG_CW * len(leg) + 0.06),
                    Inches(0.19), leg, LEG_FS, color=B["muted"], wrap=False)
            lx += 0.28 + LEG_CW * len(leg)
        # EA et GA sont dans les boites: deux lettres qui ne veulent rien dire pour
        # qui decouvre le document, et tout pour qui sait, d'ou la legende.
        for leg in stage_legs:
            textbox(s, Inches(lx), Inches(LEG_Y), Inches(LEG_CW * len(leg) + 0.06),
                    Inches(0.19), leg, LEG_FS, color=B["muted"], wrap=False)
            lx += 0.22 + LEG_CW * len(leg)
        textbox(s, Inches(lx), Inches(LEG_Y), Inches(12.93 - lx), Inches(0.19), stamp, 9,
                bold=bool(data.get("as_of")), color=B["orange"] if data.get("as_of") else B["muted"],
                align=PP_ALIGN.RIGHT, wrap=False)

        # Les etats d'un jalon, dessines comme dans les boites (coche, point,
        # anneau) et le cadre rouge d'un engagement en retard, sur la ligne du
        # titre de la frise: des carres de couleur n'expliquaient ni la coche, ni
        # le point, ni le cadre plein.
        tick_legs = [("done", _status_label("done", lang)), ("on_track", _status_label("on_track", lang)),
                     ("at_risk", _status_label("at_risk", lang)), ("blocked", _status_label("blocked", lang))]
        late_leg = _pt(lang, "late_frame")
        TL_CW = 0.088 * _fs(9) / 10
        width = sum(TICK + 0.10 + TL_CW * len(t) + 0.22 for _, t in tick_legs) + 0.36 + TL_CW * len(late_leg)
        tx, ty = 12.75 - width, 1.08
        for st, leg in tick_legs:
            status_tick(tx, ty + 0.02, st)
            textbox(s, Inches(tx + TICK + 0.08), Inches(ty), Inches(TL_CW * len(leg) + 0.06),
                    Inches(0.19), leg, 9, color=B["muted"], wrap=False)
            tx += TICK + 0.10 + TL_CW * len(leg) + 0.22
        fr_ = rrect(s, Inches(tx), Inches(ty + 0.01), Inches(0.26), Inches(0.16), B["white"],
                    line=B["red"], radius=0.1)
        fr_.line.width = Pt(1.5)
        textbox(s, Inches(tx + 0.32), Inches(ty), Inches(TL_CW * len(late_leg) + 0.06),
                Inches(0.19), late_leg, 9, color=B["muted"], wrap=False)

    # --- Assemble the deck. Une squad, une slide, la meme dans les deux cas: un
    # export d'une seule squad n'est que ce deck sans sa page de synthese.
    if not data.get("squad_scoped"):
        summary_slide()
    for r in squads[:_MAX_DETAIL_SLIDES]:
        if r.get("detail"):
            squad_slide(r)
    # Les points d'attention ferment le deck hebdo, apres les squads: la synthese
    # et les slides de squad gardent leur place, et la derniere slide est celle
    # qu'on laisse a l'ecran pour la discussion.
    if not data.get("squad_scoped") and data.get("doc") != "dashboard" and not data.get("as_of"):
        attention_slide()
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


# « +N » en fin de carte de roadmap: ce qui n'a pas tenu, dit en toutes lettres.
_RM_MORE = {"fr": "+{n} autres", "en": "+{n} more"}
_RM_MORE_ONE = {"fr": "+1 autre", "en": "+1 more"}

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
    gen_str = fmt_datetime(gen, lang) if isinstance(gen, datetime) else str(gen)
    if data.get("as_of"):
        _v = _pt(lang, "as_of", d=fmt_date(data["as_of"], lang))
        gen_str += ", " + _v[:1].lower() + _v[1:]
    months = _MONTHS[lang]

    SLIDE_W, SLIDE_H = 13.333, 7.5
    prs = pptxtpl.new_presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)

    # Column geometry (4 quarters), after a column of squad names written
    # horizontally: couches a 270 degres dans la hauteur de leur bande, les noms se
    # lisaient « GCP /… » ou « Azur e » et ne disaient plus quelle ligne etait
    # quelle squad.
    MARGIN, GAP = 0.5, 0.08
    NAME_X, NAME_W = 0.2, 1.42
    GRID_X = NAME_X + NAME_W + 0.08
    COL_W = (SLIDE_W - GRID_X - 0.3 - GAP * 3) / 4
    def col_x(i): return GRID_X + i * (COL_W + GAP)
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
        r.font.size = Pt(_fs(size)); r.font.bold = bold; r.font.color.rgb = color

    def textbox(s, x, y, w, h, runs, size, *, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
        box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Emu(0); tf.margin_top = tf.margin_bottom = Emu(0)
        tf.vertical_anchor = anchor
        p = tf.paragraphs[0]; p.alignment = align
        for txt, color, bold in runs:
            r = p.add_run(); r.text = txt
            r.font.size = Pt(_fs(size)); r.font.bold = bold; r.font.color.rgb = color
        return box

    def draw_header(s):
        title = f'{rt(lang, "roadmap_report")} | {data["scope_name"]}'
        textbox(s, MARGIN, 0.22, 8.6, 0.5, [(title, C["dark"], True)],
                22 if len(title) <= 55 else 18 if len(title) <= 70 else 15)
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
        # Le plus grave d'abord: quand la place manque, c'est la fin de la liste
        # qui passe dans « +N », et ce doit etre ce qui avance bien.
        sev = {"blocked": 0, "at_risk": 1, "on_track": 2, "done": 3}
        items = sorted(items, key=lambda it: sev.get(it.get("status"), 2))
        specs: list[tuple[str, object]] = []
        item_fs = max(7, fs - 1.5)  # milestone lines a touch smaller than the theme header
        max_lines = max(1, int((h - 0.08) / line_h))
        # A thin lane (many squads on the one slide) keeps its lines for the
        # milestones themselves: with theme headers it showed "Theme +4..." and
        # not a single title.
        with_themes = max_lines >= 4
        for theme, group in group_by_theme(items):
            if theme and with_themes:
                specs.append(("theme", theme))
            for it in group:
                specs.append(("item", it))
        shown = specs[:max_lines]
        # De la hauteur de reste (une squad seule, peu de jalons): un jalon peut
        # tenir sur plusieurs lignes (quatre au plus) au lieu d'etre coupe au tiers
        # de la carte.
        item_lines = min(4, max_lines // max(1, len(specs))) if len(specs) <= max_lines else 1
        for li, (kind, val) in enumerate(shown):
            p = tf.paragraphs[0] if li == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT  # themes + milestones are left-aligned, never centred
            p.space_after = Pt(0.5)
            if kind == "theme":
                r = p.add_run(); r.text = val
                r.font.size = Pt(_fs(fs)); r.font.bold = True; r.font.color.rgb = C["card_ink"]
                continue
            it = val
            # Un jalon, une ligne: un titre qui passait a la ligne poussait « +N »
            # hors de la carte, sur la bande de la squad suivante.
            item_cpl = int((w - 0.14) / (0.0062 * _fs(item_fs))) - 2
            if len(specs) > max_lines and (max_lines + 1) * line_h > h - 0.06:
                item_cpl -= 11
            stage_len = len(it["stage"]) + 3 if it.get("stage") else 0
            if item_lines >= 2:
                it = {**it, "title": _wrap_fit(it["title"], max(8, item_cpl), item_lines, reserve=stage_len)}
            else:
                it = {**it, "title": _cut(it["title"], max(8, item_cpl - stage_len))}
            # La pastille de statut, a la couleur du statut: la roadmap n'en
            # montrait aucune et ne disait pas ce qui etait bloque.
            rd = p.add_run(); rd.text = "● "
            rd.font.size = Pt(_fs(item_fs)); rd.font.color.rgb = rgb(_RAG_BRAND[_status_rag(it.get("status"))])
            r1 = p.add_run(); r1.text = it["title"]
            r1.font.size = Pt(_fs(item_fs)); r1.font.color.rgb = C["card_ink"]
            stage = it.get("stage")
            if stage:
                ro = p.add_run(); ro.text = " ("
                ro.font.size = Pt(_fs(item_fs)); ro.font.color.rgb = C["card_ink"]
                rs = p.add_run(); rs.text = stage
                rs.font.size = Pt(_fs(item_fs)); rs.font.bold = True
                rs.font.color.rgb = STAGE.get(stage, C["card_ink"])
                rc = p.add_run(); rc.text = ")"
                rc.font.size = Pt(_fs(item_fs)); rc.font.color.rgb = C["card_ink"]
        if len(specs) > max_lines:
            # Une carte d'une seule ligne n'a pas la place d'une deuxieme: le
            # compte se met au bout de la ligne, au lieu de deborder sur la bande
            # de la squad suivante.
            one_line = (max_lines + 1) * line_h > h - 0.06
            if one_line:
                p = tf.paragraphs[-1]
                sp_ = p.add_run(); sp_.text = "   "
                sp_.font.size = Pt(_fs(item_fs))
            else:
                p = tf.add_paragraph()
                p.alignment = PP_ALIGN.LEFT
            extra = len(specs) - max_lines
            r = p.add_run(); r.text = _RM_MORE_ONE[lang] if extra == 1 else _RM_MORE[lang].format(n=extra)
            r.font.size = Pt(_fs(max(7, item_fs - 0.5))); r.font.color.rgb = C["muted"]

    def draw_swimlanes(s, lanes):
        # Everything fits on ONE slide: band height + fonts scale with the count,
        # but with a readable floor (small decks get a comfortably large font).
        n = max(1, len(lanes))
        band_h = (Y_BOTTOM - Y_TOP) / n
        card_fs = (13 if band_h >= 1.05 else 12 if band_h >= 0.85 else 11 if band_h >= 0.68
                   else 10 if band_h >= 0.52 else 9 if band_h >= 0.40 else 8)
        line_h = _fs(card_fs) * 0.020
        # Le nom de la squad est couche dans la hauteur de sa bande: sa taille est
        # dictee par cette hauteur, pas par le confort de lecture. L'agrandir avec
        # le reste ne donnerait rien a lire de plus, seulement un nom replie en
        # morceaux dans une etiquette restee aussi courte. Il est donc exprime
        # apres FONT_SCALE et le traverse sans changer.
        # Le nom, horizontal, dans une colonne a gauche des trimestres: sur deux
        # lignes quand la bande le permet, sur une sinon, coupe avec « … ».
        top_fs = 11 if band_h >= 0.7 else 10 if band_h >= 0.45 else 9 if band_h >= 0.34 else 8

        def name_fit(name):
            """Le plus grand corps ou le nom tient entier, sur les lignes que la
            bande autorise; au plus petit, le nom se coupe avec « … »."""
            for fs in sorted({top_fs, max(8, top_fs - 1), 8}, reverse=True):
                lines = max(1, int((band_h - 0.1) / (_fs(fs) * 0.0165)))
                cpl = int((NAME_W - 0.12) / (0.0072 * _fs(fs)))
                if wrap_lines(name, cpl) <= lines:
                    return name, fs
            # Coupe au milieu, la fin gardee: « Squad supplementaire 12 » et « 13 »
            # restaient trois fois le meme « Squad supplementai… ».
            return _cut_middle(name, cpl * lines), fs

        for ri, sq in enumerate(lanes):
            by = Y_TOP + ri * band_h
            lbl = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, NAME_X, by + 0.04, NAME_W, band_h - 0.08,
                        C["dark"], round_adj=0.08)
            name, label_fs = name_fit(sq["name"] or "")
            set_text(lbl, name, label_fs, C["white"], bold=True, align=PP_ALIGN.LEFT)
            qmap = {qd["q"]: qd["items"] for qd in (sq.get("detail") or {}).get("quarters", [])}
            for i, q in enumerate((1, 2, 3, 4)):
                draw_card(s, col_x(i), by + 0.04, COL_W, band_h - 0.08, qmap.get(q, []), card_fs, line_h)

    s = pptxtpl.add_slide(prs)  # single page, always
    draw_header(s)
    draw_swimlanes(s, squads)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


_INIT_PT = {
    "fr": {"sub": "Année {year}, généré le {d}", "overdue": "dépassée", "suite": " (suite)"},
    "en": {"sub": "Year {year}, generated on {d}", "overdue": "overdue", "suite": " (cont.)"},
}


def render_initiatives_pptx(data: dict, *, lang: str = "fr") -> bytes:
    """Render the initiatives list as branded table slides, 16 rows per slide.

    Sorted by deadline, the closest first, and an overdue deadline is said in red:
    a committee reads this list for what is due, not in the order it was typed.
    Nothing is dropped any more: past a slide's worth, the table continues."""
    from datetime import date, timezone
    Presentation, Inches, Pt, Emu, RGBColor, PP_ALIGN, MSO_ANCHOR, MSO_SHAPE = _pptx_toolkit()

    def rgb(h):
        return RGBColor.from_string(h.lstrip("#").upper())

    B = {k: rgb(v) for k, v in _BRAND.items()}
    lang = _lang(lang)
    T = _INIT_T[lang]
    P = _INIT_PT[lang]
    prs = pptxtpl.new_presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    margin = Inches(0.5)
    today = date.today()
    gen = fmt_datetime(datetime.now(timezone.utc), lang)

    def due(it):
        try:
            return date.fromisoformat(str(it.get("deadline"))[:10])
        except (TypeError, ValueError):
            return None

    items = sorted(data["items"], key=lambda it: (due(it) is None, due(it) or today,
                                                  (it.get("title") or "").lower()))

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
            rr = pp.runs[0]; rr.font.size = Pt(_fs(size)); rr.font.bold = bold; rr.font.color.rgb = color

    def page(rows, cont):
        s = pptxtpl.add_slide(prs)
        head = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, Inches(1.05))
        head.fill.solid(); head.fill.fore_color.rgb = B["navy"]; head.line.fill.background(); head.shadow.inherit = False
        tf = head.text_frame; tf.margin_left = Inches(0.5); tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT   # a gauche, comme les autres decks
        r = p.add_run(); r.text = f'{T["title"]} | {data["scope_name"]}' + (P["suite"] if cont else "")
        r.font.size = Pt(_fs(22)); r.font.bold = True; r.font.color.rgb = B["white"]
        p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.LEFT
        r2 = p2.add_run(); r2.text = P["sub"].format(year=data["year"], d=gen)
        r2.font.size = Pt(_fs(11)); r2.font.color.rgb = rgb("#C7D2FE")

        headers = [T["h_init"], T["h_owner"], T["h_squad"], T["h_deadline"]]
        wfrac = [0.42, 0.22, 0.20, 0.16]
        nrows = max(2, len(rows) + 1)
        table_w = int(prs.slide_width - margin * 2)
        tbl = s.shapes.add_table(nrows, 4, margin, Inches(1.3), Emu(table_w),
                                 Inches(0.34) + Inches(0.32) * (nrows - 1)).table
        for ci, f in enumerate(wfrac):
            tbl.columns[ci].width = Emu(int(table_w * f))
        for ci, h in enumerate(headers):
            cell(tbl.cell(0, ci), h, 11, B["white"], bold=True, fill=B["navy"])
        if not rows:
            cell(tbl.cell(1, 0), T["none"], 10, B["muted"])
            for ci in range(1, 4):
                cell(tbl.cell(1, ci), " ", 10, B["muted"])
        for ri, it in enumerate(rows, start=1):
            zebra = B["zebra"] if ri % 2 == 0 else B["white"]
            d = due(it)
            late = d is not None and d < today
            when = fmt_date(it["deadline"], lang) if it["deadline"] else "-"
            if late:
                when += f' ({P["overdue"]})'
            cells = [(_cut(it["title"], 70), B["ink"], True), (_cut(it["owner"] or "-", 34), B["ink"], False),
                     (_cut(it["squad_name"] or "-", 30), B["ink"], False),
                     (when, B["red"] if late else B["ink"], late)]
            for ci, (val, color, bold) in enumerate(cells):
                cell(tbl.cell(ri, ci), val, 10, color, bold=bold, fill=zebra)

    PER = 16
    page(items[:PER], False)
    for k in range(PER, len(items), PER):
        page(items[k:k + PER], True)
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
    # Un groupe d'une ligne ne paie plus un en-tete de colonnes: celui-ci est
    # pose une fois en haut de chaque slide, et le titre de groupe est plus mince.
    ROW_H, HDR_H, GRP_H = int(Inches(0.30)), int(Inches(0.32)), int(Inches(0.36))
    TOP0, BOTTOM = int(Inches(1.25)), int(Inches(7.22))
    PL = {"fr": ("{n} dépendance", "{n} dépendances", "{n} jalon", "{n} jalons"),
          "en": ("{n} dependency", "{n} dependencies", "{n} milestone", "{n} milestones")}[lang]

    def total_lbl(n):
        return (PL[0] if n == 1 else PL[1]).format(n=n)

    def count_lbl(n):
        return (PL[2] if n == 1 else PL[3]).format(n=n)

    # Le plus grave d'abord, dans chaque groupe et entre les groupes: une
    # dependance bloquee ne doit pas attendre la sixieme slide.
    SEV = {"blocked": 0, "at_risk": 1, "on_track": 2, "done": 3}
    groups = []
    for g in data["groups"]:
        its = sorted(g["items"], key=lambda it: (SEV.get(it.get("status"), 2), it.get("year") or 0,
                                                  it.get("quarter") or 0))
        groups.append({**g, "items": its})
    groups.sort(key=lambda g: min((SEV.get(it.get("status"), 2) for it in g["items"]), default=3))

    gen = data["generated_at"]
    gen_str = fmt_datetime(gen, lang) if isinstance(gen, datetime) else str(gen)
    if data.get("as_of"):
        _v = _pt(lang, "as_of", d=fmt_date(data["as_of"], lang))
        gen_str += ", " + _v[:1].lower() + _v[1:]

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
        r.font.size = Pt(_fs(size)); r.font.bold = bold
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
                f'{total_lbl(data["total"])}'
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
        textbox(s, colx[0], y, content_w - int(Inches(2.4)), GRP_H, _cut(txt, 110), 12, bold=True, color=B["navy"])
        textbox(s, margin + content_w - int(Inches(2.4)), y, Inches(2.3), GRP_H,
                count_lbl(len(g["items"])), 10, color=B["muted"], align=PP_ALIGN.RIGHT)
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
        state["s"] = s; state["y"] = col_headers(s, TOP0)

    open_slide(False)
    for g in groups:
        if state["y"] + GRP_H + ROW_H > BOTTOM:
            open_slide(True)
        state["y"] = group_header(state["s"], state["y"], g, False)
        for idx, it in enumerate(g["items"]):
            if state["y"] + ROW_H > BOTTOM:
                open_slide(True)
                state["y"] = group_header(state["s"], state["y"], g, True)
            state["y"] = data_row(state["s"], state["y"], it, idx % 2 == 1)

    buf = io.BytesIO(); prs.save(buf); return buf.getvalue()
