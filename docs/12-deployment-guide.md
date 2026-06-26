# 12 — Deployment Guide (VMware · GCP · S3NS · AWS · Azure)

This guide explains how to deploy **Tribe Run Tracker** to production on the main
target platforms. The application ships as **one container image** plus a
**PostgreSQL** database — nothing else is required.

---

## 1. Architecture recap (what you deploy)

```
            ┌──────────────────────────────┐
  HTTPS ───▶│  Tribe Run Tracker (1 image) │───▶  PostgreSQL 16
  (LB/proxy)│  FastAPI + built React SPA   │      (managed or self-hosted)
            │  listens on :8000            │
            └──────────────────────────────┘
```

- **Single image** (`Dockerfile`, multi-stage): builds the React SPA, then serves
  it together with the API from FastAPI/uvicorn on **port 8000** (`--proxy-headers`,
  so it sits behind a TLS terminator / load balancer).
- **Stateless app**: all state lives in PostgreSQL. You can run **N replicas**.
  The in-process weekly scheduler uses a **Postgres advisory lock**, so only one
  replica ticks at a time — horizontal scaling is safe.
- **Migrations**: the entrypoint runs `alembic upgrade head` then `python -m app.init_db`
  (bootstraps the break-glass admin; seeds demo data only if `SEED_DEMO=true`).

> **Migrations & multiple replicas.** Every instance runs `alembic upgrade head`
> on start. For the *first* rollout of a new version, deploy with **1 instance**
> (or a dedicated migration job) so two instances don't race the schema, then
> scale out. Same-version restarts are idempotent and safe.

---

## 2. Configuration (environment variables)

All config is via environment variables (see `.env.example`). The essentials:

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | **yes** | Session/JWT signing key. 32+ random chars. |
| `POSTGRES_HOST` | **yes** | Hostname/IP of PostgreSQL (managed instance, proxy, or `db` in compose). |
| `POSTGRES_PORT` | | Default `5432`. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | **yes** | DB name / user / password. |
| `COOKIE_SECURE` | **prod** | `true` behind HTTPS (cookies sent only over TLS). |
| `COOKIE_SAMESITE` | | `lax` (default) or `strict`. |
| `SEED_DEMO` | | `false` in production (no demo data). |
| `BREAKGLASS_EMAIL` / `BREAKGLASS_PASSWORD` | **yes** | Emergency admin. If password is empty, a random one is printed in the logs on first boot. |
| `STALENESS_THRESHOLD_DAYS` | | Default `7`. Also editable in the admin UI. |
| `OIDC_*` | optional | SSO via OpenID Connect (Authorization Code + PKCE). |
| `SAML_*` | optional | SSO via SAML 2.0 (xmlsec is bundled in the image). |

> The app builds its DB URL from the discrete `POSTGRES_*` vars (not a single
> `DATABASE_URL`). When pointing at a managed database, set `POSTGRES_HOST` to the
> instance host (or the local socket/proxy address — see GCP/AWS/Azure below).

**Secrets** (`SECRET_KEY`, `POSTGRES_PASSWORD`, OIDC/SAML secrets) should come
from the platform's secret manager, never from a committed file.

---

## 3. Build & push the image (once, for any cloud)

```bash
# Build
docker build -t tribe-run-tracker:1.0 .

# Tag & push to your registry (examples)
docker tag tribe-run-tracker:1.0 REGISTRY/tribe-run-tracker:1.0
docker push REGISTRY/tribe-run-tracker:1.0
```

Registry per platform: **GCP/S3NS** → Artifact Registry (`REGION-docker.pkg.dev/PROJECT/REPO`),
**AWS** → ECR (`ACCOUNT.dkr.ecr.REGION.amazonaws.com/REPO`), **Azure** → ACR
(`REGISTRY.azurecr.io/REPO`), **VMware** → any registry (Harbor, Docker Hub, …).

A multi-arch build (`docker buildx build --platform linux/amd64,linux/arm64 …`)
is recommended if your runtime is ARM (e.g. AWS Graviton).

---

## 4. VMware (vSphere VM with Docker Compose)

Simplest, fully self-hosted. Ideal for on-prem / sovereign-by-default.

