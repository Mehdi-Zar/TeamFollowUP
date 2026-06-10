"""First-boot bootstrap: ensure the breaking-glass admin exists."""
import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import AuditLog, User, utcnow
from .security import hash_password

logger = logging.getLogger("trt.bootstrap")


def ensure_breakglass(db: Session) -> None:
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
