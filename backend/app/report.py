"""Weekly report: combined dashboard + progress-review, rendered to HTML and PPTX.

Used both for on-demand downloads/emails (routers/reports.py) and for the
automatic weekly send driven by the in-process scheduler (send_due_weekly_reports).
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

# Shared with the PPTX renderers; see reportcommon.
from .reportcommon import (STAGE_COLOR, _DEP_T, _INIT_T, _MONTHS, _lang,  # noqa: F401
                           _status_label, _status_rag, group_by_theme, rt)
# Re-exported so `from .report import render_pptx` keeps working; the decks
# themselves live in reportpptx.
from .reportpptx import (_pptx_toolkit, render_dependencies_pptx,  # noqa: F401
                         render_initiatives_pptx, render_pptx, render_roadmap_pptx)


def _budget_for_report(squad, year: int, viewer) -> dict | None:
    """Budget figures for a report, only when the viewer may see this squad's
    budget (admin / its tribe leader / its own squad leader) and it is enabled."""
    if viewer is None or not squad.budget_enabled:
        return None
    from .deps import is_squad_privileged
    if not is_squad_privileged(viewer, squad):
        return None
    b = budget_out(squad, year)
    return {
        "total": b.total, "spent": b.spent, "forecast": b.forecast,
        "status": b.status, "spent_pct": b.spent_pct, "forecast_pct": b.forecast_pct,
        "overrun": b.overrun, "overrun_pct": b.overrun_pct, "comment": b.comment,
    }


def _aware(dt: datetime | None) -> datetime | None:
    """Coerce a datetime to timezone-aware UTC (naive values are treated as UTC).

    Snapshots/models may store naive datetimes; comparisons and formatting here
    must be tz-aware to avoid mixing naive and aware values."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ----- RAG / status presentation -------------------------------------------------
# Presentation-layer maps and helpers that turn raw status codes into colours and
# localized labels. RAG = Red/Amber/Green (+ grey for "unknown").

RAG_COLOR = {"red": "#dc2626", "amber": "#d97706", "green": "#16a34a", "grey": "#6b7280"}


# Roadmap milestone palette (mirrors the reference "Global Roadmap" slide):
# navy ink for titles/themes, gold for EA, green for GA.
RM_INK = "#002060"


_CHANGE_LABELS = {
    "fr": {"jalon_added": "Nouveau jalon", "jalon_status": "Jalon",
           "quarter_pct": "Progression", "objective_rag": "Objectif", "kpi_trend": "KPI"},
    "en": {"jalon_added": "New milestone", "jalon_status": "Milestone",
           "quarter_pct": "Progress", "objective_rag": "Objective", "kpi_trend": "KPI"},
}


# Leave types are stored as French labels; in English show "English (French)".
_LEAVE_TYPE_EN = {
    "Congés payés": "Paid leave", "RTT": "RTT", "Maladie": "Sick leave",
    "Formation": "Training", "Autre": "Other",
}


def leave_type_label(label: str, lang: str) -> str:
    """Localize a leave-type label. Leave types are stored in French; for an
    English report keep the French original in parentheses so it stays recognizable."""
    if _lang(lang) != "en":
        return label
    en = _LEAVE_TYPE_EN.get(label)
    return f"{en} ({label})" if en and en != label else label


def _change_text(ch: dict, lang: str = "fr") -> str:
    """Render one change record (from the per-squad 'changes' list) as a localized
    sentence, e.g. 'Milestone X: At risk → Blocked'. Handles added items and
    from/to transitions, adapting the separator to the language."""
    kind = ch.get("kind", "")
    label = ch.get("label", "")
    frm, to = ch.get("from"), ch.get("to")
    prefix = _CHANGE_LABELS[_lang(lang)].get(kind, kind)
    sep = " : " if _lang(lang) == "fr" else ": "
    if kind == "jalon_added":
        return f"{prefix}{sep}{label}"
    if to is not None and frm is not None:
        return f"{prefix} {label}{sep}{_status_label(str(frm), lang)} → {_status_label(str(to), lang)}"
    if to is not None:
        return f"{prefix} {label} → {_status_label(str(to), lang)}"
    return f"{prefix} {label}".strip()


# ----- Data assembly --------------------------------------------------------------

def build_report_data(db: Session, scope_tribe: int | None, year: int | None = None,
                      since_days: int = 7, now: datetime | None = None,
                      squad_id: int | None = None, lang: str | None = None,
                      squad_ids: list[int] | None = None, viewer=None) -> dict:
    """Assemble the combined dashboard + weekly-review data for the given scope.

    squad_id, when set, narrows the report to a single squad (ignoring scope_tribe).
    squad_ids, when set, restricts the report to that subset of squads (still within
    the caller's tribe scope) - used to pick which squads appear in a global roadmap.
    lang, when set, picks the report language; otherwise the general default_lang.
    """
    now = now or utcnow()
    cfg = get_general(db)
    threshold = cfg.get("staleness_threshold_days")
    year = year or st.current_year_quarter(now)[0]
    lang = _lang(lang or cfg.get("default_lang"))

    tribes = {t.id: t for t in db.scalars(select(Tribe)).all()}
    q = select(Squad).order_by(Squad.display_order, Squad.id).options(
        selectinload(Squad.objectives), selectinload(Squad.roadmap_items),
        selectinload(Squad.quarter_progress), selectinload(Squad.kpis),
        selectinload(Squad.snapshots), selectinload(Squad.leader),
        selectinload(Squad.budgets), selectinload(Squad.key_messages),
    )
    id_filter = set(squad_ids) if squad_ids else None
    squads = []
    for s in db.scalars(q).all():
        if squad_id is not None:
            if s.id == squad_id:
                squads.append(s)
            continue
        if scope_tribe is not None and s.tribe_id != scope_tribe:
            continue  # tribe scope is the security boundary
        if id_filter is not None and s.id not in id_filter:
            continue  # caller-chosen subset
        squads.append(s)

    # Initiatives assigned to each squad (shown in that squad's report/dashboard).
    from .models import Initiative
    init_by_squad: dict[int, list[dict]] = {}
    sq_ids = [s.id for s in squads]
    if sq_ids:
        irows = db.scalars(
            select(Initiative).where(Initiative.year == year, Initiative.squad_id.in_(sq_ids))
            .order_by(Initiative.display_order, Initiative.id)).all()
        for it in irows:
            init_by_squad.setdefault(it.squad_id, []).append({
                "title": it.title, "owner": it.owner,
                "deadline": it.deadline.date().isoformat() if it.deadline else None})

    by_tribe: dict[int | None, list[dict]] = {}
    totals = {"squads": 0, "blocked": 0, "at_risk": 0, "objectives_red": 0,
              "stale": 0, "progress_sum": 0}

    for s in squads:
        c = st.counts(s, year)
        f = st.freshness(s, threshold, now)
        prog = st.year_progress(s, year)
        comments = st.quarter_comments(s, year)
        ann = annual_progress(s, year)
        # Full per-squad content (objectives + roadmap by quarter + advancement),
        # so the report/PPTX can show everything, not just the dashboard summary.
        detail = {
            "initiatives": init_by_squad.get(s.id, []),
            "objectives": [
                {"title": o.title,
                 "rag": st.objective_status(o, s, now),
                 "target_date": o.target_date.date().isoformat() if o.target_date else None}
                for o in sorted(s.objectives, key=lambda x: x.id)
                if o.year == year and o.is_active
            ],
            "quarters": [
                {"q": q, "pct": prog[q], "comment": comments.get(q),
                 "items": [
                     {"title": r.title, "status": r.status, "owner": r.owner,
                      "stage": r.release_stage, "theme": r.theme,
                      "dependency": dependency_label(r)}
                     for r in sorted(s.roadmap_items, key=lambda x: (x.display_order, x.id))
                     if r.year == year and r.quarter == q
                 ]}
                for q in (1, 2, 3, 4)
            ],
            # Hand-curated key messages (success / alert / risk) for this squad/year.
            "key_messages": [
                {"kind": m.kind, "text": m.text,
                 "created_at": _aware(m.created_at).strftime("%Y-%m-%d %H:%M") if m.created_at else None}
                for m in sorted(s.key_messages, key=lambda x: (x.display_order, x.id))
                if m.year == year
            ],
            # Budget readout - only for a viewer allowed to see this squad's figures.
            "budget": _budget_for_report(s, year, viewer),
        }
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
            "delta": 0,
            "confidence": None,
            "note": None,
            "points_in_period": 0,
            "changes": [],
            "detail": detail,
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
            "tribe_name": tribes[tid].name if tid in tribes else "-",
            "squads": rows,
        })

    # Attention list: blocked or regressing squads, across the whole scope.
    attention = [r for blk in tribe_blocks for r in blk["squads"]
                 if r["blocked"] > 0 or r["delta"] < 0 or r["is_stale"]]
    attention.sort(key=lambda r: (-r["blocked"], r["delta"]))

    avg = round(totals["progress_sum"] / totals["squads"]) if totals["squads"] else 0
    if squad_id is not None:
        sq = db.get(Squad, squad_id)
        scope_name = rt(lang, "squad_scope", name=sq.name) if sq else rt(lang, "h_squad")
    elif scope_tribe in tribes:
        scope_name = tribes[scope_tribe].name
    else:
        scope_name = rt(lang, "all_tribes")

    leaves_upcoming = _upcoming_leaves(db, scope_tribe, squad_id, sq_ids, now)

    return {
        "app_name": cfg.get("app_name") or "TeamFollowUP",
        "subtitle": cfg.get("app_subtitle") or "",
        "scope_name": scope_name,
        "squad_scoped": squad_id is not None,
        "lang": lang,
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
        "leaves_upcoming": leaves_upcoming,
    }