1. Provision a Linux VM (e.g. Ubuntu 22.04, 2 vCPU / 4 GB / 40 GB) on vSphere.
2. Install Docker Engine + Compose plugin.
3. Copy the repo (or just `docker-compose.yml` + `.env`) to the VM:
   ```bash
   cp .env.example .env
   # edit .env: set SECRET_KEY, POSTGRES_PASSWORD, BREAKGLASS_PASSWORD,
   #            SEED_DEMO=false, COOKIE_SECURE=true (if TLS terminates upstream)
   docker compose up -d --build       # or: pull the prebuilt image and `up -d`
   ```
4. Put a TLS reverse proxy in front (nginx / HAProxy / vSphere LB) forwarding
   `443 → VM:8080`, and set the `X-Forwarded-*` headers (uvicorn runs with
   `--proxy-headers`).
5. **Backups**: the compose file ships an optional `pg_dump` sidecar — enable it
   with `docker compose --profile backup up -d`, or snapshot the VM/volume.

This is the only target where the bundled PostgreSQL container is used; on the
managed-cloud options below, use the **managed** database instead.

---

## 5. Google Cloud (GCP) — Cloud Run + Cloud SQL (recommended)

Serverless, scales to zero, managed Postgres.

1. **Database**: create a **Cloud SQL for PostgreSQL 16** instance + a database +
   user.
2. **Image**: push to **Artifact Registry**.
3. **Service**: deploy to **Cloud Run**, attaching the Cloud SQL instance:
   ```bash
   gcloud run deploy tribe-run-tracker \
     --image REGION-docker.pkg.dev/PROJECT/REPO/tribe-run-tracker:1.0 \
     --region REGION --port 8000 --allow-unauthenticated \
     --add-cloudsql-instances PROJECT:REGION:INSTANCE \
     --set-env-vars POSTGRES_HOST=/cloudsql/PROJECT:REGION:INSTANCE,POSTGRES_DB=tribe,POSTGRES_USER=tribe,COOKIE_SECURE=true,SEED_DEMO=false \
     --set-secrets SECRET_KEY=tribe-secret:latest,POSTGRES_PASSWORD=tribe-db-pw:latest,BREAKGLASS_PASSWORD=tribe-admin:latest \
     --min-instances 1 --max-instances 4
   ```
   - With the Cloud SQL **Unix socket**, `POSTGRES_HOST=/cloudsql/PROJECT:REGION:INSTANCE`
     and `psycopg2` connects over the socket.
   - Secrets come from **Secret Manager** (`--set-secrets`).
   - Keep `--min-instances 1` for the first rollout so migrations don't race; then
     raise `--max-instances` as needed.
4. **TLS / domain**: Cloud Run provides HTTPS out of the box; map a custom domain
   if desired. Cloud Run already sets `X-Forwarded-*`.
5. **Alternative**: GKE (Deployment + Service + managed cert) if you need
   long-running/VPC-native workloads.

---

## 6. S3NS — "Cloud de Confiance" (sovereign GCP)

S3NS exposes GCP services under European sovereignty controls, so the **GCP
recipe (section 5) applies unchanged**: Artifact Registry + Cloud Run (or GKE) +
Cloud SQL, within your S3NS-controlled project/organization.

Sovereignty-specific points:
- Provision **all** resources (Artifact Registry repo, Cloud SQL, Cloud Run/GKE)
  in **S3NS-approved regions** and under the S3NS organization, so data and keys
  stay within the trusted boundary.
- Use **CMEK** (customer-managed encryption keys) via the S3NS key management for
  Cloud SQL and the registry where required by your sovereignty posture.
- Keep **SSO** internal: point `OIDC_*` / `SAML_*` at your sovereign IdP
  (e.g. PingFederate via SAML — already supported).
- No code change is needed — the app is cloud-agnostic; only the project,
  region, keys and IdP differ from a standard GCP deployment.

---

## 7. AWS — ECS Fargate + RDS

