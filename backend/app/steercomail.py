"""Steerco mails (ADR 0018): the monthly reminder to the Steerco leaders, and the
pack sent by hand to the committee.

Settings are per tribe, in app_settings['steerco_mail:tribe:<id>']::

    {"reminder_enabled": true, "reminder_day": 5, "recipients": ["a@x"],
     "last_reminder": "2026-10"}

* **Reminder**: on ``reminder_day`` of a month (or the first tick after it), the
  tribe's active Steerco leaders get the list of the pack's platforms whose
  previous month is not validated yet. Nothing is sent when every platform is
  validated. ``last_reminder`` holds the month already reminded, so the hourly
  scheduler sends it once.
* **Pack**: a Steerco leader sends the month's pack (summary in the body, PPTX
  attached) to the tribe's recipient list, only once every platform of the pack is
  validated: what leaves for the committee is what was validated.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from html import escape

from sqlalchemy.orm import Session

from .models import AppSetting, Platform, SteercoEntry, Tribe

log = logging.getLogger("trt.steerco")

PREFIX = "steerco_mail:tribe:"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _defaults() -> dict:
    return {"reminder_enabled": True, "reminder_day": 5, "recipients": [], "last_reminder": None}


def get_config(db: Session, tribe_id: int) -> dict:
    row = db.get(AppSetting, f"{PREFIX}{int(tribe_id)}")
    cfg = _defaults()
    if row:
        try:
            raw = json.loads(row.value)
            if isinstance(raw, dict):
                cfg.update({k: raw[k] for k in cfg if k in raw})
        except (ValueError, TypeError):
            pass
    return normalize(cfg)


def normalize(raw: dict) -> dict:
    try:
        day = int(raw.get("reminder_day") or 5)
    except (TypeError, ValueError):
        day = 5
    recipients = []
    for r in raw.get("recipients") or []:
        r = str(r or "").strip()
        if r and _EMAIL.match(r) and r.lower() not in {x.lower() for x in recipients}:
            recipients.append(r)
    last = raw.get("last_reminder")
    return {"reminder_enabled": bool(raw.get("reminder_enabled", True)),
            "reminder_day": min(max(day, 1), 28),
            "recipients": recipients[:100],
            "last_reminder": str(last) if last else None}


def set_config(db: Session, tribe_id: int, patch: dict) -> dict:
    """Store the editable part (reminder, day, recipients); no commit."""
    cur = get_config(db, tribe_id)
    for k in ("reminder_enabled", "reminder_day", "recipients"):
        if k in (patch or {}):
            cur[k] = patch[k]
    cfg = normalize(cur)
    bad = [r for r in (patch or {}).get("recipients") or [] if str(r or "").strip()
           and not _EMAIL.match(str(r).strip())]
    if bad:
        raise ValueError(f"Adresse invalide : {bad[0]}")
    _store(db, tribe_id, cfg)
    return cfg


def _store(db: Session, tribe_id: int, cfg: dict) -> None:
    key = f"{PREFIX}{int(tribe_id)}"
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=json.dumps(cfg)))
    else:
        row.value = json.dumps(cfg)


def previous_period(today: date) -> str:
    y, m = today.year, today.month - 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def pack_platforms(db: Session, tribe_id: int) -> list[Platform]:
    return (db.query(Platform)
            .filter(Platform.tribe_id == tribe_id, Platform.steerco_enabled.is_(True))
            .order_by(Platform.display_order, Platform.name).all())


def pending(db: Session, tribe_id: int, period: str) -> list[dict]:
    """The pack's platforms whose month is not validated, with how far they got."""
    from . import platforms as plat
    out = []
    for p in pack_platforms(db, tribe_id):
        e = (db.query(SteercoEntry)
             .filter(SteercoEntry.platform_id == p.id, SteercoEntry.period == period).one_or_none())
        if e is not None and e.status == "validated":
            continue
        tpl = plat.normalize_template(p.template)
        out.append({"id": p.id, "name": p.name, "filled": plat.filled_count(tpl, e.data if e else None),
                    "total": plat.item_count(tpl)})
    return out


def _month_label(period: str, lang: str) -> str:
    from .routers.steerco import I18N, _period_long
    return _period_long(period, I18N["fr" if lang == "fr" else "en"])


def _t(lang: str, fr: str, en: str) -> str:
    return fr if lang == "fr" else en