def _upcoming_leaves(db: Session, scope_tribe: int | None, squad_id: int | None,
                     sq_ids: list[int], now: datetime) -> list[dict]:
    """Approved/pending absences ending in the next 30 days, scoped like the report.
    Empty list when the leaves module is disabled."""
    from .modulesconfig import get_modules, is_active
    if not is_active(get_modules(db), "leaves"):
        return []
    from .leavesconfig import ACTIVE_STATUSES, leave_days
    from .models import Leave, Member, User

    today = now.date()
    horizon = today + timedelta(days=30)
    stmt = select(Leave).where(Leave.status.in_(ACTIVE_STATUSES),
                               Leave.end_date >= today, Leave.start_date <= horizon)
    if squad_id is not None:
        uids = list(db.scalars(select(Member.user_id).where(
            Member.squad_id == squad_id, Member.user_id.isnot(None))).all())
        stmt = stmt.where(Leave.user_id.in_(uids or [-1]))
    elif scope_tribe is not None:
        stmt = stmt.where(Leave.tribe_id == scope_tribe)
    elif sq_ids:
        uids = list(db.scalars(select(Member.user_id).where(
            Member.squad_id.in_(sq_ids), Member.user_id.isnot(None))).all())
        stmt = stmt.where(Leave.user_id.in_(uids or [-1]))

    out: list[dict] = []
    names: dict[int, str] = {}
    for lv in db.scalars(stmt.order_by(Leave.start_date, Leave.id)).all():
        if lv.user_id not in names:
            u = db.get(User, lv.user_id)
            names[lv.user_id] = u.display_name if u else f"#{lv.user_id}"
        out.append({
            "name": names[lv.user_id],
            "type_label": lv.type.label if lv.type else "",
            "detail": lv.detail or "",
            "type_color": lv.type.color if lv.type else "#6B7280",
            "start": lv.start_date.strftime("%d/%m"), "end": lv.end_date.strftime("%d/%m"),
            "days": leave_days(lv), "status": lv.status,
        })
    return out


# ----- HTML rendering -------------------------------------------------------------

def _bar(pct: int, rag: str = "green") -> str:
    """HTML progress bar clamped to 0..100, filled with the RAG colour."""
    pct = max(0, min(100, int(pct or 0)))
    color = RAG_COLOR.get(rag, RAG_COLOR["green"])
    return (
        f'<div class="bar"><div class="bar-fill" style="width:{pct}%;background:{color}"></div>'
        f'<span class="bar-label">{pct}%</span></div>'
    )


def _delta_html(delta: int) -> str:
    """Week-over-week delta as a coloured arrow (▲ green / ▼ red / → neutral)."""
    if delta > 0:
        return f'<span style="color:{RAG_COLOR["green"]}">▲ +{delta}</span>'
    if delta < 0:
        return f'<span style="color:{RAG_COLOR["red"]}">▼ {delta}</span>'
    return '<span style="color:#6b7280">→ 0</span>'


def _squad_detail_parts(r: dict, lang: str, e, *, with_title: bool = True) -> list[str]:
    """One squad's detail block, in the exact order of the squad page:
    Initiatives → OTD → Roadmap → Key messages → Budget."""
    det = r.get("detail") or {}
    parts: list[str] = ['<div class="sq-detail">']
    if with_title:
        parts.append(f'<h3>{e(r["name"])} <span class="muted">· {r["annual_pct"]}%</span></h3>')

    # Initiatives
    inits = det.get("initiatives") or []
    if inits:
        parts.append(f'<div class="d-sub">{e(rt(lang, "h_initiatives"))}</div><ul class="d-obj">')
        for ini in inits:
            meta = []
            if ini.get("owner"):
                meta.append(e(ini["owner"]))
            if ini.get("deadline"):
                meta.append(f'{e(rt(lang, "deadline"))} {e(ini["deadline"])}')
            tail = f' <span class="muted">({e(" · ".join(meta))})</span>' if meta else ""
            parts.append(f'<li>{e(ini["title"])}{tail}</li>')
        parts.append('</ul>')

    # OTD (annual objectives)
    parts.append(f'<div class="d-sub">{e(rt(lang, "h_otd_section"))}</div>')
    if det.get("objectives"):
        parts.append('<ul class="d-obj">')
        for o in det["objectives"]:
            rag = _status_rag(o["rag"])
            dl = f' · {e(rt(lang, "deadline"))} {e(o["target_date"])}' if o.get("target_date") else ""
            parts.append(f'<li><span class="dot" style="background:{RAG_COLOR[rag]}"></span>'
                         f'{e(o["title"])} <span class="muted">({e(_status_label(o["rag"], lang))}{dl})</span></li>')
        parts.append('</ul>')
    else:
        parts.append(f'<div class="muted small">{e(rt(lang, "no_obj"))}</div>')

    # Roadmap by quarter
    parts.append(f'<div class="d-sub">{e(rt(lang, "h_roadmap"))}</div><div class="d-quarters">')
    for qd in det.get("quarters", []):
        parts.append(f'<div class="d-q"><div class="d-q-head">Q{qd["q"]} '
                     f'<span class="muted">{qd["pct"]}%</span></div>')
        if qd["items"]:
            parts.append('<ul>')
            for it in qd["items"]:
                rag = _status_rag(it["status"])
                stage = f' <strong>({e(it["stage"])})</strong>' if it.get("stage") else ""
                dep = f' <span class="muted">· {e(rt(lang, "dep"))} {e(it["dependency"])}</span>' if it.get("dependency") else ""
                parts.append(f'<li><span class="dot" style="background:{RAG_COLOR[rag]}"></span>'
                             f'{e(it["title"])}{stage}{dep}</li>')
            parts.append('</ul>')
        else:
            parts.append(f'<div class="muted small">{e(rt(lang, "no_jalon"))}</div>')
        parts.append('</div>')
    parts.append('</div>')  # .d-quarters

    # Key messages
    kms = det.get("key_messages") or []
    parts.append(f'<div class="d-sub">{e(rt(lang, "h_key_messages"))}</div>')
    if kms:
        km_rag = {"success": "green", "alert": "amber", "risk": "red"}
        parts.append('<ul class="d-obj">')
        for m in kms:
            rag = km_rag.get(m["kind"], "grey")
            ts = f' <span class="muted">· {e(m["created_at"])}</span>' if m.get("created_at") else ""
            parts.append(f'<li><span class="dot" style="background:{RAG_COLOR[rag]}"></span>'
                         f'<strong>{e(rt(lang, "km_" + m["kind"]))}</strong> - {e(m["text"])}{ts}</li>')
        parts.append('</ul>')
    else:
        parts.append(f'<div class="muted small">{e(rt(lang, "no_key_message"))}</div>')

    # Budget (present only when the viewer may see this squad's figures)
    bud = det.get("budget")
    if bud is not None:
        fmtn = lambda v: "-" if v is None else f"{v:,.0f} €"
        st_rag = {"on_track": "green", "at_risk": "amber", "over": "red"}[bud["status"]]
        st_lbl = rt(lang, {"on_track": "b_on_track", "at_risk": "b_at_risk", "over": "b_over"}[bud["status"]])
        over = f' (+{fmtn(bud["overrun"])} · {bud["overrun_pct"]}%)' if bud["status"] == "over" else ""
        parts.append(f'<div class="d-sub">{e(rt(lang, "h_budget"))} '
                     f'<span class="dot" style="background:{RAG_COLOR[st_rag]}"></span> '
                     f'<span class="muted">{e(st_lbl)}{e(over)}</span></div>')
        if bud["total"] is None and bud["spent"] is None and bud["forecast"] is None:
            parts.append(f'<div class="muted small">{e(rt(lang, "no_budget"))}</div>')
        else:
            sp = f' <span class="muted">· {bud["spent_pct"]}%</span>' if bud.get("spent_pct") is not None else ""
            fp = f' <span class="muted">· {bud["forecast_pct"]}%</span>' if bud.get("forecast_pct") is not None else ""
            parts.append('<ul class="d-obj">')
            parts.append(f'<li>{e(rt(lang, "b_total"))} : <strong>{fmtn(bud["total"])}</strong></li>')
            parts.append(f'<li>{e(rt(lang, "b_spent"))} : <strong>{fmtn(bud["spent"])}</strong>{sp}</li>')
            parts.append(f'<li>{e(rt(lang, "b_forecast"))} : <strong>{fmtn(bud["forecast"])}</strong>{fp}</li>')
            if bud.get("comment"):
                parts.append(f'<li class="muted">{e(bud["comment"])}</li>')
            parts.append('</ul>')

    parts.append('</div>')  # .sq-detail
    return parts