1. **Database**: create **RDS for PostgreSQL 16** (Multi-AZ for HA), a DB and user.
2. **Image**: push to **ECR**.
3. **Service**: an **ECS Fargate** service behind an **Application Load Balancer**:
   - Task container port **8000**; ALB target group → 8000 with health check
     `GET /api/health`.
   - Env from the task definition; secrets from **Secrets Manager / SSM** mapped to
     `SECRET_KEY`, `POSTGRES_PASSWORD`, etc.
   - `POSTGRES_HOST` = the RDS endpoint; open the security group from the ECS tasks
     to RDS:5432.
   - Set `COOKIE_SECURE=true`, `SEED_DEMO=false`.
   - Run the service in private subnets; the ALB (public subnets) terminates TLS
     (ACM cert) and forwards `X-Forwarded-*`.
4. **First rollout**: deploy `desiredCount=1` (migrations), then scale out. Or run
   migrations as a one-off `aws ecs run-task` with the same image (the entrypoint
   migrates and you can stop it after).
5. **Alternative**: **AWS App Runner** (image + env/secrets + RDS) for a simpler,
   ALB-free setup.

---

## 8. Azure — Container Apps + PostgreSQL Flexible Server

1. **Database**: **Azure Database for PostgreSQL — Flexible Server** (v16), a DB
   and user. Enable VNet/private access if possible.
2. **Image**: push to **Azure Container Registry (ACR)**.
3. **App**: **Azure Container Apps**:
   ```bash
   az containerapp create -n tribe-run-tracker -g RG --environment ENV \
     --image REGISTRY.azurecr.io/tribe-run-tracker:1.0 \
     --target-port 8000 --ingress external \
     --min-replicas 1 --max-replicas 4 \
     --env-vars POSTGRES_HOST=SERVER.postgres.database.azure.com POSTGRES_DB=tribe POSTGRES_USER=tribe COOKIE_SECURE=true SEED_DEMO=false \
     --secrets tribe-secret=... db-pw=... admin-pw=... \
     --env-vars SECRET_KEY=secretref:tribe-secret POSTGRES_PASSWORD=secretref:db-pw BREAKGLASS_PASSWORD=secretref:admin-pw
   ```
   - Container Apps provides external HTTPS ingress and `X-Forwarded-*`.
   - Secrets via Container Apps secrets (or Key Vault references).
   - Keep `--min-replicas 1` for the first migration, then scale.
4. **Alternative**: **App Service for Containers** (single image) + the same
   Flexible Server.

---

## 9. Post-deployment checklist

- [ ] `GET /api/health` returns `{"status":"ok"}` through the load balancer.
- [ ] First admin login works (break-glass `BREAKGLASS_EMAIL` / `BREAKGLASS_PASSWORD`,
      or the random password printed in the logs).
- [ ] `SECRET_KEY` and `POSTGRES_PASSWORD` are **not** defaults and come from a
      secret manager.
- [ ] `COOKIE_SECURE=true` and the app is only reachable over HTTPS.
- [ ] `SEED_DEMO=false` (no demo tribes/squads in production).
- [ ] SSO configured if used (`OIDC_*` or `SAML_*`); redirect/ACS URLs point at the
      real public hostname.
- [ ] Database backups scheduled (managed automated backups, or the `pg_dump`
      sidecar on VMware).
- [ ] Migrations ran (`alembic upgrade head`) — check the startup logs.

### Loading the real organization (optional)

Helper scripts live in `backend/scripts/`:
- `seed_real_org.py` — wipes org content (keeps user accounts) and loads the real
  tribe/squads with products/hardware.
- `prune_users.py` — keeps the admin + one impersonation account per role.

Run them once against the deployed container, e.g.:
```bash
docker compose exec -T app python - < backend/scripts/seed_real_org.py
```
(or the platform equivalent of `exec` into the running container). These are
**destructive** — review before running on a populated database.

---

## 10. Sizing & scaling

- **App**: 0.5–1 vCPU / 512 MB–1 GB per replica is plenty; scale replicas behind
  the LB. The scheduler is multi-replica safe (advisory lock).
- **Database**: a small managed instance (1–2 vCPU) covers typical tribe usage;
  size storage for snapshots/audit retention (configurable via
  `AUDIT_RETENTION_DAYS` / `PROGRESS_RETENTION_DAYS`).
- **TLS**: always terminate TLS upstream (LB/ingress); the app trusts
  `X-Forwarded-*` via `--proxy-headers`.

See also `docs/05-security.md` and `docs/06-operations-runbook.md`.
