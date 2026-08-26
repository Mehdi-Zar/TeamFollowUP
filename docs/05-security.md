# 05 - Security Model

## Authentication

| Method | Mechanism |
|--------|-----------|
| Local password | Argon2 hash (`argon2-cffi`); `POST /api/auth/login` sets a signed session cookie |
| OIDC | Authlib authorization-code + PKCE (`/api/auth/oidc/*`); user matched/created by `auth_subject`/email |
| SAML | `python3-saml` (`/api/auth/saml/*`) |
| Break-glass admin | Bootstrapped on first boot (`bootstrap.ensure_breakglass`); password from `BREAKGLASS_PASSWORD` or random (logged once) |

Session = Starlette `SessionMiddleware` (itsdangerous-signed cookie), `same_site=lax`,
`max_age = session_max_age_seconds` (12h). Impersonation ("view as") is admin-only and stamps the
session with `impersonator_id`.

## Public URL and SSO callback URLs

Everything an IdP needs to know about this app is `<public base URL> + <fixed path>`:

| What the IdP asks for | Value |
|-----------------------|-------|
| OIDC redirect URI | `<public base URL>/api/auth/oidc/callback` |
| SAML SP entity ID | `<public base URL>/api/auth/saml/metadata` |
| SAML ACS URL | `<public base URL>/api/auth/saml/acs` |

So only the base URL is ever configured (`authconfig.derive_sso_urls`). It is the
address a **browser** uses, not the port the container listens on: behind a Gateway
the pod speaks HTTP on `:8000` while the public URL is HTTPS on `:443`. Sources, most
specific first: the `public_base_url` saved in **Admin → Authentication**, then the
`PUBLIC_BASE_URL` environment variable, then the incoming request (uvicorn runs with
`proxy_headers=True`, so `X-Forwarded-Proto` / `-Host` are honoured), which is correct
for local dev and any single-hostname deployment.

Each URL can still be pinned individually when an IdP registration mandates a specific
value; a "pin" that merely restates the derivation is collapsed back to empty on save,
so it keeps following the base URL rather than freezing a hostname that will change.

The same effective base URL is fed to `python3-saml` when rebuilding the request
(`saml._prepare_request`), because strict mode validates the assertion's `Destination`
against it: the internal pod URL would fail that check behind a TLS-terminating proxy.

## Transport security (TLS termination)

Two supported models, selected by `TLS_ENABLED`:

- **`false` (default, recommended)** - the app serves **plain HTTP on `:8000`** and
  the infrastructure terminates TLS (GKE Gateway API, ALB, reverse proxy). This is
  the deployment model documented in `docs/12`.
- **`true`** - the app **terminates TLS itself** on a single port, **8443**, with no
  external reverse proxy required.

In both cases there is **no HTTP→HTTPS redirect listener**: redirection is an
infrastructure concern (e.g. the GKE Gateway API redirect route), never the app's.

With `TLS_ENABLED=true` (`app/server.py` + `app/tls.py`):

- **Out of the box:** if no certificate is configured, a **self-signed** cert is
  generated on first boot (`tls.generate_self_signed`, CN `localhost` + SANs), so
  the site is HTTPS immediately. Browsers warn until it is trusted - expected for
  internal use.
- **Bring your own cert** from **Administration → HTTPS / Certificats** (admin-only):
  - import a **PEM** certificate (+ intermediates) and its private key (optionally
    passphrase-protected), or a **PFX / PKCS#12** bundle;
  - manage the **root** and **intermediate CA** store (intermediates are appended
    to the served chain);
  - regenerate a self-signed cert with a custom CN/SAN.
- **Source of truth = the database** (`AppSetting` key `tls`); on boot and on every
  change the material is written to `CERT_DIR` (`/app/certs`) and the **live
  `SSLContext` is hot-reloaded** (`ssl.SSLContext.load_cert_chain`), so a new
  certificate takes effect **without restarting the container**. The private key
  is never returned by the API; uploads are audited (`tls_config.*`).

Set **`COOKIE_SECURE=true`** as soon as the site is reachable over HTTPS, whichever
model terminates it, so session cookies are `Secure`. It must stay `false` for a
plain-HTTP local run (the compose default): a browser will not send a `Secure` cookie
over `http://localhost`, and login would silently fail. Endpoints: `GET /api/admin/tls-config`,
`POST /api/admin/tls-config/{self-signed,import-pem,import-pfx,ca}`,
`DELETE /api/admin/tls-config/ca/{id}`.

## SSO provisioning & access approval