_STATIC_ASSETS = os.path.join(os.path.dirname(__file__), "static", "assets")


_DOT_CLASS = {"green": "dot-green", "amber": "dot-orange", "red": "dot-red", "grey": "dot-grey"}


_KM_BADGE = {"success": "badge-green", "alert": "badge-orange", "risk": "badge-red"}


_BUD_BADGE = {"on_track": "badge-green", "at_risk": "badge-orange", "over": "badge-red"}


def _app_css() -> str:
    """The application's own built stylesheet (served under /assets), so a
    single-squad export renders with the exact look of the squad page. Falls back
    to the report stylesheet when no build is present (e.g. tests)."""
    try:
        for fn in sorted(os.listdir(_STATIC_ASSETS)):
            if fn.endswith(".css"):
                with open(os.path.join(_STATIC_ASSETS, fn), encoding="utf-8") as fh:
                    return f"<style>{fh.read()}</style>"
    except OSError:
        pass
    return _CSS


def _dot(rag: str) -> str:
    """Small coloured status dot using the application's own CSS classes."""
    return f'<span class="dot {_DOT_CLASS.get(rag, "dot-green")}"></span>'


def _squad_app_cards(det: dict, lang: str, e, year: int) -> list[str]:
    """The squad page's cards, in page order: Initiatives → OTD → Roadmap →
    Key messages → Budget, using the application's own component classes."""
    fmtn = lambda v: "-" if v is None else f"{v:,.0f} €"
    C: list[str] = []

    # Initiatives - always shown (even empty), to mirror the squad page.
    inits = det.get("initiatives") or []
    C.append(f'<div class="card"><h2>{e(rt(lang, "h_initiatives"))}</h2>')
    if inits:
        C.append('<table class="init-tbl"><thead><tr>'
                 f'<th>{e(rt(lang, "h_initiatives"))}</th><th>{e(rt(lang, "h_leader"))}</th>'
                 f'<th>{e(rt(lang, "deadline"))}</th></tr></thead><tbody>')
        for ini in inits:
            C.append(f'<tr><td><strong>{e(ini["title"])}</strong></td>'
                     f'<td>{e(ini.get("owner") or "-")}</td><td>{e(ini.get("deadline") or "-")}</td></tr>')
        C.append('</tbody></table>')
    else:
        C.append(f'<div class="muted small">{e(rt(lang, "no_initiative"))}</div>')
    C.append('</div>')

    # OTD (annual objectives)
    C.append(f'<div class="card"><h2>{e(rt(lang, "h_otd_section"))} {year}</h2>')
    if det.get("objectives"):
        for o in det["objectives"]:
            dl = f' · {e(rt(lang, "deadline"))} {e(o["target_date"])}' if o.get("target_date") else ""
            C.append(f'<div class="item-row">{_dot(_status_rag(o["rag"]))}'
                     f'<div class="grow"><div>{e(o["title"])}</div></div>'
                     f'<span class="small muted">{e(_status_label(o["rag"], lang))}{dl}</span></div>')
    else:
        C.append(f'<div class="small muted">{e(rt(lang, "no_obj"))}</div>')
    C.append('</div>')

    # Roadmap by quarter
    C.append(f'<div class="card"><h2>{e(rt(lang, "h_roadmap"))} {year}</h2>'
             '<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px">')
    for qd in det.get("quarters", []):
        pct = max(0, min(100, int(qd["pct"] or 0)))
        C.append(f'<div class="quarter-block"><div class="between"><h4 style="margin:0">Q{qd["q"]}</h4>'
                 f'<span class="small muted">{qd["pct"]}%</span></div>'
                 f'<div class="progress"><div style="width:{pct}%"></div></div>')
        if qd.get("comment"):
            C.append(f'<div class="small muted" style="margin-top:6px">{e(qd["comment"])}</div>')
        C.append('<div style="margin-top:8px">')
        if not qd["items"]:
            C.append(f'<div class="small muted">{e(rt(lang, "no_jalon"))}</div>')
        for it in qd["items"]:
            stage = f'<span class="badge badge-navy" style="font-size:10px">{e(it["stage"])}</span>' if it.get("stage") else ""
            dep = f'<span class="small muted">· {e(rt(lang, "dep"))} {e(it["dependency"])}</span>' if it.get("dependency") else ""
            C.append(f'<div class="item-row">{_dot(_status_rag(it["status"]))}'
                     f'<span class="grow small">{e(it["title"])}</span>{stage}'
                     f'<span class="small muted">{e(_status_label(it["status"], lang))}</span>{dep}</div>')
        C.append('</div></div>')
    C.append('</div></div>')

    # Key messages
    C.append(f'<div class="card"><h2>{e(rt(lang, "h_key_messages"))}</h2>')
    kms = det.get("key_messages") or []
    if kms:
        for m in kms:
            ts = f'<div class="small muted">{e(m["created_at"])}</div>' if m.get("created_at") else ""
            C.append(f'<div class="item-row"><span class="badge {_KM_BADGE.get(m["kind"], "badge-grey")}">'
                     f'{e(rt(lang, "km_" + m["kind"]))}</span>'
                     f'<div class="grow"><div class="small">{e(m["text"])}</div>{ts}</div></div>')
    else:
        C.append(f'<div class="small muted">{e(rt(lang, "no_key_message"))}</div>')
    C.append('</div>')

    # Budget (present only when the viewer may see the figures)
    bud = det.get("budget")
    if bud is not None:
        st_lbl = rt(lang, {"on_track": "b_on_track", "at_risk": "b_at_risk", "over": "b_over"}[bud["status"]])
        over = f' (+{fmtn(bud["overrun"])} · {bud["overrun_pct"]}%)' if bud["status"] == "over" else ""
        C.append(f'<div class="card"><div class="between"><h2 style="margin:0">{e(rt(lang, "h_budget"))}</h2>'
                 f'<span class="badge {_BUD_BADGE[bud["status"]]}">{e(st_lbl)}{e(over)}</span></div>')
        if bud["total"] is None and bud["spent"] is None and bud["forecast"] is None:
            C.append(f'<div class="small muted">{e(rt(lang, "no_budget"))}</div>')
        else:
            sp = f' · {bud["spent_pct"]}%' if bud.get("spent_pct") is not None else ""
            fp = f' · {bud["forecast_pct"]}%' if bud.get("forecast_pct") is not None else ""
            C.append('<div class="stack" style="gap:6px;margin-top:6px">'
                     f'<div class="between"><span class="small muted">{e(rt(lang, "b_total"))}</span>'
                     f'<span class="strong">{fmtn(bud["total"])}</span></div>'
                     f'<div class="between"><span class="small muted">{e(rt(lang, "b_spent"))}</span>'
                     f'<span class="strong">{fmtn(bud["spent"])}{sp}</span></div>'
                     f'<div class="between"><span class="small muted">{e(rt(lang, "b_forecast"))}</span>'
                     f'<span class="strong">{fmtn(bud["forecast"])}{fp}</span></div>')
            if bud.get("comment"):
                C.append(f'<div class="small muted" style="margin-top:4px">{e(bud["comment"])}</div>')
            C.append('</div>')
        C.append('</div>')

    return C


