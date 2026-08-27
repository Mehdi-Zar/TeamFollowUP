# Changelog

## Unreleased

### Fixed
- **The deployment guide handed you a mutable image tag, and that breaks Alembic.** The GKE
  manifests pinned `teamfollowup:1.0`, a tag anyone naturally re-pushes on the next build.
  Kubernetes defaults `imagePullPolicy` to `IfNotPresent` for every tag but `:latest`, so a
  node that already cached it keeps serving the old image - and the symptom is not "the old
  version is running", it is the pod dying on
  `Can't locate revision identified by '0027_steerco_entries'`, because the database has been
  migrated past what that stale image contains. The manifests now use the version as an
  immutable tag, the build step says never to re-push one, and §11 gains the failure with the
  three commands that settle it (what the database believes, what the image carries, and which
  image is really running **by digest**, since the tag lies). It also says plainly not to
  reach for `alembic stamp`: stamping backwards leaves the tables that migration created in
  place but unrecorded, so the next deployment tries to create them again. The same warning is
  in the maintenance guide, where upgrades actually happen.

## 2.1 - Observability, end-to-end tests, and the promises that were not kept (2026-08-27)

> **One behaviour change to know about before upgrading.** "Message retention" now
> really deletes feed posts past its window, where it used to only hide them. An
> instance with a non-zero value starts deleting on the next scheduler tick. That is
> what the setting always claimed to do; pinned posts are exempt. See *Fixed*.

### Added
- **Observability: the app finally measures itself.** The only operational signals were the
  logs and the audit trail, which say what happened but never whether it is happening more
  than usual. New `/metrics` endpoint in the Prometheus format (`app/metrics.py`), fed by a
  pure-ASGI middleware placed outside everything else, so the latency it records is the one
  the client experienced. Exposed: traffic, error rate and latency **per route template**,
  in-flight requests, connection-pool saturation, weekly-scheduler health, login outcomes
  (success, failure, throttled) and the deployed version.
  The route label carries the template (`/api/squads/{squad_id}`) and never the real path;
  two tests lock that property down, because a mislabelled counter is the easiest way to
  take the monitoring down, weeks later and with no visible link to the offending commit.
  A scrape queries no database. The endpoint can be protected with `METRICS_TOKEN` (bearer)
  and switched off with `METRICS_ENABLED=false`; the app warns at boot when it is left open
  while `PUBLIC_BASE_URL` is set, that is, when this is clearly not somebody's laptop.
  New dependency: `prometheus-client`.
- **A ready-to-run observability stack** in [`ops/`](ops): the scrape config, **seven alert
  rules** each commented one by one (down, error rate, latency excluding exports, exports too
  slow, pool exhausted, scheduler wedged, login-failure spike), a pre-declared Grafana
  datasource, and a `docker-compose.observability.yml` kept separate from the product's own.
  One command and you have graphs.
- **[17 - Observabilité](docs/17-observabilite.md)**: what each metric measures, the
  cardinality rule and why it is not negotiable, the six PromQL queries worth knowing taken
  apart piece by piece, how to build the dashboard, what each alert means and what to do when
  it fires, how to protect `/metrics`, and the transposition to Kubernetes (`ServiceMonitor`)
  and to GKE (`PodMonitoring`).

### Added
- **[20 - Données personnelles et rétention](docs/20-donnees-personnelles-et-retention.md).**
  The application describes an organisation: people, their roles, and their **absences**. That
  is personal-data processing whether or not anyone called it that. The document lists what is
  stored and why, how long each kind is kept, who can see it, and the exact queries to answer
  an access request or an erasure request - including the decisions erasure actually requires:
  leaves and feed posts are deleted, but audit entries are **detached** (`user_id = NULL`)
  rather than destroyed, because the trail answers a separate legitimate interest and the
  schema was built nullable for exactly that. It also names the two things that deserve
  attention rather than burying them: `org_members` can describe someone who never opened the
  application, and the free-text leave reason is a field where somebody can write a medical
  reason.
- **[19 - Plan de reprise](docs/19-plan-de-reprise.md): the restore procedure, as executed.**
  The roadmap has wanted a DR runbook since the first audit. This one states the RPO and RTO
  the shipped configuration actually gives (24 h and about 15 minutes) and what to change to
  move them, and its procedure was **run** rather than imagined: a witness record created,
  backed up, deleted from the live database, and found again in a database restored from that
  backup. It also gives the drill that verifies a backup **without touching production** - the
  restore goes into a throwaway database beside the real one - and states the residual
  weaknesses plainly: the backups live on the same host as the database, they are not
  encrypted, and nothing alerts when several fail in a row.
