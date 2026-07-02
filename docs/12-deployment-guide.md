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
6. **HTTPS is built in.** The app serves **HTTPS itself on port 8443** (with a
   self-signed cert by default) and redirects plain HTTP on **8080** to it — so it
   is secure out of the box. Import your own certificate (PEM/PFX) and manage CAs
   from **Administration → HTTPS / Certificats**, no restart needed. You may still
   put a load balancer / reverse proxy in front (TLS passthrough, or re-terminate
   with your own cert and forward to `:8443`/`:8080`). → each platform section.
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
  (native   │  FastAPI + built React SPA   │      (managed or self-hosted)
   TLS)     │  HTTPS :8443 · HTTP :8080 →↑ │
            └──────────────────────────────┘
```

- **Single image** (`Dockerfile`, multi-stage): builds the React SPA, then serves
  it together with the API from FastAPI/uvicorn over **native HTTPS on :8443**
  (`app/server.py`, `--proxy-headers` equivalent enabled), with an **HTTP :8080**
  listener that redirects to HTTPS. A self-signed cert is generated on first boot;
  replace it from the admin UI (see `05-security.md` → Transport security).
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
| `COOKIE_SECURE` | **prod** | `true` (default) — cookies sent only over HTTPS, which the app serves natively. |
| `APP_HTTPS_PORT` / `APP_HTTP_PORT` | | Host ports mapped to the container's `:8443` (HTTPS) / `:8080` (HTTP redirect). Defaults `8443` / `8080`. |
| `CERT_DIR` / `PUBLIC_HTTPS_PORT` | | Where TLS material is written (`/app/certs`), and the public HTTPS port used to build redirect URLs. |
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

Registry per platform: **GCP** → Artifact Registry (`REGION-docker.pkg.dev/PROJECT/REPO`),
**S3NS** → Artifact Registry on its own host (`u-france-east1-docker.s3nsregistry.fr/PROJECT/REPO` — see §6),
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

## 6. S3NS "Cloud de Confiance" from an air-gapped site (vendor) — full walkthrough

> **Who this is for.** You must put this app on **S3NS Trusted Cloud** ("Cloud de
> Confiance" — the vendor × Google sovereign cloud, SecNumCloud-qualified), and you
> do it from a **vendor-style air-gapped network** (no internet). You may never have
> deployed anything before. Every command below is copy-paste, and each one says
> *what it does* and *what you should see*. Anything in CAPITALS (`PROJECT`, `REPO`,
> `POOL_ID`…) is a value **you** replace — ask your S3NS administrator for the ones
> you don't have. The single S3NS region is **`u-france-east1`** (already filled in
> for you everywhere below).

### 6.0 The big picture (read this once — it makes the rest obvious)

The app is only **two things**: a **program** (one Docker image) and a **database**
(PostgreSQL). To run it: push the program image into S3NS, start PostgreSQL, then
start the program pointing at the database. That's the whole job.

What makes *your* case harder is **two walls** stacked on top of that simple idea:

```
  ┌──────────── WALL 1: the air gap ────────────┐   ┌──── WALL 2: S3NS ≠ normal GCP ────┐
 (1) machine WITH internet      (2) carry files     (3) machine INSIDE the S3NS network
   git clone + docker build  ─►  USB / secure   ─►  docker load → docker push → S3NS
   docker save  (→ .tar)        transfer             Artifact Registry → GKE runs it → Postgres
