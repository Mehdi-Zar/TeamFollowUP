"""Database engine, session factory and ORM base.

Wires SQLAlchemy to the configured Postgres instance and exposes the three
building blocks the rest of the app relies on:

  * ``engine``       - the connection pool to the database;
  * ``SessionLocal`` - a factory that produces per-request Sessions;
  * ``Base``         - the declarative base every ORM model inherits from.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from .config import settings

# pool_pre_ping validates connections before use so a dropped/stale DB
# connection is transparently recycled instead of surfacing as an error.
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
# autoflush/autocommit off: flush and commit are driven explicitly by the app,
# giving each request full control over transaction boundaries.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a request-scoped database session.

    Used with ``Depends(get_db)``: the session is created for the request and
    the ``finally`` guarantees it is closed (returning the connection to the
    pool) whether the request succeeds or raises.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
