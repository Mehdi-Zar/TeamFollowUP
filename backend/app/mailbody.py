"""The body of the report mails: a summary a mail client can show.

The full document (report.render_html) is built for a browser: CSS variables,
flex and grid, inline SVG curves, a 1326 px minimum width. Outlook ignores the
first three, Gmail and Outlook strip the SVG, a phone scrolls sideways, and
Gmail clips anything past 102 KB. So the mail carries a short summary in the
only layout every client renders (tables, inline styles, 640 px), with a link to
the app; the full document travels as an attached .html (opened in the browser,
rendered exactly) next to the PPTX.

``render_email`` builds that summary from the same data as the documents;
``text_of`` gives the plain-text part (the preview line of many clients, and
what a text-only client shows).
"""
from __future__ import annotations

import html as _html
import re
from datetime import datetime

from .reportcommon import _lang, _sep, _status_label, fmt_datetime, rt

NAVY = "#1F2A6B"
GREY = "#556274"
LINE = "#E3E8EF"
_RAG = {"red": "#C0262D", "amber": "#8A6410", "green": "#0F7B3F", "grey": GREY}
_FONT = "font-family:Arial,Helvetica,sans-serif"

_T = {
    "fr": {
        "open": "Ouvrir dans l'application", "attached": "Le document complet est joint : "
        "la version HTML s'ouvre dans le navigateur, la version PPTX dans PowerPoint.",
        "attached_html": "Le document complet est joint (HTML, à ouvrir dans le navigateur).",
        "squads": "Squads", "progress": "Progression", "blocked": "Jalons bloqués",
        "at_risk": "Jalons à risque", "otd_late": "OTD en retard", "stale": "Reporting périmé",
        "h_squad": "Squad", "h_status": "Statut", "h_progress": "Avanc.", "h_update": "Dernière saisie",
        "days": "il y a {n} j", "today": "aujourd'hui", "never": "jamais",
        "more": "+{n} autres squads dans le document joint",
        "km": "Messages clés", "watch": "Jalons à surveiller", "leader": "Squad leader",
        "week": "semaine {w}", "generated": "données du {d}",
        "no_squad": "Aucune squad dans ce périmètre.",
        "version": "version du {d}", "not_reported": "Non renseigné",
        "missing": "Sans saisie à cette date ({n}) : {names}",
        "link_doc": "Le document complet est dans l'application ; la version PPTX est jointe.",
        "link_doc_nopptx": "Le document complet est dans l'application.",
    },
    "en": {
        "open": "Open in the app", "attached": "The full document is attached: "
        "the HTML version opens in the browser, the PPTX version in PowerPoint.",
        "attached_html": "The full document is attached (HTML, open it in the browser).",
        "squads": "Squads", "progress": "Progress", "blocked": "Blocked milestones",
        "at_risk": "At-risk milestones", "otd_late": "Late OTDs", "stale": "Stale reporting",
        "h_squad": "Squad", "h_status": "Status", "h_progress": "Progr.", "h_update": "Last update",
        "days": "{n}d ago", "today": "today", "never": "never",
        "more": "+{n} more squads in the attached document",
        "km": "Key messages", "watch": "Milestones to watch", "leader": "Squad leader",
        "week": "week {w}", "generated": "data as of {d}",
        "no_squad": "No squad in this scope.",
        "version": "version of {d}", "not_reported": "Not reported",
        "missing": "No submission at that date ({n}): {names}",
        "link_doc": "The full document is in the app; the PPTX version is attached.",
        "link_doc_nopptx": "The full document is in the app.",
    },
}

MAX_ROWS = 25


def _t(lang: str, key: str, **kw) -> str:
    s = _T[_lang(lang)][key]
    return s.format(**kw) if kw else s


def _e(x) -> str:
    return _html.escape(str(x if x is not None else ""))


