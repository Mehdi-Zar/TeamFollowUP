"""Weekly report: combined dashboard + progress-review, rendered to HTML and PPTX.

Used both for on-demand downloads/emails (routers/reports.py) and for the
automatic weekly send driven by the in-process scheduler (send_due_weekly_reports).
"""
from __future__ import annotations

import html
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import pptxtpl
from . import status as st
from .generalconfig import get_general, reference_year
from .models import ReportSnapshot, Squad, Tribe, utcnow
from .serializers import annual_progress, budget_out, dependency_label

# Shared with the PPTX renderers; see reportcommon.
from .reportcommon import (_people_line, _sep, fmt_date, fmt_datetime, fmt_money, MOOD_EMOJI, STAGE_COLOR, _DEP_T, _INIT_T, _MONTHS, _lang,  # noqa: F401
                           _status_label, _status_rag, group_by_theme, mood_cloud_svg,
                           mood_label, otd_star_svg, rt, timeline_groups,
                           version_suffix)
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
           "quarter_pct": "Progression", "kpi_trend": "KPI"},
    "en": {"jalon_added": "New milestone", "jalon_status": "Milestone",
           "quarter_pct": "Progress", "kpi_trend": "KPI"},
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

def otd_rows_for_tribes(db: Session, tribe_ids, year: int):
    """Les engagements OTD de ces tribus pour cette annee, avec leurs jalons.

    Une requete pour tout le monde: les engagements vivent au niveau de la tribu,
    et un rapport de dix squads en aurait sinon tire dix fois les memes lignes.
    """
    from .models import Otd
    tribe_ids = {t for t in tribe_ids if t is not None}
    if not tribe_ids:
        return []
    return db.scalars(
        select(Otd).where(Otd.year == year, Otd.tribe_id.in_(tribe_ids))
        .options(selectinload(Otd.roadmap_items), selectinload(Otd.squad_items),
                 selectinload(Otd.owner))
        .order_by(Otd.display_order, Otd.id)).all()


def concerns_squad(o, sq) -> bool:
    """Does a management commitment concern this squad? When it was set on the
    squad (``squad_id``) or carries one of its milestones. Only an older one with
    neither falls back on its owner being the squad's leader: a leader of two
    squads used to see every commitment of one under the other."""
    if o.squad_id is not None and o.squad_id == sq.id:
        return True
    if any(j.squad_id == sq.id for j in o.roadmap_items):
        return True
    return (o.squad_id is None and not o.roadmap_items
            and bool(o.owner_user_id) and o.owner_user_id == sq.leader_user_id)


def otds_of_squad(sq, otd_rows, year: int, now: datetime) -> list[dict]:
    """Les engagements que cette squad porte, des deux portees.

    Un engagement du management concerne la squad s'il lui est assigne ou s'il
    embarque un de ses jalons; un engagement de squad est le sien par
    construction. Les deux sortent dans la meme liste, avec leur ``scope``, parce
    que la frise les montre cote a cote et que c'est la couleur, pas la liste, qui
    doit dire lequel vient d'ou. Meme regle que la page d'une squad, pour que les
    deux ne racontent pas deux histoires.
    """
    out = []
    for o in otd_rows:
        if o.tribe_id != sq.tribe_id:
            continue
        if o.scope == "squad":
            if o.squad_id != sq.id:
                continue
        elif not concerns_squad(o, sq):
            continue
        d = _aware(o.committed_date)
        members = o.squad_items if o.scope == "squad" else o.roadmap_items
        out.append({
            "id": o.id, "title": o.title, "scope": o.scope,
            "date": d.date().isoformat() if d else None,
            # Le rang du mois est ce qui pose l'engagement sur l'axe; une date
            # d'une autre annee n'a pas de place sur cette frise.
            "month": (d.month - 1) if d is not None and d.year == year else None,
            "status": st.otd_status(members, o.committed_date, now),
            "owner": o.owner.display_name if o.owner else None,
        })
    # Le management d'abord, la squad ensuite: la frise se lit de l'engagement
    # subi vers l'engagement choisi, et deux blocs se reperent mieux qu'un melange
    # ou seule la couleur trierait.
    out.sort(key=lambda x: (x["scope"] != "management",
                            x["month"] if x["month"] is not None else 99))
    return out