```

- **Wall 1 — the air gap.** Inside the secure zone there is *no internet*, so you
  cannot `docker build` (it downloads `node`/`python` base layers) or pull public
  images there. You do all the downloading **outside**, package it into files, carry
  them in, and load them.
- **Wall 2 — S3NS is a separate cloud, not normal Google Cloud.** Same tools
  (`gcloud`, `kubectl`, `docker`) but **different addresses**: a different login
  ("universe"), a different image-registry domain (`…s3nsregistry.fr`, *not*
  `pkg.dev`), and a **single region** `u-france-east1`. §6.3–6.5 handle this.

Order of play: one-time setup (§6.2 checklist, §6.3 gcloud, §6.4 registry) → move the
image in (§6.5) → create the cluster (§6.6) → pick a database (§6.7) → deploy (§6.8)
→ HTTPS (§6.9) → check (§6.10). Future updates are just §6.5 + one command (§6.12).

### 6.1 What's different about S3NS (the limitations, in plain words)

| Limitation | What it means for you | Where |
|---|---|---|
| **Separate "universe"** (not google.com) | `gcloud` must point at S3NS domains (`s3nsapis.fr`, `cloud.s3nscloud.fr`) and you log in through **your company IdP** (Workforce Identity Federation), not a Google account. | §6.3 |
| **Custom image registry** | Images live at `u-france-east1-docker.s3nsregistry.fr/…`, **not** `…-docker.pkg.dev/…`. Every tag uses that host. | §6.4–6.5 |
| **One region only** | Everything goes in **`u-france-east1`** (zones `-a/-b/-c`). No choice to make. | all |
| **Limited service catalogue** | ~30 services, not all of GCP. The ones this app needs **are** available: **Artifact Registry, GKE, Cloud SQL, Cloud Load Balancing, IAM, KMS, VPC**. Verify any time with `gcloud services list --available`. | §6.6–6.7 |
| **Air-gapped operations** | No internet inside: build & download **outside**, transfer, push to the S3NS registry; GKE then pulls **internally**. | §6.5 |
| **Sovereign encryption** | Data is encrypted at rest by **S3NS-managed keys** by default — nothing to do. If policy requires **your own keys**, use **Cloud KMS** (available) and turn on CMEK for GKE/Cloud SQL. | optional |

No application code change is needed. Point SSO at your **internal IdP**
(`SAML_*` / `OIDC_*`, already supported — e.g. PingFederate via SAML).

### 6.2 Before you start — the checklist

Get these from your S3NS / platform administrator and write them down:

- **Project ID** (`PROJECT`) — your S3NS project.
- **Region** — always `u-france-east1` (no need to ask).
- **Workforce pool + provider IDs** (`POOL_ID`, `PROVIDER_ID`) — they identify your
  company login. Needed once, in §6.3.
- **IAM roles on your account**: *Artifact Registry Administrator* (create repo +
  push), *Kubernetes Engine Admin* (deploy), and *Cloud SQL Admin* only if you pick
  managed Postgres (§6.7 option B).
- **Two machines**:
  1. an **internet machine** (laptop / external VM) with **Docker** — to build &
     download;
  2. an **inside machine** on the S3NS network with **Docker**, **gcloud** and
     **kubectl** — to push & deploy. *(If one machine reaches both the internet and
     S3NS, skip the save/transfer/load steps.)*
- **An approved way to move files** across the gap (sanctioned USB, data diode,
  transfer portal — follow your site's rules).
- **A TLS certificate** for your service hostname (your PKI/security team issues it).
  Public Let's Encrypt can't validate an internal-only name, so you provide the cert
  yourself in §6.9.

### 6.3 One-time: point `gcloud` at the S3NS "universe" (on the inside machine)

Plain `gcloud` talks to Google; these commands make it talk to **S3NS** instead.

```bash
# 1) Keep S3NS settings in their own profile (so they don't clash with normal gcloud)
gcloud config configurations create s3ns
gcloud config configurations activate s3ns

# 2) Tell gcloud this is the S3NS universe (its API domain)
gcloud config set universe_domain s3nsapis.fr

# 3) Build a login file tied to YOUR company identity provider.
#    POOL_ID / PROVIDER_ID come from your admin (see §6.2).
AUDIENCE="locations/global/workforcePools/POOL_ID/providers/PROVIDER_ID"
gcloud iam workforce-pools create-login-config "$AUDIENCE" \
  --universe-cloud-web-domain="cloud.s3nscloud.fr" \
  --universe-domain="s3nsapis.fr" \
  --output-file="wif-login-config.json"

