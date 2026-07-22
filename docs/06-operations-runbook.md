# 06 - Operations Runbook

## Topology

One **app** container (Uvicorn, serves API + SPA) + one **Postgres** container with a named volume
`db_data`, both `restart: unless-stopped`. Exposed on a **single port**, and the protocol depends on
where TLS is terminated:

| `TLS_ENABLED` | Listener | When |
|---|---|---|
| `false` (compose default) | plain **HTTP** `:8000`, host `${APP_HTTP_PORT:-8000}` | **recommended model**: the infrastructure terminates TLS (GKE Gateway API + ALB). The app trusts `X-Forwarded-Proto` (`proxy_headers`), so it still builds https URLs and secure cookies |
| `true` | **HTTPS** `:8443`, host `${APP_HTTPS_PORT:-8443}` | the app terminates TLS itself (self-signed by default, or a certificate uploaded in Admin → TLS) |

The mode is read from the DB toggle (**Admin → TLS**) and falls back to the `TLS_ENABLED` env.
It is **bound at boot**: flipping the toggle needs a restart to take effect (see *Admin → Ops* below).
HTTP→HTTPS redirection is never done by the app.

## Deploy / upgrade

```bash
# from repo root
docker compose up -d --build app      # rebuild image (SPA + backend) and restart
docker compose ps                     # check health
docker compose logs -f app            # follow logs
```

On startup, `docker-entrypoint.sh` runs:
1. wait for Postgres (60 attempts, 2 s apart),
2. `alembic upgrade head` (idempotent migrations),
3. `python -m app.init_db` (break-glass admin + demo seed if `SEED_DEMO=true`),
4. `python -m app.server` (picks HTTP :8000 or HTTPS :8443 per the table above).

A container restart is safe and idempotent. Health: `docker compose ps` shows `healthy`
(healthcheck curls `/api/health`).

## Database migrations

```bash
docker compose exec app alembic upgrade head           # apply
docker compose exec app alembic downgrade -1           # roll back one
docker compose exec app alembic revision -m "msg"      # author new (then edit)
docker compose exec app alembic current                # show version
```
Migration chain: `0001 → … → 0027_steerco_entries` (see `backend/alembic/versions/` for the current head).
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

## Admin → Ops (in-app operations panel)

Admin-only, for operators who cannot (or should not) shell into the container. Every action is
audited (`ops.*`).

| What | Endpoint | Notes |
|---|---|---|
| Runtime diagnostics | `GET /api/admin/runtime` | version, git sha, hostname (pod/container), pid, uptime, detected orchestrator, serving mode, and **`restart_pending`** when the TLS toggle differs from what the process bound at boot |
| **Restart** | `POST /api/admin/restart` | sends `SIGTERM` to our own pid after the response is flushed; uvicorn drains and exits, the supervisor re-creates the container with the new config. Reports `auto_restart: false` when no supervisor is detected (bare `python -m app.server`), where exiting would **not** come back. Set `OPS_DISABLE_RESTART=1` to make it a no-op |
| Recent logs | `GET /api/admin/logs?limit=&level=` | last 2000 records from an in-memory ring buffer fed by the root **and** uvicorn loggers |
| Download logs | `GET /api/admin/logs/download?fmt=txt\|json` | text or NDJSON attachment |
| Live log level | `POST /api/admin/log-level` | `{"level","persist"}`; with `persist` the level is stored in `app_settings.log_level` and re-applied at the next boot |
| Clear the buffer | `POST /api/admin/logs/clear` | clear, reproduce the issue, then read/download |

> The ring buffer is **in memory and per process**: it is emptied by a restart and is not a
> substitute for log shipping. Use it to diagnose live, not to retain.

## Monitoring & logging (current state + gaps)

- **Logs**: stdout (Uvicorn + `logging`), captured by Docker. Structured per-line. The last 2000
  records are also readable/downloadable in-app (Admin → Ops, above).
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
| TLS toggle changed, nothing happened | Admin → Ops: `restart_pending` true? | the listener is bound at boot: restart (Ops → Restart, or redeploy) |
| Need to debug without shell access | Admin → Ops → logs | set the level to DEBUG (persist off), clear the buffer, reproduce, download, then set it back |

## Rollback

Code rollback = redeploy previous image tag. **Migrations are not auto-reverted** - if a release
added a migration, roll it back explicitly (`alembic downgrade`) *before* deploying older code that
doesn't expect the new schema. Prefer additive, backward-compatible migrations.
</content>