def build_report_data(db: Session, scope_tribe: int | None, year: int | None = None,
                      since_days: int = 7, now: datetime | None = None,
                      squad_id: int | None = None, lang: str | None = None,
                      squad_ids: list[int] | None = None, viewer=None, led_by=None) -> dict:
    """Assemble the combined dashboard + weekly-review data for the given scope.

    squad_id, when set, narrows the report to a single squad (ignoring scope_tribe).
    squad_ids, when set, restricts the report to that subset of squads (still within
    the caller's tribe scope) - used to pick which squads appear in a global roadmap.
    lang, when set, picks the report language; otherwise the general default_lang.
    led_by, when set, adds the squads that person leads outside ``scope_tribe`` (a
    leader may lead a squad of another tribe, and reads it like their own).
    """
    now = now or utcnow()
    cfg = get_general(db)
    threshold = cfg.get("staleness_threshold_days")
    year = year or reference_year(db)
    lang = _lang(lang or cfg.get("default_lang"))

    tribes = {t.id: t for t in db.scalars(select(Tribe)).all()}
    q = select(Squad).order_by(Squad.display_order, Squad.id).options(
        selectinload(Squad.roadmap_items),
        selectinload(Squad.quarter_progress), selectinload(Squad.kpis),
        selectinload(Squad.snapshots).load_only(ReportSnapshot.id, ReportSnapshot.squad_id, ReportSnapshot.submitted_at),
        selectinload(Squad.leader),
        selectinload(Squad.co_leaders), selectinload(Squad.contributors),
        selectinload(Squad.budgets), selectinload(Squad.key_messages),
    )
    id_filter = set(squad_ids) if squad_ids else None
    led: set[int] = set()
    if led_by is not None and getattr(led_by, "role", None) != "admin":
        from .deps import led_squad_ids
        led = set(db.scalars(led_squad_ids(db, led_by)).all())
    squads = []
    for s in db.scalars(q).all():
        if squad_id is not None:
            if s.id == squad_id:
                squads.append(s)
            continue
        if scope_tribe is not None and s.tribe_id != scope_tribe and s.id not in led:
            continue  # tribe scope is the security boundary (plus the squads one leads)
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
                "id": it.id, "title": it.title, "owner": it.owner,
                "deadline": it.deadline.date().isoformat() if it.deadline else None})

    # Les engagements OTD vivent au niveau de la tribu, pas de la squad: on les
    # charge une fois pour toutes les tribus concernees, puis chaque squad garde
    # les siens.
    otd_rows = otd_rows_for_tribes(db, {s.tribe_id for s in squads}, year)

    def _otds_of(sq) -> list[dict]:
        return otds_of_squad(sq, otd_rows, year, now)

    by_tribe: dict[int | None, list[dict]] = {}
    totals = {"squads": 0, "blocked": 0, "at_risk": 0, "otd_late": 0,
              "stale": 0, "progress_sum": 0}
    late_ids: set[int] = set()

    for s in squads:
        c = st.counts(s, year)
        f = st.freshness(s, threshold, now)
        prog = st.year_progress(s, year)
        comments = st.quarter_comments(s, year)
        ann = annual_progress(s, year)
        # Full per-squad content (OTD + roadmap by quarter + advancement), so the
        # report/PPTX can show everything, not just the dashboard summary.
        detail = {
            "year": year,
            "initiatives": init_by_squad.get(s.id, []),
            "otds": _otds_of(s),
            "quarters": [
                {"q": q, "pct": prog[q], "comment": comments.get(q),
                 "items": [
                     {"id": r.id, "title": r.title, "status": r.status, "owner": r.owner,
                      "stage": r.release_stage, "theme": r.theme,
                      "objective_id": r.objective_id,
                      "initiative_id": r.initiative_id,
                      # Les deux rattachements d'engagement, celui du management et
                      # celui de la squad: la frise fait une ligne par engagement,
                      # et un jalon qui sert les deux apparait sous les deux.
                      "otd_id": r.otd_id,
                      "squad_otd_id": r.squad_otd_id,
                      "dependency": dependency_label(r)}
                     for r in sorted(s.roadmap_items, key=lambda x: (x.display_order, x.id))
                     if r.year == year and r.quarter == q
                 ]}
                for q in (1, 2, 3, 4)
            ],
            # Hand-curated key messages (success / alert / risk) for this squad/year.
            "key_messages": [
                {"kind": m.kind, "text": m.text,
                 "created_at": _aware(m.created_at).isoformat() if m.created_at else None}
                for m in sorted(s.key_messages, key=lambda x: (x.display_order, x.id))
                if m.year == year
            ],
            # Budget readout - only for a viewer allowed to see this squad's figures.
            "budget": _budget_for_report(s, year, viewer),
            # Lets a document tell "no budget follow-up" from "not shown here".
            "budget_enabled": bool(s.budget_enabled),
        }
        row = {
            "squad_id": s.id,
            "name": s.name,
            "leader": s.leader.display_name if s.leader else "",
            # The rest of the squad's leadership and who does its reporting: the
            # squad page names them, the document does too.
            "co_leaders": [u.display_name for u in sorted(s.co_leaders, key=lambda x: x.display_name or "")],
            "contributors": [u.display_name for u in sorted(s.contributors, key=lambda x: x.display_name or "")],
            "status": st.squad_status(s, year),
            "status_rag": _status_rag(st.squad_status(s, year)),
            # Le moral declare par la squad: la seule donnee du rapport qu'aucun
            # calcul ne produit, et celle qui explique souvent les autres.
            "mood": s.mood,
            "mood_at": _aware(s.mood_at).date().isoformat() if s.mood_at else None,
            "mood_comment": s.mood_comment,
            "quarters": {q: prog[q] for q in (1, 2, 3, 4)},
            "annual_pct": ann,
            "blocked": c["roadmap_blocked"],
            "at_risk": c["roadmap_at_risk"],
            # Late commitments (OTD) of the squad: the one number a committee asks
            # first. Replaces the "red objectives", a notion the app no longer has.
            "otd_late": sum(1 for o in detail["otds"] if o.get("status") == "late"),
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
        # A management OTD served by several squads is late once, not N times.
        late_ids.update(o["id"] for o in detail["otds"] if o.get("status") == "late")
        totals["stale"] += 1 if row["is_stale"] else 0
        # Only the squads that planned something count in the average.
        if c.get("roadmap_total", 0) > 0:
            totals["progress_sum"] += ann
            totals["planned"] = totals.get("planned", 0) + 1

    # Order squads within a tribe by severity: blocked, then at risk, then late
    # commitments, then stale reporting, then by name. (The old key sorted on
    # "delta", always 0, so the at-risk squads came out alphabetically and a cut
    # list could hide them behind green ones.)
    _severity = severity_key
    for rows in by_tribe.values():
        rows.sort(key=_severity)

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
                 if is_attention(r)]
    attention.sort(key=_severity)

    totals["otd_late"] = len(late_ids)
    # A management commitment that no squad carries (no squad named, no milestone)
    # appeared in no document at all: the tribe's part lists them.
    carried = {o["id"] for blk in by_tribe.values() for r in blk for o in (r.get("detail") or {}).get("otds", [])}
    tribe_otds = []
    if squad_id is None:
        for o in otd_rows:
            if o.scope != "management" or o.id in carried:
                continue
            d = _aware(o.committed_date)
            tribe_otds.append({"id": o.id, "title": o.title, "date": d.date().isoformat() if d else None,
                               "status": st.otd_status(o.roadmap_items, o.committed_date, now)})
    avg = round(totals["progress_sum"] / totals["planned"]) if totals.get("planned") else 0
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
            "otd_late": totals["otd_late"],
            "stale": totals["stale"],
            "avg_progress": avg,
        },
        "tribes": tribe_blocks,
        "attention": attention,
        "tribe_otds": tribe_otds,
        "leaves_upcoming": leaves_upcoming,
        "leaves_enabled": _leaves_enabled(db),
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
    """One squad's detail block, in the order of the squad page: the annual
    timeline (quarters, OTD commitments, initiatives and their milestones), then
    key messages and budget."""
    det = r.get("detail") or {}
    parts: list[str] = ['<div class="sq-detail">']
    if with_title:
        parts.append(f'<h3>{e(r["name"])} <span class="muted">({r["annual_pct"]}%)</span> '
                     f'{_mood_html(r, lang, e)}</h3>')
        if r.get("co_leaders") or r.get("contributors"):
            parts.append(f'<div class="muted small">{e(rt(lang, "h_leader"))}{_sep(lang)}{e(r.get("leader") or "-")}'
                         f'{_people_line(r, lang, e)}</div>')

    # La frise: les trimestres, les engagements OTD poses a leur date, puis une
    # ligne par initiative avec les jalons qui la servent. Un seul bloc la ou il y
    # en avait trois, parce qu'ils repondaient tous a la meme question.
    parts.append(_timeline_html(det, lang, e, det.get("year") or 0))

    # Key messages
    kms = det.get("key_messages") or []
    parts.append(f'<div class="d-sub">{e(rt(lang, "h_key_messages"))}</div>')
    if kms:
        km_rag = {"success": "green", "alert": "amber", "risk": "red"}
        parts.append('<ul class="d-obj">')
        for m in kms:
            rag = km_rag.get(m["kind"], "grey")
            ts = f' <span class="muted">({e(fmt_datetime(m["created_at"], lang))})</span>' if m.get("created_at") else ""
            parts.append(f'<li><span class="dot" style="background:{RAG_COLOR[rag]}"></span>'
                         f'<strong>{e(rt(lang, "km_" + m["kind"]))}</strong>{_sep(lang)}{e(m["text"])}{ts}</li>')
        parts.append('</ul>')
    else:
        parts.append(f'<div class="muted small">{e(rt(lang, "no_key_message"))}</div>')

    # Budget (present only when the viewer may see this squad's figures)
    bud = det.get("budget")
    if bud is not None:
        fmtn = lambda v: fmt_money(v, lang)
        st_rag = {"on_track": "green", "at_risk": "amber", "over": "red"}[bud["status"]]
        st_lbl = rt(lang, {"on_track": "b_on_track", "at_risk": "b_at_risk", "over": "b_over"}[bud["status"]])
        over = f' (+{fmtn(bud["overrun"])}, {bud["overrun_pct"]}%)' if bud["status"] == "over" else ""
        parts.append(f'<div class="d-sub">{e(rt(lang, "h_budget"))} '
                     f'<span class="dot" style="background:{RAG_COLOR[st_rag]}"></span> '
                     f'<span class="muted">{e(st_lbl)}{e(over)}</span></div>')
        if bud["total"] is None and bud["spent"] is None and bud["forecast"] is None:
            parts.append(f'<div class="muted small">{e(rt(lang, "no_budget"))}</div>')
        else:
            sp = f' <span class="muted">({bud["spent_pct"]}%)</span>' if bud.get("spent_pct") is not None else ""
            fp = f' <span class="muted">({bud["forecast_pct"]}%)</span>' if bud.get("forecast_pct") is not None else ""
            parts.append('<ul class="d-obj">')
            parts.append(f'<li>{e(rt(lang, "b_total"))}{_sep(lang)}<strong>{fmtn(bud["total"])}</strong></li>')
            parts.append(f'<li>{e(rt(lang, "b_spent"))}{_sep(lang)}<strong>{fmtn(bud["spent"])}</strong>{sp}</li>')
            parts.append(f'<li>{e(rt(lang, "b_forecast"))}{_sep(lang)}<strong>{fmtn(bud["forecast"])}</strong>{fp}</li>')
            if bud.get("comment"):
                parts.append(f'<li class="muted">{e(bud["comment"])}</li>')
            parts.append('</ul>')

    parts.append('</div>')  # .sq-detail
    return parts