- **`app/import_org.py` went from 0% to 83% covered** (`tests/test_import_org.py`, 30 tests).
  It was the largest hole the new coverage measurement named, and it is the module that parses
  a file an administrator uploads: columns read **by position**, booleans written as words in
  two languages, an import that promises to be safe to re-run against a populated environment.
  Every one of those is a promise the code made and nothing was checking. The tests now hold it
  to all of them, including the round trip nobody had tied together: the blank template the app
  hands out must be readable by the parser that receives it back. They immediately found the
  `Tribu` bug above.
- **End-to-end tests, in a browser, against the real deployment** (`e2e/`, twelve tests,
  [18](docs/18-tests-e2e.md)). They drive the Docker image serving the built SPA and its API in
  front of a real PostgreSQL, not `vite dev` with a stubbed backend, because the bugs that
  justify an end-to-end suite are the ones that only exist once the pieces are assembled: a
  route guard that lets a member open Administration (the API returns 403, but the screen was
  shown), a build shipping a stale chunk, a session cookie the browser refuses to send, a
  dependency upgrade that passes typecheck and build then breaks at runtime. That last one is
  not hypothetical: this suite was written right after the move to React 19 and Vite 8, and it
  is what confirmed the app actually works rather than merely compiles.
  Covered: the login screen and its refusal to say which half of the credentials was wrong,
  logout really invalidating the session server-side, the route guard on a URL typed by hand,
  a tribe created and deleted through the running app, the audit trail recording it and the
  filter finding it, pagination that neither repeats nor skips a row, and a member being
  refused Administration by the navigation, by the URL and by the API.
  A new CI job starts the stack with `docker compose up -d --build`, waits for `/api/health`
  and runs them, publishing the logs and the HTML report as artefacts when it fails.

### Security
- **The shipped defaults are now visible in the product, not only in a log line.** The startup
  guard has warned about a default `SECRET_KEY` or database password since the first hardening
  pass, and that warning is read once, by whoever happened to deploy, and never again.
  **Administration > Ops** now lists every default still in use with the consequence spelled
  out (a default `SECRET_KEY` means anyone can forge a session cookie), and adds three the
  guard never covered: the example break-glass password, a session cookie left unmarked while
  a public URL is configured, and an open `/metrics`. Severity is raised to **critical** when
  `PUBLIC_BASE_URL` is set, which is the honest signal that this is not somebody's laptop -
  a security notice that fires on every developer machine is one everybody learns to ignore.
  Nine tests in `tests/test_insecure_defaults.py`, including the one that matters: a properly
  configured deployment reports nothing at all.