def _render_squad_page(data: dict, standalone: bool, e, lang: str) -> str:
    """Single-squad export rendered with the application's own stylesheet and
    component markup, so it looks exactly like the squad page."""
    r = next((rr for blk in data["tribes"] for rr in blk["squads"] if rr.get("detail")), None)
    style = _app_css()
    if r is None:
        body = f'<div class="export-page"><h1>{e(data["scope_name"])}</h1></div>'
    else:
        year = data["year"]
        fresh_cls = "badge-grey" if r["is_stale"] else "badge-navy"
        fresh_lbl = rt(lang, "stale") if r["is_stale"] else rt(lang, "h_freshness_ok")
        badges = [f'<span class="badge badge-navy">{e(rt(lang, "h_progress_long"))} {r["annual_pct"]}%</span>']
        if r["blocked"]:
            badges.append(f'<span class="badge badge-red">{r["blocked"]} {e(rt(lang, "h_blocked"))}</span>')
        if r["at_risk"]:
            badges.append(f'<span class="badge badge-orange">{r["at_risk"]} {e(rt(lang, "h_atrisk"))}</span>')
        badges.append(f'<span class="badge {fresh_cls}">{e(fresh_lbl)}</span>')
        P = [f'<div class="export-page"><h1 style="color:var(--navy);margin:0 0 8px">{e(r["name"])}</h1>',
             f'<div class="inline" style="gap:10px;flex-wrap:wrap;margin-bottom:6px">{"".join(badges)}</div>',
             f'<div class="muted small" style="margin-bottom:16px">{e(rt(lang, "h_leader"))} : '
             f'<span class="strong">{e(r["leader"] or "-")}</span> · {e(rt(lang, "year"))} {year}</div>',
             '<div class="stack" style="gap:18px">']
        P.extend(_squad_app_cards(r["detail"], lang, e, year))
        P.append('</div></div>')
        body = "\n".join(P)
    page_css = ('<style>body{background:var(--bg,#F5F7FA);margin:0;padding:24px;color:var(--text,#1E293B);'
                'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}'
                '.export-page{max-width:1040px;margin:0 auto}'
                '.init-tbl{width:100%;border-collapse:collapse}'
                '.init-tbl th,.init-tbl td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line,#E2E8F0)}</style>')
    if not standalone:
        return f'{style}{page_css}{body}'
    title = e(r["name"]) if r else e(data["scope_name"])
    return (f'<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title>{style}{page_css}</head><body>{body}</body></html>')


# =============================================================================
# "What's new since your last report" - change detection against a stored
# per-scope baseline (see models.ReportBaseline).
# =============================================================================

def _ms_lbl(status: str, lang: str) -> str:
    """Localized milestone-status label for the changelog (passes unknowns through)."""
    return rt(lang, {"on_track": "ms_on_track", "at_risk": "ms_at_risk",
                     "blocked": "ms_blocked", "done": "ms_done"}.get(status, "h_status")) \
        if status in ("on_track", "at_risk", "blocked", "done") else status


def _rag_lbl(rag: str, lang: str) -> str:
    """Localized RAG label for the changelog (passes unknown values through)."""
    return rt(lang, {"green": "rag_green", "amber": "rag_amber", "red": "rag_red"}.get(rag, "rag_green")) \
        if rag in ("green", "amber", "red") else rag


def report_signature(data: dict) -> dict:
    """Compact, diff-friendly snapshot of a report's per-squad state."""
    sig: dict = {}
    for blk in data.get("tribes", []):
        for r in blk.get("squads", []):
            d = r.get("detail", {}) or {}
            b = d.get("budget") or None
            sig[str(r["squad_id"])] = {
                "name": r["name"],
                "status": r.get("status"),
                "annual_pct": r.get("annual_pct", 0),
                "is_stale": bool(r.get("is_stale")),
                "milestones": {it["title"]: it["status"]
                               for q in d.get("quarters", []) for it in q.get("items", [])},
                "objectives": {o["title"]: o["rag"] for o in d.get("objectives", [])},
                "budget": {k: b.get(k) for k in ("total", "spent", "forecast", "status")} if b else None,
                "km": len(d.get("key_messages", [])),
            }
    return sig


def diff_report(prev: dict | None, cur: dict, lang: str) -> dict:
    """Compare two report signatures. Returns
    {first, count, summary, by_squad:[{name, items:[str]}]}."""
    if not prev:
        return {"first": True, "count": 0, "summary": "", "by_squad": []}
    by_squad: list[dict] = []
    tally = {"moved": 0, "delivered": 0, "blocked": 0, "stale": 0}
    for sid, c in cur.items():
        p = prev.get(sid)
        items: list[str] = []
        if p is None:
            items.append(rt(lang, "chg_new_squad", name=c["name"]))
        else:
            if c["annual_pct"] != p["annual_pct"]:
                d = c["annual_pct"] - p["annual_pct"]
                items.append(rt(lang, "chg_progress", d=(f"+{d}" if d > 0 else str(d))))
                tally["moved"] += 1
            if c.get("status") != p.get("status") and p.get("status"):
                items.append(rt(lang, "chg_status", frm=p["status"], to=c["status"]))
            for title, stt in c["milestones"].items():
                if title not in p["milestones"]:
                    items.append(rt(lang, "chg_ms_new", title=title))
                elif p["milestones"][title] != stt:
                    items.append(rt(lang, "chg_ms_status", title=title,
                                    frm=_ms_lbl(p["milestones"][title], lang), to=_ms_lbl(stt, lang)))
                    if stt == "done":
                        tally["delivered"] += 1
                    if stt == "blocked" and p["milestones"][title] != "blocked":
                        tally["blocked"] += 1
            for title in p["milestones"]:
                if title not in c["milestones"]:
                    items.append(rt(lang, "chg_ms_removed", title=title))
            for title, rag in c["objectives"].items():
                if title not in p["objectives"]:
                    items.append(rt(lang, "chg_obj_new", title=title))
                elif p["objectives"][title] != rag:
                    items.append(rt(lang, "chg_obj_status", title=title,
                                    frm=_rag_lbl(p["objectives"][title], lang), to=_rag_lbl(rag, lang)))
            if (c.get("budget") or {}) != (p.get("budget") or {}):
                items.append(rt(lang, "chg_budget"))
            if c.get("km", 0) > p.get("km", 0):
                items.append(rt(lang, "chg_km", n=c["km"] - p["km"]))
            if c["is_stale"] and not p["is_stale"]:
                items.append(rt(lang, "chg_stale"))
                tally["stale"] += 1
            elif not c["is_stale"] and p["is_stale"]:
                items.append(rt(lang, "chg_unstale"))
        if items:
            by_squad.append({"name": c["name"], "items": items})
    # Squads present in the baseline but gone from the current report (deleted /
    # moved out of scope) are reported as removals.
    for sid, p in prev.items():
        if sid not in cur:
            by_squad.append({"name": p["name"], "items": [rt(lang, "chg_squad_removed", name=p["name"])]})

    count = sum(len(s["items"]) for s in by_squad)
    parts = []
    if tally["moved"]:
        parts.append(rt(lang, "sum_moved", n=tally["moved"]))
    if tally["delivered"]:
        parts.append(rt(lang, "sum_delivered", n=tally["delivered"]))
    if tally["blocked"]:
        parts.append(rt(lang, "sum_blocked", n=tally["blocked"]))
    if tally["stale"]:
        parts.append(rt(lang, "sum_stale", n=tally["stale"]))
    return {"first": False, "count": count, "summary": " · ".join(parts), "by_squad": by_squad}