# 4) Log in (opens your org's IdP), then choose project + region
gcloud auth login --login-config=wif-login-config.json
gcloud config set project PROJECT
gcloud config set compute/region u-france-east1
```

*What you should see:* `gcloud config list` now shows `universe_domain = s3nsapis.fr`,
your `project`, and `region = u-france-east1`. If `gcloud projects list` returns your
project, the connection works.

### 6.4 One-time: create the image registry (Artifact Registry)

A "repository" is just a folder for your images inside S3NS.

```bash
# Create a Docker repository named "tribe" in the only region
gcloud artifacts repositories create tribe \
  --repository-format=docker --location=u-france-east1 \
  --project=PROJECT --description="Tribe Run Tracker images"

# Let docker authenticate to the S3NS registry host (note: s3nsregistry.fr, NOT pkg.dev)
gcloud auth configure-docker u-france-east1-docker.s3nsregistry.fr
```

From now on, every image is named:
`u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/NAME:TAG`.

---

### 6.5 Bring the image across the air gap (step by step)

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

> In the commands below, replace `PROJECT` with your S3NS project id. The region is
> always `u-france-east1` and the repo is `tribe` (created in §6.4) — already filled in.

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

**Step 7 — Make sure docker can push to S3NS.** You already pointed `gcloud` at the
S3NS universe and logged in (§6.3) and let docker authenticate (§6.4). If this is a
fresh machine, do §6.3 + §6.4 first. To re-check the docker credential helper:
```bash
gcloud auth configure-docker u-france-east1-docker.s3nsregistry.fr
```

**Step 8 — Re-tag the images for YOUR S3NS registry, then push**
```bash
# App image
docker tag tribe-run-tracker:1.0 \
  u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/tribe-run-tracker:1.0
docker push u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/tribe-run-tracker:1.0

# Postgres (only if running it in-cluster — skip if you use managed Cloud SQL)
docker tag postgres:16-alpine \
  u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/postgres:16-alpine
docker push u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/postgres:16-alpine
```

**Step 9 — Confirm the images are there:**
```bash
gcloud artifacts docker images list \
  u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe
```
You should see `tribe-run-tracker` (and `postgres` if you pushed it). The images now
live in S3NS; GKE pulls them with **no internet**. For every new version, repeat
steps 2 → 9 with a new tag (`:1.1`, …) — see §6.12.

---

### 6.6 Create the GKE cluster

GKE is the container runtime we use on S3NS. **Autopilot** means Google/S3NS manage
the nodes for you — you only deploy pods. Create it once, then load its credentials
so `kubectl` talks to it:
```bash
gcloud container clusters create-auto tribe-cluster --region u-france-east1
gcloud container clusters get-credentials tribe-cluster --region u-france-east1
```
*Check:* `kubectl get nodes` eventually lists nodes (Autopilot adds them on demand).

### 6.7 Choose your database, then 6.8 deploy

Pick **one** database option, then continue to §6.8:
- **Option A — Postgres inside the cluster** (simplest; fewest moving parts; uses the
  `postgres:16-alpine` image you pushed in §6.5). Good to get running fast.
- **Option B — Cloud SQL for PostgreSQL** (managed: automatic backups, HA). Create a
  *Cloud SQL for PostgreSQL 16* instance in `u-france-east1`, give it a **private IP**
  on your VPC, then in §6.8 set `POSTGRES_HOST` to that private IP and **skip** the
  Postgres StatefulSet. (No public internet is involved — it stays inside S3NS.)

### 6.8 Deploy the application on GKE

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
          image: u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/postgres:16-alpine
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
          image: u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/tribe-run-tracker:1.0
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

### 6.9 Put HTTPS in front

The app speaks plain HTTP on port 8000 — **never** expose that directly. Terminate
TLS in front of it. In an internal/sovereign setup you use **your own certificate**
(public Let's Encrypt can't validate an internal name). Load your cert + key as a
secret and attach an Ingress:
```bash
kubectl create secret tls tribe-tls --cert=server.crt --key=server.key
```
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: tribe-ingress
  annotations: { kubernetes.io/ingress.class: "gce-internal" }   # internal HTTP(S) LB
spec:
  tls: [{ hosts: ["tribe.internal.example"], secretName: tribe-tls }]
  rules:
    - host: tribe.internal.example
      http:
        paths:
          - path: /
            pathType: Prefix
            backend: { service: { name: tribe-app, port: { number: 8000 } } }
```
Apply it (`kubectl apply -f ingress.yaml`), point your internal **DNS** record
(`tribe.internal.example`) at the load balancer address
(`kubectl get ingress tribe-ingress`), and keep `COOKIE_SECURE=true`. The LB sets
`X-Forwarded-*`, which the app honours (`--proxy-headers`). *(If you set the app
`Service` to `port: 8000` instead of 443, the Ingress backend port stays 8000 too.)*

