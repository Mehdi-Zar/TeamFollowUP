"""Best-effort email sending via the DB-configured SMTP server."""
import logging
import smtplib
import threading
from email.message import EmailMessage
from html import escape

from . import trust

logger = logging.getLogger("trt.mail")


def send_email(cfg: dict, to: str, subject: str, body: str, attachment: tuple | None = None,
               html: bool = False, cc: list[str] | None = None) -> bool:
    """Send synchronously. attachment = (filename, bytes, maintype, subtype).

    When html=True, `body` is sent as an HTML body (with a plain-text fallback).
    `cc` (optional) is a list of addresses to put in copy. Returns True on success.
    """
    if not cfg.get("enabled") or not cfg.get("host") or not to:
        return False
    msg = EmailMessage()
    from_name = cfg.get("from_name") or "TeamFollowUP"
    msg["From"] = f"{from_name} <{cfg.get('from_addr')}>"
    msg["To"] = to
    cc = [c for c in (cc or []) if c]
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    # Le pied de page choisi dans Administration > Personnalisation. Passe par le
    # parametre plutot que lu ici: mail.py ne connait pas la base, et c'est ce qui
    # lui permet d'etre teste sans elle.
    footer = (cfg.get("email_footer") or "").strip()
    if footer:
        body += (f'<p style="color:#64748B;font-size:12px">{escape(footer)}</p>'
                 if html else "\n\n" + footer)
    if html:
        msg.set_content("Ce rapport nécessite un client mail compatible HTML.")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)
    if attachment:
        filename, data, maintype, subtype = attachment
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
        return False


def send_async(cfg: dict, to: str, subject: str, body: str, attachment: tuple | None = None) -> None:
    """Send an email on a daemon thread so the caller (a request) is never blocked
    by SMTP latency. Fire-and-forget: the outcome is only logged, not returned."""
    threading.Thread(target=send_email, args=(cfg, to, subject, body, attachment), daemon=True).start()
