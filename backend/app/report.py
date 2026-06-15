"""Weekly report: combined dashboard + progress-review, rendered to HTML and PPTX.

Used both for on-demand downloads/emails (routers/reports.py) and for the
automatic weekly send driven by the in-process scheduler (send_due_weekly_reports).
"""
from __future__ import annotations

import html
import io
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import status as st
from .generalconfig import get_general
from .models import Squad, Tribe, utcnow
from .serializers import annual_progress

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
                      since_days: int = 7, now: datetime | None = None) -> dict:
    """Assemble the combined dashboard + weekly-review data for the given scope."""
    from .routers.progress import aggregate_review  # local import avoids a cycle

    now = now or utcnow()
    cfg = get_general(db)
    threshold = cfg.get("staleness_threshold_days")
    year = year or st.current_year_quarter(now)[0]

    review_rows = {r.squad_id: r for r in aggregate_review(db, scope_tribe, since_days, year)}

    tribes = {t.id: t for t in db.scalars(select(Tribe)).all()}
    q = select(Squad).order_by(Squad.display_order, Squad.id)
    squads = [s for s in db.scalars(q).all()
              if scope_tribe is None or s.tribe_id == scope_tribe]

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
    scope_name = tribes[scope_tribe].name if (scope_tribe in tribes) else "Toutes les tribus"

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

