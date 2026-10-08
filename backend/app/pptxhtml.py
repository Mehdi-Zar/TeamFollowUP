"""Studio des exports: the preview of a deck, drawn from the deck itself.

The preview is not a second rendering of the data: it reads the very presentation
the export would save (shapes, text, tables, charts, pictures, the master's own
decorations) and writes each slide as positioned HTML, at 96 pixels per inch. The
geometry is therefore the deck's to the EMU; only the text is laid out by the
browser, so a line may break one word earlier or later than in PowerPoint.

While it reads, it checks what a projected slide cannot afford: text smaller than
8 points, text that does not fit its box, text too pale on its background, and the
two characters the repository never prints. Those checks come back with the HTML.
"""
from __future__ import annotations

import base64
import html
import math
import re

from lxml import etree

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
A, P, R, C = (f"{{{NS[k]}}}" for k in ("a", "p", "r", "c"))
EMU_PX = 9525.0                       # 914400 EMU per inch / 96 px per inch
PT_PX = 96.0 / 72.0
BANNED = ("\u2014", "\u00b7")
MIN_PT = 8.0


def _px(emu) -> float:
    return round(float(emu or 0) / EMU_PX, 2)


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


# --------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------
class Theme:
    """The colour scheme and the body font of a master, to resolve scheme colours."""

    def __init__(self, master):
        self.colors = {"dk1": "000000", "lt1": "FFFFFF", "dk2": "1F497D", "lt2": "EEECE1",
                       "accent1": "4F81BD", "accent2": "C0504D", "accent3": "9BBB59",
                       "accent4": "8064A2", "accent5": "4BACC6", "accent6": "F79646",
                       "hlink": "0000FF", "folHlink": "800080"}
        self.font = "Calibri"
        try:
            for rel in master.part.rels.values():
                if rel.reltype.endswith("/theme"):
                    root = etree.fromstring(rel.target_part.blob)
                    scheme = root.find(".//a:clrScheme", NS)
                    if scheme is not None:
                        for el in scheme:
                            name = el.tag.split("}")[1]
                            srgb = el.find("a:srgbClr", NS)
                            sysc = el.find("a:sysClr", NS)
                            if srgb is not None:
                                self.colors[name] = srgb.get("val")
                            elif sysc is not None and sysc.get("lastClr"):
                                self.colors[name] = sysc.get("lastClr")
                    minor = root.find(".//a:minorFont/a:latin", NS)
                    if minor is not None and minor.get("typeface"):
                        self.font = minor.get("typeface")
                    break
        except Exception:  # pragma: no cover - a template without a readable theme
            pass
        self.colors.setdefault("tx1", self.colors["dk1"])
        self.colors.setdefault("bg1", self.colors["lt1"])
        self.colors.setdefault("tx2", self.colors["dk2"])
        self.colors.setdefault("bg2", self.colors["lt2"])

    def color(self, el) -> str | None:
        """``#rrggbb`` of a fill/colour element (srgbClr, schemeClr, sysClr), or None."""
        if el is None:
            return None
        for child in el:
            tag = child.tag.split("}")[1]
            val = None
            if tag == "srgbClr":
                val = child.get("val")
            elif tag == "schemeClr":
                val = self.colors.get(child.get("val"), "000000")
            elif tag == "sysClr":
                val = child.get("lastClr") or "000000"
            elif tag == "prstClr":
                val = {"black": "000000", "white": "FFFFFF", "red": "FF0000"}.get(child.get("val"), "000000")
            if val:
                return "#" + _apply_mods(val, child)
        return None


