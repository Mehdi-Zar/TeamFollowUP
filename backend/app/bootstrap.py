"""First-boot bootstrap: ensure the breaking-glass admin exists.

The "break-glass" account is the always-available local admin used to recover the
app when SSO is misconfigured or unreachable. It is created idempotently on
startup from environment settings, protected from deletion/disabling elsewhere,
and its generated password (if any) is logged once so an operator can capture it.
"""
import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import AuditLog, User, utcnow
from .security import hash_password

logger = logging.getLogger("trt.bootstrap")


def ensure_breakglass(db: Session) -> None:
    """Create the break-glass admin if missing, or re-assert its flags if present.

    Idempotent: safe to call on every boot. Effects:
      * existing account -> forced back to admin + break-glass (so it can never be
        accidentally demoted or un-flagged and lock everyone out);
      * missing account -> created active with a password from the environment, or
        a freshly generated one that is logged once (see ``generated``).
    """
    email = settings.breakglass_email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        # keep it an admin / break-glass flagged
        existing.is_break_glass = True
        existing.role = "admin"
        db.commit()
        return

    password = settings.breakglass_password
    generated = False
    if not password:
        # No password supplied: mint a strong random one so the account is never
        # created with an empty/guessable secret. It is surfaced via the log below.
        password = secrets.token_urlsafe(12)
        generated = True

    user = User(
        email=email,
        display_name="Administrateur (compte de secours)",
        role="admin",
        is_break_glass=True,
        password_hash=hash_password(password),
        created_at=utcnow(),
    )
    db.add(user)
    # Audit with user_id=None: this is a system action, not performed by any user.
    db.add(AuditLog(user_id=None, action="bootstrap.breakglass.created",
                    entity="user", detail={"email": email}))
    db.commit()

    banner = "=" * 70
    if generated:
        logger.warning(
            "\n%s\nCOMPTE DE SECOURS (BREAKING-GLASS) CRÉÉ\n  Email    : %s\n  Mot de passe (généré, NOTEZ-LE) : %s\n%s",
            banner, email, password, banner,
        )
    else:
        logger.info("Compte de secours créé pour %s (mot de passe fourni via l'environnement).", email)