def _status(row: dict, lang: str) -> tuple[str, str]:
    """(colour, label) of a squad's status; grey "Not reported" when it never
    submitted (it read "On track" in green)."""
    if row.get("age_days") is None:
        return GREY, _t(lang, "not_reported")
    rag = row.get("status_rag") or "grey"
    return _RAG.get(rag, GREY), _status_label(row.get("status"), lang)


def _age(row: dict, lang: str) -> tuple[str, bool]:
    n = row.get("age_days")
    if n is None:
        return _t(lang, "never"), True
    return (_t(lang, "today") if n == 0 else _t(lang, "days", n=n)), bool(row.get("is_stale"))


def button(url: str, label: str) -> str:
    """A link that looks like a button in every client (a padded table cell)."""
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:18px 0 6px">'
            f'<tr><td bgcolor="{NAVY}" style="border-radius:6px;padding:10px 18px">'
            f'<a href="{_e(url)}" style="{_FONT};font-size:14px;font-weight:bold;color:#ffffff;'
            f'text-decoration:none">{_e(label)}</a></td></tr></table>')


def notice_box(inner_html: str) -> str:
    """The opening sentence of a mail (who changed what, and when)."""
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin:0 0 16px"><tr><td style="{_FONT};font-size:14px;color:#1B2433;'
            f'background:#EEF2F7;border-left:4px solid {NAVY};padding:12px 14px">{inner_html}</td></tr></table>')


def layout(title: str, subtitle: str, content: str, *, footer: str = "") -> str:
    """The shell every mail of the app shares: a 640 px table, a navy title band,
    the content, then the footer (why this mail, how to change it)."""
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_e(title)}</title></head>'
        f'<body style="margin:0;padding:0;background:#F4F6FA">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#F4F6FA">'
        f'<tr><td align="center" style="padding:16px 8px">'
        # Outlook (Word engine) ignores max-width: a fixed table holds it at 640.
        '<!--[if mso]><table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->'
        f'<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%;max-width:640px;background:#ffffff;border:1px solid {LINE};border-radius:8px">'
        f'<tr><td bgcolor="{NAVY}" style="padding:16px 20px;border-radius:8px 8px 0 0">'
        f'<div style="{_FONT};font-size:18px;font-weight:bold;color:#ffffff">{_e(title)}</div>'
        + (f'<div style="{_FONT};font-size:13px;color:#DCE3F0;margin-top:4px">{_e(subtitle)}</div>' if subtitle else "")
        + f'</td></tr><tr><td style="padding:18px 20px;{_FONT};font-size:14px;color:#1B2433;line-height:1.45">'
        f'{content}</td></tr>'
        + (f'<tr><td style="padding:12px 20px 16px;border-top:1px solid {LINE};{_FONT};font-size:12px;'
           f'color:{GREY};line-height:1.45">{footer}<!--instance-footer--></td></tr>' if footer else "")
        + '</table><!--[if mso]></td></tr></table><![endif]--></td></tr></table></body></html>')


def _kpis(s: dict, lang: str) -> str:
    cells = [("squads", s.get("squads_total", 0), None),
             ("progress", f'{s.get("avg_progress", 0)}%', None),
             ("blocked", s.get("blocked", 0), "red" if s.get("blocked") else None),
             ("at_risk", s.get("at_risk", 0), "amber" if s.get("at_risk") else None),
             ("otd_late", s.get("otd_late", 0), "red" if s.get("otd_late") else None),
             ("stale", s.get("stale", 0), "amber" if s.get("stale") else None)]
    tds = "".join(
        f'<td width="33%" valign="top" style="padding:8px 10px;border:1px solid {LINE}">'
        f'<div style="{_FONT};font-size:20px;font-weight:bold;color:{_RAG.get(rag or "", NAVY)}">{_e(v)}</div>'
        f'<div style="{_FONT};font-size:12px;color:{GREY}">{_e(_t(lang, k))}</div></td>'
        + ('</tr><tr>' if i == 2 else "")
        for i, (k, v, rag) in enumerate(cells))
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;margin:4px 0 18px"><tr>{tds}</tr></table>')


