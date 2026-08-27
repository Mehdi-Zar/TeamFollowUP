# Changelog

## 2.0 - SSO driven by one public URL, single-port container (2026-08-27)

### Added
- **The Kubernetes/Keycloak bench is now part of the repository** (`bench/k8s-sso/`) with a
  step-by-step tutorial, [16 - Banc Kubernetes de bout en bout](docs/16-banc-kubernetes-sso.md).
  Four manifests, the Keycloak realm, the 18-check driver (`run-tests.py`) and an optional
  access-history seeder reproduce, on any machine, the exact chain the SSO work was validated
  against: app on a single plain-HTTP port behind an Envoy gateway that terminates TLS with an
  internal CA, two public names on one certificate, then a full OIDC login and a full SAML login
  against a real IdP. `make-pki.sh` generates the throwaway PKI, which stays gitignored. The
  app deployment is deliberately the one prescribed by §6.9 of the deployment guide, so running
  the bench also tests the documentation.
- **`backend/scripts/dump_openapi.py`** writes `docs/openapi.json` from the app's routes without
  starting a server, and `--check` fails when the committed snapshot is stale. The CI **Backend**
  job now runs that check on every push, so an unintended contract change surfaces in the pull
  request. The snapshot was already two endpoints behind (`/api/admin/auth-config/test` and
  `/api/access-requests/history`); it is now regenerated and accurate (140 paths). Closes TD-API-1.
- **"Test the connection to the IdP" button**, one per protocol, in Administration →
  Authentification (`POST /api/admin/auth-config/test`, `app/ssotest.py`). Returns an
  ordered list of checks so a failure names the field to fix rather than reporting a
  bare connection error: OIDC discovery, issuer consistency, endpoints, signing keys,
  PKCE, and the client credentials; for SAML, metadata retrieval, IdP entity ID and
  SSO endpoint, signing-certificate expiry, and the SP settings assembled and
  validated by python3-saml exactly as the login path does. It probes what is on
  screen, saved or not, so a change can be checked before it is committed, and it
  signs nobody in. Verified against a live Keycloak, including the failure paths
  (wrong secret, wrong client id, unreachable issuer, unreadable metadata).
- **Access history.** The review screen now shows what has already been handled, not
  only the pending queue (`GET /api/access-requests/history`): SSO arrivals and the
  approve/deny decisions taken on them, newest first, with who decided and where the
  person was placed. Read from the audit trail, the only place recording the author
  of a decision. Gatekeepers see everything; a squad leader sees their own decisions.

### Fixed
- **`e2e_test.py` asserted the shipped application name.** The check read
  `app_name == "Tribe Cockpit"`, so it broke on the rename and, more importantly, on any
  instance whose administrator had renamed the app, which the setting exists for. It now
  asserts the public config serves a name at all.
- **`LOG_FORMAT` and `LOG_LEVEL` were undocumented**, in neither `.env.example` nor the
  deployment guide's variable table, although `LOG_FORMAT=json` is what makes the logs
  parseable by GCP Cloud Logging and the manifests already set it. Both are now in the two
  `.env.example` files and in the guide's variable table, and `LOG_LEVEL` is passed through
  `docker-compose.yml` like every other knob (only `LOG_FORMAT` was).
- **Saving the auth page froze `PUBLIC_BASE_URL` into the database.** Every save
  of Admin → Authentication persisted the whole config, environment-derived values
  included, so the deployment's `PUBLIC_BASE_URL` became a stored override. After
  any single save, changing it in the manifest or `.env` had no effect and every
  SSO callback URL kept pointing at the previous hostname. The value is now
  persisted only when it actually differs from the environment, so the env var
  stays authoritative until an administrator really types something else. Found
  by moving a running Kubernetes bench from one hostname to another; regression
  tests in `tests/test_authconfig_urls.py`.
- **SAML login was impossible against any IdP that advertises a NameIDFormat**
  (Keycloak, PingFederate). `OneLogin_Saml2_IdPMetadataParser` returns an `sp`
  hint and a `security` block alongside `idp`, and `saml.build_settings` merged
  the whole thing with a flat `dict.update`, replacing our SP section with the
  one-key hint. python3-saml then rejected the settings with
  `sp_entityId_not_found,sp_acs_not_found` and every SAML endpoint answered 500.
  The merge now preserves the values we set and treats the parsed ones as
  suggestions. An IdP asking for signed AuthnRequests is honoured only when an SP
  key pair is configured, instead of making the settings unbuildable. Found by
  driving a real Keycloak from a Kubernetes bench; regression tests in
  `tests/test_saml_settings.py`.

