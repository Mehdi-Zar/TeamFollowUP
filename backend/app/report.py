"""Weekly report: combined dashboard + progress-review, rendered to HTML and PPTX.

Used both for on-demand downloads/emails (routers/reports.py) and for the
automatic weekly send driven by the in-process scheduler (send_due_weekly_reports).
"""
from __future__ import annotations

import html
import io
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import status as st
from .generalconfig import get_general
from .models import Squad, Tribe, utcnow
from .serializers import annual_progress


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

# ----- RAG / status presentation -------------------------------------------------

RAG_COLOR = {"red": "#dc2626", "amber": "#d97706", "green": "#16a34a", "grey": "#6b7280"}

_STATUS_RAG = {"blocked": "red", "at_risk": "amber", "on_track": "green",
               "done": "green", "red": "red", "amber": "amber", "green": "green"}

_STATUS_LABEL_FR = {
    "blocked": "Bloqué", "at_risk": "À risque", "on_track": "En cours",
    "done": "Terminé", "red": "Rouge", "amber": "Orange", "green": "Vert",
}

_CHANGE_LABEL_FR = {
    "jalon_added": "Nouveau jalon", "jalon_status": "Jalon",
    "quarter_pct": "Progression", "objective_rag": "Objectif", "kpi_trend": "KPI",
}


def _status_rag(status: str | None) -> str:
    return _STATUS_RAG.get(status or "", "grey")


def _status_label(status: str | None) -> str:
    return _STATUS_LABEL_FR.get(status or "", status or "—")


def _change_text(ch: dict) -> str:
    kind = ch.get("kind", "")
    label = ch.get("label", "")
    frm, to = ch.get("from"), ch.get("to")
    prefix = _CHANGE_LABEL_FR.get(kind, kind)
    if kind == "jalon_added":
        return f"{prefix} : {label}"
    if to is not None and frm is not None:
        return f"{prefix} {label} : {_status_label(str(frm))} → {_status_label(str(to))}"
    if to is not None:
        return f"{prefix} {label} → {_status_label(str(to))}"
    return f"{prefix} {label}".strip()


# ----- Data assembly --------------------------------------------------------------

