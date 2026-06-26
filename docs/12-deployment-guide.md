# 12 — Deployment Guide (VMware · GCP · S3NS · AWS · Azure)

This guide explains how to deploy **Tribe Run Tracker** to production on the main
target platforms. The application ships as **one container image** plus a
**PostgreSQL** database — nothing else is required.

---

## 0. In plain words — the whole deployment, start to finish

If you have never deployed anything before, read this section first. It is the
entire process in order, with no jargon. Each step points to the detailed section
that follows.

The app is just **two things talking to each other**: a *program* (one Docker
image) and a *database* (PostgreSQL, where all the data is stored). Deploying =
starting the database, then starting the program and telling it where the database
is. That's it. Everything below is detail around those two moves.

**Do them in this order:**

1. **Get a machine (or a cloud project).** A Linux VM, a Kubernetes cluster, or a
   cloud account — whatever you have. This is where the app will run. → see your
   platform's section (4 VMware, 5 GCP, 6 S3NS, 7 AWS, 8 Azure).
2. **Create the database.** Stand up a PostgreSQL 16 instance and write down 5
   things: its **host**, **port** (usually 5432), **database name**, **user**, and
   **password**. You'll hand these to the app in the next step. → §3, §4.
3. **Prepare the settings (environment variables).** Copy `.env.example` and fill
   in: the 5 database values above, a long random `SECRET_KEY`, and a
   `BREAKGLASS_EMAIL` (the emergency admin login). In production also set
   `COOKIE_SECURE=true` and `SEED_DEMO=false`. → §2.
4. **Get the program (the image).** Either build it from the source
   (`docker build`) or pull a pre-built image. If your servers have **no internet**,
   you build it on a connected machine, save it to a file, carry the file over, and
   load it on the other side. → §9 (build), §6.x (air-gapped transfer).
5. **Start it.** Run the image and pass it the settings from step 3. On the very
   first start the app **creates all its tables automatically** (it runs the
   database migrations for you) and creates the emergency admin account. → §3, §4.