def _squad_table(rows: list[dict], lang: str, past: bool = False) -> str:
    if not rows:
        return f'<p style="color:{GREY}">{_e(_t(lang, "no_squad"))}</p>'
    th = (f'style="{_FONT};font-size:12px;color:{GREY};text-align:left;padding:6px 8px;'
          f'border-bottom:2px solid {LINE}"')
    out = [f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
           f'style="border-collapse:collapse">',
           f'<tr><th {th}>{_e(_t(lang, "h_squad"))}</th><th {th}>{_e(_t(lang, "h_status"))}</th>'
           f'<th {th}>{_e(_t(lang, "h_progress"))}</th>'
           + ("" if past else f'<th {th}>{_e(_t(lang, "h_update"))}</th>') + '</tr>']
    td = f'style="{_FONT};font-size:13px;padding:6px 8px;border-bottom:1px solid {LINE}"'
    for r in rows[:MAX_ROWS]:
        col, label = _status(r, lang)
        age, stale = _age(r, lang)
        last = ("" if past else
                f'<td {td}><span style="color:{_RAG["amber"] if stale else "#1B2433"}">{_e(age)}</span></td>')
        out.append(
            f'<tr><td {td}><strong>{_e(r.get("name"))}</strong></td>'
            f'<td {td}><span style="color:{col};font-weight:bold">&#9679;</span> {_e(label)}</td>'
            f'<td {td}>{_e(r.get("annual_pct", 0))}%</td>{last}</tr>')
    out.append("</table>")
    if len(rows) > MAX_ROWS:
        out.append(f'<p style="{_FONT};font-size:12px;color:{GREY};margin:6px 0 0">'
                   f'{_e(_t(lang, "more", n=len(rows) - MAX_ROWS))}</p>')
    return "".join(out)


def _squad_focus(r: dict, lang: str) -> str:
    """One squad: leader, key messages and the milestones that need attention."""
    det = r.get("detail") or {}
    out = []
    if r.get("leader"):
        out.append(f'<p style="margin:0 0 10px">{_e(_t(lang, "leader"))}{_e(_sep(lang))}'
                   f'<strong>{_e(r["leader"])}</strong></p>')
    kms = det.get("key_messages") or []
    if kms:
        rag = {"risk": "red", "alert": "amber", "success": "green"}
        kms = sorted(kms, key=lambda m: {"risk": 0, "alert": 1, "success": 2}.get(m.get("kind"), 3))
        out.append(f'<p style="margin:12px 0 4px;font-weight:bold">{_e(_t(lang, "km"))}</p><ul style="margin:0;padding-left:18px">')
        for m in kms[:6]:
            out.append(f'<li style="margin:2px 0"><span style="color:{_RAG[rag.get(m.get("kind"), "grey")]};'
                       f'font-weight:bold">{_e(rt(lang, "km_" + (m.get("kind") or "")))}</span>'
                       f'{_e(_sep(lang))}{_e(m.get("text"))}</li>')
        out.append("</ul>")
    watch = [it for q in det.get("quarters") or [] for it in q.get("items") or []
             if it.get("status") in ("blocked", "at_risk")]
    if watch:
        out.append(f'<p style="margin:12px 0 4px;font-weight:bold">{_e(_t(lang, "watch"))}</p><ul style="margin:0;padding-left:18px">')
        for it in sorted(watch, key=lambda x: x.get("status") != "blocked")[:8]:
            col = _RAG["red" if it.get("status") == "blocked" else "amber"]
            out.append(f'<li style="margin:2px 0"><span style="color:{col};font-weight:bold">'
                       f'{_e(_status_label(it.get("status"), lang))}</span>{_e(_sep(lang))}{_e(it.get("title"))}</li>')
        out.append("</ul>")
    return "".join(out)


