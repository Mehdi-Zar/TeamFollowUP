"""Change-notification emails: when a squad's reporting changes, email the
configured recipients **that squad's export only** (a summary in the mail, the
full HTML document and optionally the PPTX attached).

The heavy work (render + SMTP) runs in a background thread with its own DB
session, so the triggering request is never blocked. Honours the granular config
in changeconfig (which events, recipients, grouping window, scope, year filter).

Grouping: with ``min_interval_minutes`` at 0 each change sends at once. Above 0,
changes are gathered per squad and ONE mail leaves once the squad has been quiet
for that long, listing every kind of change and every author (the first change
used to go out alone and the next ones were dropped).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

log = logging.getLogger("trt.changenotify")

# Read-modify-write of the pending batches: one at a time in this process.
_LOCK = threading.Lock()

# Human label for each modification kind, used in the (clear) email subject.
_EVENT_LABEL = {
    "fr": {"submission": "soumission", "progress": "avancement", "roadmap": "roadmap",
           "budget": "budget", "key_message": "messages clés", "otd": "engagements",
           "kpi": "KPI", "committee": "comités", "team": "équipe", "mood": "moral"},
    "en": {"submission": "submission", "progress": "progress", "roadmap": "roadmap",
           "budget": "budget", "key_message": "key messages", "otd": "commitments",
           "kpi": "KPIs", "committee": "committees", "team": "team", "mood": "mood"},
}


def _actor(actor) -> tuple[str | None, str | None]:
    """(name, email) of whoever made the change: a User, or just a name."""
    if actor is None or isinstance(actor, str):
        return actor, None
    return getattr(actor, "display_name", None), getattr(actor, "email", None)


def _recipients(db, cfg: dict, squad, exclude: set[str] | None = None) -> list[str]:
    """The fixed list, plus the tribe leaders and the squad's own leaders when the
    admin ticked them. De-duplicated, case-insensitively, in that order, and
    without the author(s) of the change: nobody needs a mail about what they
    just did."""
    from sqlalchemy import select
    from .models import User
    out = list(cfg.get("recipients") or [])
    if cfg.get("tribe_leaders") and squad.tribe_id is not None:
        out += [u.email for u in db.scalars(select(User).where(
            User.role == "tribe_leader", User.tribe_id == squad.tribe_id,
            User.status == "active")).all() if u.email]
    if cfg.get("squad_leaders"):
        leaders = ([squad.leader] if squad.leader else []) + list(squad.co_leaders)
        out += [u.email for u in leaders if u.email and u.status == "active"]
    skip = {a.lower() for a in (exclude or set()) if a}
    seen, uniq = set(), []
    for a in out:
        k = a.lower()
        if k not in seen and k not in skip:
            seen.add(k)
            uniq.append(a)
    return uniq


def _join(items: list[str], lang: str) -> str:
    """ "a, b et c" / "a, b and c"."""
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + (" and " if lang == "en" else " et ") + items[-1]


def _article(what: str) -> str:
    """ "l'avancement", "la roadmap", "les KPI": the object of "a mis à jour"."""
    return f"<strong>{what}</strong>" if "," in what or " et " in what else {
        "avancement": "l'<strong>avancement</strong>", "roadmap": "la <strong>roadmap</strong>",
        "budget": "le <strong>budget</strong>", "messages clés": "les <strong>messages clés</strong>",
        "engagements": "les <strong>engagements</strong>", "KPI": "les <strong>KPI</strong>",
        "comités": "les <strong>comités</strong>", "équipe": "l'<strong>équipe</strong>",
        "moral": "le <strong>moral</strong>"}.get(what, f"<strong>{what}</strong>")


def _notice(lang: str, actors: list[str], labels: list[str], squad: str, when: datetime,
            details: list[str] | None = None, submitted: bool = False,
            submitters: list[str] | None = None) -> str:
    """The sentence the mail opens with: who changed what, and when (Paris
    time), then the changes themselves when they can be told."""
    import html as _h
    from .mailbody import notice_box
    from .reportcommon import fmt_datetime
    stamp = _h.escape(fmt_datetime(when, lang))
    who = _h.escape(_join(actors, lang) or ("Someone" if lang == "en" else "Quelqu'un"))
    what, sq = _h.escape(_join(labels, lang)), _h.escape(squad)
    if submitted:
        subs = submitters or actors
        by = _h.escape(_join(subs, lang) or ("Someone" if lang == "en" else "Quelqu'un"))
        text = (f"<strong>{by}</strong> submitted the report for squad <strong>{sq}</strong> "
                f"on {stamp}." if lang == "en" else
                f"<strong>{by}</strong> {'ont' if len(subs) > 1 else 'a'} soumis le reporting de la squad "
                f"<strong>{sq}</strong> le {stamp}.")
        if what:
            text += (f" Also updated: <strong>{what}</strong>." if lang == "en" else
                     f" Également mis à jour : <strong>{what}</strong>.")
    else:
        text = (f"<strong>{who}</strong> updated the <strong>{what}</strong> of squad "
                f"<strong>{sq}</strong> on {stamp}." if lang == "en" else
                f"<strong>{who}</strong> {'ont' if len(actors) > 1 else 'a'} mis à jour {_article(what)} de la squad "
                f"<strong>{sq}</strong> le {stamp}.")
    if details:
        text += '<ul style="margin:8px 0 0;padding-left:18px">' + "".join(
            f"<li>{_h.escape(d)}</li>" for d in details[:12]) + "</ul>"
    return notice_box(text)


def notify_change(squad_id: int, event: str, actor=None, year: int | None = None) -> None:
    """Fire-and-forget: schedule a change-notification email for a squad.
    ``actor`` is the User who made the change (or just a name)."""
    name, email = _actor(actor)
    threading.Thread(target=_run, args=(squad_id, event, name, year, email),
                     daemon=True).start()


def _run(squad_id: int, event: str, actor_name: str | None, year: int | None,
         actor_email: str | None = None) -> None:
    """Background worker: check the config, then send now or add to the squad's
    pending batch. All exceptions are swallowed and logged so a notification can
    never break the triggering request."""
    from .database import SessionLocal
    db = SessionLocal()
    try:
        from .changeconfig import get_change_notify, get_state, set_state
        from .models import Squad
        from .modulesconfig import get_modules, is_active
        from .smtpconfig import get_smtp

        cfg = get_change_notify(db)
        if not cfg.get("enabled") or event not in cfg.get("events", []):
            return
        if not is_active(get_modules(db), "review", "weekly_report"):
            return
        if not get_smtp(db).get("enabled"):
            return
        squad = db.get(Squad, squad_id)
        if squad is None:
            return
        if cfg.get("scope_squads") and squad.id not in cfg["scope_squads"]:
            return
        from .generalconfig import reference_year
        cur_year = reference_year(db)  # the instance's year, as every screen
        if cfg.get("current_year_only") and year is not None and year != cur_year:
            return

        now = datetime.now(timezone.utc)
        interval = int(cfg.get("min_interval_minutes") or 0)
        batch = {"events": [event], "actors": [actor_name] if actor_name else [],
                 "submitters": [actor_name] if actor_name and event == "submission" else [],
                 "emails": [actor_email] if actor_email else [], "year": year or cur_year,
                 "last": now.isoformat()}
        if not interval:
            if _send(db, squad, batch, now) is False:
                # Refused by the mail server: queued, the hourly tick retries.
                with _LOCK:
                    state = get_state(db)
                    state.setdefault("pending", {})[str(squad.id)] = dict(batch, attempts=1)
                    set_state(db, state)
                    db.commit()
            return
        # Gather: add to the squad's batch; a timer sends it once quiet.
        with _LOCK:
            state = get_state(db)
            pending = state.setdefault("pending", {})
            cur = pending.get(str(squad.id))
            if cur:
                for k in ("events", "actors", "emails", "submitters"):
                    cur[k] = list(dict.fromkeys((cur.get(k) or []) + batch[k]))
                cur["last"], cur["year"] = batch["last"], batch["year"]
            else:
                pending[str(squad.id)] = batch
            set_state(db, state)
            db.commit()
        t = threading.Timer(interval * 60 + 5, flush_pending)
        t.daemon = True
        t.start()
    except Exception as exc:  # never let a notification break anything
        log.warning("change-notify failed for squad %s (%s): %s", squad_id, event, exc)
    finally:
        db.close()


def flush_pending(now: datetime | None = None) -> int:
    """Send every pending batch whose squad has been quiet for the configured
    window. Called by the batch timers and, as a safety net after a restart, by
    the hourly scheduler. Returns the number of batches sent."""
    from .database import SessionLocal
    db = SessionLocal()
    done = 0
    try:
        from .changeconfig import get_change_notify, get_state, set_state
        from .models import Squad
        now = now or datetime.now(timezone.utc)
        interval = int(get_change_notify(db).get("min_interval_minutes") or 0)
        with _LOCK:
            state = get_state(db)
            pending = state.get("pending") or {}
            due = {}
            for sid, b in list(pending.items()):
                try:
                    last = datetime.fromisoformat(b.get("last"))
                except (TypeError, ValueError):
                    last = now
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if now - last >= timedelta(minutes=interval):
                    due[sid] = pending.pop(sid)
            if due:
                set_state(db, state)
                db.commit()
        failed = {}
        for sid, b in due.items():
            squad = db.get(Squad, int(sid))
            if squad is None:
                continue
            res = _send(db, squad, b, now)
            if res:
                done += 1
            elif res is False and int(b.get("attempts") or 0) < 48:
                # The mail server refused: the batch goes back in the queue, the
                # hourly scheduler tries again (for two days at most).
                failed[sid] = dict(b, attempts=int(b.get("attempts") or 0) + 1)
        if failed:
            with _LOCK:
                state = get_state(db)
                pending = state.setdefault("pending", {})
                for sid, b in failed.items():
                    cur = pending.get(sid)
                    if cur:  # new changes arrived meanwhile: merge them in
                        for k in ("events", "actors", "emails", "submitters"):
                            cur[k] = list(dict.fromkeys((b.get(k) or []) + (cur.get(k) or [])))
                    else:
                        pending[sid] = b
                set_state(db, state)
                db.commit()
    except Exception as exc:
        log.warning("change-notify flush failed: %s", exc)
    finally:
        db.close()
    return done


def _send(db, squad, batch: dict, now: datetime) -> bool | None:
    """Render the squad's export and mail it to the recipients. Returns True when
    at least one mail left, False when every mail was refused, None when there
    was nobody to write to."""
    from .changeconfig import get_change_notify
    from .mailbody import instance_lang
    from . import pptxtpl
    from .report import (_file_base, build_report_data, diff_report, get_baseline, render_pptx,
                         report_mail, report_signature, set_baseline)
    from .smtpconfig import get_smtp

    cfg = get_change_notify(db)
    recipients = _recipients(db, cfg, squad, exclude=set(batch.get("emails") or []))
    if not recipients:
        return None
    lang = instance_lang(db)
    # viewer=None → budget figures are NOT included (avoid leaking to a fixed list).
    data = build_report_data(db, None, batch.get("year"), squad_id=squad.id, lang=lang, viewer=None)
    # What changed since the previous notice of this squad, when it can be told.
    key = f"chg:{squad.id}"
    sig = report_signature(data)
    diff = diff_report(get_baseline(db, key), sig, lang)
    details = [i for g in diff.get("by_squad") or [] for i in g.get("items") or []]
    names = _EVENT_LABEL.get(lang, _EVENT_LABEL["fr"])
    events = batch.get("events") or []
    submitted = "submission" in events
    labels = [names.get(e, e) for e in events if e != "submission"]
    actors = batch.get("actors") or []
    try:
        when = datetime.fromisoformat(batch.get("last")) if batch.get("last") else now
    except (TypeError, ValueError):
        when = now
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    submitters = batch.get("submitters") or []
    notice = _notice(lang, actors, labels, squad.name, when, details, submitted=submitted,
                     submitters=submitters)
    pptx = b""
    if cfg.get("attach_pptx"):
        try:
            pptxtpl.use(pptxtpl.get(db))
            pptx = render_pptx(data) or b""
        except Exception:
            pptx = b""
    tribe = squad.tribe.name if squad.tribe else None
    scope = squad.name + (f" ({tribe})" if tribe else "")
    what = _join(labels, lang)
    if lang == "en":
        who = f" by {_join(actors, lang)}" if actors else ""
        by = f" by {_join(submitters, lang)}" if submitters else who
        subject = (f"[Reporting] {scope}: report submitted{by}" if submitted
                   else f"[Reporting] {scope}: {what} updated{who}")
    else:
        who = f" par {_join(actors, lang)}" if actors else ""
        by = f" par {_join(submitters, lang)}" if submitters else who
        subject = (f"[Reporting] {scope} : reporting soumis{by}" if submitted
                   else f"[Reporting] {scope} : mise à jour ({what}){who}")
    from .report import local_now
    file_base = _file_base(lang, squad.name, local_now(now).date().isoformat())
    smtp = get_smtp(db)
    sent = 0
    for addr in recipients:
        if report_mail(db, smtp, addr, subject, data, why="change", file_base=file_base,
                       pptx=pptx, notice_html=notice):
            sent += 1
    if sent:
        set_baseline(db, key, sig)
        db.commit()
        log.info("change-notify sent for squad %s (%s) to %s recipient(s)",
                 squad.id, ",".join(batch.get("events") or []), sent)
    return bool(sent)
