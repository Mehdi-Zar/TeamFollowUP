"""Change-notification emails: when a squad's reporting changes, email the
configured recipients **that squad's export only** (HTML body + optional PPTX).

The heavy work (render + SMTP) runs in a background thread with its own DB
session, so the triggering request is never blocked. Honours the granular config
in changeconfig (which events, recipients, debounce, scope, year filter).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

log = logging.getLogger("trt.changenotify")

# Human label for each modification kind, used in the (clear) email subject.
_EVENT_LABEL = {
    "fr": {"progress": "avancement", "roadmap": "roadmap", "objectives": "OTD",
           "budget": "budget", "key_message": "messages clés"},
    "en": {"progress": "progress", "roadmap": "roadmap", "objectives": "OTD",
           "budget": "budget", "key_message": "key messages"},
}


def notify_change(squad_id: int, event: str, actor_name: str | None = None,
                  year: int | None = None) -> None:
    """Fire-and-forget: schedule a change-notification email for a squad."""
    threading.Thread(target=_run, args=(squad_id, event, actor_name, year),
                     daemon=True).start()


def _run(squad_id: int, event: str, actor_name: str | None, year: int | None) -> None:
    from .database import SessionLocal
    db = SessionLocal()
    try:
        from . import status as st
        from .changeconfig import get_change_notify, get_state, set_state
        from .generalconfig import get_general
        from .mail import send_email
        from .models import Squad
        from .modulesconfig import get_modules, is_active
        from .report import build_report_data, render_html, render_pptx
        from .smtpconfig import get_smtp

        cfg = get_change_notify(db)
        if not cfg.get("enabled") or event not in cfg.get("events", []):
            return
        if not is_active(get_modules(db), "review", "weekly_report"):
            return
        recipients = cfg.get("recipients") or []
        if not recipients:
            return
        smtp = get_smtp(db)
        if not smtp.get("enabled"):
            return

        squad = db.get(Squad, squad_id)
        if squad is None:
            return
        if cfg.get("scope_squads") and squad.id not in cfg["scope_squads"]:
            return

        now = datetime.now(timezone.utc)
        cur_year = st.current_year_quarter(now)[0]
        if cfg.get("current_year_only") and year is not None and year != cur_year:
            return

        # Per-squad debounce.
        interval = int(cfg.get("min_interval_minutes") or 0)
        state = get_state(db)
        if interval:
            last = state.get(str(squad.id))
            if last:
                try:
                    prev = datetime.fromisoformat(last)
                    if prev.tzinfo is None:
                        prev = prev.replace(tzinfo=timezone.utc)
                    if (now - prev) < timedelta(minutes=interval):
                        return
                except ValueError:
                    pass

        lang = "en" if get_general(db).get("default_lang") == "en" else "fr"
        report_year = year or cur_year
        # viewer=None → budget figures are NOT included (avoid leaking to a fixed list).
        data = build_report_data(db, None, report_year, squad_id=squad.id, lang=lang, viewer=None)
        html_body = render_html(data, standalone=True)
        attachment = None
        if cfg.get("attach_pptx"):
            try:
                pptx = render_pptx(data)
                if pptx:
                    attachment = (f"{_slug(squad.name)}_{report_year}.pptx", pptx,
                                  "application",
                                  "vnd.openxmlformats-officedocument.presentationml.presentation")
            except Exception:
                attachment = None

        label = _EVENT_LABEL.get(lang, _EVENT_LABEL["fr"]).get(event, event)
        tribe = squad.tribe.name if squad.tribe else None
        who = f" · {actor_name}" if actor_name else ""
        if lang == "en":
            subject = f"[Reporting] {squad.name}" + (f" ({tribe})" if tribe else "") + \
                      f" — {label} updated{who}"
        else:
            subject = f"[Reporting] {squad.name}" + (f" ({tribe})" if tribe else "") + \
                      f" — {label} mis à jour{who}"

        sent = 0
        seen = set()
        for addr in recipients:
            key = addr.lower()
            if key in seen:
                continue
            seen.add(key)
            if send_email(smtp, addr, subject, html_body, attachment=attachment, html=True):
                sent += 1

        if sent:
            state[str(squad.id)] = now.isoformat()
            set_state(db, state)
            db.commit()
            log.info("change-notify sent for squad %s (%s) to %s recipient(s)",
                     squad.id, event, sent)
    except Exception as exc:  # never let a notification break anything
        log.warning("change-notify failed for squad %s (%s): %s", squad_id, event, exc)
    finally:
        db.close()


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).strip("_") or "squad"