- **`react-router-dom` was vulnerable to an open redirect leading to XSS**
  ([GHSA-jjmj-jmhj-qwj2](https://github.com/advisories/GHSA-jjmj-jmhj-qwj2), plus
  [GHSA-wrjc-x8rr-h8h6](https://github.com/advisories/GHSA-wrjc-x8rr-h8h6): a backslash in a
  `<Link>` target or a `useNavigate` call escaping the app's origin). The whole 6.x line is
  affected and the fix only exists in 7.x, so the router moved to 7.18.2. Nothing in the app
  had to change: it uses `BrowserRouter` / `Routes` / `Link` / `NavLink` / `Navigate` /
  `Outlet` / `useLocation` / `useNavigate` / `useParams` / `useSearchParams`, all unchanged in
  v7. `npm audit` now reports **0 vulnerabilities**, production and development alike.
  Dependabot had not opened a pull request for this one.

### Fixed
- **"Message retention" retained everything.** The setting, offered in Administration >
  Settings as *Message retention (days, 0 = keep all)*, only ever **hid** older posts from the
  listing endpoint. They stayed in the database and in every backup, forever. An administrator
  who set it to satisfy a retention policy had satisfied nothing, and had no way of knowing.
  The hourly purge now really deletes feed posts past the window, along with their replies and
  reactions, through the ORM so the declared cascade runs (the foreign keys have no
  `ON DELETE CASCADE`, so a bulk delete would have failed). **Pinned posts are exempt**:
  pinning is somebody deciding this one stays, which is also how the listing already treated
  them. The admin screen now says plainly that the messages are permanently deleted.
  **Behaviour change**: an instance that already has a non-zero value will start deleting on
  the next scheduler tick. That is what the setting always claimed to do. Eight regression
  tests in `tests/test_retention.py`, where the module had two.
- **The backup sidecar was leaving zero-byte files that counted as backups.** It wrote
  `pg_dump` straight into the final filename, so a failed dump left an empty
  `tribe_AAAAMMJJ_HHMMSS.sql` behind: indistinguishable from a real backup, counted by the
  rotation, and therefore **pushing genuine backups out of the retention window**. Five of them
  were sitting in a running instance. The dump now goes to a temporary file and is published
  only once `pg_dump` has exited 0, the file is non-empty, and it ends with the marker
  PostgreSQL writes at the end of a complete dump; rotation runs only after a success, and only
  over files that really are backups. The success line reports the size, so a glance at the log
  says whether the backup is real.
- **A failed dump skipped the whole day.** The loop slept the full interval after a failure, so
  the usual cause - the database still coming up after a restart, which fixes itself in
  seconds - cost 24 hours of backups, silently. It now retries after `BACKUP_RETRY_SECONDS`
  (5 minutes) and prints the `pg_dump` error.
- **A blank "Annee" cell silently discarded the whole tribe.** The Excel reader dropped any row
  whose **first** cell was empty, which is right for the sheets where the first column is the
  name, and wrong for the `Tribu` sheet where the first column is the year. An administrator
  who left the year blank, a cell the importer is documented to default, got
  `400 : le fichier ne contient pas de tribu` about a file that plainly contained one. The
  `Tribu` sheet is now keyed on the tribe name. And a missing name raises a sentence naming the
  column to fill instead of reaching the database and coming back as an `IntegrityError` on
  `tribes.name`. Found by writing the tests below, which is the whole argument for writing them.
- **The SMTP admin panel was French-only.** Six labels (host, port, username, password, sender
  address, sender name) were hard-coded French strings, so an administrator running the app in
  English read them in French. The CI parity check cannot catch this: it compares the FR and EN
  key sets, and a string that never became a key is in neither. Now translated. A scan of the
  whole frontend found no other case.
- **Every form control in Administration has an accessible name.** Screen-reader users heard
  nothing on most of them: the visible `<label>` was a sibling of its field, never associated
  with it, and the inline editors in the tables have no visible label at all (the column header
  plays that role, which a screen reader reading a single cell never sees). All of them now
  carry the label, taken from the same i18n key so the two can never drift apart. Partial fix,
  and recorded as such in [10](docs/10-tech-debt-and-risk-register.md): the other pages are
  untouched, and clicking a label still does not focus its field, which needs `htmlFor`/`id`.

### Changed
- **`report.py` split: 2440 lines down to 1400.** The four PowerPoint decks moved to
  `reportpptx.py` (890 lines of python-pptx machinery that reads nothing like the HTML
  templating beside it), and the eleven declarations both formats share moved to
  `reportcommon.py`. The dependency runs one way only, `reportpptx` importing `reportcommon`
  and never `report`, and `report` re-exports the deck renderers so no caller had to change.
  Same discipline as below: a seventeen-test surface smoke test was written and run green
  first, and it earned its place immediately by catching two things the plan had missed - the
  roadmap HTML also uses the month labels, and two tests patch the slide cap, which now has to
  be patched on the module that reads it rather than on a re-exported name. Verified further by
  fetching all eight export endpoints from the running container and checking each returns a
  real document.
- **`AdminPage.tsx` split: 3085 lines down to a 152-line shell.** It was one file holding the
  navigation, the permission logic and twenty-five panels covering everything from TLS
  certificates to leave types. The panels now live in `src/pages/admin/`, one module per
  navigation group (`organisation`, `imports`, `configuration`, `authentication`, `oversight`,
  plus `shared` for the two hooks more than one panel needs), and `AdminPage.tsx` keeps only
  what it is: the shell that resolves which tabs a role may open and mounts the active one.
  The refactor was done **after** building the net that catches it, not before: a new
  end-to-end test opens all eighteen sections and asserts each renders without an error banner,
  an empty panel or a console error. It was green before the move and green after, which is the
  only reason a mechanical 3000-line move is defensible. That test stays.
- **Every pending dependency update applied and verified**, closing the thirteen Dependabot
  pull requests that had piled up. Backend: authlib 1.4 to 1.7.2, google-auth 2.38 to 2.56.3,
  PyJWT 2.10.1 to 2.13.0, argon2-cffi 23.1 to 25.1, psycopg2-binary 2.9.12. Frontend: React 18
  to 19.2, react-router-dom 7.18.2 (see above), and a coordinated build-toolchain upgrade -
  vite 5 to 8, vitest 2 to 4 and `@vitejs/plugin-react` 4 to 6 **have to move together**,
  which is exactly why the three separate pull requests could not be merged one by one. Also
  jsdom 25 to 30, `@types/node` 22 to 26, and the GitHub Actions to checkout v7 / setup-node v7
  / setup-python v7.
  React 19 removed the global `JSX` namespace from `@types/react`; three files now import the
  type from the module instead. Two consequences worth knowing: the initial bundle grew from
  317 to 382 KB (117 KB gzipped) between React 19 and router 7, and the production build got
  about three times faster.
  New guard: `tests/test_oidc_client.py` pins the Authlib surface the login actually calls.
  The real OIDC exchange is covered by the Kubernetes bench, which needs a cluster; a rename
  in a future Authlib release would otherwise go unnoticed until somebody clicks "Sign in".
- **Coverage is measured and enforced.** `pytest-cov` with a `fail_under` floor in
  `backend/.coveragerc`, run by the CI backend job. The floor is deliberately a **ratchet**
  set just under what the suite actually reaches (74% of `app/`), not an aspiration: a floor
  above reality fails the build on day one and gets deleted by the first person in a hurry.
  Entry points and one-shot data loaders are excluded, because counting code that is
  exercised by running the app rather than by tests lets real gaps hide behind a comfortable
  percentage. Coverage stays out of `addopts` so a local `pytest` does not pay for it.
  The measurement immediately named the largest genuine hole: `app/import_org.py`, 188
  statements at 0%, which parses an administrator-supplied Excel file. Recorded in
  [08](docs/08-testing-strategy.md). No frontend gate: with eleven unit tests the floor would
  sit at a number that protects nothing, and the real gap there is end-to-end coverage.
- **The audit log is paginated and filterable, and says who acted.** The screen rendered "the
  last 200 entries", which on an instance that has been running for a year answers no question
  at all: what an administrator needs is *who disabled this account* or *what happened on the
  12th*. `GET /api/audit-log` now takes `limit` / `offset` and filters on action (substring,
  case-insensitive), entity, acting user and a date range, and returns
  `{items, total, limit, offset}` - `total` counting the filtered set, so the screen can say
  how much it is not showing. The acting user is resolved server-side into `user_email` /
  `user_name` instead of the bare numeric id the table used to print; it stays null when the
  account has since been deleted, which the nullable foreign key allows on purpose. The admin
  screen gained the matching filter bar, a page size and pagination, with the action box
  debounced so typing does not fire a request per keystroke. **Breaking for any direct API
  consumer**: the response is now an object, not a bare list. Ten regression tests in
  `tests/test_audit_api.py`, where there were none.
- **Doc 16 now teaches the bench instead of listing it.** It assumed minikube, kubectl,
  OpenSSL and Docker were already installed, the scripts already understood, and the purpose
  of each command guessable. Rewritten so nothing is magic: why the bench exists at all (in
  production the app never speaks TLS, so testing SSO on `localhost:8000` proves nothing),
  installation of all five tools per operating system with the command that proves it worked,
  an inventory of the folder before any command is run, `make-pki.sh` explained flag by flag
  so it can be replayed by hand, what `run-tests.py` actually does in seven steps (it was not
  obvious at all that the driver configures the SSO itself through the admin API and resets it
  afterwards), the non-obvious parts of the manifests with the reason each is there, and a
  diagnosis section. The negative control is now three clicks in the admin screen instead of
  an opaque script.

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
- **Milestone-dependency deck (PPTX/HTML).** New export listing every jalon that
  depends on another team, grouped by the entity it waits on. Each line shows the
  jalon, its source squad·tribe, the quarter, the owner and the status. By default
  it keeps only **cross-tribe** dependencies (`mode=cross_tribe`, the real
  coordination points); `mode=all` includes same-tribe and free-text actors. The
  table paginates across slides so no dependency is ever dropped. Available from
  the Export menu ("Dépendances") and via `GET /api/reports/dependencies.pptx`
  (and `.html`), scoped like the other exports (`tribe_id` / `squad_ids` / `year`).

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
