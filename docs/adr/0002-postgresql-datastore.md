# ADR-0002 - PostgreSQL as the system of record

**Status:** Accepted

## Context
The product is relational (tribes → squads → objectives/roadmap/kpis/members, timelines, audit) and
needs transactions, constraints, JSON columns and a mature migration story.

## Options Considered
1. **PostgreSQL** + SQLAlchemy 2 + Alembic.
2. SQLite (single file).
3. A document store (Mongo).

## Decision
PostgreSQL 16, accessed via SQLAlchemy 2 ORM; Alembic for migrations; SQLite only for fast offline tests.

## Rationale
Strong relational integrity (FKs, unique constraints), native JSON for snapshots/state, ubiquitous
ops knowledge, and SQLAlchemy gives portability (tests use in-memory SQLite).

## Consequences
- Reliable constraints and cascades; JSON columns for snapshot/state/changes/audit detail.
- Test suite runs offline on SQLite via `create_all` (no Postgres needed).

## Risks
- ORM-level cascades + dual DB (SQLite tests vs Postgres prod) can hide dialect differences. Mitigated
  by keeping migrations the source of truth and avoiding exotic SQL.

## Future Evolution
Read replica for heavy dashboard/report reads; managed Postgres (HA, PITR backups) for production.
</content>
