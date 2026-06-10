"""Best-effort email sending via the DB-configured SMTP server."""
import logging
import smtplib
import threading
from email.message import EmailMessage

logger = logging.getLogger("trt.mail")


def send_email(cfg: dict, to: str, subject: str, body: str, attachment: tuple | None = None) -> bool:
    """Send synchronously. attachment = (filename, bytes, maintype, subtype). Returns True on success."""
    if not cfg.get("enabled") or not cfg.get("host") or not to:
        return False
    msg = EmailMessage()
    from_name = cfg.get("from_name") or "Tribe Cockpit"
    msg["From"] = f"{from_name} <{cfg.get('from_addr')}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment:
        filename, data, maintype, subtype = attachment
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    try:
        host, port = cfg["host"], int(cfg.get("port") or 587)
        if cfg.get("use_ssl"):
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if cfg.get("use_tls"):
                server.starttls()
        if cfg.get("username"):
            server.login(cfg["username"], cfg.get("password") or "")
        server.send_message(msg)
        server.quit()
        return True
    except Exception as exc:  # never let email failures break the request
        logger.warning("Échec d'envoi d'email à %s : %s", to, exc)
        return False


def send_async(cfg: dict, to: str, subject: str, body: str, attachment: tuple | None = None) -> None:
    threading.Thread(target=send_email, args=(cfg, to, subject, body, attachment), daemon=True).start()