### Changed
- **Version 2.0.0, and the first tagged release.** The project documented its own release
  procedure (bump `backend/app/main.py`, tag `vX.Y.Z`, build the image under that tag,
  `docs/13`) but had never applied it: the version stayed at `1.0.0` while this section grew,
  and the repository had no tag at all, so nothing linked a running container back to a
  commit. The major number reflects the breaking changes below (single-port container, the
  `:8080` redirect listener and `PUT /api/admin/tls-config` removed). `app/ops.py`'s
  `APP_VERSION` default, shown in Admin > Ops, follows, and `docs/openapi.json` was
  regenerated so the published contract announces the same version.
- **One name for the application: TeamFollowUP.** Three coexisted - "Tribe Run Tracker" in the
  README and `package.json`, "Tribe Cockpit" in the backend default `app_name`, the i18n `brand`
  key, the SPA `<title>`, the SMTP sender, the print header, the generated certificates and most
  of the documentation, and "TeamFollowUP" in the repository and the deployment guide. Everything
  now says TeamFollowUP. Existing instances are unaffected: `app_name` is an `AppSetting`, so only
  fresh installs pick up the new default.
- **Documentation figures refreshed against the code**: 289 backend tests over 32 modules (the
  testing strategy still claimed 131 over 13), 11 frontend tests, FR/EN parity on 1132 keys (not
  540), ~17k/~15k lines back/front. The deployment guide's opening summary still said the pod
  "serves HTTPS on :8443, its only port", contradicting §6.9 since the single-port change; it now
  states the port is chosen by `TLS_ENABLED`.
- **SSO configuration is now driven by one public URL.** The OIDC redirect URI and
  the SAML SP entity ID / ACS URL are no longer three absolute URLs to keep in sync
  by hand: they are derived from the app's **public base URL** plus a fixed path
  (`authconfig.derive_sso_urls`). The base URL comes from the new **URL publique**
  field in Administration → Authentification, else `PUBLIC_BASE_URL`, else the
  incoming request (`X-Forwarded-Proto` / `X-Forwarded-Host` are honoured), so a
  local run and any single-hostname deployment need no SSO URL configuration at all.
  Administration → Authentification displays the three resolved URLs ready to copy
  into the IdP; per-URL pinning moved under "Avancé". A pinned URL that merely
  restates the derivation is stored empty, so it keeps following the public URL
  instead of freezing a hostname. `OIDC_REDIRECT_URI`, `SAML_SP_ENTITY_ID` and
  `SAML_ACS_URL` now default to empty (they were `https://localhost:8443/…`, which
  leaked into every fresh install and every `.env` copied from the example).
- **SAML strict-mode validation uses the public URL.** `saml._prepare_request` now
  rebuilds the request from the effective base URL, so the assertion `Destination`
  check compares against the address the browser used and not the pod's internal
  one when a proxy terminates TLS.
- **Documentation and samples realigned on the plain-HTTP model.** `README`, `docs/02`,
  `docs/04`, `docs/06`, `docs/07`, `docs/12`, `docs/13`, `docs/14`, both `.env.example`
  files and `e2e_test.py` referred to `https://localhost:8443` as *the* address; they
  now describe the compose default (plain HTTP `:8000`, TLS terminated upstream) with
  `TLS_ENABLED=true` documented as the standalone alternative. The shipped `.env` also
  had `COOKIE_SECURE=true` against a plain-HTTP listener, which prevents the session
  cookie from being sent at all.

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
- **Single-port container, no HTTP→HTTPS redirect listener.** The plain-HTTP :8080
  listener (301 → HTTPS) is removed, along with its admin toggle ("Rediriger HTTP
  vers HTTPS"), the `PUT /api/admin/tls-config` endpoint and the
  `PUBLIC_HTTPS_PORT` variable. Redirection is now exclusively an infrastructure
  concern (e.g. the GKE Gateway API redirect route, `docs/12` §6.9.2); nothing may
  target :8080 anymore.
  The container binds exactly one port, chosen by `TLS_ENABLED`: plain **HTTP
  :8000** (`false`, the recommended model, what compose and the manifests set,
  variables `HTTP_PORT` / `APP_HTTP_PORT`) or **HTTPS :8443** (`true`, the app
  terminating TLS itself, variable `APP_HTTPS_PORT`). Match K8s `containerPort`,
  probe `scheme` and Service `targetPort` to the mode you run (`docs/12` §6.9/§6.10).

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
- Example organization loaded (Cloud Platform Tribe + product/transverse squads
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