def _apply_mods(hexval: str, el) -> str:
    """lumMod / lumOff / tint / shade, enough for template decorations."""
    try:
        r, g, b = (int(hexval[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "000000"
    for m in el:
        tag, v = m.tag.split("}")[1], int(m.get("val", "100000")) / 100000.0
        if tag == "lumMod":
            r, g, b = (int(x * v) for x in (r, g, b))
        elif tag == "lumOff":
            r, g, b = (int(x + 255 * v) for x in (r, g, b))
        elif tag == "tint":
            r, g, b = (int(255 - (255 - x) * v) for x in (r, g, b))
        elif tag == "shade":
            r, g, b = (int(x * v) for x in (r, g, b))
    return "".join(f"{max(0, min(255, x)):02X}" for x in (r, g, b))


def _lum(hexcol: str) -> float:
    r, g, b = (int(hexcol[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# --------------------------------------------------------------------------
# The converter
# --------------------------------------------------------------------------
class _Slide:
    def __init__(self, conv, index):
        self.conv, self.index = conv, index
        self.out: list[str] = []
        self.texts: list[str] = []
        # Filled shapes drawn so far (x, y, w, h, colour): what a text box without
        # a fill of its own is read against.
        self.fills: list[tuple] = []


class Converter:
    def __init__(self, prs):
        self.prs = prs
        self.w, self.h = _px(prs.slide_width), _px(prs.slide_height)
        self.lints: list[dict] = []

    # ---- geometry --------------------------------------------------------------
    @staticmethod
    def _xfrm(el):
        x = el.find(".//a:xfrm", NS) if el.tag != f"{P}grpSp" else el.find("p:grpSpPr/a:xfrm", NS)
        if x is None:
            x = el.find("p:xfrm", NS)
        if x is None:
            return None
        off, ext = x.find("a:off", NS), x.find("a:ext", NS)
        if off is None or ext is None:
            return None
        return {"x": int(off.get("x", 0)), "y": int(off.get("y", 0)), "cx": int(ext.get("cx", 0)),
                "cy": int(ext.get("cy", 0)), "rot": int(x.get("rot", 0)) / 60000.0,
                "flipH": x.get("flipH") == "1", "flipV": x.get("flipV") == "1", "el": x}

    # ---- entry -----------------------------------------------------------------
    def slide_html(self, slide, index: int) -> str:
        st = _Slide(self, index)
        layout = slide.slide_layout
        master = layout.slide_master
        self.theme = Theme(master)
        bg = self._background(slide) or self._background(layout) or self._background(master) or "#FFFFFF"
        st.bg = bg
        if layout.element.get("showMasterSp") != "0" and slide._element.get("showMasterSp") != "0":
            self._tree(st, master.shapes._spTree, master.part, decor=True)
        self._tree(st, layout.shapes._spTree, layout.part, decor=True)
        self._tree(st, slide.shapes._spTree, slide.part)
        body = "".join(st.out)
        return (f'<section class="slide" data-index="{index}" style="width:{self.w}px;height:{self.h}px;'
                f'background:{bg}">{body}</section>')

    def _background(self, obj) -> str | None:
        try:
            bg = obj._element.find("p:cSld/p:bg", NS)
        except Exception:
            return None
        if bg is None:
            return None
        fill = bg.find("p:bgPr/a:solidFill", NS)
        if fill is not None:
            return self.theme.color(fill) if hasattr(self, "theme") else None
        ref = bg.find("p:bgRef", NS)
        if ref is not None:
            return self.theme.color(ref)
        return None

    def _tree(self, st, tree, part, decor=False, tf=None):
        for el in tree.iterchildren():
            tag = el.tag.split("}")[1]
            try:
                if decor and el.find(".//p:nvPr/p:ph", NS) is not None:
                    continue           # placeholders of a layout or master are not drawn
                if tag == "sp":
                    self._shape(st, el, tf)
                elif tag == "cxnSp":
                    self._connector(st, el, tf)
                elif tag == "pic":
                    self._picture(st, el, part, tf)
                elif tag == "graphicFrame":
                    self._frame(st, el, part, tf)
                elif tag == "grpSp":
                    self._group(st, el, part, decor, tf)
            except Exception as exc:  # pragma: no cover - never fail a preview on one shape
                st.out.append(f"<!-- {type(exc).__name__} -->")

    def _box(self, xf, tf=None):
        x, y, w, h = xf["x"], xf["y"], xf["cx"], xf["cy"]
        if tf is not None:
            x, y, w, h = tf(x, y, w, h)
        return _px(x), _px(y), _px(w), _px(h)

    def _group(self, st, el, part, decor, tf):
        g = el.find("p:grpSpPr/a:xfrm", NS)
        if g is None:
            return self._tree(st, el, part, decor, tf)
        off, ext = g.find("a:off", NS), g.find("a:ext", NS)
        choff, chext = g.find("a:chOff", NS), g.find("a:chExt", NS)
        ox, oy = int(off.get("x")), int(off.get("y"))
        ew, eh = int(ext.get("cx")) or 1, int(ext.get("cy")) or 1
        cx0, cy0 = int(choff.get("x")), int(choff.get("y"))
        cw, ch = int(chext.get("cx")) or 1, int(chext.get("cy")) or 1
        sx, sy = ew / cw, eh / ch

        def inner(x, y, w, h):
            nx, ny, nw, nh = ox + (x - cx0) * sx, oy + (y - cy0) * sy, w * sx, h * sy
            return tf(nx, ny, nw, nh) if tf else (nx, ny, nw, nh)
        self._tree(st, el, part, decor, inner)

    # ---- shapes ----------------------------------------------------------------
    def _fill(self, sppr, style=None):
        if sppr is None:
            return None
        if sppr.find("a:noFill", NS) is not None:
            return None
        sf = sppr.find("a:solidFill", NS)
        if sf is not None:
            return self.theme.color(sf)
        if sppr.find("a:gradFill", NS) is not None:
            gs = sppr.find("a:gradFill/a:gsLst/a:gs", NS)
            return self.theme.color(gs) if gs is not None else None
        if style is not None:
            ref = style.find("a:fillRef", NS)
            if ref is not None and ref.get("idx") not in ("0", None):
                return self.theme.color(ref)
        return None

    def _line(self, sppr, style=None):
        ln = sppr.find("a:ln", NS) if sppr is not None else None
        color, width, dash = None, 0.75, None
        if ln is not None:
            if ln.find("a:noFill", NS) is not None:
                return None
            sf = ln.find("a:solidFill", NS)
            if sf is not None:
                color = self.theme.color(sf)
            if ln.get("w"):
                width = int(ln.get("w")) / 12700.0
            pd = ln.find("a:prstDash", NS)
            if pd is not None and pd.get("val") not in ("solid", None):
                dash = pd.get("val")
        if color is None and style is not None:
            ref = style.find("a:lnRef", NS)
            if ref is not None and ref.get("idx") not in ("0", None):
                color = self.theme.color(ref)
        if color is None:
            return None
        return color, max(0.5, width * PT_PX), dash

    def _shape(self, st, el, tf):
        xf = self._xfrm(el)
        if xf is None:
            return
        x, y, w, h = self._box(xf, tf)
        sppr = el.find("p:spPr", NS)
        style = el.find("p:style", NS)
        fill = self._fill(sppr, style)
        line = self._line(sppr, style)
        geom = sppr.find("a:prstGeom", NS) if sppr is not None else None
        prst = geom.get("prst") if geom is not None else ("custom" if sppr is not None and
                                                         sppr.find("a:custGeom", NS) is not None else "rect")
        rot = f"transform:rotate({xf['rot']}deg);" if xf["rot"] else ""
        pos = f"left:{x}px;top:{y}px;width:{w}px;height:{h}px;{rot}"
        if fill and w > 0 and h > 0:
            st.fills.append((x, y, w, h, fill))
        if prst in ("rect", "roundRect", "ellipse", "flowChartProcess"):
            css = pos
            if fill:
                css += f"background:{fill};"
            if line:
                css += f"border:{line[1]:.2f}px {'dashed' if line[2] else 'solid'} {line[0]};"
            if prst == "roundRect":
                adj = 16667
                gd = geom.find("a:avLst/a:gd", NS)
                if gd is not None:
                    m = re.search(r"val (\d+)", gd.get("fmla") or "")
                    adj = int(m.group(1)) if m else adj
                css += f"border-radius:{min(w, h) * adj / 100000:.1f}px;"
            elif prst == "ellipse":
                css += "border-radius:50%;"
            st.out.append(f'<div class="sh" style="{css}"></div>')
        else:
            st.out.append(self._svg_shape(prst, sppr, x, y, w, h, fill, line, rot))
        tx = el.find("p:txBody", NS)
        if tx is not None:
            self._text(st, tx, x, y, w, h, fill, rot, line)

    def _svg_shape(self, prst, sppr, x, y, w, h, fill, line, rot):
        stroke = (f' stroke="{line[0]}" stroke-width="{line[1]:.2f}"'
                  + (' stroke-dasharray="4 3"' if line and line[2] else "")) if line else ""
        fillattr = f' fill="{fill}"' if fill else ' fill="none"'
        d = ""
        if prst == "custom":
            d = self._custom_path(sppr, w, h)
        elif prst == "star5":
            pts = []
            for i in range(10):
                ang = -math.pi / 2 + i * math.pi / 5
                rad = 0.5 if i % 2 == 0 else 0.19
                pts.append((w / 2 + math.cos(ang) * w * rad * 1.0, h / 2 + math.sin(ang) * h * rad * 1.05 + h * 0.03))
            d = "M" + " L".join(f"{px:.2f} {py:.2f}" for px, py in pts) + " Z"
        elif prst in ("triangle", "isoTriangle"):
            d = f"M{w / 2:.2f} 0 L{w:.2f} {h:.2f} L0 {h:.2f} Z"
        elif prst == "chevron":
            d = f"M0 0 L{w * 0.8:.2f} 0 L{w:.2f} {h / 2:.2f} L{w * 0.8:.2f} {h:.2f} L0 {h:.2f} L{w * 0.2:.2f} {h / 2:.2f} Z"
        elif prst == "line":
            d = f"M0 0 L{w:.2f} {h:.2f}"
        else:
            d = f"M0 0 H{w:.2f} V{h:.2f} H0 Z"
        return (f'<svg class="sh" style="left:{x}px;top:{y}px;width:{max(w, 1)}px;height:{max(h, 1)}px;{rot}" '
                f'viewBox="0 0 {max(w, 1):.2f} {max(h, 1):.2f}" preserveAspectRatio="none">'
                f'<path d="{d}"{fillattr}{stroke}/></svg>')

    def _custom_path(self, sppr, w, h):
        out = []
        for path in sppr.findall("a:custGeom/a:pathLst/a:path", NS):
            pw = int(path.get("w") or 0) or 1
            ph = int(path.get("h") or 0) or 1
            sx, sy = w / pw, h / ph
            for cmd in path:
                tag = cmd.tag.split("}")[1]
                pts = [(int(p.get("x")) * sx, int(p.get("y")) * sy) for p in cmd.findall("a:pt", NS)]
                if tag == "moveTo" and pts:
                    out.append(f"M{pts[0][0]:.2f} {pts[0][1]:.2f}")
                elif tag == "lnTo" and pts:
                    out.append(f"L{pts[0][0]:.2f} {pts[0][1]:.2f}")
                elif tag == "cubicBezTo" and len(pts) == 3:
                    out.append("C" + " ".join(f"{a:.2f} {b:.2f}" for a, b in pts))
                elif tag == "close":
                    out.append("Z")
        return " ".join(out)

    def _connector(self, st, el, tf):
        xf = self._xfrm(el)
        if xf is None:
            return
        x, y, w, h = self._box(xf, tf)
        sppr = el.find("p:spPr", NS)
        line = self._line(sppr, el.find("p:style", NS)) or ("#94A3B8", 1.0, None)
        x1, y1, x2, y2 = 0, 0, w, h
        if xf["flipH"]:
            x1, x2 = w, 0
        if xf["flipV"]:
            y1, y2 = h, 0
        arrow = sppr is not None and sppr.find("a:ln/a:tailEnd", NS) is not None
        mid = f"m{st.index}_{len(st.out)}"
        marker = (f'<defs><marker id="{mid}" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">'
                  f'<path d="M0,0 L6,3 L0,6 Z" fill="{line[0]}"/></marker></defs>') if arrow else ""
        st.out.append(
            f'<svg class="sh" style="left:{x - 4}px;top:{y - 4}px;width:{w + 8}px;height:{h + 8}px;overflow:visible" '
            f'viewBox="-4 -4 {w + 8:.2f} {h + 8:.2f}">{marker}<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{line[0]}" stroke-width="{line[1]:.2f}"'
            + (' stroke-dasharray="4 3"' if line[2] else "")
            + (f' marker-end="url(#{mid})"' if arrow else "") + "/></svg>")

    def _picture(self, st, el, part, tf):
        xf = self._xfrm(el)
        blip = el.find(".//a:blip", NS)
        if xf is None or blip is None:
            return
        rid = blip.get(f"{R}embed")
        try:
            img = part.related_part(rid)
        except Exception:
            return
        mime = getattr(img, "content_type", "image/png")
        if not mime.startswith("image/"):
            return
        x, y, w, h = self._box(xf, tf)
        data = base64.b64encode(img.blob).decode("ascii")
        st.out.append(f'<img class="sh" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px" '
                      f'src="data:{mime};base64,{data}" alt="">')

    # ---- text ------------------------------------------------------------------
    def _text(self, st, tx, x, y, w, h, fill, rot, line=None):
        body = tx.find("a:bodyPr", NS)
        ins = {"l": 91440, "t": 45720, "r": 91440, "b": 45720}
        anchor, wrap = "t", True
        if body is not None:
            for k, attr in (("l", "lIns"), ("t", "tIns"), ("r", "rIns"), ("b", "bIns")):
                if body.get(attr) is not None:
                    ins[k] = int(body.get(attr))
            anchor = body.get("anchor") or "t"
            wrap = body.get("wrap") != "none"
        paras_html, total_chars, sizes, lines_est = [], 0, [], 0.0
        inner_w = max(1.0, w - _px(ins["l"]) - _px(ins["r"]))
        inner_h = max(1.0, h - _px(ins["t"]) - _px(ins["b"]))
        text_all = []
        colors = []
        height_px = 0.0
        for p in tx.findall("a:p", NS):
            ppr = p.find("a:pPr", NS)
            algn = (ppr.get("algn") if ppr is not None else None) or "l"
            spc_after = 0.0
            sa = ppr.find("a:spcAft/a:spcPts", NS) if ppr is not None else None
            if sa is not None:
                spc_after = int(sa.get("val")) / 100.0 * PT_PX
            runs_html, ptext, psize = [], "", 0.0
            for r in p:
                tag = r.tag.split("}")[1]
                if tag == "br":
                    runs_html.append("<br>")
                    ptext += "\n"
                    continue
                if tag not in ("r", "fld"):
                    continue
                rpr = r.find("a:rPr", NS)
                t = r.find("a:t", NS)
                txt = t.text if t is not None and t.text else ""
                sz = int(rpr.get("sz")) / 100.0 if rpr is not None and rpr.get("sz") else 18.0
                bold = rpr is not None and rpr.get("b") == "1"
                ital = rpr is not None and rpr.get("i") == "1"
                col = self.theme.color(rpr.find("a:solidFill", NS)) if rpr is not None else None
                col = col or "#" + self.theme.colors.get("tx1", "000000")
                face = None
                if rpr is not None and rpr.find("a:latin", NS) is not None:
                    face = rpr.find("a:latin", NS).get("typeface")
                css = f"font-size:{sz * PT_PX:.2f}px;color:{col};"
                if bold:
                    css += "font-weight:700;"
                if ital:
                    css += "font-style:italic;"
                if face and not face.startswith("+"):
                    css += f"font-family:'{_esc(face)}',{self._family()};"
                runs_html.append(f'<span style="{css}">{_esc(txt)}</span>')
                ptext += txt
                psize = max(psize, sz)
                if txt.strip():
                    sizes.append(sz)
                    # A status dot or a star is a sign, not text: its colour is the
                    # status, and it is not read against its background.
                    if any(ch.isalnum() for ch in txt):
                        colors.append(col)
            if not psize:
                end = p.find("a:endParaRPr", NS)
                psize = int(end.get("sz")) / 100.0 if end is not None and end.get("sz") else 18.0
            text_all.append(ptext)
            ta = {"l": "left", "ctr": "center", "r": "right", "just": "justify"}.get(algn, "left")
            paras_html.append(f'<p style="text-align:{ta};margin:0 0 {spc_after:.2f}px 0;'
                              f'font-size:{psize * PT_PX:.2f}px">{"".join(runs_html) or "&#8203;"}</p>')
            # estimate the lines this paragraph takes, for the overflow check
            line_h = psize * PT_PX * 1.2
            if wrap:
                cpl = max(1.0, inner_w / (psize * PT_PX * 0.47))
                n = 0
                for seg in (ptext.split("\n") or [""]):
                    n += max(1, math.ceil(len(seg) / cpl)) if seg else 1
            else:
                n = 1 + ptext.count("\n")
            height_px += n * line_h + spc_after
            total_chars += len(ptext)
        jc = {"t": "flex-start", "ctr": "center", "b": "flex-end"}.get(anchor, "flex-start")
        ws = "normal" if wrap else "nowrap"
        st.out.append(
            f'<div class="tx" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{rot}'
            f'padding:{_px(ins["t"])}px {_px(ins["r"])}px {_px(ins["b"])}px {_px(ins["l"])}px;'
            f'justify-content:{jc};white-space:{ws}">{"".join(paras_html)}</div>')
        text = "\n".join(text_all).strip()
        if not text:
            return
        st.texts.append(text)
        snippet = text.replace("\n", " ")[:60]
        small = [s for s in sizes if s < MIN_PT]
        if small:
            self._lint(st, "small_text", snippet, size=min(small))
        if wrap and height_px > inner_h * 1.35 + 6:
            self._lint(st, "overflow", snippet)
        elif not wrap:
            longest = max((len(t) for t in "\n".join(text_all).split("\n")), default=0)
            if sizes and longest * max(sizes) * PT_PX * 0.47 > inner_w * 1.35 + 10:
                self._lint(st, "overflow", snippet)
        bgc = fill or self._under(st, x + w / 2, y + h / 2) or getattr(st, "bg", "#FFFFFF")
        for col in set(colors):
            if bgc and bgc.startswith("#") and len(bgc) == 7 and contrast(col, bgc) < 3.0:
                self._lint(st, "contrast", snippet, ratio=round(contrast(col, bgc), 2))
                break
        for ch in BANNED:
            if ch in text:
                self._lint(st, "banned_char", snippet)
                break

    @staticmethod
    def _under(st, cx: float, cy: float) -> str | None:
        """The colour of the last filled shape under this point, if any."""
        for x, y, w, h, col in reversed(st.fills):
            if x <= cx <= x + w and y <= cy <= y + h:
                return col
        return None

    def _family(self) -> str:
        f = getattr(self, "theme", None).font if getattr(self, "theme", None) else "Calibri"
        return f"'{_esc(f)}',Carlito,Calibri,'Segoe UI',Arial,sans-serif"

    def _lint(self, st, kind, text, **extra):
        self.lints.append({"slide": st.index, "kind": kind, "text": text, **extra})

    # ---- tables and charts -----------------------------------------------------
    def _frame(self, st, el, part, tf):
        xf = self._xfrm(el)
        if xf is None:
            return
        x, y, w, h = self._box(xf, tf)
        tbl = el.find(".//a:tbl", NS)
        if tbl is not None:
            return self._table(st, tbl, x, y, w, h, tf)
        chart = el.find(".//c:chart", NS)
        if chart is not None:
            try:
                cpart = part.related_part(chart.get(f"{R}id"))
                return self._chart(st, etree.fromstring(cpart.blob), x, y, w, h)
            except Exception:
                pass
        st.out.append(f'<div class="sh ph" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"></div>')

    def _table(self, st, tbl, x, y, w, h, tf):
        cols = [_px(int(g.get("w"))) for g in tbl.findall("a:tblGrid/a:gridCol", NS)]
        if tf is not None:
            scale = w / max(1.0, sum(cols))
            cols = [c * scale for c in cols]
        rows_html = []
        for tr in tbl.findall("a:tr", NS):
            rh = _px(int(tr.get("h") or 0))
            cells = []
            for tc in tr.findall("a:tc", NS):
                if tc.get("hMerge") == "1" or tc.get("vMerge") == "1":
                    continue
                tcpr = tc.find("a:tcPr", NS)
                fill = self._fill(tcpr) if tcpr is not None else None
                pad = [45720, 91440, 45720, 91440]
                if tcpr is not None:
                    for i, k in enumerate(("marT", "marR", "marB", "marL")):
                        if tcpr.get(k) is not None:
                            pad[i] = int(tcpr.get(k))
                va = {"ctr": "middle", "b": "bottom"}.get(tcpr.get("anchor") if tcpr is not None else "", "top")
                inner = Converter._cell_text(self, st, tc.find("a:txBody", NS), fill)
                span = f' colspan="{tc.get("gridSpan")}"' if tc.get("gridSpan") else ""
                cells.append(f'<td{span} style="background:{fill or "transparent"};vertical-align:{va};'
                             f'padding:{_px(pad[0])}px {_px(pad[1])}px {_px(pad[2])}px {_px(pad[3])}px">'
                             f'{inner}</td>')
            rows_html.append(f'<tr style="height:{rh}px">{"".join(cells)}</tr>')
        colgroup = "".join(f'<col style="width:{c:.2f}px">' for c in cols)
        st.out.append(f'<table class="sh tb" style="left:{x}px;top:{y}px;width:{sum(cols):.2f}px">'
                      f'<colgroup>{colgroup}</colgroup>{"".join(rows_html)}</table>')

    def _cell_text(self, st, tx, fill):
        if tx is None:
            return ""
        out, text = [], []
        for p in tx.findall("a:p", NS):
            ppr = p.find("a:pPr", NS)
            algn = {"ctr": "center", "r": "right"}.get(ppr.get("algn") if ppr is not None else "", "left")
            runs = []
            for r in p.findall("a:r", NS):
                rpr = r.find("a:rPr", NS)
                t = r.find("a:t", NS)
                txt = t.text if t is not None and t.text else ""
                sz = int(rpr.get("sz")) / 100.0 if rpr is not None and rpr.get("sz") else 18.0
                col = (self.theme.color(rpr.find("a:solidFill", NS)) if rpr is not None else None) or "#000000"
                b = rpr is not None and rpr.get("b") == "1"
                runs.append(f'<span style="font-size:{sz * PT_PX:.2f}px;color:{col};'
                            f'{"font-weight:700;" if b else ""}">{_esc(txt)}</span>')
                text.append(txt)
                if txt.strip() and sz < MIN_PT:
                    self._lint(st, "small_text", txt[:60], size=sz)
                if txt.strip() and fill and contrast(col, fill) < 3.0:
                    self._lint(st, "contrast", txt[:60], ratio=round(contrast(col, fill), 2))
            out.append(f'<p style="text-align:{algn};margin:0">{"".join(runs) or "&#8203;"}</p>')
        joined = " ".join(text)
        if any(ch in joined for ch in BANNED):
            self._lint(st, "banned_char", joined[:60])
        st.texts.append(joined)
        return "".join(out)

    def _chart(self, st, root, x, y, w, h):
        plot_l, plot_r, plot_t, plot_b = 34.0, 8.0, 8.0, 18.0
        pw, ph = max(1.0, w - plot_l - plot_r), max(1.0, h - plot_t - plot_b)
        axes = {}
        for ax in root.iter(f"{C}valAx"):
            aid = ax.find("c:axId", NS).get("val")
            sc = ax.find("c:scaling", NS)
            mn = sc.find("c:min", NS) if sc is not None else None
            mx = sc.find("c:max", NS) if sc is not None else None
            axes[aid] = (float(mn.get("val")) if mn is not None else None,
                         float(mx.get("val")) if mx is not None else None,
                         (ax.find("c:axPos", NS).get("val") if ax.find("c:axPos", NS) is not None else "l"),
                         ax.find("c:delete", NS) is not None and ax.find("c:delete", NS).get("val") == "1")
        parts, cats = [], []
        for chart in root.iter(f"{C}lineChart", f"{C}barChart"):
            ax_ids = [a.get("val") for a in chart.findall("c:axId", NS)]
            series = []
            for ser in chart.findall("c:ser", NS):
                vals = []
                for pt in ser.findall(".//c:val//c:pt", NS):
                    v = pt.find("c:v", NS)
                    vals.append((int(pt.get("idx")), float(v.text) if v is not None and v.text else None))
                n = ser.find(".//c:val//c:ptCount", NS)
                count = int(n.get("val")) if n is not None else len(vals)
                arr = [None] * count
                for i, v in vals:
                    if 0 <= i < count:
                        arr[i] = v
                if not cats:
                    cats = [c.find("c:v", NS).text for c in ser.findall(".//c:cat//c:pt", NS)
                            if c.find("c:v", NS) is not None]
                sf = ser.find("c:spPr/a:ln/a:solidFill", NS)
                color = self.theme.color(sf) if sf is not None else "#1E2761"
                series.append((arr, color))
            vax = next((axes[a] for a in ax_ids if a in axes), (None, None, "l", False))
            allv = [v for arr, _c in series for v in arr if v is not None]
            lo = vax[0] if vax[0] is not None else (min(allv) if allv else 0)
            hi = vax[1] if vax[1] is not None else (max(allv) if allv else 1)
            if hi <= lo:
                hi = lo + 1
            for arr, color in series:
                n = max(1, len(arr) - 1)
                pts, cur = [], []
                for i, v in enumerate(arr):
                    if v is None:
                        if cur:
                            pts.append(cur)
                        cur = []
                        continue
                    px = plot_l + pw * i / n
                    py = plot_t + ph * (1 - (v - lo) / (hi - lo))
                    cur.append(f"{px:.1f},{py:.1f}")
                if cur:
                    pts.append(cur)
                for seg in pts:
                    if len(seg) == 1:
                        cx, cy = seg[0].split(",")
                        parts.append(f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{color}"/>')
                    else:
                        parts.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{color}" '
                                     f'stroke-width="2"/>')
            if not vax[3]:
                side_x = plot_l - 4 if vax[2] != "r" else plot_l + pw + 4
                anchor = "end" if vax[2] != "r" else "start"
                for frac, val in ((0, hi), (1, lo)):
                    parts.append(f'<text x="{side_x:.1f}" y="{plot_t + ph * frac + 3:.1f}" font-size="9" '
                                 f'text-anchor="{anchor}" fill="#6B7280">{_num(val)}</text>')
        grid = (f'<line x1="{plot_l}" y1="{plot_t + ph}" x2="{plot_l + pw}" y2="{plot_t + ph}" '
                f'stroke="#CBD5E1" stroke-width="1"/>')
        labels = ""
        if cats:
            step = max(1, math.ceil(len(cats) / max(1, int(pw / 34))))
            n = max(1, len(cats) - 1)
            labels = "".join(f'<text x="{plot_l + pw * i / n:.1f}" y="{h - 4:.1f}" font-size="9" '
                             f'text-anchor="middle" fill="#6B7280">{_esc(c)}</text>'
                             for i, c in enumerate(cats) if i % step == 0)
        st.out.append(f'<svg class="sh" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px" '
                      f'viewBox="0 0 {w:.2f} {h:.2f}">{grid}{"".join(parts)}{labels}</svg>')


def _num(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v / 1000:.1f}k".replace(".0k", "k")
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


CSS = """
.deck{display:flex;flex-direction:column;gap:18px;align-items:center}
.slide{position:relative;overflow:hidden;box-shadow:0 1px 4px rgba(15,23,42,.18);flex:none;
 font-family:Calibri,Carlito,'Segoe UI',Arial,sans-serif;line-height:1.2}
.slide .sh,.slide .tx{position:absolute;box-sizing:border-box}
.slide .tx{display:flex;flex-direction:column;overflow:visible;pointer-events:none}
.slide .tx p{white-space:inherit;overflow-wrap:anywhere}
.slide svg.sh{overflow:visible}
.slide table.tb{border-collapse:collapse;table-layout:fixed}
.slide table.tb td{border:1px solid #fff;overflow:hidden;line-height:1.15}
.slide .ph{border:1px dashed #CBD5E1}
"""


def render(prs, *, title: str = "", standalone: bool = True) -> tuple[str, list[dict], int]:
    """The deck as HTML slides, the readability checks, and the number of slides."""
    conv = Converter(prs)
    slides = [conv.slide_html(s, i) for i, s in enumerate(prs.slides, start=1)]
    body = f'<div class="deck">{"".join(slides)}</div>'
    if not standalone:
        return body, conv.lints, len(slides)
    doc = (f'<!doctype html><html><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{_esc(title)}</title><style>body{{margin:0;padding:18px;background:#E5E7EB}}{CSS}'
           f'</style></head><body>{body}</body></html>')
    return doc, conv.lints, len(slides)