_STATIC_ASSETS = os.path.join(os.path.dirname(__file__), "static", "assets")


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


def _squad_app_cards(det: dict, lang: str, e, year: int) -> list[str]:
    """The squad page's cards, in page order: the annual timeline, then key
    messages and budget, using the application's own component classes."""
    fmtn = lambda v: fmt_money(v, lang)
    C: list[str] = []

    # La frise annuelle, dans sa propre carte: le meme bloc unique que la page.
    C.append(f'<div class="card">{_timeline_html(det, lang, e, year)}</div>')

    # Key messages
    C.append(f'<div class="card"><h2>{e(rt(lang, "h_key_messages"))}</h2>')
    kms = det.get("key_messages") or []
    if kms:
        for m in kms:
            ts = f'<div class="small muted">{e(fmt_datetime(m["created_at"], lang))}</div>' if m.get("created_at") else ""
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
        over = f' (+{fmtn(bud["overrun"])}, {bud["overrun_pct"]}%)' if bud["status"] == "over" else ""
        C.append(f'<div class="card"><div class="between"><h2 style="margin:0">{e(rt(lang, "h_budget"))}</h2>'
                 f'<span class="badge {_BUD_BADGE[bud["status"]]}">{e(st_lbl)}{e(over)}</span></div>')
        if bud["total"] is None and bud["spent"] is None and bud["forecast"] is None:
            C.append(f'<div class="small muted">{e(rt(lang, "no_budget"))}</div>')
        else:
            sp = f' ({bud["spent_pct"]}%)' if bud.get("spent_pct") is not None else ""
            fp = f' ({bud["forecast_pct"]}%)' if bud.get("forecast_pct") is not None else ""
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


# ----- La frise annuelle (HTML) ---------------------------------------------------
#
# Le meme bloc que la page d'une squad, rendu en HTML autonome: son style ne
# depend pas de la feuille de l'application, parce que ce meme HTML sert aussi
# l'export JPG et le rapport multi-squads, qui eux ne la chargent pas. Les
# couleurs restent prises dans les variables du theme quand elles existent, pour
# qu'un export garde la charte choisie dans Administration > Personnalisation.

_TIMELINE_CSS = """<style>
/* La frise tient sur trois etages et un seul sens de lecture: les trimestres et
   les mois en tete, les engagements poses sur leur mois, puis les boites de
   jalons, reliees a leur date par un trait qui ne remonte jamais plus haut que
   les engagements. C'est ce qui garantit qu'aucun trait ne traverse un titre. */
.xtl{margin-top:10px}
.xtl-scroll{overflow-x:auto}
.xtl-scroll{overflow-x:auto;margin-top:10px}
.xtl-grid{min-width:920px}
/* Aucun ecart entre les colonnes: c'est ce qui permet a un repere de tomber
   exactement sur sa case de mois, d'une rangee a l'autre. L'air se prend en marge
   interne, dans les cellules. */
.xtl-row{display:grid;grid-template-columns:190px repeat(12,1fr);align-items:start}
.xtl-label{min-width:0;padding:4px 8px 4px 0;font-size:13px}
.xtl-q{background:var(--ice-soft,#E8F0FE);border:1px solid var(--line,#E2E8F0);border-radius:10px;
  padding:6px 8px;margin:0 6px 4px 0}
.xtl-q-head{display:flex;justify-content:space-between;align-items:baseline}
.xtl-q-head b{color:var(--navy,#1E2761);font-size:13px}
.xtl-q-head span{font-size:12px;color:var(--grey,#64748B)}
.xtl-bar{height:5px;background:var(--line,#E2E8F0);border-radius:99px;margin-top:5px;overflow:hidden}
.xtl-bar>span{display:block;height:100%;background:var(--accent,#175CD3);border-radius:99px}
.xtl-qc{margin-top:4px;font-size:12px;color:var(--grey,#64748B);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.xtl-months{border-bottom:1px solid var(--line,#E2E8F0);padding-bottom:4px;margin-bottom:2px}
.xtl-m{text-align:center;font-size:12px;color:var(--grey,#64748B)}
/* Un engagement tient dans la largeur d'un mois, pas plus: son titre passe a la
   ligne. Etale a cote de son etoile, il courait sur trois ou quatre mois et on ne
   savait plus a quelle colonne il repondait. Deux engagements du meme mois se
   suivent dans la meme colonne, l'un sous l'autre. */
.xtl-otds{padding:6px 0 8px}
.xtl-otd-cell{display:flex;flex-direction:column;gap:6px;min-width:0;padding:0 3px}
.xtl-otd{display:flex;flex-direction:column;align-items:center;gap:2px;min-width:0;
  font-size:11.5px;font-weight:700;line-height:14px;text-align:center}
.xtl-otd .xtl-star{line-height:0}
.xtl-otd span{overflow-wrap:break-word;min-width:0}
/* Deux couleurs, et deux seulement: ce qui est peint ici n'est pas le statut
   (il se lit sur les jalons) mais QUI a pris l'engagement. */
.xtl-scope-management{color:#1E2761}
.xtl-scope-squad{color:#0E7490}
/* Le trait qui relie une boite a sa date: en pointille, d'une encre claire, et
   tout droit. Il traverse la bande des engagements par le couloir libre que
   laisse le bord de leur case, donc il ne croise aucun titre. Il est pose dans
   cette bande meme, etire sur toute sa hauteur, ce qui evite de la mesurer. */
.xtl-drop{align-self:stretch;width:0;border-left:1px dashed var(--line,#CBD5E1);
  position:relative;margin-bottom:-9px}
.xtl-drop::before{content:"";position:absolute;left:-3.5px;top:-9px;width:6px;height:6px;
  border-radius:50%;background:var(--line,#CBD5E1)}
.xtl-drop::after{content:"";position:absolute;left:-4px;bottom:-5px;width:0;height:0;
  border-left:4px solid transparent;border-right:4px solid transparent;
  border-top:5px solid var(--line,#CBD5E1)}
/* Une boite par engagement, ou par theme pour les jalons qui n'en tiennent aucun,
   avec son titre dedans et ses jalons l'un sous l'autre. Elle commence au bord de
   la case de son mois, ce qui est ce qui permet au trait d'etre droit. */
.xtl-boxes{align-items:start}
/* Les boites d'un trimestre s'empilent, elles ne se partagent pas sa largeur:
   une boite large porte un texte plus gros et ne coupe pas ses mots. Le deck
   suit la meme regle, et les deux supports doivent montrer le meme dessin. */
.xtl-quarter{display:flex;flex-direction:column;gap:8px;min-width:0;
  align-items:stretch;padding-right:8px}
.xtl-box{flex:0 0 auto;min-width:0;border:1px dashed var(--line,#CBD5E1);border-radius:8px;
  padding:7px 9px;background:#fff}
.xtl-box-title{font-weight:700;font-size:13px;line-height:16px;color:var(--navy,#1E2761);
  padding-bottom:4px;overflow-wrap:break-word}
/* La coche est a droite: la colonne de gauche est celle des titres, et un oeil
   qui descend une liste lit des titres alignes. */
.xtl-jal{display:flex;flex-direction:row-reverse;align-items:flex-start;gap:6px;
  font-size:12.5px;line-height:16px;padding:2px 0;overflow-wrap:break-word;min-width:0}
.xtl-jal>span{flex:1}
.xtl-jal>span{min-width:0}
.xtl-jal em{font-style:normal;font-size:11px;color:var(--grey,#64748B)}
/* La dependance sur sa propre ligne: a la suite du titre, elle prenait le pas sur
   lui alors que c'est le titre qu'on lit en premier. */
.xtl-dep{display:block}
/* La coche: pleine et cochee quand le jalon est livre, un anneau sinon. On voit
   d'un coup ce qui est fait, et la couleur dit le reste. */
.xtl-tick{flex:0 0 auto;width:14px;height:14px;margin-top:2px;border-radius:50%;
  border:2px solid currentColor;position:relative}
.xtl-jal.rag-green{color:var(--green,#027A48)}
.xtl-jal.rag-amber{color:var(--orange,#B54708)}
.xtl-jal.rag-red{color:var(--red,#B42318)}
.xtl-jal.rag-grey{color:var(--grey,#94A3B8)}
.xtl-jal>span{color:var(--ink,#111827)}
.xtl-jal.done .xtl-tick{background:currentColor}
.xtl-jal.done .xtl-tick::after{content:"";position:absolute;left:3px;top:0;width:4px;
  height:8px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg)}
/* Trois etats, trois dessins: plein et coche = fait, un point au centre = en
   cours, vide = pas commence. La couleur seule ne se lit pas de loin. */
.xtl-jal:not(.done):not(.rag-grey) .xtl-tick::after{content:"";position:absolute;
  left:50%;top:50%;width:6px;height:6px;margin:-3px 0 0 -3px;border-radius:50%;
  background:currentColor}
.xtl-none{font-size:12px;color:var(--grey,#64748B);grid-column:span 12;padding:4px 0}
.xtl-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:var(--grey,#64748B);
  padding:8px 0 0}
.xtl-legend span{display:inline-flex;align-items:center;gap:6px}
.xtl-legend i{width:9px;height:9px;border-radius:50%}
.xtl-mood{display:inline-flex;align-items:center;gap:8px}
.xtl-mood .mood-cloud{display:block;flex:0 0 auto}
.xtl .between{display:flex;justify-content:space-between;gap:16px}
.xtl .small,.xtl-mood .small{font-size:12px}
.xtl .muted,.xtl-mood .muted{color:var(--grey,#64748B)}
.xtl .strong{font-weight:700}
.xtl h2{font-size:16px;margin:0 0 2px;padding:0;border:0;color:var(--navy,#1E2761);
  text-transform:none;letter-spacing:normal}
</style>"""


