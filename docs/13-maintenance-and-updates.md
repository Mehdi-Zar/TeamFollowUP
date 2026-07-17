# 13 - Maintenance & Updates (shipping a new version without losing data)

This document answers a very specific, real-world question:

> *"I develop the app on my machine with my usual dev tooling. But the place where
> the app actually runs (S3NS / GKE, possibly air-gapped) has **no dev tooling and
> no internet**. How do I produce a new version here, push it over there, and update
> the running app **without losing the data**?"*

It is written for the exact setup of this project: **one Docker image** + **one
PostgreSQL database**, with schema changes handled by **Alembic migrations**. Read
[§0 of the Deployment Guide](12-deployment-guide.md) first if you have never
deployed it at all - this document is about *updating* an app that is already live.

---

## 1. The mental model: two separate worlds

The cleanest way to reason about this is to accept that you live in **two worlds
that never connect directly**:

| | **Dev world** (your laptop) | **Run world** (S3NS / prod) |
|---|---|---|
| Has internet | yes | no (or restricted) |
| Has dev tooling / CLI | yes | no |
| Has the source code | yes | **no - and it shouldn't** |
| Runs the app for users | no | yes |
| Holds the real data | no | **yes (PostgreSQL)** |

You **build** in the dev world and you **run** in the run world. The only thing
that crosses the gap is a **finished, self-contained artifact: the Docker image.**
Source code, `node_modules`, the dev tooling, and the internet all stay on the dev side.
This is what makes the air-gap manageable - you never need a toolchain in prod.

```
  DEV WORLD (laptop, internet, dev tooling)       RUN WORLD (air-gapped prod)
  ───────────────────────────────────            ────────────────────────────
  1. dev + test locally                           (nothing changes yet - app
  2. build image  →  app:1.1.0                     keeps serving users on 1.0.0)
  3. export the image to a file  ──────┐
                                       │  transfer the file (USB, bastion,
                                       │  internal Artifact Registry, etc.)
                                       └────────▶  4. back up the database
                                                   5. load the new image
                                                   6. run it once (migrations)
                                                   7. switch traffic → 1.1.0
                                                   8. smoke-test, keep 1.0.0 as
                                                      rollback for a while
```

---

## 2. The golden rule (the one thing that protects your data)

> **All state lives in PostgreSQL. The image is disposable; the database is
> precious.**

The app container is **stateless** (confirmed by the architecture: N replicas, no
local state). That means:

- Stopping, deleting, replacing, or rebuilding the **container** loses **nothing**.
- The only way to lose data is to delete the **database** or its **disk/volume**.

So the entire update strategy reduces to:

1. **Never** put the database on a disk that gets wiped on redeploy (use a managed
   Postgres, or a Kubernetes `PersistentVolume` / a named Docker volume that you
   never `docker compose down -v`).
2. **Always back up the database before an update** (§6). Cheap insurance.
3. Treat the image as a thing you can swap freely.

---

## 3. Version everything (so you can tell what's running and roll back)

Before you ship anything, give the new build an identity. Without versions, "the
new one" and "the old one" become indistinguishable and rollback is guesswork.