def changes_block(changes: dict | None, lang: str) -> str:
    """The "what's new since your last report" list, mail version."""
    if not changes or changes.get("first"):
        return ""
    if not changes.get("count"):
        return (f'<p style="margin:0 0 14px;color:#0F7B3F">{_e(rt(lang, "no_changes"))}</p>')
    out = [f'<p style="margin:0 0 4px;font-weight:bold">{_e(rt(lang, "whatsnew"))}</p>']
    if changes.get("summary"):
        out.append(f'<p style="margin:0 0 6px;color:{GREY}">{_e(changes["summary"])}</p>')
    out.append('<ul style="margin:0 0 16px;padding-left:18px">')
    for grp in changes.get("by_squad") or []:
        out.append(f'<li style="margin:2px 0"><strong>{_e(grp.get("name"))}</strong>{_e(_sep(lang))}'
                   f'{_e(", ".join(grp.get("items") or []))}</li>')
    out.append("</ul>")
    return "".join(out)


def render_email(data: dict, *, changes: dict | None = None, notice_html: str = "",
                 link: str | None = None, footer: str = "", has_pptx: bool = True,
                 week: int | None = None) -> str:
    """The summary mail of a report (whole scope or one squad)."""
    lang = data.get("lang", "fr")
    rows = [r for blk in data.get("tribes") or [] for r in blk.get("squads") or []]
    gen = data.get("generated_at")
    doc = rt(lang, "dashboard_doc" if data.get("doc") == "dashboard" else "report")
    sub = [data.get("scope_name") or ""]
    if week:
        sub.append(_t(lang, "week", w=week))
    past = bool(data.get("as_of"))
    if past:
        # A past version says so first: it reads like today's report otherwise.
        from .reportcommon import fmt_date
        sub.append(_t(lang, "version", d=fmt_date(data["as_of"], lang)))
    elif isinstance(gen, datetime):
        sub.append(_t(lang, "generated", d=fmt_datetime(gen, lang)))
    parts = [notice_html] if notice_html else []
    missing = data.get("as_of_missing") or []
    if past and missing:
        names = ", ".join(missing[:8]) + (f" (+{len(missing) - 8})" if len(missing) > 8 else "")
        parts.append(f'<p style="margin:0 0 12px;color:{_RAG["amber"]}">'
                     f'{_e(_t(lang, "missing", n=len(missing), names=names))}</p>')
    parts.append(changes_block(changes, lang))
    if data.get("squad_scoped") and rows:
        r = rows[0]
        col, label = _status(r, lang)
        age, stale = _age(r, lang)
        update = ("" if past else
                  f', {_e(_t(lang, "h_update").lower())} '
                  f'<span style="color:{_RAG["amber"] if stale else "#1B2433"}">{_e(age)}</span>')
        parts.append(
            f'<p style="margin:0 0 10px;font-size:15px"><span style="color:{col};'
            f'font-weight:bold">&#9679; {_e(label)}</span>, '
            f'{_e(_t(lang, "progress").lower())} {_e(r.get("annual_pct", 0))}%{update}</p>')
        parts.append(_squad_focus(r, lang))
    else:
        parts.append(_kpis(data.get("summary") or {}, lang))
        parts.append(_squad_table(rows, lang, past))
    if link:
        parts.append(button(link, _t(lang, "open")))
    if link:
        note = "link_doc" if has_pptx else "link_doc_nopptx"
    else:
        note = "attached" if has_pptx else "attached_html"
    parts.append(f'<p style="margin:12px 0 0;font-size:12px;color:{GREY}">{_e(_t(lang, note))}</p>')
    # One squad: its name is the title (a change notice is not a "weekly report").
    if data.get("squad_scoped") and rows:
        doc = rows[0].get("name") or doc
        sub[0] = data.get("tribes")[0].get("tribe_name") or ""
    return layout(f'{data.get("app_name") or ""} | {doc}', ", ".join(x for x in sub if x),
                  "".join(parts), footer=footer)