### 6.10 Verify it works

```bash
kubectl get pods                       # tribe-app + postgres should be Running
kubectl logs deploy/tribe-app | grep -i "migration\|secours"   # migrations + break-glass pwd
curl -k https://tribe.internal.example/api/health              # {"status":"ok"}
```
Then open the URL in a browser, log in with the break-glass admin
(`BREAKGLASS_EMAIL` / the password you set, or the random one printed in the logs on
first boot), and finish setup (SSO, SMTP, backups) from the admin UI (§9–§10).

### 6.11 When something fails (the usual suspects)

| Symptom | Likely cause | Fix |
|---|---|---|
| Pod stuck `ImagePullBackOff` | wrong registry host, image not pushed, or no pull permission | Check the `image:` host is `u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/…`; re-run §6.5 step 9 to confirm it exists; ensure the cluster's service account has *Artifact Registry Reader*. |
| `gcloud` errors / wrong account | gcloud not on the S3NS universe | Re-run §6.3; check `gcloud config list` shows `universe_domain = s3nsapis.fr`. |
| `docker push` denied | docker not authenticated to S3NS | Re-run `gcloud auth configure-docker u-france-east1-docker.s3nsregistry.fr` (§6.4). |
| App pod crashes, logs show DB connection refused | wrong `POSTGRES_HOST` / DB not up | Option A: `kubectl get pods` — is `postgres` Running? Host must be `postgres`. Option B (Cloud SQL): host = the **private IP**, and the cluster VPC must reach it. |
| Two pods race the migration on first deploy | scaled out too early | First rollout with **1 replica** (the manifest already does); scale up only after it's healthy. |

### 6.12 Ship a new version later

You do **not** redo all of the above. The data stays in the database. Just:
```bash
# OUTSIDE (internet): build the new tag and save it
docker build -t tribe-run-tracker:1.1 . && docker save tribe-run-tracker:1.1 -o app-1.1.tar
# …transfer app-1.1.tar across the gap…
# INSIDE: load, tag, push, then roll the deployment
docker load -i app-1.1.tar
docker tag tribe-run-tracker:1.1 u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/tribe-run-tracker:1.1
docker push u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/tribe-run-tracker:1.1
kubectl set image deployment/tribe-app app=u-france-east1-docker.s3nsregistry.fr/PROJECT/tribe/tribe-run-tracker:1.1
kubectl rollout status deployment/tribe-app
```
The new pod runs `alembic upgrade head` automatically. **Back up the database first**
(§10). Full upgrade/rollback playbook: `13-maintenance-and-updates.md`.

> **S3NS references** (verify specifics against your tenant — the catalogue evolves):
> [S3NS docs](https://documentation.s3ns.fr/products) ·
> [set up gcloud for S3NS](https://documentation.s3ns.fr/docs/get-started-tpc/setup-gcloud) ·
> [regions & zones](https://documentation.s3ns.fr/docs/get-started-tpc/regions-and-zones) ·
> [Artifact Registry (Docker)](https://documentation.s3ns.fr/artifact-registry/docs/docker/store-docker-container-images).

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