def subject_prefix(changes: dict | None, lang: str) -> str:
    """Subject tag: '[3 nouveautés] ' / '[à jour] ' / '' (first report)."""
    if not changes or changes.get("first"):
        return ""
    if changes["count"] == 0:
        return rt(lang, "subj_uptodate") + " "
    return rt(lang, "subj_changes", n=changes["count"]) + " "


def render_changes_html(changes: dict | None, lang: str) -> str:
    """Render the "What's new since your last report" box as HTML.

    Three states: first report (nothing to compare), no changes (up-to-date
    banner), or a per-squad list. Lists are capped (12 squads, 8 items each) to
    keep the email digestible. Returns '' when there is nothing to show."""
    if not changes:
        return ""
    e = html.escape
    head = f'<div class="chg-h">{e(rt(lang, "whatsnew"))}</div>'
    if changes.get("first"):
        return f'<div class="changes-box"><div class="chg-h">{e(rt(lang, "whatsnew"))}</div>' \
               f'<div class="chg-empty">{e(rt(lang, "first_report"))}</div></div>'
    if changes["count"] == 0:
        return f'<div class="changes-box uptodate">{head}' \
               f'<div class="chg-empty">✓ {e(rt(lang, "no_changes"))}</div></div>'
    out = [f'<div class="changes-box">{head}']
    if changes["summary"]:
        out.append(f'<div class="chg-sum">{e(changes["summary"])}</div>')
    for sq in changes["by_squad"][:12]:
        out.append(f'<div class="chg-sq"><span class="chg-sqn">{e(sq["name"])}</span><ul>')
        for it in sq["items"][:8]:
            out.append(f'<li>{e(it)}</li>')
        out.append('</ul></div>')
    out.append('</div>')
    return "".join(out)


def get_baseline(db, scope_key: str) -> dict | None:
    """Load the stored signature for a scope (used as the 'previous' side of a
    diff). scope_key identifies the recipient scope, e.g. 'global', 'tribe:3',
    'sub:12'. Returns None when no baseline exists yet (first report)."""
    from .models import ReportBaseline
    row = db.get(ReportBaseline, scope_key)
    return row.signature if row else None


def set_baseline(db, scope_key: str, signature: dict) -> None:
    """Persist the current signature as the new baseline for a scope (upsert).

    Called after a report is prepared so the next send diffs against this state.
    Does not commit - the caller controls the transaction."""
    from .models import ReportBaseline
    row = db.get(ReportBaseline, scope_key)
    if row is None:
        db.add(ReportBaseline(scope_key=scope_key, signature=signature, updated_at=utcnow()))
    else:
        row.signature = signature
        row.updated_at = utcnow()


def render_html(data: dict, *, standalone: bool = True, changes: dict | None = None) -> str:
    """Render the full weekly report as an HTML document.

    Layout: header → optional "what's new" box → summary KPI cards → attention
    list → upcoming absences → one table per tribe → full per-squad detail blocks.
    A single-squad export is delegated to _render_squad_page (it mirrors the squad
    page rather than the dashboard). standalone wraps the body in a full <html>
    document; otherwise only the report fragment (with inlined CSS) is returned so
    it can be embedded. changes, when given, injects the changelog box."""
    e = html.escape
    lang = data.get("lang", "fr")
    # A single-squad export mirrors the squad page, not the whole dashboard report.
    if data.get("squad_scoped"):
        return _render_squad_page(data, standalone, e, lang)
    s = data["summary"]
    gen = data["generated_at"]
    gen_str = gen.strftime("%d/%m/%Y %H:%M") if isinstance(gen, datetime) else str(gen)

    parts: list[str] = []
    parts.append(f'<div class="hdr"><h1>{e(data["app_name"])} - {e(rt(lang, "report"))}</h1>')
    parts.append(f'<div class="sub">{e(data["scope_name"])} · {e(rt(lang, "year"))} {data["year"]} · '
                 f'{e(rt(lang, "generated"))} {e(gen_str)} · {e(rt(lang, "window", n=data["since_days"]))}</div></div>')

    # "What's new since your last report" - right under the header.
    if changes is not None:
        parts.append(render_changes_html(changes, lang))

    # Summary cards
    cards = [
        (rt(lang, "k_squads"), s["squads_total"], "#111827"),
        (rt(lang, "k_progress"), f'{s["avg_progress"]}%', RAG_COLOR["green"]),
        (rt(lang, "k_blocked"), s["blocked"], RAG_COLOR["red"] if s["blocked"] else "#111827"),
        (rt(lang, "k_atrisk"), s["at_risk"], RAG_COLOR["amber"] if s["at_risk"] else "#111827"),
        (rt(lang, "k_obj_red"), s["objectives_red"], RAG_COLOR["red"] if s["objectives_red"] else "#111827"),
        (rt(lang, "k_stale"), s["stale"], RAG_COLOR["amber"] if s["stale"] else "#111827"),
    ]
    parts.append('<div class="cards">')
    for label, val, color in cards:
        parts.append(f'<div class="kpi"><div class="kpi-val" style="color:{color}">{e(str(val))}</div>'
                     f'<div class="kpi-lbl">{e(label)}</div></div>')
    parts.append('</div>')

    # Attention list
    if data["attention"]:
        parts.append(f'<h2>{e(rt(lang, "attention"))}</h2><ul class="attention">')
        for r in data["attention"][:12]:
            bits = []
            if r["blocked"]:
                bits.append(f'{r["blocked"]} {rt(lang, "blocked_n")}')
            if r["delta"] < 0:
                bits.append(f'{r["delta"]} pt')
            if r["is_stale"]:
                bits.append(rt(lang, "stale"))
            parts.append(f'<li><span class="dot" style="background:{RAG_COLOR["red"]}"></span>'
                         f'<strong>{e(r["name"])}</strong> - {e(", ".join(bits))}</li>')
        parts.append('</ul>')

    # Upcoming absences (next 30 days), when the leaves module is enabled.
    if data.get("leaves_upcoming"):
        parts.append(f'<h2>{e(rt(lang, "leaves_upcoming"))}</h2><ul class="attention">')
        for lv in data["leaves_upcoming"][:30]:
            pending = f' <span class="badge">{e(rt(lang, "leaves_pending"))}</span>' if lv["status"] == "pending" else ""
            parts.append(
                f'<li><span class="dot" style="background:{e(lv["type_color"])}"></span>'
                f'<strong>{e(lv["name"])}</strong> - {e(leave_type_label(lv["type_label"], lang))}'
                f'{e(" (" + lv["detail"] + ")") if lv.get("detail") else ""} '
                f'<span class="muted">({e(lv["start"])} → {e(lv["end"])}, {lv["days"]:g} {e(rt(lang, "days_short"))})</span>'
                f'{pending}</li>')
        parts.append('</ul>')

    # Per-tribe tables
    for blk in data["tribes"]:
        parts.append(f'<h2>{e(blk["tribe_name"])}</h2>')
        parts.append('<table><thead><tr>'
                     f'<th>{e(rt(lang, "h_squad"))}</th><th>{e(rt(lang, "h_leader"))}</th>'
                     f'<th>{e(rt(lang, "h_status"))}</th>'
                     f'<th>{e(rt(lang, "h_progress_long"))}</th><th>{e(rt(lang, "h_delta"))}</th>'
                     f'<th>{e(rt(lang, "h_blocked"))}</th>'
                     f'<th>{e(rt(lang, "h_atrisk"))}</th><th>{e(rt(lang, "h_facts"))}</th>'
                     '</tr></thead><tbody>')
        for r in blk["squads"]:
            changes = r["changes"][:4]
            ch_html = "<br>".join(e(_change_text(c, lang)) for c in changes) if changes else \
                ('<span class="muted">-</span>' if not r["note"] else "")
            if r["note"]:
                note = e(r["note"]).replace("\n", " ")
                if len(note) > 160:
                    note = note[:159] + "…"
                ch_html = (ch_html + "<br>" if ch_html else "") + f'<em class="note">« {note} »</em>'
            stale_badge = f' <span class="badge">{e(rt(lang, "stale"))}</span>' if r["is_stale"] else ""
            parts.append(
                f'<tr><td><strong>{e(r["name"])}</strong>{stale_badge}</td>'
                f'<td>{e(r["leader"])}</td>'
                f'<td><span class="pill" style="background:{RAG_COLOR[r["status_rag"]]}">'
                f'{e(_status_label(r["status"], lang))}</span></td>'
                f'<td>{_bar(r["annual_pct"], r["status_rag"])}</td>'
                f'<td>{_delta_html(r["delta"])}</td>'
                f'<td>{r["blocked"] or ""}</td><td>{r["at_risk"] or ""}</td>'
                f'<td class="changes">{ch_html}</td></tr>'
            )
        parts.append('</tbody></table>')

    # --- Full detail per squad: annual objectives + roadmap/milestones by quarter.
    all_squads = [r for blk in data["tribes"] for r in blk["squads"]]
    if any(r.get("detail") for r in all_squads):
        parts.append(f'<h2 class="detail-h">{e(rt(lang, "detail_title"))}</h2>')
    for r in all_squads:
        if r.get("detail"):
            parts.extend(_squad_detail_parts(r, lang, e))

    body = "\n".join(parts)
    if not standalone:
        return f'<div class="tc-report">{_CSS}{body}</div>'
    return (
        f'<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">'
        f'<title>{e(data["app_name"])} - {e(rt(lang, "report"))}</title>'
        f'{_CSS}</head><body><div class="tc-report">{body}</div></body></html>'
    )