def render_pptx(data: dict) -> bytes:
    """Render the report as a .pptx deck. Requires python-pptx."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    def rgb(hexstr: str) -> RGBColor:
        return RGBColor.from_string(hexstr.lstrip("#").upper())

    INK = rgb("#111827")
    MUTED = rgb("#6b7280")

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    SW, SH = prs.slide_width, prs.slide_height

    def add_text(slide, left, top, width, height, text, size, *, bold=False,
                 color=INK, align=PP_ALIGN.LEFT):
        box = slide.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = align
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        return box

    gen = data["generated_at"]
    gen_str = gen.strftime("%d/%m/%Y %H:%M") if isinstance(gen, datetime) else str(gen)

    # --- Title slide
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.9), Inches(2.3), Inches(11.5), Inches(1.2),
             f'{data["app_name"]} — Rapport hebdomadaire', 40, bold=True)
    add_text(s, Inches(0.9), Inches(3.5), Inches(11.5), Inches(0.8),
             f'{data["scope_name"]} · Année {data["year"]}', 22, color=MUTED)
    add_text(s, Inches(0.9), Inches(4.2), Inches(11.5), Inches(0.6),
             f'Généré le {gen_str} · fenêtre {data["since_days"]} jours', 14, color=MUTED)

    # --- Summary slide
    sm = data["summary"]
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.6), Inches(0.4), Inches(12), Inches(0.8), "Synthèse", 28, bold=True)
    kpis = [
        ("Squads", str(sm["squads_total"]), INK),
        ("Progression moy.", f'{sm["avg_progress"]}%', rgb("#16a34a")),
        ("Jalons bloqués", str(sm["blocked"]), rgb("#dc2626") if sm["blocked"] else INK),
        ("Jalons à risque", str(sm["at_risk"]), rgb("#d97706") if sm["at_risk"] else INK),
        ("Objectifs rouges", str(sm["objectives_red"]), rgb("#dc2626") if sm["objectives_red"] else INK),
        ("Reporting périmé", str(sm["stale"]), rgb("#d97706") if sm["stale"] else INK),
    ]
    cw, gap = Inches(3.9), Inches(0.3)
    for i, (label, val, color) in enumerate(kpis):
        col, rowi = i % 3, i // 3
        left = Inches(0.6) + col * (cw + gap)
        top = Inches(1.6) + rowi * Inches(2.3)
        card = s.shapes.add_shape(1, left, top, cw, Inches(2.0))  # rectangle
        card.fill.solid()
        card.fill.fore_color.rgb = rgb("#f9fafb")
        card.line.color.rgb = rgb("#e5e7eb")
        card.shadow.inherit = False
        tf = card.text_frame
        tf.word_wrap = True
        p0 = tf.paragraphs[0]
        p0.alignment = PP_ALIGN.CENTER
        r0 = p0.add_run(); r0.text = val
        r0.font.size = Pt(40); r0.font.bold = True; r0.font.color.rgb = color
        p1 = tf.add_paragraph(); p1.alignment = PP_ALIGN.CENTER
        r1 = p1.add_run(); r1.text = label
        r1.font.size = Pt(14); r1.font.color.rgb = MUTED

    # --- Attention slide
    if data["attention"]:
        s = prs.slides.add_slide(blank)
        add_text(s, Inches(0.6), Inches(0.4), Inches(12), Inches(0.8),
                 "Points d'attention", 28, bold=True)
        box = s.shapes.add_textbox(Inches(0.6), Inches(1.5), Inches(12.1), Inches(5.5))
        tf = box.text_frame
        tf.word_wrap = True
        first = True
        for r in data["attention"][:14]:
            bits = []
            if r["blocked"]:
                bits.append(f'{r["blocked"]} bloqué(s)')
            if r["delta"] < 0:
                bits.append(f'{r["delta"]} pt')
            if r["is_stale"]:
                bits.append('périmé')
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            rn = p.add_run(); rn.text = f'• {r["name"]} — {", ".join(bits)}'
            rn.font.size = Pt(16); rn.font.color.rgb = INK
        # nothing else

    # --- Per-tribe table slides
    for blk in data["tribes"]:
        s = prs.slides.add_slide(blank)
        add_text(s, Inches(0.6), Inches(0.35), Inches(12), Inches(0.7), blk["tribe_name"], 24, bold=True)
        rows = blk["squads"]
        headers = ["Squad", "Resp.", "Statut", "Progr.", "Δ", "Bloq.", "À risq.", "Faits de la semaine"]
        widths = [Inches(2.2), Inches(1.5), Inches(1.2), Inches(0.9), Inches(0.6),
                  Inches(0.7), Inches(0.8), Inches(4.31)]
        nrows = len(rows) + 1
        tbl_shape = s.shapes.add_table(nrows, len(headers), Inches(0.5), Inches(1.25),
                                       sum(widths, Inches(0)), Inches(0.4) + Inches(0.42) * len(rows))
        table = tbl_shape.table
        for ci, w in enumerate(widths):
            table.columns[ci].width = w
        for ci, h in enumerate(headers):
            cell = table.cell(0, ci)
            cell.text = h
            para = cell.text_frame.paragraphs[0]
            para.runs[0].font.size = Pt(11)
            para.runs[0].font.bold = True
            para.runs[0].font.color.rgb = rgb("#374151")
            cell.fill.solid(); cell.fill.fore_color.rgb = rgb("#f3f4f6")
        for ri, r in enumerate(rows, start=1):
            note = (r["note"] or "").replace("\n", " ")
            changes = "; ".join(_change_text(c) for c in r["changes"][:3])
            facts = changes or (f'« {note[:90]} »' if note else "—")
            values = [
                r["name"], r["leader"], _status_label(r["status"]),
                f'{r["annual_pct"]}%',
                (f'+{r["delta"]}' if r["delta"] > 0 else str(r["delta"])),
                str(r["blocked"] or ""), str(r["at_risk"] or ""), facts,
            ]
            for ci, val in enumerate(values):
                cell = table.cell(ri, ci)
                cell.text = val or " "  # avoid an empty paragraph (no run to style)
                runs = cell.text_frame.paragraphs[0].runs
                if not runs:
                    continue
                run = runs[0]
                run.font.size = Pt(10)
                if ci == 2:  # statut colored
                    run.font.color.rgb = rgb(RAG_COLOR[r["status_rag"]])
                    run.font.bold = True
                elif ci == 4 and r["delta"]:
                    run.font.color.rgb = rgb(RAG_COLOR["green"] if r["delta"] > 0 else RAG_COLOR["red"])
                else:
                    run.font.color.rgb = INK

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

    # 1) Fixed recipient list → global report.
    targets: list[tuple[str, int | None]] = [(a, None) for a in cfg.get("recipients", [])]

    # 2) Opt-in users → report scoped to their visibility.
    for u in db.scalars(select(User).where(User.subscribe_weekly_report.is_(True))).all():
        if not u.email:
            continue
        scope = None if u.role == "admin" else u.tribe_id
        targets.append((u.email, scope))

    # De-duplicate (address, scope) pairs.
    seen = set()
    for addr, scope in targets:
        key = (addr.lower(), scope)
        if key in seen:
            continue
        seen.add(key)
        send_to(addr, scope)

    cfg["last_sent_week"] = week
    set_report(db, cfg)
    db.commit()
    return sent
