# ADR-0010 — Alembic migrations as schema source of truth

**Status:** Accepted

## Context
Schema evolves (8 migrations so far); production data must migrate safely and reproducibly.

## Options Considered
1. **Alembic** migrations applied at startup; tests use `create_all` for speed.
2. ORM `create_all` everywhere (no migrations).
3. Hand-written SQL scripts.

## Decision
Option 1. Migrations live in `backend/alembic/versions` (`0001 → 0008`), applied by the entrypoint
(`alembic upgrade head`) before the app starts. Tests build the schema with `Base.metadata.create_all`
on in-memory SQLite for speed.

## Rationale
Deterministic, reversible, reviewable schema changes in prod; fast, isolated tests offline.

## Consequences
- Every model change **must** ship a migration (the test `create_all` will mask a missing one).
- Migrations should be additive/backward-compatible to allow safe rollback (ADR aligns with ops runbook).

## Risks
- Divergence between `create_all` (tests) and migrations (prod) if a migration is forgotten. Mitigated by
  code review + CI; consider a CI check that `create_all` schema == migration head.

## Future Evolution
Add a CI assertion comparing ORM metadata to the latest migration; gate deploys on `alembic upgrade`.
</content>