def render_roadmap_html(data: dict, *, standalone: bool = True) -> str:
    """Roadmap matrix web page: quarters in columns, squads (themes) in rows,
    milestone titles in the cells, colour-coded by status."""
    e = html.escape
    lang = data.get("lang", "fr")
    year = data["year"]
    gen = data["generated_at"]
    gen_str = gen.strftime("%d/%m/%Y %H:%M") if isinstance(gen, datetime) else str(gen)
    squads = [row for blk in data["tribes"] for row in blk["squads"]]

    parts: list[str] = []
    parts.append(f'<div class="hdr"><h1>{e(data["app_name"])} - {e(rt(lang, "roadmap_report"))}</h1>')
    parts.append(f'<div class="sub">{e(data["scope_name"])} · {e(rt(lang, "year"))} {year} · '
                 f'{e(rt(lang, "generated"))} {e(gen_str)}</div></div>')

    # EA/GA legend (status is no longer colour-coded in the roadmap view)
    parts.append('<div class="rm-legend">')
    parts.append(f'<span><b class="rm-ea">EA</b> {e(rt(lang, "stage_ea"))}</span>')
    parts.append(f'<span><b class="rm-ga">GA</b> {e(rt(lang, "stage_ga"))}</span>')
    parts.append('</div>')

    months = _MONTHS[lang]
    parts.append('<table class="rm"><thead>')
    parts.append('<tr><th class="rm-corner" rowspan="2"></th>')
    for q in (1, 2, 3, 4):
        parts.append(f'<th class="rm-q" colspan="3">Q{q} {year}</th>')
    parts.append('</tr><tr>')
    for mi in range(12):
        parts.append(f'<th class="rm-m">{e(months[mi])}</th>')
    parts.append('</tr></thead><tbody>')
    for sq in squads:
        parts.append(f'<tr><th class="rm-row">{e(sq["name"])}</th>')
        qmap = {qd["q"]: qd["items"] for qd in (sq.get("detail") or {}).get("quarters", [])}
        for q in (1, 2, 3, 4):
            items = qmap.get(q, [])
            parts.append('<td colspan="3"><div class="rm-card">' if items else '<td colspan="3">')
            for theme, group in group_by_theme(items):
                if theme:
                    parts.append(f'<div class="rm-theme">{e(theme)}</div>')
                for it in group:
                    stage = it.get("stage")
                    st_html = ""
                    if stage:
                        cls = "rm-ea" if stage == "EA" else "rm-ga"
                        st_html = f' (<span class="{cls}">{e(stage)}</span>)'
                    parts.append(f'<div class="rm-j">{e(it["title"])}{st_html}</div>')
            parts.append('</div></td>' if items else '</td>')
        parts.append('</tr>')
    parts.append('</tbody></table>')

    body = "\n".join(parts)
    if not standalone:
        return f'<div class="tc-report">{_CSS}{body}</div>'
    return (
        f'<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">'
        f'<title>{e(data["app_name"])} - {e(rt(lang, "roadmap_report"))}</title>'
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
.tc-report .changes-box{border:1px solid #dbe4ff;background:#f5f8ff;border-left:4px solid #175CD3;border-radius:10px;padding:12px 16px;margin:16px 0}
.tc-report .changes-box.uptodate{border-color:#d1fae5;background:#f0fdf6;border-left-color:#059669}
.tc-report .chg-h{font-size:13px;font-weight:700;color:#1E2761;text-transform:uppercase;letter-spacing:.03em;margin-bottom:6px}
.tc-report .chg-sum{font-size:14px;font-weight:600;color:#111827;margin-bottom:8px}
.tc-report .chg-empty{font-size:13px;color:#4b5563}
.tc-report .chg-sq{margin:6px 0}
.tc-report .chg-sqn{font-weight:700;font-size:13px;color:#175CD3}
.tc-report .chg-sq ul{margin:2px 0 0;padding-left:18px}
.tc-report .chg-sq li{font-size:12.5px;padding:1px 0}
.tc-report .note{color:#4b5563}
.tc-report .muted{color:#9ca3af}
.tc-report .badge{background:#fef3c7;color:#92400e;border-radius:4px;padding:1px 5px;font-size:10px}
.tc-report ul.attention{list-style:none;padding:0;margin:0}
.tc-report ul.attention li{padding:5px 0;font-size:13px}
.tc-report .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px}
.tc-report h2.detail-h{margin-top:30px}
.tc-report .sq-detail{border:1px solid #e5e7eb;border-radius:10px;padding:12px 14px;margin:12px 0;background:#fff;break-inside:avoid}
.tc-report .sq-detail h3{margin:0 0 6px;font-size:15px}
.tc-report .d-sub{font-size:12px;font-weight:700;color:#374151;margin:10px 0 4px;text-transform:uppercase;letter-spacing:.03em}
.tc-report ul.d-obj{list-style:none;padding:0;margin:0}
.tc-report ul.d-obj li{padding:3px 0;font-size:13px}
.tc-report .d-quarters{display:flex;flex-wrap:wrap;gap:10px}
.tc-report .d-q{flex:1;min-width:170px;border:1px solid #eef0f3;border-radius:8px;padding:8px 10px;background:#f9fafb}
.tc-report .d-q-head{font-weight:700;font-size:13px;margin-bottom:4px}
.tc-report .d-q ul{list-style:none;padding:0;margin:0}
.tc-report .d-q li{padding:2px 0;font-size:12px}
.tc-report .rm-legend{display:flex;gap:16px;margin:14px 0 8px;font-size:12px;color:#374151}
.tc-report table.rm{table-layout:fixed;border-collapse:separate;border-spacing:3px}
.tc-report table.rm th.rm-q{background:#304957;color:#fff;text-align:center;font-size:15px;padding:7px}
.tc-report table.rm th.rm-m{background:#97A3AA;color:#fff;text-align:center;font-size:11px;font-weight:500;padding:3px}
.tc-report table.rm th.rm-corner{background:transparent;border:none}
.tc-report table.rm th.rm-row{background:#304957;color:#fff;text-align:center;width:58px;vertical-align:middle;font-size:12.5px;writing-mode:vertical-rl;transform:rotate(180deg);padding:7px 4px}
.tc-report table.rm td{vertical-align:top;padding:0}
.tc-report .rm-card{background:#F2F2F2;border-radius:8px;padding:8px 10px;height:100%;box-sizing:border-box}
.tc-report .rm-theme{font-size:13px;font-weight:800;color:#002060;margin:6px 0 1px;line-height:1.3}
.tc-report .rm-theme:first-child{margin-top:0}
.tc-report .rm-j{font-size:12.5px;padding:1px 0 1px 10px;line-height:1.32;color:#002060}
.tc-report .rm-legend b.rm-ea,.tc-report .rm-j .rm-ea{color:#FFC000;font-weight:800}
.tc-report .rm-legend b.rm-ga,.tc-report .rm-j .rm-ga{color:#00B050;font-weight:800}
</style>"""


def _deadline_str(d) -> str:
    """Format a deadline as an ISO date string (YYYY-MM-DD), '-' when missing.
    Accepts a datetime, a date, or an already-string value."""
    if not d:
        return "-"
    if isinstance(d, datetime):
        return d.date().isoformat()
    return str(d)[:10]


def build_initiative_list(db: Session, scope_tribe: int | None, year: int) -> dict:
    """Flat list of initiatives in scope: title, owner, squad, deadline."""
    from .models import Initiative, Tribe
    tribes = {t.id: t.name for t in db.scalars(select(Tribe)).all()}
    q = (select(Initiative).where(Initiative.year == year)
         .order_by(Initiative.display_order, Initiative.id))
    if scope_tribe is not None:
        q = q.where(Initiative.tribe_id == scope_tribe)
    items = [{"id": i.id, "title": i.title, "owner": i.owner,
              "squad_name": i.squad.name if i.squad else None,
              "deadline": _deadline_str(i.deadline)} for i in db.scalars(q).all()]
    scope_name = tribes.get(scope_tribe) if scope_tribe is not None else "Toutes les tribus"
    return {"year": year, "scope_name": scope_name or "-", "items": items}


def render_initiatives_html(data: dict, *, lang: str = "fr", standalone: bool = True) -> str:
    """Render the flat initiatives list (title / owner / squad / deadline) as HTML."""
    e = html.escape
    lang = _lang(lang)
    T = _INIT_T[lang]
    parts = [f'<div class="hdr"><h1>{e(T["title"])} - {e(data["scope_name"])}</h1>',
             f'<div class="sub">{e(T["year"])} {data["year"]}</div></div>']
    if not data["items"]:
        parts.append(f'<div class="muted small">{e(T["none"])}</div>')
    else:
        parts.append('<table><thead><tr>'
                     f'<th>{e(T["h_init"])}</th><th>{e(T["h_owner"])}</th>'
                     f'<th>{e(T["h_squad"])}</th><th>{e(T["h_deadline"])}</th></tr></thead><tbody>')
        for it in data["items"]:
            parts.append(f'<tr><td><strong>{e(it["title"])}</strong></td>'
                         f'<td>{e(it["owner"] or "-")}</td>'
                         f'<td>{e(it["squad_name"] or "-")}</td>'
                         f'<td>{e(it["deadline"])}</td></tr>')
        parts.append('</tbody></table>')
    body = "\n".join(parts)
    if not standalone:
        return f'<div class="tc-report">{_CSS}{body}</div>'
    return (f'<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">'
            f'<title>{e(T["title"])}</title>{_CSS}</head>'
            f'<body><div class="tc-report">{body}</div></body></html>')


# ----- Automatic weekly send ------------------------------------------------------

def _iso_week_key(dt: datetime) -> str:
    """ISO week identifier 'YYYY-Www' used to make the weekly send idempotent."""
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
    if now.weekday() not in cfg["weekdays"] or now.hour < cfg["hour"]:
        return 0
    today = now.date().isoformat()
    if cfg.get("last_sent_day") == today:
        return 0

    since = cfg.get("since_days", 7)
    year = st.current_year_quarter(now)[0]
    lang = _lang(get_general(db).get("default_lang"))

    only_changes = bool(cfg.get("only_when_changes"))
    week = now.isocalendar()[1]
    sent = 0
    prepared: dict[str, dict] = {}

    def prepare(scope: int | None, scope_key: str, scope_label: str) -> dict:
        """Build the report for a scope once: data, changelog (vs baseline),
        HTML (with the "what's new" encart), PPTX and a prefixed subject."""
        if scope_key not in prepared:
            data = build_report_data(db, scope, year, since, now, lang=lang)
            sig = report_signature(data)
            changes = diff_report(get_baseline(db, scope_key), sig, lang)
            html_body = render_html(data, standalone=True, changes=changes)
            try:
                pptx_bytes = render_pptx(data)
            except Exception:
                pptx_bytes = b""
            subject = subject_prefix(changes, lang) + rt(lang, "subject", scope=scope_label, w=week)
            prepared[scope_key] = {"sig": sig, "changes": changes, "html": html_body,
                                   "pptx": pptx_bytes, "subject": subject}
        return prepared[scope_key]

    def attachment_of(p: dict):
        if p["pptx"] and cfg.get("attach_pptx", True):
            return (f"rapport_hebdo_{today}.pptx", p["pptx"],
                    "application", "vnd.openxmlformats-officedocument.presentationml.presentation")
        return None

    def worth_sending(p: dict) -> bool:
        c = p["changes"]
        # Always send the very first report (establishes the baseline); otherwise
        # honour the "only when changes" policy.
        return c.get("first") or not (only_changes and c["count"] == 0)

    # Fixed recipient list → global report.
    recipients = list(dict.fromkeys(a for a in (cfg.get("recipients") or []) if a))
    if recipients:
        p = prepare(None, "global", rt(lang, "all_tribes"))
        if worth_sending(p):
            att = attachment_of(p)
            for addr in recipients:
                if send_email(smtp, addr, p["subject"], p["html"], attachment=att, html=True):
                    sent += 1
        set_baseline(db, "global", p["sig"])

    # Optional: each tribe leader also receives their OWN tribe-scoped report,
    # with that tribe's squad leaders in CC.
    if cfg.get("tribe_leader_digest"):
        for tribe in db.scalars(select(Tribe).order_by(Tribe.display_order, Tribe.id)).all():
            leaders = [u for u in db.scalars(
                select(User).where(User.role == "tribe_leader", User.tribe_id == tribe.id)).all()
                if (u.email or "").strip() and u.status == "active"]
            if not leaders:
                continue
            to = ", ".join(dict.fromkeys(l.email.strip() for l in leaders))
            leader_emails = {l.email.strip().lower() for l in leaders}
            sq_leader_ids = [s.leader_user_id for s in db.scalars(
                select(Squad).where(Squad.tribe_id == tribe.id)).all() if s.leader_user_id]
            cc, seen_cc = [], set()
            if sq_leader_ids:
                for u in db.scalars(select(User).where(User.id.in_(sq_leader_ids))).all():
                    e = (u.email or "").strip()
                    el = e.lower()
                    if e and u.status == "active" and el not in leader_emails and el not in seen_cc:
                        seen_cc.add(el)
                        cc.append(e)
            scope_key = f"tribe:{tribe.id}"
            p = prepare(tribe.id, scope_key, tribe.name)
            if worth_sending(p):
                if send_email(smtp, to, p["subject"], p["html"],
                              attachment=attachment_of(p), html=True, cc=cc):
                    sent += 1
            set_baseline(db, scope_key, p["sig"])

    cfg["last_sent_day"] = today
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
    from .models import ReportSubscription, Squad, Tribe, User
    from .modulesconfig import get_modules, is_active

    now = now or utcnow()
    if not is_active(get_modules(db), "review", "weekly_report"):
        return 0
    smtp = get_smtp(db)
    if not smtp.get("enabled"):
        return 0

    from .reportconfig import get_report
    year = st.current_year_quarter(now)[0]
    lang = _lang(get_general(db).get("default_lang"))
    only_changes = bool(get_report(db).get("only_when_changes"))
    # Cache report data + PPTX per (scope_tribe, squad_id, since); HTML is rendered
    # per subscription because the "what's new" encart is per-recipient baseline.
    rendered: dict[tuple, tuple[dict, bytes]] = {}

    def render(scope_tribe: int | None, squad_id: int | None, since: int) -> tuple[dict, bytes]:
        key = (scope_tribe, squad_id, since)
        if key not in rendered:
            data = build_report_data(db, scope_tribe, year, since, now, squad_id=squad_id, lang=lang)
            try:
                pptx_bytes = render_pptx(data)
            except Exception:
                pptx_bytes = b""
            rendered[key] = (data, pptx_bytes)
        return rendered[key]

    sent = 0
    for sub in db.scalars(select(ReportSubscription)).all():
        wd = sub.weekdays or []
        if not wd and sub.interval_days <= 0:
            continue  # inactive subscription
        user = db.get(User, sub.user_id)
        if user is None or not user.email:
            continue
        last = _aware(sub.last_sent_at)
        if wd:
            # Weekday schedule: fire on a chosen day, past the hour, once per day.
            if now.weekday() not in wd or now.hour < sub.hour:
                continue
            if last is not None and last.date() == now.date():
                continue
            since = 7
        else:
            # Legacy "every N days" cadence.
            if last is not None and (now - last) < timedelta(days=sub.interval_days):
                continue
            since = max(sub.interval_days, 7)
        if sub.squad_id is not None:
            data, pptx_bytes = render(None, sub.squad_id, since)
        else:
            scope_tribe = None if user.role == "admin" else user.tribe_id
            data, pptx_bytes = render(scope_tribe, None, since)

        scope_key = f"sub:{sub.id}"
        sig = report_signature(data)
        changes = diff_report(get_baseline(db, scope_key), sig, lang)

        def _mark_done():
            set_baseline(db, scope_key, sig)
            sub.last_sent_at = now
            if sub.squad_id is None:
                user.report_last_sent_at = now

        # "Only when changes": skip the email but still advance the cadence/baseline.
        if only_changes and not changes.get("first") and changes["count"] == 0:
            _mark_done()
            continue

        html_body = render_html(data, standalone=True, changes=changes)
        attachment = None
        if pptx_bytes:
            attachment = (f"rapport_{now.date().isoformat()}.pptx", pptx_bytes,
                          "application", "vnd.openxmlformats-officedocument.presentationml.presentation")
        if sub.squad_id is not None:
            sq = db.get(Squad, sub.squad_id)
            scope_lbl = sq.name if sq else rt(lang, "h_squad")
        elif user.role == "admin":
            scope_lbl = rt(lang, "all_tribes")
        else:
            tr = db.get(Tribe, user.tribe_id) if user.tribe_id else None
            scope_lbl = tr.name if tr else rt(lang, "all_tribes")
        subject = subject_prefix(changes, lang) + rt(lang, "subject_personal", scope=scope_lbl, n=sub.interval_days)
        if send_email(smtp, user.email, subject, html_body, attachment=attachment, html=True):
            _mark_done()
            sent += 1
    db.commit()  # persist baselines / last_sent even when only skips occurred
    return sent


def build_dependencies_data(db: Session, scope_tribe: int | None, year: int | None = None,
                            squad_ids: list[int] | None = None, viewer=None,
                            lang: str | None = None, mode: str = "cross_tribe") -> dict:
    """Collect the jalons that carry a dependency, grouped by the entity they wait
    on. mode='cross_tribe' keeps only dependencies that point outside the source
    squad's tribe; mode='all' keeps every dependency (incl. same-tribe + free text)."""
    from .models import RoadmapItem  # noqa: F401  (ensures mapper import)
    now = utcnow()
    cfg = get_general(db)
    year = year or st.current_year_quarter(now)[0]
    lang = _lang(lang or cfg.get("default_lang"))
    cross_only = mode != "all"

    tribes = {t.id: t for t in db.scalars(select(Tribe)).all()}
    all_squads = {s.id: s for s in db.scalars(select(Squad)).all()}

    q = select(Squad).order_by(Squad.display_order, Squad.id).options(selectinload(Squad.roadmap_items))
    id_filter = set(squad_ids) if squad_ids else None
    groups: dict = {}
    total = 0
    for s in db.scalars(q).all():
        if scope_tribe is not None and s.tribe_id != scope_tribe:
            continue
        if id_filter is not None and s.id not in id_filter:
            continue
        src_tribe = tribes[s.tribe_id].name if s.tribe_id in tribes else "-"
        for r in s.roadmap_items:
            if r.year != year:
                continue
            kind = r.dependency_kind
            ttype = target_label = target_key = None
            target_tribe = None
            if kind == "tribe" and r.dependency_tribe_id:
                if cross_only and r.dependency_tribe_id == s.tribe_id:
                    continue
                tt = tribes.get(r.dependency_tribe_id)
                ttype, target_label, target_key = "tribe", (tt.name if tt else None), ("tribe", r.dependency_tribe_id)
            elif kind == "squad" and r.dependency_squad_id:
                tgt = all_squads.get(r.dependency_squad_id)
                if not tgt:
                    continue
                if cross_only and tgt.tribe_id == s.tribe_id:
                    continue
                target_tribe = tribes[tgt.tribe_id].name if tgt.tribe_id in tribes else None
                ttype, target_label, target_key = "squad", tgt.name, ("squad", tgt.id)
            elif (kind == "text" or kind is None) and (r.dependencies or "").strip():
                if cross_only:
                    continue  # free-text actors are not a tribe boundary
                target_label = r.dependencies.strip()
                ttype, target_key = "text", ("text", target_label.lower())
            if not target_label:
                continue
            g = groups.get(target_key)
            if g is None:
                g = {"target_type": ttype, "target_label": target_label,
                     "target_tribe": target_tribe, "items": []}
                groups[target_key] = g
            g["items"].append({
                "jalon": r.title, "description": (r.description or "").strip(),
                "squad_name": s.name, "tribe_name": src_tribe,
                "quarter": r.quarter, "year": r.year,
                "owner": r.owner or "", "status": r.status, "stage": r.release_stage or "",
            })
            total += 1

    type_order = {"tribe": 0, "squad": 1, "text": 2}
    group_list = sorted(groups.values(),
                        key=lambda g: (type_order.get(g["target_type"], 9), (g["target_label"] or "").lower()))
    for g in group_list:
        g["items"].sort(key=lambda it: (it["quarter"], it["squad_name"].lower(), it["jalon"].lower()))

    scope_name = tribes[scope_tribe].name if scope_tribe in tribes else rt(lang, "all_tribes")
    return {
        "app_name": cfg.get("app_name") or "TeamFollowUP",
        "scope_name": scope_name, "lang": lang, "year": year,
        "generated_at": now, "mode": mode, "groups": group_list, "total": total,
    }


def render_dependencies_html(data: dict, *, standalone: bool = True) -> str:
    """Render the milestone-dependency report as HTML: one section per waited-on
    entity (tribe/squad/external), each with a table of the jalons depending on it."""
    e = html.escape
    lang = _lang(data.get("lang", "fr"))
    T = _DEP_T[lang]
    parts = [f'<div class="hdr"><h1>{e(T["title"])} - {e(data["scope_name"])}</h1>',
             f'<div class="sub">{e(rt(lang, "year"))} {data["year"]} · '
             f'{e(T["total"].format(n=data["total"]))}</div></div>']
    if data["total"] == 0:
        parts.append(f'<div class="muted small">{e(T["none"])}</div>')
    for g in data["groups"]:
        tlbl = {"tribe": T["t_tribe"], "squad": T["t_squad"], "text": T["t_text"]}.get(g["target_type"], "")
        if g["target_type"] == "squad" and g.get("target_tribe"):
            tlbl = f'{tlbl} · {e(g["target_tribe"])}'
        parts.append(f'<h2>▶ {e(g["target_label"])} '
                     f'<span class="muted">({tlbl} · {e(T["gcount"].format(n=len(g["items"])))})</span></h2>')
        parts.append('<table><thead><tr>'
                     f'<th>{e(T["c_jalon"])}</th><th>{e(T["c_squad"])}</th><th>{e(T["c_trim"])}</th>'
                     f'<th>{e(T["c_owner"])}</th><th>{e(T["c_status"])}</th></tr></thead><tbody>')
        for it in g["items"]:
            parts.append(
                f'<tr><td><strong>{e(it["jalon"])}</strong></td>'
                f'<td>{e(it["squad_name"])} · {e(it["tribe_name"])}</td>'
                f'<td>Q{it["quarter"]} {str(it["year"])[2:]}</td>'
                f'<td>{e(it["owner"] or "-")}</td>'
                f'<td>{e(_status_label(it["status"], lang))}</td></tr>')
        parts.append('</tbody></table>')
    body = "".join(parts)
    if not standalone:
        return f'<div class="tc-report">{_CSS}{body}</div>'
    return (f'<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{e(T["title"])}</title>{_CSS}</head><body><div class="tc-report">{body}</div></body></html>')
