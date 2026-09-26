"""Best-effort email sending via the DB-configured SMTP server."""
import logging
import smtplib
import threading
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape

from . import trust

logger = logging.getLogger("trt.mail")

# Why the last send of this thread failed (read by the admin's test buttons,
# which used to answer "ok: false" and nothing more).
_last = threading.local()


def last_error() -> str | None:
    """The reason of this thread's last failed send, if any."""
    return getattr(_last, "error", None)


def send_email(cfg: dict, to: str, subject: str, body: str, attachment=None,
               html: bool = False, cc: list[str] | None = None, text: str | None = None,
               lang: str = "fr") -> bool:
    """Send synchronously. Returns True on success.

    ``attachment``: one (filename, bytes, maintype, subtype) tuple, or a list of
    them. When html=True, ``body`` is the HTML part and ``text`` the plain-text
    part (derived from the HTML when not given: a real summary, not a sentence
    saying the mail needs HTML). ``cc``: addresses in copy.
    """
    _last.error = None
    if not cfg.get("enabled") or not cfg.get("host") or not to:
        _last.error = "SMTP non configuré" if lang != "en" else "SMTP not configured"
        return False
    msg = EmailMessage()
    from_name = cfg.get("from_name") or "TeamFollowUP"
    from_addr = cfg.get("from_addr") or ""
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to
    cc = [c for c in (cc or []) if c]
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    # Headers a mail robot is expected to carry: a date, a unique id, and the
    # "auto-generated" mark that stops out-of-office replies from looping back.
    msg["Date"] = formatdate(localtime=True)
    domain = from_addr.rpartition("@")[2] or None
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    # Le pied de page choisi dans Administration > Personnalisation. Passe par le
    # parametre plutot que lu ici: mail.py ne connait pas la base, et c'est ce qui
    # lui permet d'etre teste sans elle.
    footer = (cfg.get("email_footer") or "").strip()
    if footer:
        if html:
            # Inside the card when the body has the slot (mailbody.layout), else
            # before </body>; never after </html>, where clients may drop it.
            if "<!--instance-footer-->" in body:
                body = body.replace("<!--instance-footer-->", f"<br>{escape(footer)}", 1)
            else:
                note = f'<p style="color:#556274;font-size:12px;font-family:Arial,sans-serif;margin:12px 16px">{escape(footer)}</p>'
                idx = body.lower().rfind("</body>")
                body = body[:idx] + note + body[idx:] if idx >= 0 else body + note
        else:
            body += "\n\n" + footer
    if html:
        from .mailbody import text_of
        plain = text if text is not None else text_of(body)
        msg.set_content(plain or ("This mail needs an HTML-capable mail client." if lang == "en"
                                  else "Ce mail nécessite une messagerie compatible HTML."))
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)
    atts = attachment if isinstance(attachment, list) else ([attachment] if attachment else [])
    for att in atts:
        if att:
            filename, data, maintype, subtype = att
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    try:
        host, port = cfg["host"], int(cfg.get("port") or 587)
        # An explicit context is required, not a nicety: called without one,
        # smtplib falls back to ssl._create_stdlib_context(), which sets
        # check_hostname=False and verify_mode=CERT_NONE. The credentials below
        # would then be handed to whatever answered on that host and port. The
        # context carries the admin-managed CA store, so an internal relay is
        # reached by importing its authority rather than by trusting anything.
        ctx = trust.context()
        if cfg.get("use_ssl"):
            server = smtplib.SMTP_SSL(host, port, timeout=15, context=ctx)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if cfg.get("use_tls"):
                server.starttls(context=ctx)
        if cfg.get("username"):
            server.login(cfg["username"], cfg.get("password") or "")
        server.send_message(msg)
        server.quit()
        return True
    except Exception as exc:  # never let email failures break the request
        logger.warning("Échec d'envoi d'email à %s : %s", to, exc)
        _last.error = f"{type(exc).__name__}: {exc}"
        return False


def send_async(cfg: dict, to: str, subject: str, body: str, attachment: tuple | None = None,
               html: bool = False, lang: str = "fr") -> None:
    """Send an email on a daemon thread so the caller (a request) is never blocked
    by SMTP latency. Fire-and-forget: the outcome is only logged, not returned."""
    threading.Thread(target=send_email, args=(cfg, to, subject, body, attachment),
                     kwargs={"html": html, "lang": lang}, daemon=True).start()
