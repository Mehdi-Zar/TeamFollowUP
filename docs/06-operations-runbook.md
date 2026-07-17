# 06 - Operations Runbook

## Topology

One **app** container (Uvicorn, serves API + SPA) + one **Postgres** container with a named volume
`db_data`. Exposed on a **single port**: host `:8443` → container `:8443` (**HTTPS**). Override with
`APP_HTTPS_PORT`. No HTTP listener - HTTP→HTTPS redirection is handled upstream (e.g. GKE Gateway API).

## Deploy / upgrade

```bash
# from repo root
docker compose up -d --build app      # rebuild image (SPA + backend) and restart
docker compose ps                     # check health
docker compose logs -f app            # follow logs
```

On startup, `docker-entrypoint.sh` runs:
1. wait for Postgres,
2. `alembic upgrade head` (idempotent migrations),
3. `python -m app.init_db` (break-glass admin + demo seed if `SEED_DEMO=true`),
4. `python -m app.server` (HTTPS :8443, single port).

A container restart is safe and idempotent. Health: `docker compose ps` shows `healthy`
(healthcheck via `curl`), and `GET /api/config` returns 200.

## Database migrations

```bash
docker compose exec app alembic upgrade head           # apply
docker compose exec app alembic downgrade -1           # roll back one
docker compose exec app alembic revision -m "msg"      # author new (then edit)
docker compose exec app alembic current                # show version
```
Migration chain: `0001 → … → 0026_api_keys` (see `backend/alembic/versions/` for the current head).
**Always** add a migration for any model change (tests use `create_all`, prod uses Alembic - do not
rely on `create_all`).

## Backup & restore (Postgres)

```bash
# Backup
docker compose exec -T db pg_dump -U tribe tribe > backup_$(date +%F).sql
# Restore (DANGER: overwrites)
docker compose exec -T db psql -U tribe -d tribe < backup_YYYY-MM-DD.sql
# Volume snapshot alternative: back up the db_data volume.
```
> No automated backup is configured - **add a scheduled `pg_dump`** (cron/sidecar) before production.

## Scheduled jobs (in-process)

The weekly-report scheduler runs **inside the app process** (async loop, hourly). It is **safe only
with a single app replica**. If scaling horizontally, externalize it (see [ADR-0009](adr/0009-in-process-scheduler.md)
and roadmap). Manual trigger: `POST /api/admin/progress/run-weekly` (admin).

## Configuration

Runtime config lives in DB (`app_settings`) and is editable from **Admin** (modules, personas,
settings, SMTP, report, auth). Bootstrap/infra config is environment variables - see
[`backend/.env.example`](../backend/.env.example).

## Monitoring & logging (current state + gaps)

- **Logs**: stdout (Uvicorn + `logging`), captured by Docker. Structured per-line.
- **Audit**: `audit_log` table (admin-visible at `/api/admin → Audit`).
- **Gaps**: no metrics (Prometheus), no centralized log shipping, no alerting, no uptime probe beyond
  the container healthcheck. Tracked in [10](10-tech-debt-and-risk-register.md) / roadmap.

## Incident playbooks

| Symptom | First checks | Action |
|---------|--------------|--------|
| App unhealthy / 502 | `docker compose logs app`; DB healthy? | restart `app`; verify `alembic upgrade` succeeded |
| Migrations failed on boot | entrypoint logs (alembic) | fix migration, `docker compose up -d --build app`; if partial, `alembic current` + manual repair |
| Login broken (all users) | check `SECRET_KEY` changed? (invalidates sessions) | if rotated intentionally, users re-login; else restore previous secret |
| Locked out of admin | break-glass admin (`admin@local`) | reset its password via DB or `BREAKGLASS_PASSWORD` + restart |
| Emails not sending | Admin → SMTP "test"; `smtp.enabled` | fix SMTP config; check app logs for send failures |
| Weekly report not sent | scheduler single-replica? `weekly_report` enabled? SMTP on? | `POST /api/admin/progress/run-weekly`; verify `last_sent_week` |

## Rollback

Code rollback = redeploy previous image tag. **Migrations are not auto-reverted** - if a release
added a migration, roll it back explicitly (`alembic downgrade`) *before* deploying older code that
doesn't expect the new schema. Prefer additive, backward-compatible migrations.
</content>