6. **Put HTTPS in front.** The app listens on plain port 8000; never expose that
   directly. Place a load balancer / reverse proxy (or the cloud's ingress) in
   front to handle the `https://` certificate. → each platform section.
7. **Check it works.** Open the site, log in with the break-glass admin, and click
   around. Then configure SSO, SMTP (for emails), backups, etc. from the admin UI. → §10.

**When a new version comes out later**, you do **not** redo all this. You only
swap the image for the newer one and restart — the data stays in the database
untouched. That update procedure has its own document: **`13-maintenance-and-updates.md`**.

> **The one rule that protects your data:** the database is the only thing that
> holds state. As long as you don't delete the database (or its disk/volume), you
> can stop, restart, upgrade, or rebuild the program as often as you like without
> losing anything. Back up the database (§10) before any upgrade.

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

S3NS is GCP under European sovereignty controls, with three constraints that make
it different from a vanilla GCP deployment:

1. **No Cloud Run** — the only container runtime is **GKE Autopilot**. So you run
   the app as a Kubernetes Deployment (section 6.2), not as a Cloud Run service.
2. **No CMEK** — you use **Google-managed encryption keys** (the default). Nothing
   to configure; data is encrypted at rest by Google's keys within the S3NS
   boundary.
3. **Often air-gapped** — the environment has **no internet access**. You cannot
   `docker pull`/`build` public images from inside. But you **can push images to
   your S3NS Artifact Registry**, and GKE pulls from it internally. Section 6.1
   walks you through this step by step.

Keep all resources (Artifact Registry, GKE, Cloud SQL) in your **S3NS project /
region**, and point SSO (`OIDC_*` / `SAML_*`) at your **internal IdP** (e.g.
PingFederate via SAML — already supported). No application code change is needed.

---

### 6.1 Get the image into the S3NS Artifact Registry (air-gapped, step by step)

**The problem.** Your vendor/S3NS environment has no internet. A `docker build`
downloads base images (`node`, `python`) from the internet, and GKE would
normally pull images from the internet too — both impossible here. **The trick:**
prepare every image on a machine **that has internet**, carry them into the S3NS
zone, push them to your **S3NS Artifact Registry**, then let GKE pull from there
(internal, no internet needed).

**What you need:**
- A **build machine WITH internet** (your laptop or an external VM) with **Docker**.
- A way to move files into the air-gapped zone (approved USB / secure transfer).
- An **inside machine** (in the S3NS zone) that can reach the S3NS Artifact
  Registry, with **Docker** and **gcloud** installed.
- *(If one machine has BOTH internet and access to the S3NS registry, skip the
  save/transfer/load steps and push directly.)*

> Replace `REGION` / `PROJECT` / `REPO` everywhere with your S3NS values
> (e.g. region `europe-west9`, your project id, and your Artifact Registry repo name).

**Step 1 — On the internet machine: get the source**
```bash
git clone https://github.com/Mehdi-Zar/TeamFollowUP.git
cd TeamFollowUP
```

**Step 2 — Build the application image** (this is the only build; it downloads
`node` + `python` and bakes the React frontend + FastAPI backend into one image):
```bash
docker build -t tribe-run-tracker:1.0 .
```

**Step 3 — Also fetch the database image you'll use.** Two choices:
- **Cloud SQL** (managed Postgres on S3NS, recommended): you don't need a Postgres
  image, but you need the Cloud SQL connector:
  ```bash
  docker pull gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.11.0
  ```
- **Postgres inside the cluster** (simpler to reason about, no managed DB):
  ```bash
  docker pull postgres:16-alpine
  ```

**Step 4 — Save the images to files** (so you can carry them):
```bash
docker save tribe-run-tracker:1.0 -o app.tar
docker save postgres:16-alpine    -o postgres.tar          # if in-cluster Postgres
# or
docker save gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.11.0 -o sqlproxy.tar   # if Cloud SQL
```

**Step 5 — Move the `.tar` files into the S3NS zone** (approved USB / transfer).

**Step 6 — On the inside machine: load the images back into Docker**
```bash
docker load -i app.tar
docker load -i postgres.tar        # or sqlproxy.tar
```

**Step 7 — Log in to your S3NS Artifact Registry**
```bash
gcloud auth login                                   # with your S3NS credentials
gcloud auth configure-docker REGION-docker.pkg.dev  # lets docker push to that registry
```

**Step 8 — Re-tag the images to point at YOUR registry, then push**
```bash
# App image
docker tag tribe-run-tracker:1.0 \
  REGION-docker.pkg.dev/PROJECT/REPO/tribe-run-tracker:1.0
docker push REGION-docker.pkg.dev/PROJECT/REPO/tribe-run-tracker:1.0

# Postgres (only if running it in-cluster)
docker tag postgres:16-alpine \
  REGION-docker.pkg.dev/PROJECT/REPO/postgres:16-alpine
docker push REGION-docker.pkg.dev/PROJECT/REPO/postgres:16-alpine
```

Your images now live in the S3NS Artifact Registry. GKE can pull them with **no
internet**. For every new version, repeat steps 2 → 8 with a new tag (`:1.1`, …).

---

### 6.2 Deploy on GKE Autopilot

**Create the cluster** (Autopilot, in your S3NS region):
```bash
gcloud container clusters create-auto tribe-cluster --region REGION
gcloud container clusters get-credentials tribe-cluster --region REGION
```

**Secrets** (`tribe-secrets.yaml` — never commit real values):
```yaml
apiVersion: v1
kind: Secret
metadata: { name: tribe-secrets }
type: Opaque
stringData:
  SECRET_KEY: "<32+ random chars>"
  POSTGRES_PASSWORD: "<db password>"
  BREAKGLASS_PASSWORD: "<admin password>"
```

**Database — option A: Postgres in the cluster** (`postgres.yaml`, uses the image
you pushed in 6.1):
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata: { name: postgres }
spec:
  serviceName: postgres
  replicas: 1
  selector: { matchLabels: { app: postgres } }
  template:
    metadata: { labels: { app: postgres } }
    spec:
      containers:
        - name: postgres
          image: REGION-docker.pkg.dev/PROJECT/REPO/postgres:16-alpine
          env:
            - { name: POSTGRES_DB, value: tribe }
            - { name: POSTGRES_USER, value: tribe }
            - { name: POSTGRES_PASSWORD, valueFrom: { secretKeyRef: { name: tribe-secrets, key: POSTGRES_PASSWORD } } }
          ports: [{ containerPort: 5432 }]
          volumeMounts: [{ name: data, mountPath: /var/lib/postgresql/data }]
  volumeClaimTemplates:
    - metadata: { name: data }
      spec: { accessModes: [ReadWriteOnce], resources: { requests: { storage: 10Gi } } }
---
apiVersion: v1
kind: Service
metadata: { name: postgres }
spec:
  selector: { app: postgres }
  ports: [{ port: 5432, targetPort: 5432 }]
```
*(Option B — Cloud SQL: create a Cloud SQL for PostgreSQL 16 instance and add the
`cloud-sql-proxy` image you pushed as a sidecar in the app pod; set
`POSTGRES_HOST=127.0.0.1`. Skip the StatefulSet above.)*

**The application** (`app.yaml`):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: tribe-app }
spec:
  replicas: 1                      # keep 1 for the first rollout (migrations); scale up after
  selector: { matchLabels: { app: tribe-app } }
  template:
    metadata: { labels: { app: tribe-app } }
    spec:
      containers:
        - name: app
          image: REGION-docker.pkg.dev/PROJECT/REPO/tribe-run-tracker:1.0
          ports: [{ containerPort: 8000 }]
          env:
            - { name: POSTGRES_HOST, value: postgres }   # or 127.0.0.1 with Cloud SQL proxy
            - { name: POSTGRES_DB, value: tribe }
            - { name: POSTGRES_USER, value: tribe }
            - { name: SEED_DEMO, value: "false" }
            - { name: COOKIE_SECURE, value: "true" }
            - { name: BREAKGLASS_EMAIL, value: admin@local }
            - { name: SECRET_KEY, valueFrom: { secretKeyRef: { name: tribe-secrets, key: SECRET_KEY } } }
            - { name: POSTGRES_PASSWORD, valueFrom: { secretKeyRef: { name: tribe-secrets, key: POSTGRES_PASSWORD } } }
            - { name: BREAKGLASS_PASSWORD, valueFrom: { secretKeyRef: { name: tribe-secrets, key: BREAKGLASS_PASSWORD } } }
          readinessProbe: { httpGet: { path: /api/health, port: 8000 }, initialDelaySeconds: 20, periodSeconds: 10 }
---
apiVersion: v1
kind: Service
metadata:
  name: tribe-app
  annotations: { networking.gke.io/load-balancer-type: "Internal" }   # internal LB (sovereign)
spec:
  type: LoadBalancer
  selector: { app: tribe-app }
  ports: [{ port: 443, targetPort: 8000 }]
```

**Apply, then check:**
```bash
kubectl apply -f tribe-secrets.yaml -f postgres.yaml -f app.yaml
kubectl rollout status deployment/tribe-app
kubectl logs deploy/tribe-app | grep -i "migration\|secours"   # migrations + break-glass
```
The container entrypoint runs `alembic upgrade head` on start, so the first pod
migrates the DB. Put TLS termination on the internal load balancer / Ingress and
forward `X-Forwarded-*` (the app runs with `--proxy-headers`). Once healthy, scale
with `kubectl scale deployment/tribe-app --replicas=3` (the in-process scheduler
is multi-replica safe via a Postgres advisory lock).

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
