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

## Transport security (native HTTPS / TLS)

The application **terminates TLS itself** - no external reverse proxy is required
to get HTTPS (though you may still put one in front). The launcher `app/server.py`
serves HTTPS on a **single port, 8443**. There is **no HTTP listener**: HTTP→HTTPS
redirection is an infrastructure concern (e.g. the GKE Gateway API redirect route),
never the app's.

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

Because the site is HTTPS by default, set **`COOKIE_SECURE=true`** (the compose
default) so session cookies are `Secure`. Endpoints: `GET /api/admin/tls-config`,
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
- Reviewers are notified (in-app + best-effort email) of new requests; the user is
  notified on approval. *(SCIM auto-deprovisioning is a future enhancement; the
  disable flow covers manual revocation.)*

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
