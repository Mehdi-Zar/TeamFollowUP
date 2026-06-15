"""One-off data reset: wipe business data and seed the Cloud Foundations tribe.

Preserves admin configuration (app_settings: SMTP, modules, general, …) and the
breaking-glass admin login. Run inside the app container:

    docker compose exec app python -m app.reset_data
"""
import logging

from .bootstrap import ensure_breakglass
from .config import settings
from .database import Base, SessionLocal
from .models import Squad, Tribe, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("trt.reset")

TRIBE_NAME = "Cloud Foundations"
SQUADS = [
    "Portal",
    "Managed Services",
    "Azure",
    "GCP / S3NS",
    "AWS",
    "VMWare",
    "Edge Computing",
    "Run & Operation",
    "Customer Success",
    "Architecture",
    "Demand & Product Management",
    "Vision & Strategie",
    "Tribe Office",
]

# Configuration we keep across a data reset (admin-managed settings).
PRESERVE_TABLES = {"app_settings"}


def reset(db) -> None:
    bg_email = settings.breakglass_email.lower().strip()
    # Delete child rows first (reverse dependency order). Keep config tables and
    # the break-glass admin so the existing login keeps working.
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in PRESERVE_TABLES:
            continue
        if table.name == "users":
            db.execute(table.delete().where(User.email != bg_email))
        else:
            db.execute(table.delete())
    db.commit()
    logger.info("Données métier effacées (config + compte de secours préservés).")

    # Make sure the break-glass admin still exists / is flagged admin.
    ensure_breakglass(db)

    tribe = Tribe(name=TRIBE_NAME, display_order=1)
    db.add(tribe)
    db.flush()
    for i, name in enumerate(SQUADS, start=1):
        db.add(Squad(name=name, tribe_id=tribe.id, display_order=i))
    db.commit()
    logger.info("Tribe '%s' créée avec %d squads.", TRIBE_NAME, len(SQUADS))


def main() -> None:
    db = SessionLocal()
    try:
        reset(db)
        logger.info("Reset terminé.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