def reminder_mail(db: Session, tribe: Tribe, period: str, rows: list[dict], lang: str,
                  contributor: bool = False) -> tuple[str, str]:
    from .mailbody import app_link, button, footer, layout
    month = _month_label(period, lang)
    title = _t(lang, f"Steerco {month} : {len(rows)} plateforme(s) à valider",
               f"Steerco {month}: {len(rows)} platform(s) to validate")
    lines = []
    for r in rows:
        if r["filled"] == 0:
            state = _t(lang, "à faire", "to do")
        elif r["filled"] < r["total"]:
            state = _t(lang, f"en cours ({r['filled']}/{r['total']})", f"in progress ({r['filled']}/{r['total']})")
        else:
            state = _t(lang, "complet, non validé", "complete, not validated")
        lines.append(f'<tr><td style="padding:6px 8px;border-bottom:1px solid #E3E8EF">{escape(r["name"])}</td>'
                     f'<td style="padding:6px 8px;border-bottom:1px solid #E3E8EF;color:#6B7C90">{escape(state)}</td></tr>')
    intro = _t(lang, f"La présentation Steerco de {month} de la tribe {tribe.name} n'est pas encore validée pour :",
               f"The {month} Steerco presentation of {tribe.name} is not validated yet for:")
    body = (f'<p style="margin:0 0 10px">{escape(intro)}</p>'
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">{"".join(lines)}</table>')
    link = app_link(db, "/steerco")
    if link:
        body += button(link, _t(lang, "Ouvrir la saisie Steerco", "Open the Steerco entry"))
    return title, layout(title, tribe.name, body,
                         footer=footer(lang, "steerco_reminder_contrib" if contributor else "steerco_reminder"))


def send_due_reminders(db: Session, today: date | None = None) -> list[str]:
    """Send the monthly reminder of every tribe for which it is due. Returns the
    names of the tribes reminded."""
    from . import steercoaccess
    from .mail import send_email
    from .mailbody import instance_lang
    from .modulesconfig import get_modules, is_active
    from .smtpconfig import get_smtp

    if not is_active(get_modules(db), "steerco"):
        return []
    today = today or date.today()
    period = previous_period(today)
    smtp = get_smtp(db)
    lang = instance_lang(db)
    done = []
    for tribe in db.query(Tribe).all():
        cfg = get_config(db, tribe.id)
        if not cfg["reminder_enabled"] or today.day < cfg["reminder_day"]:
            continue
        if cfg["last_reminder"] == period or not pack_platforms(db, tribe.id):
            continue
        rows = pending(db, tribe.id, period)
        if rows:
            to = steercoaccess.leader_emails(db, tribe.id)
            # A contributor (ADR 0019) is reminded of the platforms they fill in, only.
            theirs: dict[str, list[dict]] = {}
            for r in rows:
                for addr in steercoaccess.contributor_emails(db, r["id"]):
                    if addr not in to:
                        theirs.setdefault(addr, []).append(r)
            if not to and not theirs:
                continue
            subject, html = reminder_mail(db, tribe, period, rows, lang)
            sent = any([send_email(smtp, addr, subject, html, html=True, lang=lang) for addr in to])
            for addr, mine in theirs.items():
                sub2, html2 = reminder_mail(db, tribe, period, mine, lang, contributor=True)
                sent = send_email(smtp, addr, sub2, html2, html=True, lang=lang) or sent
            if not sent:
                continue  # retried at the next tick, the SMTP may come back
            done.append(tribe.name)
        cfg["last_reminder"] = period
        _store(db, tribe.id, cfg)
        db.commit()
    return done


def pack_mail(db: Session, tribe: Tribe, period: str, lang: str, sender: str) -> tuple[str, str]:
    """The pack mail's body: per platform, its key figures and its degraded SLAs."""
    from .mailbody import app_link, button, footer, layout
    from .routers.steerco import _aggregate
    month = _month_label(period, lang)
    title = f"Steerco {tribe.name}, {month}"
    parts = [f'<p style="margin:0 0 12px">{escape(_t(lang, f"Présentation Steerco envoyée par {sender}, en pièce jointe.", f"Steerco presentation sent by {sender}, as an attached file."))}</p>']
    for p in pack_platforms(db, tribe.id):
        d = _aggregate(db, p.id, period)
        kpis = [k for k in (d.get("kpis") or []) if str(k.get("value") or "").strip()][:6]
        figures = ", ".join(f'{escape(str(k.get("label")))} {escape(str(k.get("value")))}' for k in kpis)
        sla = d.get("sla") or {}
        bad = []
        for i, svc in enumerate(sla.get("services") or []):
            cells = next((r.get("cells") or [] for r in sla.get("rows") or []
                          if r.get("period") == "__current__"), [])
            c = cells[i] if i < len(cells) and isinstance(cells[i], dict) else {}
            if c.get("s") in ("warn", "ko"):
                bad.append(f'{escape(str(svc))} {escape(str(c.get("v") or ""))}')
        parts.append(f'<div style="margin:0 0 12px"><div style="font-weight:bold">{escape(p.name)}</div>'
                     + (f'<div style="color:#1B2433">{figures}</div>' if figures else "")
                     + (f'<div style="color:#B42318">{escape(_t(lang, "SLA sous le seuil : ", "SLA below target: "))}{", ".join(bad)}</div>' if bad else "")
                     + '</div>')
    link = app_link(db, "/steerco?tab=month")
    body = "".join(parts)
    if link:
        body += button(link, _t(lang, "Ouvrir dans l'application", "Open in the app"))
    return title, layout(title, "", body, footer=footer(lang, "steerco_pack"))
