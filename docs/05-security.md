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

**The app serves plain HTTP on `HTTP_PORT` (default 8000) and never terminates
TLS.** A load balancer, a GKE Gateway, an ALB or any reverse proxy does it in
front of the container, HTTP→HTTPS redirection included. The reasoning is in
[ADR-0013](adr/0013-tls-terminated-by-the-infrastructure.md).

`app/server.py` binds that single listener with `proxy_headers=True` and
`forwarded_allow_ips="*"`, so `X-Forwarded-Proto` / `-Host` give the app the
original scheme and host: redirects, SSO callback URLs and the `Secure` cookie
decision all follow the public URL, not the container port. The flip side is that
the port must be reachable **through the proxy only**; a client that could reach
it directly could forge those headers.

Set **`COOKIE_SECURE=true`** as soon as the site is reachable over HTTPS, so
session cookies are `Secure`. It must stay `false` for a plain-HTTP local run (the
compose default): a browser will not send a `Secure` cookie over
`http://localhost`, and login would silently fail.

### Outbound TLS trust (the certificates the app *accepts*)

Serving TLS and trusting TLS are different problems, and the app only has the
second one. Whoever terminates the inbound connection, the app still **calls** an
OIDC/SAML IdP, an SMTP relay and a log sink, and on an internal network those are
routinely issued by a private authority no public trust store knows about.
Without that authority the very first OIDC call, the discovery fetch, fails with
`self signed certificate in certificate chain`, and SSO simply cannot work.

**Administration → Autorités de certification** is the supported answer, and the
only certificate screen the app has.

- Imported roots and intermediates are merged with the public roots into
  `CERT_DIR/trust_bundle.pem` (`app/trust.py`).
- Every call site we build verifies against it: OIDC discovery / JWKS / token
  exchange (`app/oidc.py`), SAML metadata (`app/saml.py`), SMTP STARTTLS and
  implicit TLS (`app/mail.py`), the SSO connectivity test (`app/ssotest.py`).
- `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` point at the same bundle for clients we
  do not construct ourselves (google-auth in `app/logexport.py`).
- Add and remove take effect on the **next outbound call, without a restart**, and
  are audited (`trust_store.add_ca`, `trust_store.remove_ca`). Endpoints:
  `GET /api/admin/trust-store`, `POST /api/admin/trust-store/ca`,
  `DELETE /api/admin/trust-store/ca/{id}`,
  `GET /api/admin/trust-store/ca/{id}/download`.

The public roots are always kept: replacing them would make the internal IdP
reachable and break every public endpoint in the same move. A bundle supplied at
deploy time (`SSL_CERT_FILE` baked into the image, as the Kubernetes bench does)
is used as the base, so it composes with the store instead of being replaced.

**There is no "skip verification" switch, by design.** Every outbound call gets an
explicit verifying context, including the two that are easy to get wrong: SAML
metadata is fetched verified, and SMTP `starttls()` is handed a context rather
than letting smtplib fall back to `ssl._create_stdlib_context()`, which means
`check_hostname=False` and `verify_mode=CERT_NONE`, that is the SMTP credentials
handed to whatever answered on that host and port. **The consequence to plan for:**
an internal SMTP relay or metadata URL with a privately issued certificate is
unreachable until its authority is imported above. That is the supported path.

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
   feed, reporting, mysquads, leaves`) per persona, admin-configurable in
   **Admin → Personas**. See [ADR-0005](adr/0005-persona-capability-model.md).
   Six of the seven are enforced by `require_capability(cap)` on the router that serves the
   section: `dashboard` (dashboard + `/api/reports/*`), `roadmap`, `org` (org + org export),
   `feed`, `reporting` (snapshots), `leaves`.
   **`mysquads` is a navigation capability only, and deliberately so.** The screen it opens
   drives routes that other sections also drive (`PUT /api/squads/{id}` carries the budget
   toggle on the squad page and the Steerco toggle on the entry page), so gating that route on
   the capability would break unrelated features for a persona that merely has the menu entry
   hidden. What protects the actions themselves is layer 1 plus ownership:
   `require_tribe_or_admin` on squad create and delete, and on update a tribe-scope check with
   the structural fields (leader, ordering, KPI/budget toggles) reserved to tribe leaders and
   admins. Turning `mysquads` off removes the entry point, not the permission: a squad leader
   who reaches the API directly can still edit their own squad, which is what their role says
   they may do.
3. **Module on/off** (`modulesconfig`) - `require_module(module[,feature])` returns 404 when a feature
   is disabled (a disabled service is indistinguishable from a missing one).

Plus **tribe scoping** (`assert_tribe_scope`, `visible_tribe_id`) and **ownership**
(`assert_can_edit_squad`) for data-level isolation. Every privileged mutation writes to `audit_log`.

**Co-leaders.** A squad has one named leader (`leader_user_id`, the identity an OTD is
committed on) and any number of **co-leaders** (`squad_coleaders`) holding exactly the
same rights over that squad. Every squad-level check goes through a single helper,
`deps.leads_this_squad(squad, user)` (and `deps.led_squad_ids` on the query side), so
naming a co-leader opens every door the leader has and not one more. Naming them is
**structural**: reserved to the tribe leader and the admin, like assigning the leader,
and a co-leader from another tribe is refused because it would open that squad through
the door tribe scope closes. Naming a plain member promotes them to `squad_leader`,
otherwise the account would be listed as a leader and refused by every check.

**Leaves** add a dedicated guard `can_manage_leave(viewer, target)` (admin, the target's tribe leader, or
a squad leader of a squad the target belongs to): it gates approve/edit/cancel-for-others and the
visibility of the private motif. Absences are otherwise readable by anyone in the same tribe; the leave
type and detail are public.

## OWASP Top 10 (2021) - quick assessment

| # | Risk | Status |
|---|------|--------|
| A01 Broken Access Control | **Mitigated** - layered server-side guards + tribe scoping + tests (`test_rbac*`, `test_personas`, `test_review_access`). |
| A02 Cryptographic Failures | **Partial** - Argon2 for passwords; **session cookie `https_only=False`** and a **default `secret_key`** must be overridden in prod (see TD/risks). Outbound TLS verifies against the admin-managed trust store (`app/trust.py`), SMTP and SAML metadata included, with no way to switch verification off. |
| A03 Injection | **Mitigated** - SQLAlchemy ORM/parameterized queries; Pydantic validation; SPA escapes; report HTML uses `html.escape`. |
| A04 Insecure Design | **Mitigated** - explicit RBAC, derived statuses, immutable snapshots. |
| A05 Security Misconfiguration | **Action needed** - prod must set `SECRET_KEY`, `POSTGRES_PASSWORD`, `BREAKGLASS_PASSWORD`, HTTPS, and `https_only` cookie. See `.env.example`. |
| A06 Vulnerable Components | **Process gap** - no dependency scanning/Dependabot yet (CI added; see roadmap). |
| A07 Auth Failures | **Mitigated** - Argon2, session expiry, break-glass guarded; **no account lockout / rate limiting** (tracked). |
| A08 Integrity Failures | **Mitigated** - audit log; immutable snapshots; signed cookie. |
| A09 Logging & Monitoring | **Partial** - `audit_log` + app logs; **no centralized monitoring/alerting** (tracked). |
| A10 SSRF | **Low** - outbound only to the configured SMTP relay, IdP and log sink, all admin-set, all certificate-verified against the trust store. |

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
