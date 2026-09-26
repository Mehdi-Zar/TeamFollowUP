"""Compare a migrated database with the models, and fail on any difference.

The tests build their schema with ``create_all``; production runs the Alembic
migrations. This script catches the gap between the two (an index declared in
the models but never migrated, a NOT NULL that exists only in Python...).

Usage, against a throwaway Postgres already upgraded with ``alembic upgrade head``
(connection from the usual POSTGRES_* variables):

    python -m alembic upgrade head
    python scripts/check_schema_drift.py

Exit code 1 and the list of differences when the schema has drifted.
"""
import pprint
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from app import models  # noqa: E402,F401
from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402


def main() -> int:
    eng = create_engine(settings.database_url)
    with eng.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True, "compare_server_default": False})
        diff = compare_metadata(ctx, Base.metadata)
    for d in diff:
        pprint.pprint(d)
    print(f"{len(diff)} difference(s)")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