**SSO authenticates *who* you are; the app authorizes *whether* you may enter.** An
IdP login is necessary but not sufficient - identity ≠ access.

- **Account lifecycle** (`users.status`): `pending → active → disabled`. Only
  `active` accounts may use the app. Locally-created and break-glass accounts are
  `active`; SSO-provisioned ones start `pending`.
- **Two gates at the SSO callback** (`_provision` + `authconfig`):
  1. **Email-domain allowlist** (`allowed_email_domains`, optional) - outside the
     allowed domains, no account is even created.
  2. **Manual approval** (`require_approval`, default on) - new accounts are
     `pending` and gain nothing until a manager validates them.
- **Authorization gate** (`deps.get_current_user`) - every protected endpoint
  requires `status == "active"`; otherwise `403 access_pending|access_disabled`.
  Only `/api/auth/me` + `/me/permissions` resolve any-status (so the SPA can show
  the "pending / revoked" screen). A `disabled` account also fails local login.
- **Delegated, scoped validation** (`app/access.py`, `POST /api/access-requests/*`):
  admins validate anyone (any role/tribe); tribe leaders validate into **their
  tribe** (squad_leader/member); squad leaders validate into **their own squad**
  (member). The *visibility* of the pending queue is broad (a new account has no
  tribe yet) but the *grant* is strictly scoped - and **deny** (disable) is reserved
  to admin / tribe leaders. Every decision is audited (`access.approve|deny`).
- **Decision history** (`GET /api/access-requests/history`, `access.decision_history`):
  the review screen shows what has already been handled, not only what is queued.
  It is read from the **audit trail**, the only place that records *who decided*:
  once validated, an account is indistinguishable from any other. Entries cover the
  SSO arrivals (`user.provisioned.oidc|saml`) and the decisions taken on them
  (`access.approve|deny`), newest first. Scope mirrors the delegation model:
  gatekeepers (admin, tribe leader) see every decision, a squad leader sees the ones
  they took themselves.
- Reviewers are notified (in-app + best-effort email) of new requests; the user is
  notified on approval. *(SCIM auto-deprovisioning is a future enhancement; the
  disable flow covers manual revocation.)*

## Checking an IdP before rolling it out

**Administration → Authentification** carries a *Tester la connexion à l'IdP* button
per protocol (`POST /api/admin/auth-config/test`, `app/ssotest.py`). It answers the
question an administrator has before enabling SSO, without asking a real user to
attempt a login, and returns an ordered list of checks so a failure names the field
to fix instead of reporting "connection error".

- It probes **what is on screen**, saved or not, so a change can be validated before
  it is committed. It is read-only and signs nobody in.
- **OIDC**: discovery document reachable, announced issuer consistent with the
  configured one, authorization/token/JWKS endpoints present, signing keys
  retrieved, PKCE S256 advertised (a warning, not a failure, since some IdPs support
  it silently), and the client credentials. The credential probe is an
  `authorization_code` request carrying a bogus code: client authentication is
  evaluated *before* the grant, so `invalid_client` means wrong id/secret while
  `invalid_grant` means the credentials were accepted. A `client_credentials` probe
  cannot be used, as Keycloak checks whether the grant is enabled first and answers
  `unauthorized_client` even for a wrong secret.
- **SAML**: native stack present, metadata source reachable and parsed, IdP entity ID
  and SSO endpoint, signing-certificate expiry (a classic silent breakage), and
  finally the **SP settings assembled and validated by python3-saml** exactly as the
  login path would. That last step turns a settings defect into a red line on a
  button instead of a 500 during someone's first login.

Outbound calls go to URLs the administrator supplied, which is the trust level the
login path already has (only an admin sets an issuer or a metadata URL, and the app
fetches both during a real login). Timeouts are short so a wrong host fails fast.

## Authorization (defense in depth)

Three independent layers, all enforced **server-side** (the SPA only hides UI):

1. **Role tiers** - `admin > tribe_leader > squad_leader > member` (+ custom persona keys).
   Coarse guards: `require_admin`, `require_tribe_or_admin`, `require_writer`.
2. **Persona → capability matrix** (`personasconfig`) - section access (`dashboard, roadmap, org,
   feed, reporting, mysquads, leaves`) per persona, enforced by `require_capability(cap)`.
   Admin-configurable in **Admin → Personas**. See [ADR-0005](adr/0005-persona-capability-model.md).
3. **Module on/off** (`modulesconfig`) - `require_module(module[,feature])` returns 404 when a feature
   is disabled (a disabled service is indistinguishable from a missing one).

