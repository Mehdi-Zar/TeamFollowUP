"""Post-migration initialization: breaking-glass admin + demo seed."""
import logging

from .bootstrap import ensure_breakglass
from .database import SessionLocal
from .seed import run_seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("trt.init")


def main() -> None:
    db = SessionLocal()
    try:
        ensure_breakglass(db)
        run_seed(db)
        logger.info("Initialisation terminée.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