def build_report_data(db: Session, scope_tribe: int | None, year: int | None = None,
                      since_days: int = 7, now: datetime | None = None,
                      squad_id: int | None = None) -> dict:
    """Assemble the combined dashboard + weekly-review data for the given scope.

    squad_id, when set, narrows the report to a single squad (ignoring scope_tribe).
    """
    from .routers.progress import aggregate_review  # local import avoids a cycle

    now = now or utcnow()
    cfg = get_general(db)
    threshold = cfg.get("staleness_threshold_days")
    year = year or st.current_year_quarter(now)[0]

    review_rows = {r.squad_id: r for r in aggregate_review(db, scope_tribe, since_days, year)}

    tribes = {t.id: t for t in db.scalars(select(Tribe)).all()}
    q = select(Squad).order_by(Squad.display_order, Squad.id)
    squads = [s for s in db.scalars(q).all()
              if (squad_id is not None and s.id == squad_id)
              or (squad_id is None and (scope_tribe is None or s.tribe_id == scope_tribe))]

    by_tribe: dict[int | None, list[dict]] = {}
    totals = {"squads": 0, "blocked": 0, "at_risk": 0, "objectives_red": 0,
              "stale": 0, "progress_sum": 0}

    for s in squads:
        c = st.counts(s, year)
        f = st.freshness(s, threshold, now)
        prog = st.year_progress(s, year)
        rv = review_rows.get(s.id)
        ann = annual_progress(s, year)
        row = {
            "squad_id": s.id,
            "name": s.name,
            "leader": s.leader.display_name if s.leader else "",
            "status": st.squad_status(s, year),
            "status_rag": _status_rag(st.squad_status(s, year)),
            "quarters": {q: prog[q] for q in (1, 2, 3, 4)},
            "annual_pct": ann,
            "blocked": c["roadmap_blocked"],
            "at_risk": c["roadmap_at_risk"],
            "objectives_red": c["objectives_red"],
            "age_days": f.get("age_days"),
            "is_stale": bool(f.get("is_stale")),
            "delta": rv.progress_delta if rv else 0,
            "confidence": rv.confidence if rv else None,
            "note": rv.note if rv else None,
            "points_in_period": rv.points_in_period if rv else 0,
            "changes": rv.changes if rv else [],
        }
        by_tribe.setdefault(s.tribe_id, []).append(row)
        totals["squads"] += 1
        totals["blocked"] += row["blocked"]
        totals["at_risk"] += row["at_risk"]
        totals["objectives_red"] += row["objectives_red"]
        totals["stale"] += 1 if row["is_stale"] else 0
        totals["progress_sum"] += ann

    # Order squads within a tribe: most blocked / worst movers first.
    for rows in by_tribe.values():
        rows.sort(key=lambda r: (-r["blocked"], r["delta"], r["name"]))

    tribe_blocks = []
    for tid, rows in sorted(by_tribe.items(),
                            key=lambda kv: (tribes[kv[0]].display_order if kv[0] in tribes else 0,
                                            tribes[kv[0]].name if kv[0] in tribes else "")):
        tribe_blocks.append({
            "tribe_id": tid,
            "tribe_name": tribes[tid].name if tid in tribes else "—",
            "squads": rows,
        })

    # Attention list: blocked or regressing squads, across the whole scope.
    attention = [r for blk in tribe_blocks for r in blk["squads"]
                 if r["blocked"] > 0 or r["delta"] < 0 or r["is_stale"]]
    attention.sort(key=lambda r: (-r["blocked"], r["delta"]))

    avg = round(totals["progress_sum"] / totals["squads"]) if totals["squads"] else 0
    if squad_id is not None:
        sq = db.get(Squad, squad_id)
        scope_name = f"Squad {sq.name}" if sq else "Squad"
    elif scope_tribe in tribes:
        scope_name = tribes[scope_tribe].name
    else:
        scope_name = "Toutes les tribus"

    return {
        "app_name": cfg.get("app_name") or "Tribe Cockpit",
        "subtitle": cfg.get("app_subtitle") or "",
        "scope_name": scope_name,
        "year": year,
        "since_days": since_days,
        "generated_at": now,
        "summary": {
            "squads_total": totals["squads"],
            "blocked": totals["blocked"],
            "at_risk": totals["at_risk"],
            "objectives_red": totals["objectives_red"],
            "stale": totals["stale"],
            "avg_progress": avg,
        },
        "tribes": tribe_blocks,
        "attention": attention,
    }


# ----- HTML rendering -------------------------------------------------------------

def _bar(pct: int, rag: str = "green") -> str:
    pct = max(0, min(100, int(pct or 0)))
    color = RAG_COLOR.get(rag, RAG_COLOR["green"])
    return (
        f'<div class="bar"><div class="bar-fill" style="width:{pct}%;background:{color}"></div>'
        f'<span class="bar-label">{pct}%</span></div>'
    )


def _delta_html(delta: int) -> str:
    if delta > 0:
        return f'<span style="color:{RAG_COLOR["green"]}">▲ +{delta}</span>'
    if delta < 0:
        return f'<span style="color:{RAG_COLOR["red"]}">▼ {delta}</span>'
    return '<span style="color:#6b7280">→ 0</span>'