def _mood_html(r: dict, lang: str, e) -> str:
    """Le moral declare, avec sa date: un moral de mars affiche en septembre ment
    plus surement qu'une case vide."""
    mood = r.get("mood")
    # Un nuage dessine, pas un emoji: l'emoji depend de la police installee sur le
    # poste qui ouvre le document, et sort en carre la ou elle manque.
    face = mood_cloud_svg(mood, size=34)
    when = f' <span class="muted small">{e(rt(lang, "mood_at", d=fmt_date(r["mood_at"], lang)))}</span>' if r.get("mood_at") else ""
    note = f' <span class="muted small">{e(r["mood_comment"])}</span>' if r.get("mood_comment") else ""
    return (f'<span class="xtl-mood">{face}'
            f'<span class="small">{e(rt(lang, "h_mood"))}{_sep(lang)}{e(mood_label(mood, lang))}</span>'
            f'{when}{note}</span>')


def _page_min_width(data: dict) -> int:
    """La largeur minimale de la page, pour que la frise la plus large tienne.

    Sans elle, la frise defile a l'interieur de sa carte: a l'ecran c'est
    acceptable, mais le JPG est rendu a la largeur de la page et n'aurait montre
    que les premieres boites. Une page large defile, un document tronque ment.
    """
    widths = [_grid_width(r["detail"]) for blk in data.get("tribes") or []
              for r in blk["squads"] if r.get("detail")]
    return max(widths, default=920) + 56


def _grid_width(det: dict) -> int:
    """La largeur minimale de la frise, en pixels, selon le trimestre le plus charge.

    Les boites d'un trimestre s'empilent au lieu de se partager sa largeur, donc la
    frise ne s'elargit plus a chaque boite: elle s'elargit quand un engagement de la
    bande du haut, lui, n'a plus la largeur d'un mois pour son titre. Douze mois a
    quatre-vingt-dix pixels tiennent n'importe quel titre, et la page reste a une
    largeur qu'un ecran montre en entier.
    """
    return max(920, 190 + 90 * 12)


