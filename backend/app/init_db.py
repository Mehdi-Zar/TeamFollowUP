"""Post-migration initialization: breaking-glass admin + demo seed.

Run once after Alembic migrations (schema already exists). Idempotent: it ensures
the break-glass admin login, seeds the default leave types, and applies the demo
dataset - each step is a no-op if already done - so it is safe to run on every boot.
"""
import logging

from .bootstrap import ensure_breakglass
from .database import SessionLocal
from .leavesconfig import ensure_default_leave_types
from .seed import run_seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("trt.init")


def main() -> None:
    """Open a session and run the three idempotent init steps, then close it."""
    db = SessionLocal()
    try:
        ensure_breakglass(db)
        ensure_default_leave_types(db)
        run_seed(db)
        logger.info("Initialisation terminée.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
