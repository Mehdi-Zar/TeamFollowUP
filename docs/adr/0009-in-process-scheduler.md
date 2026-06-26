# ADR-0009 — In-process background scheduler

**Status:** Accepted (revisit at scale)

## Context
Weekly progress points, scheduled report emails and per-user subscriptions must run periodically
without extra infrastructure.

## Options Considered
1. **In-process async loop** started at app startup (hourly tick).
2. External scheduler (Celery beat, APScheduler + broker, system cron).
3. Cloud scheduler triggering an endpoint.

## Decision
Option 1. `main.py` `@app.on_event("startup")` spawns an asyncio task that every hour calls
`ensure_weekly`, `send_due_weekly_reports` (idempotent per ISO week) and `send_personal_subscriptions`.

## Rationale
Zero extra moving parts for a single-replica internal deployment; idempotency guards prevent duplicates
within a tick window.

## Consequences
- Works out of the box with `docker compose`.
- **Correct only with a single app replica** — multiple replicas would each run the loop.

## Risks
- Horizontal scaling would duplicate scheduled work (R-3). Idempotency (per-week guard) limits but does
  not eliminate duplicates across replicas.

## Future Evolution
Before running >1 replica: externalize (leader election / advisory lock, or a dedicated worker /
Celery beat / cloud scheduler hitting `POST /api/admin/progress/run-weekly`).
</content>