def text_of(html_body: str) -> str:
    """Plain-text version of a mail body: block ends become line breaks, links
    keep their address, tags go, entities are decoded, blank runs collapse."""
    s = re.sub(r"(?is)<(head|style|script)\b.*?</\1>", "", html_body)
    s = re.sub(r'(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", s)
    s = re.sub(r"(?i)<li\b[^>]*>", "\n- ", s)
    s = re.sub(r"(?i)</(p|div|tr|h\d|ul|table)>|<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</t[dh]>", "  ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()



# ----- Context shared by every mail: the link to the app, and why it came -----

_WHY = {
    "fr": {
        "schedule": "Vous recevez ce mail car l'envoi programmé du rapport vous inclut. Il se règle dans Administration.",
        "leaders": "Vous recevez ce document car vous dirigez cette squad.",
        "subscription": "Vous recevez ce rapport car vous y êtes abonné. L'abonnement se règle depuis le tableau de bord, bouton du rapport.",
        "change": "Vous recevez ce mail car les avis de modification vous incluent. Ils se règlent dans Administration.",
        "manual": "Envoyé à la demande d'un utilisateur depuis l'application.",
        "feed": "Vous recevez ce mail car vous suivez le fil. Cela se règle dans vos Préférences.",
        "access": "Vous recevez ce mail car vous validez les demandes d'accès.",
        "account": "Vous recevez ce mail au sujet de votre compte.",
        "test": "Mail de test envoyé depuis Administration.",
    },
    "en": {
        "schedule": "You receive this mail because the scheduled report includes you. It is set in Administration.",
        "leaders": "You receive this document because you lead this squad.",
        "subscription": "You receive this report because you subscribed to it. Manage it from the dashboard, report button.",
        "change": "You receive this mail because the change notices include you. They are set in Administration.",
        "manual": "Sent at a user's request from the app.",
        "feed": "You receive this mail because you follow the feed. Change it in your Preferences.",
        "access": "You receive this mail because you review access requests.",
        "account": "You receive this mail about your account.",
        "test": "Test mail sent from Administration.",
    },
}


def app_link(db, path: str = "/") -> str | None:
    """Absolute link into the app, from the configured public base URL. None when
    no base URL is set (a background job has no request to derive it from)."""
    try:
        from .authconfig import get_auth_config
        base = (get_auth_config(db).get("public_base_url") or "").rstrip("/")
    except Exception:
        base = ""
    if not base:
        return None
    return base + (path if path.startswith("/") else "/" + path)


def footer(lang: str, why: str, link: str | None = None, link_label: str | None = None) -> str:
    """Footer line: why this mail came, and where to go."""
    txt = _e(_WHY[_lang(lang)].get(why, ""))
    if link:
        label = link_label or ("Open the app" if _lang(lang) == "en" else "Ouvrir l'application")
        txt += f' <a href="{_e(link)}" style="color:{NAVY}">{_e(label)}</a>'
    return txt


def instance_lang(db) -> str:
    """The instance's language (Administration > General), which every mail follows."""
    from .generalconfig import get_general
    return _lang(get_general(db).get("default_lang"))


def simple_mail(title: str, lines_html: list[str], *, lang: str, why: str,
                link: str | None = None, link_label: str | None = None) -> str:
    """A short mail (feed, access, account, test): a title, a few paragraphs, a
    button when there is somewhere to go, and the footer. A "[App] " tag at the
    start of the title (the subject's) is left to the subject line."""
    import re as _re
    title = _re.sub(r"^\[[^\]]+\]\s*", "", title)
    body = "".join(f'<p style="margin:0 0 10px">{ln}</p>' for ln in lines_html)
    if link:
        body += button(link, link_label or ("Open the app" if _lang(lang) == "en" else "Ouvrir l'application"))
    return layout(title, "", body, footer=footer(lang, why))