def _timeline_html(det: dict, lang: str, e, year: int) -> str:
    """La frise: les trimestres, la bande des mois, les engagements poses sur leur
    mois, puis les boites de jalons reliees a leur date.

    Meme dessin et meme groupement que la slide (``timeline_groups``): deux mises
    en page qui se contrediraient sur la place d'un jalon seraient pires qu'une
    seule imparfaite.
    """
    months = _MONTHS[_lang(lang)]
    otds = det.get("otds") or []
    quarters = {qd["q"]: qd for qd in det.get("quarters") or []}
    P = [f'<div class="xtl"><div class="between" style="align-items:flex-start">'
         f'<div><h2 style="margin:0">{e(rt(lang, "h_timeline", year=year))}</h2>'
         f'<div class="small muted">{e(rt(lang, "tl_hint"))}</div></div>'
         f'<div class="xtl-legend">'
         f'<span><i style="background:{RAG_COLOR["green"]}"></i>{e(_status_label("on_track", lang))}</span>'
         f'<span><i style="background:{RAG_COLOR["amber"]}"></i>{e(_status_label("at_risk", lang))}</span>'
         f'<span><i style="background:{RAG_COLOR["red"]}"></i>{e(_status_label("blocked", lang))}</span>'
         f'</div></div><div class="xtl-scroll">'
         f'<div class="xtl-grid" style="min-width:{_grid_width(det)}px">']

    # Les trimestres, avec l'avancement calcule de chacun et son commentaire.
    P.append('<div class="xtl-row"><div class="xtl-label"></div>')
    for q in (1, 2, 3, 4):
        qd = quarters.get(q) or {"pct": 0, "comment": None}
        pct = max(0, min(100, int(qd.get("pct") or 0)))
        planned = bool(qd.get("items"))
        cm = f'<div class="xtl-qc">{e(qd["comment"])}</div>' if qd.get("comment") else ""
        # Nothing planned is not "0 % delivered": the annual figure ignores it too.
        shown = f"{pct} %" if planned else e(rt(lang, "q_nothing"))
        P.append(f'<div style="grid-column:span 3"><div class="xtl-q">'
                 f'<div class="xtl-q-head"><b>Q{q}</b><span>{shown}</span></div>'
                 + (f'<div class="xtl-bar"><span style="width:{pct}%"></span></div>' if planned else "")
                 + f'{cm}</div></div>')
    P.append('</div>')

    # Les mois, qui donnent la resolution de l'axe, juste sous les trimestres.
    P.append('<div class="xtl-row xtl-months"><div class="xtl-label"></div>')
    P.extend(f'<div class="xtl-m">{e(m)}</div>' for m in months)
    P.append('</div>')

    # Les boites sont calculees avant la bande des engagements: c'est dans cette
    # bande que descend leur trait, etire sur toute sa hauteur.
    groups_for_drops = timeline_groups(det)

    # Les engagements: une etoile sur le mois, le titre dessous, dans la largeur
    # d'une case. Deux engagements du meme mois se suivent l'un sous l'autre.
    by_month: dict[int, list] = {}
    for o in otds:
        if o.get("month") is not None:
            by_month.setdefault(o["month"], []).append(o)
    P.append(f'<div class="xtl-row xtl-otds">'
             f'<div class="xtl-label small strong">{e(rt(lang, "h_otd_section"))}</div>')
    for month, column in sorted(by_month.items()):
        P.append(f'<div class="xtl-otd-cell" style="grid-column:{2 + month}">')
        for o in column:
            scope = o.get("scope") or "management"
            P.append(f'<div class="xtl-otd xtl-scope-{scope}"'
                     f' title="{e(o["title"])}{_sep(lang)}{e(rt(lang, "otd_" + o["status"]))}'
                     f' ({e(rt(lang, "otd_scope_" + scope))})">'
                     f'{otd_star_svg(scope, 12)}<span>{e(o["title"])}</span>'
                     + (f' <span class="pill" style="background:{RAG_COLOR["red"]}">{e(rt(lang, "otd_late"))}</span>'
                        if o.get("status") == "late" else "")
                     + '</div>')
        P.append('</div>')
    if not by_month:
        P.append('<div class="xtl-cell"></div>')
    for g in groups_for_drops:
        P.append(f'<i class="xtl-drop" aria-hidden="true"'
                 f' style="grid-column:{2 + g["month"]};grid-row:1"></i>')
    P.append('</div>')
    # Un engagement sans date n'a pas de place sur l'axe, ce qui n'est pas une
    # raison de le taire: il est cite sous la bande.
    undated = [o for o in otds if o.get("month") is None]
    if undated:
        names = ", ".join(o["title"] for o in undated)
        P.append(f'<div class="xtl-row"><div class="xtl-label"></div>'
                 f'<div class="xtl-none">{e(rt(lang, "tl_no_date"))}{_sep(lang)}{e(names)}</div></div>')
    if not otds:
        P.append(f'<div class="xtl-row"><div class="xtl-label"></div>'
                 f'<div class="xtl-none">{e(rt(lang, "no_otd"))}</div></div>')

    # Les traits, puis les boites. Les boites sont rangees dans l'ordre des dates
    # et de largeur egale: un trait relie chacune a son mois sans jamais croiser
    # son voisin, et aucun ne remonte au-dessus des engagements.
    groups = groups_for_drops
    if groups:
        # Un trimestre, une cellule: ses boites s'en partagent la largeur et n'en
        # sortent pas. Une boite a cheval sur deux trimestres se lisait sous le
        # mauvais, et une boite de decembre n'avait nulle part ou s'etendre.
        by_quarter: dict[int, list] = {}
        for g in groups:
            by_quarter.setdefault(g["month"] // 3, []).append(g)
        P.append('<div class="xtl-row xtl-boxes"><div class="xtl-label"></div>')
        for quarter in range(4):
            P.append('<div class="xtl-quarter" style="grid-column:span 3">')
            for g in by_quarter.get(quarter, []):
                P.append('<div class="xtl-box">')
                if g["title"]:
                    cls = f' class="xtl-scope-{g["scope"]}"' if g["scope"] else ""
                    P.append(f'<div class="xtl-box-title"{cls}>{e(g["title"])}</div>')
                for it in g["items"]:
                    stage = f' <em>{e(it["stage"])}</em>' if it.get("stage") else ""
                    # La dependance est souvent la seule ligne qui explique un
                    # glissement. Elle reste en HTML, qui n'a pas de bas de page a
                    # tenir, sur sa propre ligne pour ne pas noyer le titre.
                    dep = (f'<em class="xtl-dep">{e(rt(lang, "dep"))} {e(it["dependency"])}</em>'
                           if it.get("dependency") else "")
                    done = " done" if it["status"] == "done" else ""
                    P.append(f'<div class="xtl-jal rag-{_status_rag(it["status"])}{done}"'
                             f' title="{e(_status_label(it["status"], lang))}">'
                             f'<i class="xtl-tick"></i>'
                             f'<span>{e(it["title"])}{stage}{dep}</span></div>')
                P.append('</div>')
            P.append('</div>')
        P.append('</div>')
    else:
        P.append(f'<div class="xtl-row"><div class="xtl-label"></div>'
                 f'<div class="xtl-none">{e(rt(lang, "tl_empty"))}</div></div>')

    P.append('</div>')
    P.append('<div class="xtl-legend">' + "".join(
        f'<span class="xtl-scope-{sc}">{otd_star_svg(sc)}{e(rt(lang, "otd_scope_" + sc))}</span>'
        for sc in ("management", "squad")) + '</div>')
    P.append('</div></div>')
    return "".join(P)

def severity_key(r: dict):
    """Order of squads in every document: blocked, then at risk, then late
    commitments, then stale reporting, then by name."""
    return (-r["blocked"], -r["at_risk"], -r["otd_late"], not r.get("is_stale"), r["name"].lower())


def is_attention(r: dict) -> bool:
    """A squad the documents list under "attention points"."""
    return r["blocked"] > 0 or r["otd_late"] > 0 or bool(r.get("is_stale"))


def _leaves_enabled(db: Session) -> bool:
    """Is the absences module on (the documents drop their absences column when not)?"""
    from .modulesconfig import get_modules, is_active
    return bool(is_active(get_modules(db), "leaves"))


def _render_squad_page(data: dict, standalone: bool, e, lang: str, changes: dict | None = None) -> str:
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
        badges.append(_mood_html(r, lang, e))
        P = [f'<div class="export-page"><h1 style="color:var(--navy);margin:0 0 8px">{e(r["name"])}</h1>',
             f'<div class="inline" style="gap:10px;flex-wrap:wrap;margin-bottom:6px">{"".join(badges)}</div>',
             f'<div class="muted small" style="margin-bottom:16px">{e(rt(lang, "h_leader"))}{_sep(lang)}'
             f'<span class="strong">{e(r["leader"] or "-")}</span>, {e(rt(lang, "year"))} {year}'
             f'{_people_line(r, lang, e)}</div>',
             '<div class="stack" style="gap:18px">']
        # "What's new since your last report": a squad's own mail announced
        # "[3 new items]" in its subject and never showed them.
        if changes is not None and not changes.get("first"):
            from .mailbody import changes_block
            box = changes_block(changes, lang)
            if box:
                P.insert(-1, '<div style="border:1px solid #dbe4ff;background:#f5f8ff;border-left:4px solid #175CD3;'
                             f'border-radius:10px;padding:12px 16px;margin:0 0 16px">{box}</div>')
        P.extend(_squad_app_cards(r["detail"], lang, e, year))
        P.append('</div></div>')
        body = "\n".join(P)
    page_css = ('<style>body{background:var(--bg,#F5F7FA);margin:0;padding:24px;color:var(--text,#1E293B);'
                'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}'
                '.export-page{max-width:1040px;margin:0 auto}'
                '.init-tbl{width:100%;border-collapse:collapse}'
                '.init-tbl th,.init-tbl td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line,#E2E8F0)}</style>')
    if not standalone:
        return f'{style}{page_css}{_TIMELINE_CSS}{body}'
    title = e(r["name"]) if r else e(data["scope_name"])
    wide = _page_min_width(data)
    return (f'<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title>{style}{page_css}{_TIMELINE_CSS}'
            f'<style>.export-page{{max-width:{wide - 48}px}}</style>'
            f'</head><body style="min-width:{wide}px">{body}</body></html>')


# =============================================================================
# "What's new since your last report" - change detection against a stored
# per-scope baseline (see models.ReportBaseline).
# =============================================================================

def _ms_lbl(status: str, lang: str) -> str:
    """Localized milestone-status label for the changelog (passes unknowns through)."""
    return rt(lang, {"on_track": "ms_on_track", "at_risk": "ms_at_risk",
                     "blocked": "ms_blocked", "done": "ms_done"}.get(status, "h_status")) \
        if status in ("on_track", "at_risk", "blocked", "done") else status


def _otd_lbl(status: str | None, lang: str) -> str:
    """Localized OTD status label for the changelog (passes unknown values through)."""
    key = {"on_track": "otd_on_track", "at_risk": "otd_at_risk", "late": "otd_late",
           "delivered": "otd_delivered"}.get(status or "")
    return rt(lang, key) if key else (status or "-")


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
                # The commitments, by title: what the change mail reports on (the
                # retired squad objectives used to stand here, labelled "OTD").
                "otds": {o["title"]: o.get("status") for o in d.get("otds", [])},
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
            # A signature stored before this change has no "otds": nothing to compare.
            prev_otds = p.get("otds")
            for title, stt in (c.get("otds") or {}).items() if prev_otds is not None else ():
                if title not in prev_otds:
                    items.append(rt(lang, "chg_obj_new", title=title))
                elif prev_otds[title] != stt:
                    items.append(rt(lang, "chg_obj_status", title=title,
                                    frm=_otd_lbl(prev_otds[title], lang), to=_otd_lbl(stt, lang)))
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
    return {"first": False, "count": count, "summary": ", ".join(parts), "by_squad": by_squad}


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
        return _render_squad_page(data, standalone, e, lang, changes)
    s = data["summary"]
    gen = data["generated_at"]
    gen_str = fmt_datetime(gen, lang) if isinstance(gen, datetime) else str(gen)
    gen_str += version_suffix(data, lang)

    parts: list[str] = []
    doc_title = rt(lang, "dashboard_doc" if data.get("doc") == "dashboard" else "report")
    parts.append(f'<div class="hdr"><h1>{e(data["app_name"])} | {e(doc_title)}</h1>')
    parts.append(f'<div class="sub">{e(data["scope_name"])}, {e(rt(lang, "year"))} {data["year"]}, '
                 f'{e(rt(lang, "generated"))} {e(gen_str)}'
                 + ("" if data.get("doc") == "dashboard" or data.get("as_of")
                    else f', {e(rt(lang, "window", n=data["since_days"]))}')
                 + '</div></div>')

    # "What's new since your last report" - right under the header.
    if changes is not None:
        parts.append(render_changes_html(changes, lang))

    # Summary cards
    cards = [
        (rt(lang, "k_squads"), s["squads_total"], "#111827"),
        (rt(lang, "k_progress"), f'{s["avg_progress"]}%', RAG_COLOR["green"]),
        (rt(lang, "k_blocked"), s["blocked"], RAG_COLOR["red"] if s["blocked"] else "#111827"),
        (rt(lang, "k_atrisk"), s["at_risk"], RAG_COLOR["amber"] if s["at_risk"] else "#111827"),
        (rt(lang, "k_otd_late"), s["otd_late"], RAG_COLOR["red"] if s["otd_late"] else "#111827"),
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
                         f'<strong>{e(r["name"])}</strong>{_sep(lang)}{e(", ".join(bits))}</li>')
        parts.append('</ul>')

    # Upcoming absences (next 30 days), when the leaves module is enabled.
    if data.get("leaves_upcoming"):
        parts.append(f'<h2>{e(rt(lang, "leaves_upcoming"))}</h2><ul class="attention">')
        for lv in data["leaves_upcoming"][:30]:
            pending = f' <span class="badge">{e(rt(lang, "leaves_pending"))}</span>' if lv["status"] == "pending" else ""
            parts.append(
                f'<li><span class="dot" style="background:{e(lv["type_color"])}"></span>'
                f'<strong>{e(lv["name"])}</strong>{_sep(lang)}{e(leave_type_label(lv["type_label"], lang))}'
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
                     f'<th>{e(rt(lang, "h_progress_long"))}</th>'
                     f'<th>{e(rt(lang, "h_blocked"))}</th>'
                     f'<th>{e(rt(lang, "h_atrisk"))}</th>'
                     '</tr></thead><tbody>')
        for r in blk["squads"]:
            # Who leads it, as on the squad page: leader, then co-leaders and contributors.
            stale_badge = f' <span class="badge">{e(rt(lang, "stale"))}</span>' if r["is_stale"] else ""
            parts.append(
                f'<tr><td><strong>{e(r["name"])}</strong>{stale_badge}</td>'
                f'<td>{e(r["leader"])}</td>'
                f'<td><span class="pill" style="background:{RAG_COLOR[r["status_rag"]]}">'
                f'{e(_status_label(r["status"], lang))}</span></td>'
                f'<td>{_bar(r["annual_pct"], r["status_rag"])}</td>'
                f'<td>{r["blocked"] or ""}</td><td>{r["at_risk"] or ""}</td></tr>'
            )
        parts.append('</tbody></table>')

    # --- The tribe's commitments no squad carries (no squad named, no milestone).
    if data.get("tribe_otds"):
        parts.append(f'<h2>{e(rt(lang, "h_tribe_otds"))}</h2><ul class="attn">')
        for o in data["tribe_otds"]:
            when = fmt_date(o["date"], lang) if o.get("date") else rt(lang, "tl_no_date_short")
            parts.append(f'<li><strong>{e(o["title"])}</strong>{_sep(lang)}{e(when)}, '
                         f'{e(rt(lang, "otd_" + o["status"]))}</li>')
        parts.append('</ul>')

    # --- Full detail per squad: OTD + roadmap/milestones by quarter.
    all_squads = [r for blk in data["tribes"] for r in blk["squads"]]
    if any(r.get("detail") for r in all_squads):
        parts.append(f'<h2 class="detail-h">{e(rt(lang, "detail_title"))}</h2>')
    for r in all_squads:
        if r.get("detail"):
            parts.extend(_squad_detail_parts(r, lang, e))

    body = "\n".join(parts)
    if not standalone:
        return f'<div class="tc-report">{_CSS}{_TIMELINE_CSS}{body}</div>'
    return (
        f'<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8">'
        f'<title>{e(data["app_name"])} | {e(rt(lang, "dashboard_doc" if data.get("doc") == "dashboard" else "report"))}</title>'
        f'{_CSS}{_TIMELINE_CSS}</head>'
        f'<body style="min-width:{_page_min_width(data)}px">'
        f'<div class="tc-report">{body}</div></body></html>'
    )


def render_roadmap_html(data: dict, *, standalone: bool = True) -> str:
    """Roadmap matrix web page: quarters in columns, squads (themes) in rows,
    milestone titles in the cells, colour-coded by status."""
    e = html.escape
    lang = data.get("lang", "fr")
    year = data["year"]
    gen = data["generated_at"]
    gen_str = fmt_datetime(gen, lang) if isinstance(gen, datetime) else str(gen)
    gen_str += version_suffix(data, lang)
    squads = [row for blk in data["tribes"] for row in blk["squads"]]

    parts: list[str] = []
    parts.append(f'<div class="hdr"><h1>{e(data["app_name"])} | {e(rt(lang, "roadmap_report"))}</h1>')
    parts.append(f'<div class="sub">{e(data["scope_name"])}, {e(rt(lang, "year"))} {year}, '
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
        f'<title>{e(data["app_name"])} | {e(rt(lang, "roadmap_report"))}</title>'
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


def build_initiative_list(db: Session, scope_tribe: int | None, year: int, lang: str = "fr") -> dict:
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
    scope_name = tribes.get(scope_tribe) if scope_tribe is not None else rt(_lang(lang), "all_tribes")
    return {"year": year, "scope_name": scope_name or "-", "items": items}


def render_initiatives_html(data: dict, *, lang: str = "fr", standalone: bool = True) -> str:
    """Render the flat initiatives list (title / owner / squad / deadline) as HTML."""
    e = html.escape
    lang = _lang(lang)
    T = _INIT_T[lang]
    parts = [f'<div class="hdr"><h1>{e(T["title"])} | {e(data["scope_name"])}</h1>',
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
                         f'<td>{e(fmt_date(it["deadline"], lang) if it["deadline"] else "-")}</td></tr>')
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


def _squad_leader_emails(squad: Squad) -> list[str]:
    """The squad's named leader and co-leaders, active, with an email."""
    people = ([squad.leader] if squad.leader else []) + list(squad.co_leaders)
    return list(dict.fromkeys(u.email.strip() for u in people
                              if u is not None and (u.email or "").strip() and u.status == "active"))


def _file_slug(name: str) -> str:
    """A file-name-safe version of a squad or tribe name (accents flattened)."""
    import re as _re
    import unicodedata as _ud
    flat = _ud.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return _re.sub(r"[^A-Za-z0-9]+", "_", flat).strip("_") or "squad"


def _file_base(lang: str, scope_label: str, day: str) -> str:
    """Attachment name without extension: what it is, for whom, of when
    ("Rapport_hebdomadaire_Squad_A_2026-09-26")."""
    return f"{_file_slug(rt(lang, 'report'))}_{_file_slug(scope_label)}_{day}"


_PPTX_MIME = ("application", "vnd.openxmlformats-officedocument.presentationml.presentation")


def report_mail(db: Session, smtp: dict, to: str, subject: str, data: dict, *, why: str,
                file_base: str, changes: dict | None = None, pptx: bytes = b"",
                cc: list[str] | None = None, notice_html: str = "", week: int | None = None,
                attach_pptx: bool = True) -> bool:
    """Send one report mail: a summary every mail client renders, the full HTML
    document attached (it needs a browser), the PPTX next to it."""
    from .mail import send_email
    from .mailbody import app_link, footer, render_email
    lang = data.get("lang", "fr")
    rows = [r for blk in data.get("tribes") or [] for r in blk.get("squads") or []]
    path = f"/squads/{rows[0]['squad_id']}" if data.get("squad_scoped") and rows else "/"
    has_pptx = bool(pptx) and attach_pptx
    link = app_link(db, path)
    body = render_email(data, changes=changes, notice_html=notice_html, link=link,
                        footer=footer(lang, why), has_pptx=has_pptx, week=week)
    atts = []
    if not link:
        atts.append((f"{file_base}.html", render_html(data, standalone=True, changes=changes).encode("utf-8"),
                     "text", "html"))
    if has_pptx:
        atts.append((f"{file_base}.pptx", pptx, *_PPTX_MIME))
    return send_email(smtp, to, subject, body, attachment=atts, html=True, cc=cc, lang=lang)


def local_now(now: datetime) -> datetime:
    """The scheduler's clock: Paris time, the one the settings screens show.
    (Comparing the chosen hour with UTC sent "8 h" at 10 h in summer.)"""
    from .reportcommon import _paris
    return _paris(now if now.tzinfo else now.replace(tzinfo=timezone.utc))


def send_squad_docs_to_leaders(db: Session, squads: list, now: datetime | None = None,
                               since: int = 7) -> dict:
    """Send each squad's own document (and nothing else) to its leaders, now.

    Behind the "send to the squad leaders" button: one mail per squad, To its
    leader and co-leaders. Returns {"sent": n, "skipped": [squads without a leader
    email], "failed": [squads whose mail the server refused], "smtp": bool}.
    Touches no baseline: it is not a scheduled send.
    """
    from .smtpconfig import get_smtp
    now = now or utcnow()
    smtp = get_smtp(db)
    if not smtp.get("enabled"):
        return {"sent": 0, "skipped": [], "failed": [], "smtp": False}
    pptxtpl.use(pptxtpl.get(db))
    year = reference_year(db)
    lang = _lang(get_general(db).get("default_lang"))
    local = local_now(now)
    week = local.isocalendar()[1]
    sent, skipped, failed = 0, [], []
    for squad in squads:
        to = _squad_leader_emails(squad)
        if not to:
            skipped.append(squad.name)
            continue
        data = build_report_data(db, None, year, since, now, squad_id=squad.id, lang=lang)
        try:
            pptx_bytes = render_pptx(data)
        except Exception:
            pptx_bytes = b""
        if report_mail(db, smtp, ", ".join(to), rt(lang, "subject", scope=squad.name, w=week), data,
                       why="leaders", file_base=_file_base(lang, squad.name, local.date().isoformat()),
                       pptx=pptx_bytes, week=week):
            sent += 1
        else:
            failed.append(squad.name)
    return {"sent": sent, "skipped": skipped, "failed": failed, "smtp": True}


def send_due_weekly_reports(db: Session, now: datetime | None = None) -> int:
    """Send every scheduled report that is due: the admin's (all tribes), then each
    tribe's own (set by its tribe leader). Returns the number of emails sent.

    Each schedule is idempotent within a day (its own last_sent_day). Safe to call
    repeatedly from the scheduler.
    """
    from .reportconfig import get_report, tribe_schedules
    from .smtpconfig import get_smtp
    from .modulesconfig import get_modules, is_active

    now = now or utcnow()
    if not is_active(get_modules(db), "review", "weekly_report"):
        return 0
    smtp = get_smtp(db)
    if not smtp.get("enabled"):
        return 0
    pptxtpl.use(pptxtpl.get(db))
    sent = _send_schedule(db, smtp, get_report(db), None, now)
    for tid in tribe_schedules(db):
        if db.get(Tribe, tid) is not None:
            sent += _send_schedule(db, smtp, get_report(db, tid), tid, now)
    return sent


def _send_schedule(db: Session, smtp: dict, cfg: dict, tribe_id: int | None, now: datetime) -> int:
    """One schedule (the admin's when tribe_id is None, else a tribe's).

    What goes out, each part switched on in the config:
      * global_doc: the fixed recipients get the whole document of the scope;
      * per_squad: the fixed recipients get one mail per squad, that squad only;
      * squad_leaders: each squad's leaders get their own squad's document;
      * tribe_leader_digest (admin schedule only): each tribe leader gets their
        tribe's document, the tribe's squad leaders in CC.
    ``squad_ids`` narrows the squads of the per-squad parts (empty = all).

    The day, the weekday and the hour are Paris time. A document reaches an
    address once, whatever the parts that include it. When the mail server
    refuses every mail, nothing is marked as done: the next tick tries again, and
    the "what's new" baseline does not move past what nobody received.
    """
    from .reportconfig import set_report
    from .models import User

    if not cfg.get("enabled"):
        return 0
    local = local_now(now)
    if local.weekday() not in cfg["weekdays"] or local.hour < cfg["hour"]:
        return 0
    today = local.date().isoformat()
    if cfg.get("last_sent_day") == today:
        return 0

    since = cfg.get("since_days", 7)
    year = reference_year(db)
    lang = _lang(get_general(db).get("default_lang"))
    only_changes = bool(cfg.get("only_when_changes"))
    week = local.isocalendar()[1]
    # Baselines are per schedule: the admin's and a tribe's must not consume each
    # other's "what's new".
    prefix = "" if tribe_id is None else f"t{tribe_id}:"
    sent = 0
    attempted = 0
    prepared: dict[str, dict] = {}
    delivered: set[tuple[str, str]] = set()
    baselines: list[tuple[str, dict]] = []

    def prepare(scope, scope_key: str, scope_label: str, squad_id=None) -> dict:
        """Build a document once: data, changelog (vs baseline), PPTX and subject."""
        if scope_key not in prepared:
            data = build_report_data(db, scope, year, since, now, lang=lang, squad_id=squad_id)
            sig = report_signature(data)
            changes = diff_report(get_baseline(db, scope_key), sig, lang)
            try:
                pptx_bytes = render_pptx(data)
            except Exception:
                pptx_bytes = b""
            subject = subject_prefix(changes, lang) + rt(lang, "subject", scope=scope_label, w=week)
            prepared[scope_key] = {"data": data, "sig": sig, "changes": changes, "pptx": pptx_bytes,
                                   "subject": subject, "file": _file_base(lang, scope_label, today)}
        return prepared[scope_key]

    def deliver(p: dict, key: str, addrs: list[str], why: str, cc: list[str] | None = None) -> None:
        """One mail To ``addrs`` (skipping those who already got this document)."""
        nonlocal sent, attempted
        todo = [a for a in addrs if (key, a.lower()) not in delivered]
        if not todo:
            return
        cc = [c for c in (cc or []) if (key, c.lower()) not in delivered]
        attempted += 1
        if report_mail(db, smtp, ", ".join(todo), p["subject"], p["data"], why=why, file_base=p["file"],
                       changes=p["changes"], pptx=p["pptx"], cc=cc, week=week,
                       attach_pptx=cfg.get("attach_pptx", True)):
            sent += 1
            delivered.update((key, a.lower()) for a in todo + cc)

    def worth_sending(p: dict) -> bool:
        c = p["changes"]
        # Always send the very first report (establishes the baseline); otherwise
        # honour the "only when changes" policy.
        return c.get("first") or not (only_changes and c["count"] == 0)

    recipients = list(dict.fromkeys(a for a in (cfg.get("recipients") or []) if a))

    # 1. The whole document of the scope, to the fixed recipients.
    if recipients and cfg.get("global_doc", True):
        if tribe_id is None:
            key = "global"
            p = prepare(None, key, rt(lang, "all_tribes"))
        else:
            tribe = db.get(Tribe, tribe_id)
            key = f"{prefix}tribe"
            p = prepare(tribe_id, key, tribe.name if tribe else "")
        if worth_sending(p):
            for addr in recipients:
                deliver(p, key, [addr], "schedule")
        baselines.append((key, p["sig"]))

    # 2. and 3. One document per squad: to the fixed recipients (per_squad) and/or
    # to the squad's own leaders (squad_leaders).
    if (recipients and cfg.get("per_squad")) or cfg.get("squad_leaders"):
        q = select(Squad).order_by(Squad.display_order, Squad.id)
        if tribe_id is not None:
            q = q.where(Squad.tribe_id == tribe_id)
        if cfg.get("squad_ids"):
            q = q.where(Squad.id.in_(cfg["squad_ids"]))
        for squad in db.scalars(q).all():
            key = f"{prefix}squad:{squad.id}"
            p = prepare(None, key, squad.name, squad_id=squad.id)
            if worth_sending(p):
                if recipients and cfg.get("per_squad"):
                    for addr in recipients:
                        deliver(p, key, [addr], "schedule")
                if cfg.get("squad_leaders"):
                    deliver(p, key, _squad_leader_emails(squad), "leaders")
            baselines.append((key, p["sig"]))

    # 4. Admin schedule only: each tribe leader receives their OWN tribe-scoped
    # report, with that tribe's squad leaders (co-leaders included) in CC.
    if tribe_id is None and cfg.get("tribe_leader_digest"):
        for tribe in db.scalars(select(Tribe).order_by(Tribe.display_order, Tribe.id)).all():
            leaders = [u for u in db.scalars(
                select(User).where(User.role == "tribe_leader", User.tribe_id == tribe.id)).all()
                if (u.email or "").strip() and u.status == "active"]
            if not leaders:
                continue
            to = list(dict.fromkeys(l.email.strip() for l in leaders))
            leader_emails = {a.lower() for a in to}
            cc, seen_cc = [], set()
            for sq in db.scalars(select(Squad).where(Squad.tribe_id == tribe.id)).all():
                for e in _squad_leader_emails(sq):
                    el = e.lower()
                    if el not in leader_emails and el not in seen_cc:
                        seen_cc.add(el)
                        cc.append(e)
            scope_key = f"tribe:{tribe.id}"
            p = prepare(tribe.id, scope_key, tribe.name)
            if worth_sending(p):
                deliver(p, scope_key, to, "schedule", cc=cc)
            baselines.append((scope_key, p["sig"]))

    if attempted and not sent:
        # The mail server refused everything (down, wrong credentials): keep the
        # day open and the baselines where they were, the next tick retries.
        import logging
        logging.getLogger("trt.report").warning(
            "scheduled report%s: every mail failed, retrying at the next tick",
            "" if tribe_id is None else f" of tribe {tribe_id}")
        return 0
    for key, sig in baselines:
        set_baseline(db, key, sig)
    cfg["last_sent_day"] = today
    set_report(db, cfg, tribe_id)
    db.commit()
    return sent


def send_personal_subscriptions(db: Session, now: datetime | None = None) -> int:
    """Send the report to each subscription (global or per-squad) that is due.

    A global subscription (squad_id NULL) follows the user's visibility (admin →
    all tribes, others → their tribe); a per-squad subscription targets that squad.
    Returns the number of emails sent. Safe to call repeatedly from the scheduler.
    Weekday and hour are Paris time; a failed mail is retried at the next tick.
    """
    from .smtpconfig import get_smtp
    from .models import ReportSubscription, Squad, Tribe, User
    from .modulesconfig import get_modules, is_active

    now = now or utcnow()
    if not is_active(get_modules(db), "review", "weekly_report"):
        return 0
    smtp = get_smtp(db)
    if not smtp.get("enabled"):
        return 0

    from .reportconfig import get_report
    year = reference_year(db)
    lang = _lang(get_general(db).get("default_lang"))
    only_changes = bool(get_report(db).get("only_when_changes"))
    local = local_now(now)
    week = local.isocalendar()[1]
    # Cache report data + PPTX per (scope_tribe, squad_id, since); the "what's
    # new" part is per-recipient baseline.
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
        # A revoked account stops receiving the report, and a squad subscription
        # follows the account's current reach (it may have changed tribe since).
        if user.status != "active":
            continue
        if sub.squad_id is not None:
            from .subscriptions import user_can_see_squad
            if not user_can_see_squad(db, user, sub.squad_id):
                continue
        last = _aware(sub.last_sent_at)
        if wd:
            # Weekday schedule: fire on a chosen day, past the hour, once per day.
            if local.weekday() not in wd or local.hour < sub.hour:
                continue
            if last is not None and local_now(last).date() == local.date():
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
            from .deps import scoped_tribe_id
            scope_tribe = scoped_tribe_id(user)
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

        if sub.squad_id is not None:
            sq = db.get(Squad, sub.squad_id)
            scope_lbl = sq.name if sq else rt(lang, "h_squad")
        elif user.role == "admin":
            scope_lbl = rt(lang, "all_tribes")
        else:
            tr = db.get(Tribe, user.tribe_id) if user.tribe_id else None
            scope_lbl = tr.name if tr else rt(lang, "all_tribes")
        subject = subject_prefix(changes, lang) + rt(lang, "subject_personal", scope=scope_lbl, w=week)
        if report_mail(db, smtp, user.email, subject, data, why="subscription",
                       file_base=_file_base(lang, scope_lbl, local.date().isoformat()),
                       changes=changes, pptx=pptx_bytes, week=week):
            _mark_done()
            sent += 1
    db.commit()  # persist baselines / last_sent even when only skips occurred
    return sent


def build_dependencies_data(db: Session, scope_tribe: int | None, year: int | None = None,
                            squad_ids: list[int] | None = None, viewer=None,
                            lang: str | None = None, mode: str = "all") -> dict:
    """Collect the jalons that carry a dependency, grouped by the entity they wait
    on. mode='all' (what the export menu asks for) keeps every dependency;
    mode='cross_tribe' keeps only those pointing outside the source squad's tribe.

    Le document partait en ``cross_tribe``, et une installation d'une seule tribu
    n'a par construction aucune dependance inter-tribu: l'export s'ouvrait donc sur
    « Aucune dependance » alors que les jalons en portaient. Un document qui dit
    « aucune » est pire qu'un document vide, il repond a la question.
    """
    from .models import RoadmapItem  # noqa: F401  (ensures mapper import)
    now = utcnow()
    cfg = get_general(db)
    year = year or reference_year(db)
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
    # Un document filtre doit dire qu'il l'est, sinon il se lit comme complet et
    # son « aucune dependance » repond a une question qu'on n'a pas posee.
    filt = f', {T["cross_only"]}' if data.get("mode") == "cross_tribe" else ""
    parts = [f'<div class="hdr"><h1>{e(T["title"])} | {e(data["scope_name"])}</h1>',
             f'<div class="sub">{e(rt(lang, "year"))} {data["year"]}, '
             f'{e(T["total"].format(n=data["total"]))}{e(filt)}</div></div>']
    if data["total"] == 0:
        parts.append(f'<div class="muted small">{e(T["none"])}</div>')
    for g in data["groups"]:
        tlbl = {"tribe": T["t_tribe"], "squad": T["t_squad"], "text": T["t_text"]}.get(g["target_type"], "")
        if g["target_type"] == "squad" and g.get("target_tribe"):
            tlbl = f'{tlbl}, {e(g["target_tribe"])}'
        parts.append(f'<h2>▶ {e(g["target_label"])} '
                     f'<span class="muted">({tlbl}, {e(T["gcount"].format(n=len(g["items"])))})</span></h2>')
        parts.append('<table><thead><tr>'
                     f'<th>{e(T["c_jalon"])}</th><th>{e(T["c_squad"])}</th><th>{e(T["c_trim"])}</th>'
                     f'<th>{e(T["c_owner"])}</th><th>{e(T["c_status"])}</th></tr></thead><tbody>')
        for it in g["items"]:
            parts.append(
                f'<tr><td><strong>{e(it["jalon"])}</strong></td>'
                f'<td>{e(it["squad_name"])} ({e(it["tribe_name"])})</td>'
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