def render_html(data: dict, *, standalone: bool = True) -> str:
    e = html.escape
    s = data["summary"]
    gen = data["generated_at"]
    gen_str = gen.strftime("%d/%m/%Y %H:%M") if isinstance(gen, datetime) else str(gen)

    parts: list[str] = []
    parts.append(f'<div class="hdr"><h1>{e(data["app_name"])} — Rapport hebdomadaire</h1>')
    parts.append(f'<div class="sub">{e(data["scope_name"])} · Année {data["year"]} · '
                 f'généré le {e(gen_str)} · fenêtre {data["since_days"]} j</div></div>')

    # Summary cards
    cards = [
        ("Squads", s["squads_total"], "#111827"),
        ("Progression moy.", f'{s["avg_progress"]}%', RAG_COLOR["green"]),
        ("Jalons bloqués", s["blocked"], RAG_COLOR["red"] if s["blocked"] else "#111827"),
        ("Jalons à risque", s["at_risk"], RAG_COLOR["amber"] if s["at_risk"] else "#111827"),
        ("Objectifs rouges", s["objectives_red"], RAG_COLOR["red"] if s["objectives_red"] else "#111827"),
        ("Reporting périmé", s["stale"], RAG_COLOR["amber"] if s["stale"] else "#111827"),
    ]
    parts.append('<div class="cards">')
    for label, val, color in cards:
        parts.append(f'<div class="kpi"><div class="kpi-val" style="color:{color}">{e(str(val))}</div>'
                     f'<div class="kpi-lbl">{e(label)}</div></div>')
    parts.append('</div>')

    # Attention list
    if data["attention"]:
        parts.append('<h2>Points d\'attention</h2><ul class="attention">')
        for r in data["attention"][:12]:
            bits = []
            if r["blocked"]:
                bits.append(f'{r["blocked"]} bloqué(s)')
            if r["delta"] < 0:
                bits.append(f'{r["delta"]} pt')
            if r["is_stale"]:
                bits.append('périmé')
            parts.append(f'<li><span class="dot" style="background:{RAG_COLOR["red"]}"></span>'
                         f'<strong>{e(r["name"])}</strong> — {e(", ".join(bits))}</li>')
        parts.append('</ul>')

    # Per-tribe tables
    for blk in data["tribes"]:
        parts.append(f'<h2>{e(blk["tribe_name"])}</h2>')
        parts.append('<table><thead><tr>'
                     '<th>Squad</th><th>Responsable</th><th>Statut</th>'
                     '<th>Progression</th><th>Δ sem.</th><th>Bloqués</th>'
                     '<th>À risque</th><th>Faits de la semaine</th>'
                     '</tr></thead><tbody>')
        for r in blk["squads"]:
            changes = r["changes"][:4]
            ch_html = "<br>".join(e(_change_text(c)) for c in changes) if changes else \
                ('<span class="muted">—</span>' if not r["note"] else "")
            if r["note"]:
                note = e(r["note"]).replace("\n", " ")
                if len(note) > 160:
                    note = note[:159] + "…"
                ch_html = (ch_html + "<br>" if ch_html else "") + f'<em class="note">« {note} »</em>'
            stale_badge = ' <span class="badge">périmé</span>' if r["is_stale"] else ""
            parts.append(
                f'<tr><td><strong>{e(r["name"])}</strong>{stale_badge}</td>'
                f'<td>{e(r["leader"])}</td>'
                f'<td><span class="pill" style="background:{RAG_COLOR[r["status_rag"]]}">'
                f'{e(_status_label(r["status"]))}</span></td>'
                f'<td>{_bar(r["annual_pct"], r["status_rag"])}</td>'
                f'<td>{_delta_html(r["delta"])}</td>'
                f'<td>{r["blocked"] or ""}</td><td>{r["at_risk"] or ""}</td>'
                f'<td class="changes">{ch_html}</td></tr>'
            )
        parts.append('</tbody></table>')

    body = "\n".join(parts)
    if not standalone:
        return f'<div class="tc-report">{_CSS}{body}</div>'
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        f'<title>{e(data["app_name"])} — Rapport hebdomadaire</title>'
        f'{_CSS}</head><body><div class="tc-report">{body}</div></body></html>'
    )