- **Bump the app version** in `backend/app/main.py` (`version="1.0.0"` → `1.1.0`).
  Use [SemVer](https://semver.org): patch for fixes, minor for features, major for
  breaking changes.
- **Tag the git commit**: `git tag v1.1.0 && git push --tags` (in the dev world).
- **Tag the Docker image with the same number** - never rely on `:latest` for
  prod. `:latest` is a moving target; `:1.1.0` is forever that exact build.

> Keeping git tag, app version, and image tag identical means that from a running
> container you can always answer "what source produced this?" - essential when
> the source and your dev tooling aren't there to consult.

---

## 4. Build the artifact in the dev world

On your laptop, after you finish a version and **all tests pass**
(`pytest` + frontend `tsc`/`vitest` - see [§8 Testing](08-testing-strategy.md)):

```bash
# 1. Build the production image, tagged with the version
docker build -t teamfollowup:1.1.0 .

# 2. Smoke-test it locally against a throwaway DB before you ever ship it
docker compose up -d --build      # uses the local compose Postgres
#   → open https://localhost:8443 (self-signed cert warning is expected), log in, click around
docker compose down               # (WITHOUT -v: keeps the volume)
```

Now turn the image into something that can cross the air-gap. **Pick one** of the
two transfer methods:

### 4.a - File transfer (true air-gap: USB stick / one-way bastion)

```bash
# Save the image (and its base layers) into a single tar file
docker save teamfollowup:1.1.0 -o teamfollowup-1.1.0.tar

# (optional) compress - these images are ~300-500 MB
gzip teamfollowup-1.1.0.tar     # → teamfollowup-1.1.0.tar.gz
```

Carry that one file across however your environment allows (removable media,
data-diode, approved file-transfer portal). Nothing else needs to travel.

### 4.b - Internal registry (S3NS Artifact Registry reachable from prod)

If the run world can pull from an **internal** registry (no public internet, but
an Artifact Registry inside the perimeter - the S3NS case), push there instead of
shipping a tar. This is the cleaner, more automatable option:

```bash
# Authenticate once to the internal Artifact Registry, then:
docker tag teamfollowup:1.1.0 <REGION>-docker.pkg.dev/<PROJECT>/<REPO>/teamfollowup:1.1.0
docker push                     <REGION>-docker.pkg.dev/<PROJECT>/<REPO>/teamfollowup:1.1.0
```

See [Deployment Guide §6 (S3NS, air-gapped)](12-deployment-guide.md) for the full
Artifact Registry + GKE wiring.

---

## 5. Apply the update in the run world

Now you're on the prod side. The app is still serving users on **1.0.0**. The data
is in PostgreSQL. Here is the safe sequence - **the order matters.**

> ⚠️ **Upgrading from an image that still had the :8080 listener?** Since the
> single-port change (see `CHANGELOG.md` → Breaking changes), the container serves
> **HTTPS :8443 only** - the :8080 HTTP→HTTPS redirect listener is gone. Before
> rolling the new image, remove anything that targets :8080: port mappings,
> monitoring probes, bookmarks/links, K8s `containerPort: 8080`, and the
> `APP_HTTP_PORT` / `HTTP_PORT` / `PUBLIC_HTTPS_PORT` variables. The HTTP→HTTPS
> redirect is now the Gateway's job (deployment guide §6.9.2).

### Step 1 - Back up the database (non-negotiable)

```bash
pg_dump -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -Fc \
        -f backup-before-1.1.0-$(date +%Y%m%d-%H%M).dump
```

Store this off the app host. If anything in the update goes wrong, this is your
undo button (§6).

### Step 2 - Get the new image onto the run world

- If you shipped a tar (4.a): `docker load -i teamfollowup-1.1.0.tar` (un-gzip
  first if needed). On Kubernetes nodes without a registry, `docker load` /
  `ctr images import` on each node, or import into the cluster's image store.
- If you pushed to an internal registry (4.b): nothing to do; the cluster will
  pull `:1.1.0` on demand.

### Step 3 - Run migrations with exactly ONE instance

This is the single most important rule for schema safety. The container's
entrypoint runs `alembic upgrade head` on start. If two fresh instances start at
once, they **race** on the schema. So for the first start of a new version:

- **docker compose / single VM**: you already have one app container - just
  recreate it with the new image; it migrates on boot.

  ```bash
  # point compose at the new tag (edit image: teamfollowup:1.1.0) then:
  docker compose up -d            # recreates the app container; runs migrations
  docker compose logs -f app      # watch for "alembic upgrade head" success
  ```

- **Kubernetes / GKE**: scale the app to **1 replica** (or run a dedicated
  one-shot migration `Job`) **before** rolling out, let it migrate, then scale
  back out:

  ```bash
  kubectl scale deploy/teamfollowup --replicas=1
  kubectl set image deploy/teamfollowup app=<...>/teamfollowup:1.1.0
  kubectl rollout status deploy/teamfollowup        # waits until healthy
  kubectl scale deploy/teamfollowup --replicas=3    # scale back out
  ```

  (The Deployment Guide already calls this out: *"deploy the first rollout with 1
  instance so two instances don't race the schema, then scale out."*)

### Step 4 - Smoke-test, then keep the old image around

- Log in as the break-glass admin, open the dashboard, a squad page, run an export.
- Watch logs for errors for a few minutes.
- **Do not delete the 1.0.0 image yet.** Keep it (and the DB backup) until you're
  confident. That pair *is* your rollback.

---

## 6. Backups & restore (your safety net)

**Back up regularly, not just before updates.** The compose file already includes a
backup sidecar; for managed Postgres use the platform's automated backups +
point-in-time recovery. A manual dump/restore pair:

```bash
# Backup (custom format, compressed, restorable selectively)
pg_dump -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f snapshot.dump

# Restore into a CLEAN database (e.g. after a bad migration)
pg_restore -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists snapshot.dump
```

Test your restore at least once in a staging DB - an untested backup is a rumor.

---

## 7. Rollback strategy

Two different things can go wrong, and they roll back differently:

| What broke | How to roll back |
|---|---|
| **App code** (bug in 1.1.0), schema unchanged or compatible | Just redeploy the **old image** (`:1.0.0`). Data untouched. Seconds. This is why you keep the old image. |
| **A migration** corrupted or mis-shaped data | Redeploy old image **and restore the pre-update DB dump** (§6, Step 1). This is why the backup is non-negotiable and comes *first*. |

> **Alembic migrations are effectively forward-only in practice.** Don't count on
> `alembic downgrade` to save you in prod - a downgrade that drops a column also
> drops its data. The reliable "undo" for a schema change is **restore the dump**,
> not downgrade. Plan migrations to be *expand/contract* (next section) so you
> rarely need to undo at all.

---

## 8. Make schema changes safe by design (expand / contract)

The way to almost never need a rollback is to make every schema change **additive
and backward-compatible**, so the old and new app versions can both run against
the new schema during the switch:

1. **Expand** - add new tables/columns as **nullable / with defaults**. Deploy.
   (Old code ignores them; new code uses them.) This is what migrations 0013-0016
   already do - e.g. `weekdays` defaults to `[]`, `hour` defaults to `8`.
2. **Migrate data** in a separate step if needed (backfill).
3. **Contract** - only once nothing uses the old column anymore, a *later* release
   removes it.

Never rename-in-place or drop-and-recreate a column that holds data in a single
migration; that's how data disappears. Add-new → backfill → switch reads →
drop-old, across separate releases.

---

## 9. Cleaner alternatives (if/when you can have them)

The tar-over-USB flow works with zero infrastructure, but if your environment
allows a bit more, these are progressively cleaner:

- **Internal Artifact Registry (recommended for S3NS).** Push `:1.1.0` to the
  in-perimeter registry from a connected build box; GKE pulls it. No tar juggling,
  natural versioning, easy rollback (`set image` to the old tag). This is the
  approach the S3NS section is built around.
- **A CI pipeline as the "build world".** Instead of building on your laptop, let
  an internal CI runner build, test, tag, and push the image on every git tag.
  You still *write* the code locally; CI produces the *artifact*
  deterministically. Removes "works on my machine" risk.
- **GitOps (Argo CD / Flux) for GKE.** The cluster watches a git repo of manifests
  and reconciles itself to the declared image tag. Updating = commit "image:
  1.1.0". Gives you history, review, and one-click rollback - all inside the
  perimeter.
- **Blue/green or canary** for zero-downtime: run 1.1.0 alongside 1.0.0, shift
  traffic gradually, roll back instantly by shifting it back. Only worthwhile once
  migrations are reliably expand/contract (§8), since both versions share one DB.

You don't need these on day one. Start with §4-§5; graduate to a registry, then CI,
then GitOps as the need (and the environment's openness) grows.

---

## 10. The update checklist (print this)

**Dev world**
- [ ] Feature done; `pytest` + frontend `tsc`/`vitest` green.
- [ ] Bump `version` in `backend/app/main.py`; `git tag vX.Y.Z`.
- [ ] `docker build -t teamfollowup:X.Y.Z .`
- [ ] Local smoke test (`docker compose up`, click around).
- [ ] Export artifact: `docker save … -o teamfollowup-X.Y.Z.tar` **or** push to internal registry.

**Run world**
- [ ] **`pg_dump` backup taken and stored off-host.**
- [ ] New image present (`docker load` or pullable from registry).
- [ ] Migrate with **one** instance / migration job; watch `alembic upgrade head` succeed.
- [ ] Health check green; smoke test (login, dashboard, a squad, an export).
- [ ] Scale back out (if K8s).
- [ ] Keep previous image **and** the DB backup until confident.
- [ ] (Later) prune old images once the new version is proven.

---

*See also:* [12 - Deployment Guide](12-deployment-guide.md) ·
[06 - Operations Runbook](06-operations-runbook.md) ·
[08 - Testing Strategy](08-testing-strategy.md).