Plus **tribe scoping** (`assert_tribe_scope`, `visible_tribe_id`) and **ownership**
(`assert_can_edit_squad`) for data-level isolation. Every privileged mutation writes to `audit_log`.

**Leaves** add a dedicated guard `can_manage_leave(viewer, target)` (admin, the target's tribe leader, or
a squad leader of a squad the target belongs to): it gates approve/edit/cancel-for-others and the
visibility of the private motif. Absences are otherwise readable by anyone in the same tribe; the leave
type and detail are public.

## OWASP Top 10 (2021) - quick assessment

| # | Risk | Status |
|---|------|--------|
| A01 Broken Access Control | **Mitigated** - layered server-side guards + tribe scoping + tests (`test_rbac*`, `test_personas`, `test_review_access`). |
| A02 Cryptographic Failures | **Partial** - Argon2 for passwords; **session cookie `https_only=False`** and a **default `secret_key`** must be overridden in prod (see TD/risks). |
| A03 Injection | **Mitigated** - SQLAlchemy ORM/parameterized queries; Pydantic validation; SPA escapes; report HTML uses `html.escape`. |
| A04 Insecure Design | **Mitigated** - explicit RBAC, derived statuses, immutable snapshots. |
| A05 Security Misconfiguration | **Action needed** - prod must set `SECRET_KEY`, `POSTGRES_PASSWORD`, `BREAKGLASS_PASSWORD`, HTTPS, and `https_only` cookie. See `.env.example`. |
| A06 Vulnerable Components | **Process gap** - no dependency scanning/Dependabot yet (CI added; see roadmap). |
| A07 Auth Failures | **Mitigated** - Argon2, session expiry, break-glass guarded; **no account lockout / rate limiting** (tracked). |
| A08 Integrity Failures | **Mitigated** - audit log; immutable snapshots; signed cookie. |
| A09 Logging & Monitoring | **Partial** - `audit_log` + app logs; **no centralized monitoring/alerting** (tracked). |
| A10 SSRF | **Low** - outbound only to configured SMTP/IdP. |

## Risk matrix

| ID | Risk | Likelihood | Impact | Priority | Mitigation |
|----|------|-----------|--------|----------|------------|
| SEC-1 | Default `secret_key` / Postgres password used in prod | Med | High | **P0** | Enforce env override; fail-fast if defaults in non-dev |
| SEC-2 | Cookie `https_only=False` (cookie theft over HTTP) | Med | High | **P0** | Set `https_only=True` behind TLS; HSTS |
| SEC-3 | No rate limiting / lockout on `/login` | Med | Med | P1 | Add IP/user throttling (e.g. slowapi) |
| SEC-4 | CSRF on cookie-auth mutations (SameSite=Lax partial) | Low | Med | P1 | Add CSRF token or `SameSite=Strict` for mutations |
| SEC-5 | No dependency vulnerability scanning | Med | Med | P1 | Dependabot + `pip-audit`/`npm audit` in CI |
| SEC-6 | Cross-tribe name disclosure via milestone dependency label | Low | Low | P2 | Accepted (inter-team dependency by design) |
| SEC-7 | No audit-log retention/rotation | Low | Low | P2 | Define retention + archival |

## Secrets management

Configuration comes from environment variables (Pydantic Settings, `backend/app/config.py`).
**Defaults are dev-only.** See [`backend/.env.example`](../backend/.env.example) for the full list.
Production must inject: `SECRET_KEY`, `POSTGRES_PASSWORD`, `BREAKGLASS_PASSWORD`, OIDC/SAML and SMTP
credentials - via the orchestrator's secret store (never committed).

### GCP authentication for audit-log export (keyless by default)

The audit-log export to **GCS / BigQuery** (Admin → Logs) authenticates through
Google's recommended ladder, **keyless first** ([ADR-0012](adr/0012-gcp-auth-keyless.md)):

- **`adc` (default)** - Application Default Credentials: the **attached service
  account** (Workload Identity Federation for GKE, or the Cloud Run/GCE identity).
  **No secret stored** in the app or DB.
- **`wif`** - Workload Identity Federation via an `external_account` config file
  (not a key) for workloads running **off** Google Cloud.
- **`impersonation`** - an ADC base identity impersonating a target service account.
- **`key`** - a downloaded JSON key. **Discouraged** (long-lived secret; Google
  advises `iam.disableServiceAccountKeyCreation`). Kept for compatibility, stored
  masked in `app_settings`, shown behind a warning in the UI.

Prefer keyless in production so no Google credential ever lives in the database.
On GKE this requires binding the pod's Kubernetes ServiceAccount to a Google
service account - see the deployment guide's IAM section.
</content>