_CSS = """<style>
.tc-report{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111827;
  max-width:980px;margin:0 auto;padding:24px;line-height:1.45;background:#fff}
.tc-report h1{font-size:22px;margin:0 0 4px}
.tc-report h2{font-size:16px;margin:26px 0 10px;border-bottom:2px solid #e5e7eb;padding-bottom:4px}
.tc-report .sub{color:#6b7280;font-size:13px}
.tc-report .cards{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.tc-report .kpi{flex:1;min-width:120px;border:1px solid #e5e7eb;border-radius:10px;padding:12px 14px;background:#f9fafb}
.tc-report .kpi-val{font-size:24px;font-weight:700}
.tc-report .kpi-lbl{font-size:12px;color:#6b7280;margin-top:2px}
.tc-report table{width:100%;border-collapse:collapse;font-size:13px}
.tc-report th{text-align:left;background:#f3f4f6;padding:7px 9px;border-bottom:2px solid #e5e7eb;font-size:12px;color:#374151}
.tc-report td{padding:7px 9px;border-bottom:1px solid #eef0f3;vertical-align:top}
.tc-report .pill{color:#fff;border-radius:999px;padding:2px 9px;font-size:11px;white-space:nowrap}
.tc-report .bar{position:relative;background:#eef0f3;border-radius:6px;height:16px;width:120px;overflow:hidden}
.tc-report .bar-fill{position:absolute;left:0;top:0;bottom:0;border-radius:6px}
.tc-report .bar-label{position:relative;font-size:11px;padding-left:6px;line-height:16px;color:#111827}
.tc-report .changes{color:#374151;font-size:12px}
.tc-report .note{color:#4b5563}
.tc-report .muted{color:#9ca3af}
.tc-report .badge{background:#fef3c7;color:#92400e;border-radius:4px;padding:1px 5px;font-size:10px}
.tc-report ul.attention{list-style:none;padding:0;margin:0}
.tc-report ul.attention li{padding:5px 0;font-size:13px}
.tc-report .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px}
</style>"""


# ----- PPTX rendering -------------------------------------------------------------

# Brand palette (mirrors the app theme): navy / accent + RAG.
_BRAND = {
    "navy": "#1E2761", "navy_deep": "#141B47", "accent": "#175CD3",
    "green": "#027A48", "orange": "#B54708", "red": "#B42318",
    "ink": "#1F2937", "muted": "#6B7280", "card": "#F1F5F9",
    "line": "#E2E8F0", "white": "#FFFFFF", "zebra": "#F8FAFC",
}
_RAG_BRAND = {"red": "#B42318", "amber": "#B54708", "green": "#027A48", "grey": "#6B7280"}


