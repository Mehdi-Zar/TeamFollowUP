# Changelog

## Unreleased

### Security
- **OTD owner assignment is validated against the tribe (cross-tribe disclosure fix).**
  `POST/PUT /api/otds` accepted an arbitrary `owner_user_id`; a tribe leader could
  assign a squad leader of **another tribe**, who would then see that tribe's OTD
  (title, committed date, budget ref, milestones) through the owner-based
  visibility rule. The owner is now required to be a **squad leader of the OTD's
  own tribe** (`otds._validate_owner`, fail-closed 400 otherwise). Regression test
  in `tests/test_otds.py`.
- **Security review (this branch): no other exploitable issue found.** The keyless
  GCP auth (ADC/WIF/impersonation) keeps TLS verification on (httpx default), the
  `assert_leads_squad` guard is fail-closed, and export responses build their
  `Content-Disposition` filename from integers only. The WIF `external_account`
  config can point its `credential_source` at an admin-chosen URL/file, but that
  endpoint is `require_admin` (same trust level that already controls
  `universe_domain`/`syslog_host`), and executable sources stay disabled unless
  `GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES=1` - no lower-privilege attack path.

### Breaking changes
- **Single-port container: HTTPS :8443 only.** The plain-HTTP listener on :8080
  (301 → HTTPS) is removed, along with its admin toggle ("Rediriger HTTP vers
  HTTPS"), the `PUT /api/admin/tls-config` endpoint, and the `HTTP_PORT` /
  `PUBLIC_HTTPS_PORT` / `APP_HTTP_PORT` variables. HTTP→HTTPS redirection is now
  exclusively an infrastructure concern (e.g. the GKE Gateway API redirect route,
  `docs/12` §6.9.2). K8s manifests need `containerPort: 8443` only; nothing may
  target :8080 anymore.

### Security
- **Keyless GCP authentication for audit-log export (GCS / BigQuery).** The export
  no longer assumes a service-account **JSON key** (a long-lived secret Google
  ranks last and recommends disabling org-wide). A new **auth method** selector in
  **Admin → Logs** offers, keyless-first: **`adc`** (attached service account /
  Workload Identity for GKE - the new default, no secret stored), **`wif`**
  (Workload Identity Federation via an `external_account` config file, for off-GCP
  workloads), **`impersonation`** (base ADC + IAM `generateAccessToken`), and
  **`key`** (the legacy JSON key, kept behind an in-UI warning). Token acquisition
  goes through `google-auth`; the data-plane calls stay on httpx via a small
  transport adapter, so no `requests` dependency is added. The S3NS universe is
  honoured for the STS/IAM endpoints too. Existing key users are unaffected (their
  method stays `key`). New dependency: `google-auth`. See
  [ADR-0012](docs/adr/0012-gcp-auth-keyless.md); infra binding in the deployment
  guide §6.10.a.

### Features
- **Milestone-dependency deck (PPTX/HTML).** New export listing every jalon that
  depends on another team, grouped by the entity it waits on. Each line shows the
  jalon, its source squad·tribe, the quarter, the owner and the status. By default
  it keeps only **cross-tribe** dependencies (`mode=cross_tribe`, the real
  coordination points); `mode=all` includes same-tribe and free-text actors. The
  table paginates across slides so no dependency is ever dropped. Available from
  the Export menu ("Dépendances") and via `GET /api/reports/dependencies.pptx`
  (and `.html`), scoped like the other exports (`tribe_id` / `squad_ids` / `year`).

### Fixes
- **Dead setting removed: `PROGRESS_RETENTION_DAYS`.** It referred to the
  `progress_updates` table dropped in migration 0017 and had no effect; removed
  from `config.py`, compose and the `.env` examples. Docs (02/03/07/08/10/11)
  no longer reference `progress.py` / `progress_updates`, and the data-model
  reference now covers all 27 tables (initiatives, OTD, budgets, key messages,
  committees, report baselines, API keys).
- **Dashboard PPTX export no longer silently drops squads.** Multi-squad decks
  were capped at 40 detail slides, so a large selection (e.g. a full org of 130+
  squads) lost every squad past the 40th - the deck came back missing squads like
  "Catalog 12" with no error. The cap is raised well above any realistic squad
  count, and if it is ever exceeded the deck ends with a visible "+N autres
  squads" notice instead of dropping them without a trace. Covered by new
  regression tests plus a randomized loop-mode fuzz harness
  (`backend/tests/fuzz_export_loop.py`).

## 1.0 - V1 (production-ready)

First delivered version. Built on the initial tribe-steering tool, with the
following additions and a finalization pass.

### Squad content
- **Products & hardware** per squad: one or more product names, plus optional
  hardware names, set on squad **create/edit** (tribe leader / admin, and the
  squad leader for their own squad). Shown at the top of the squad page with the
  squad leader.
- **OTD** - the squad's committed annual objectives are surfaced at the top of the
  squad page (label "OTD"), above the detailed roadmap.
- **Key messages** - curated success / alert / risk notes per squad, timestamped
  (date & time), shown below the roadmap.
- **Governance / comitologie** - optional section (module `committees`, off by
  default) where the squad leader declares the squad's recurring committees
  (name, objective, frequency, day, time, duration, participants, active flag),
  shown as a clean table with a modal editor. Standing (not year-scoped); on the
  squad page and readable by the tribe leader for oversight. Admin toggles it
  from *Services*.
- **Budget tracking** - the tribe leader sets the **total** envelope; the squad
  leader reports **spent** (to date) and **forecast** (projected landing) + a
  comment. Status is derived from forecast (else spent) vs total:
  **on track** (< 90%) · **at risk** (90-100%) · **over** (> 100%, with overrun
  amount & %). **Visible only** to the admin, the tribe leader, and the squad's
  own leader (enforced server-side; a squad leader never sees another squad's
  budget, and cannot change the total).

### Exports
- Single-squad **HTML export** rendered with the application's own stylesheet and
  component markup, mirroring the squad page exactly (Initiatives → OTD →
  Roadmap → Key messages → Budget), without the global report scaffolding.
- Single-squad **PPTX export** restyled to match (navy header, white rounded
  cards, RAG badges, progress bars), same section order. Budget figures are
  gated to authorized viewers in both formats.

### Administration
- **Redesigned admin navigation**: a grouped left sidebar (Organisation ·
  Configuration · Authentification & Email · Modération & Journaux) replacing the
  flat tab bar. Sober, text-only, role-aware (empty groups hidden).

### Security / Transport (HTTPS)
- **Native HTTPS** - the app now terminates TLS itself: HTTPS on **:8443** and an
  HTTP **:8080** listener that 301-redirects to HTTPS (`app/server.py`). No reverse
  proxy required to be secure.
- **Self-signed by default** - a certificate is generated on first boot so the site
  is HTTPS out of the box.
- **Certificate management UI** (Administration → *HTTPS / Certificats*, admin-only):
  import **PEM + key** or **PFX/PKCS#12**, manage **root & intermediate CAs**,
  regenerate self-signed (CN/SAN), toggle HTTP→HTTPS redirect. Changes apply
  **hot** (live `SSLContext` reload) without restarting the container. The DB is the
  source of truth (`AppSetting` key `tls`); the private key is never exposed and all
  changes are audited. Compose now defaults `COOKIE_SECURE=true`.

### Data & operations
- Real organization loaded (Cloud Foundations Tribe + product/transverse squads
  with products & hardware). One-shot scripts under `backend/scripts/`
  (`seed_real_org.py`, `prune_users.py`).
- Static `index.html` is served with `Cache-Control: no-cache` so a new build is
  always picked up (no stale SPA after deploy).

### Docs & housekeeping
- New **[Deployment Guide](docs/12-deployment-guide.md)** (VMware · GCP · S3NS ·
  AWS · Azure).
- Untracked compiled artifacts (`__pycache__`/`*.pyc`), removed Office temp lock
  files, hardened `.gitignore`, organized one-shot scripts.

### Migrations
- `0013` squad budget + key messages · `0014` budget forecast ·
  `0015` squad products & hardware.