def render_pptx(data: dict) -> bytes:
    """Render the report as a single branded slide (one-pager). Requires python-pptx."""
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

    def rgb(hexstr: str) -> RGBColor:
        return RGBColor.from_string(hexstr.lstrip("#").upper())

    B = {k: rgb(v) for k, v in _BRAND.items()}

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    s = prs.slides.add_slide(prs.slide_layouts[6])

    def textbox(left, top, width, height, text, size, *, bold=False, color=B["ink"],
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
        r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color
        return box

    def rect(left, top, width, height, fill, line=None):
        from pptx.enum.shapes import MSO_SHAPE
        sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
        sh.fill.solid(); sh.fill.fore_color.rgb = fill
        if line is None:
            sh.line.fill.background()
        else:
            sh.line.color.rgb = line
        sh.shadow.inherit = False
        return sh

    gen = data["generated_at"]
    gen_str = gen.strftime("%d/%m/%Y %H:%M") if isinstance(gen, datetime) else str(gen)
    sm = data["summary"]
    squads = [r for blk in data["tribes"] for r in blk["squads"]]

    # --- Header band (navy)
    rect(Inches(0), Inches(0), prs.slide_width, Inches(1.12), B["navy"])
    textbox(Inches(0.55), Inches(0.18), Inches(9.5), Inches(0.5),
            f'{data["app_name"]} — Rapport', 26, bold=True, color=B["white"])
    textbox(Inches(0.57), Inches(0.68), Inches(9.5), Inches(0.35),
            f'{data["scope_name"]} · Année {data["year"]}', 13, color=rgb("#C7D2FE"))
    textbox(Inches(9.3), Inches(0.3), Inches(3.5), Inches(0.6),
            f'Généré le {gen_str}\nFenêtre {data["since_days"]} j', 11,
            color=rgb("#C7D2FE"), align=PP_ALIGN.RIGHT)

    # --- KPI banner (6 cards)
    kpis = [
        ("Squads", str(sm["squads_total"]), B["navy"]),
        ("Progression moy.", f'{sm["avg_progress"]}%', B["accent"]),
        ("Jalons bloqués", str(sm["blocked"]), B["red"] if sm["blocked"] else B["ink"]),
        ("Jalons à risque", str(sm["at_risk"]), B["orange"] if sm["at_risk"] else B["ink"]),
        ("Objectifs rouges", str(sm["objectives_red"]), B["red"] if sm["objectives_red"] else B["ink"]),
        ("Reporting périmé", str(sm["stale"]), B["orange"] if sm["stale"] else B["ink"]),
    ]
    margin = Inches(0.5)
    gap = Inches(0.14)
    n = len(kpis)
    total_w = prs.slide_width - margin * 2
    card_w = Emu(int((total_w - gap * (n - 1)) / n))
    ky, kh = Inches(1.34), Inches(1.05)
    for i, (label, val, color) in enumerate(kpis):
        left = Emu(int(margin) + i * (int(card_w) + int(gap)))
        rect(left, ky, card_w, kh, B["card"], line=B["line"])
        textbox(left, Inches(1.46), card_w, Inches(0.5), val, 26, bold=True, color=color, align=PP_ALIGN.CENTER)
        textbox(left, Inches(2.04), card_w, Inches(0.3), label, 10, color=B["muted"], align=PP_ALIGN.CENTER)

    # --- Squads table (mini)
    headers = ["Squad", "Responsable", "Statut", "Progr.", "Δ sem.", "Bloqués", "À risque"]
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

    for ci, h in enumerate(headers):
        align = PP_ALIGN.LEFT if ci < 2 else PP_ALIGN.CENTER
        style_cell(tbl.cell(0, ci), h, 10, B["white"], bold=True, align=align, fill=B["navy"])

    for ri, r in enumerate(shown, start=1):
        zebra = B["zebra"] if ri % 2 == 0 else B["white"]
        delta = r["delta"]
        cells = [
            (r["name"], B["ink"], True, PP_ALIGN.LEFT),
            (r["leader"] or "—", B["muted"], False, PP_ALIGN.LEFT),
            (_status_label(r["status"]), rgb(_RAG_BRAND[r["status_rag"]]), True, PP_ALIGN.CENTER),
            (f'{r["annual_pct"]}%', B["ink"], False, PP_ALIGN.CENTER),
            ((f'+{delta}' if delta > 0 else str(delta)),
             (B["green"] if delta > 0 else B["red"]) if delta else B["muted"], False, PP_ALIGN.CENTER),
            (str(r["blocked"] or "—"), B["red"] if r["blocked"] else B["muted"], r["blocked"] > 0, PP_ALIGN.CENTER),
            (str(r["at_risk"] or "—"), B["orange"] if r["at_risk"] else B["muted"], r["at_risk"] > 0, PP_ALIGN.CENTER),
        ]
        for ci, (val, color, bold, align) in enumerate(cells):
            style_cell(tbl.cell(ri, ci), val, 9.5, color, bold=bold, align=align, fill=zebra)

    if overflow > 0:
        last = len(shown) + 1
        style_cell(tbl.cell(last, 0), f'… +{overflow} autres squads', 9, B["muted"], align=PP_ALIGN.LEFT)
        for ci in range(1, len(headers)):
            style_cell(tbl.cell(last, ci), " ", 9, B["muted"])

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ----- Automatic weekly send ------------------------------------------------------

def _iso_week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def send_due_weekly_reports(db: Session, now: datetime | None = None) -> int:
    """Send the weekly report if today/now matches the configured schedule.

    Idempotent within an ISO week (guarded by last_sent_week). Returns the number
    of emails sent. Safe to call repeatedly from the scheduler.
    """
    from .reportconfig import get_report, set_report
    from .smtpconfig import get_smtp
    from .mail import send_email
    from .models import User
    from .modulesconfig import get_modules, is_active

    now = now or utcnow()
    if not is_active(get_modules(db), "review", "weekly_report"):
        return 0
    cfg = get_report(db)
    if not cfg.get("enabled"):
        return 0
    smtp = get_smtp(db)
    if not smtp.get("enabled"):
        return 0
    if now.weekday() != cfg["weekday"] or now.hour < cfg["hour"]:
        return 0
    week = _iso_week_key(now)
    if cfg.get("last_sent_week") == week:
        return 0

    since = cfg.get("since_days", 7)
    year = st.current_year_quarter(now)[0]

    # Cache rendered output per scope (None = global) to avoid recomputation.
    rendered: dict[int | None, tuple[str, bytes]] = {}

    def render_scope(scope: int | None) -> tuple[str, bytes]:
        if scope not in rendered:
            data = build_report_data(db, scope, year, since, now)
            html_body = render_html(data, standalone=True)
            try:
                pptx_bytes = render_pptx(data)
            except Exception:
                pptx_bytes = b""
            rendered[scope] = (html_body, pptx_bytes)
        return rendered[scope]

    subject = f'Rapport hebdomadaire — semaine {now.isocalendar()[1]}'
    sent = 0

    def send_to(addr: str, scope: int | None) -> None:
        nonlocal sent
        html_body, pptx_bytes = render_scope(scope)
        attachment = None
        if pptx_bytes:
            attachment = (f"rapport_hebdo_{week}.pptx", pptx_bytes,
                          "application", "vnd.openxmlformats-officedocument.presentationml.presentation")
        if send_email(smtp, addr, subject, html_body, attachment=attachment, html=True):
            sent += 1

    # Fixed recipient list → global report. (Per-user subscriptions are handled
    # separately by send_personal_subscriptions, on each user's own cadence.)
    seen = set()
    for addr in cfg.get("recipients", []):
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        send_to(addr, None)

    cfg["last_sent_week"] = week
    set_report(db, cfg)
    db.commit()
    return sent


def send_personal_subscriptions(db: Session, now: datetime | None = None) -> int:
    """Send the report to each subscription (global or per-squad) that is due.

    A global subscription (squad_id NULL) follows the user's visibility (admin →
    all tribes, others → their tribe); a per-squad subscription targets that squad.
    Returns the number of emails sent. Safe to call repeatedly from the scheduler.
    """
    from .smtpconfig import get_smtp
    from .mail import send_email
    from .models import ReportSubscription, User
    from .modulesconfig import get_modules, is_active

    now = now or utcnow()
    if not is_active(get_modules(db), "review", "weekly_report"):
        return 0
    smtp = get_smtp(db)
    if not smtp.get("enabled"):
        return 0

    year = st.current_year_quarter(now)[0]
    # Cache rendered output per (scope_tribe, squad_id) key.
    rendered: dict[tuple, tuple[str, bytes]] = {}

    def render(scope_tribe: int | None, squad_id: int | None, since: int) -> tuple[str, bytes]:
        key = (scope_tribe, squad_id)
        if key not in rendered:
            data = build_report_data(db, scope_tribe, year, since, now, squad_id=squad_id)
            html_body = render_html(data, standalone=True)
            try:
                pptx_bytes = render_pptx(data)
            except Exception:
                pptx_bytes = b""
            rendered[key] = (html_body, pptx_bytes)
        return rendered[key]

    sent = 0
    for sub in db.scalars(select(ReportSubscription).where(ReportSubscription.interval_days > 0)).all():
        user = db.get(User, sub.user_id)
        if user is None or not user.email:
            continue
        last = _aware(sub.last_sent_at)
        if last is not None and (now - last) < timedelta(days=sub.interval_days):
            continue
        since = max(sub.interval_days, 7)
        if sub.squad_id is not None:
            html_body, pptx_bytes = render(None, sub.squad_id, since)
        else:
            scope_tribe = None if user.role == "admin" else user.tribe_id
            html_body, pptx_bytes = render(scope_tribe, None, since)
        attachment = None
        if pptx_bytes:
            attachment = (f"rapport_{now.date().isoformat()}.pptx", pptx_bytes,
                          "application", "vnd.openxmlformats-officedocument.presentationml.presentation")
        subject = f"Rapport — {sub.interval_days} j"
        if send_email(smtp, user.email, subject, html_body, attachment=attachment, html=True):
            sub.last_sent_at = now
            if sub.squad_id is None:
                user.report_last_sent_at = now
            sent += 1
    if sent:
        db.commit()
    return sent
