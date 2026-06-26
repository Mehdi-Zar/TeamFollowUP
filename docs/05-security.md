# 05 — Security Model

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

## Authorization (defense in depth)

Three independent layers, all enforced **server-side** (the SPA only hides UI):

1. **Role tiers** — `admin > tribe_leader > squad_leader > member` (+ custom persona keys).
   Coarse guards: `require_admin`, `require_tribe_or_admin`, `require_writer`.
2. **Persona → capability matrix** (`personasconfig`) — section access (`dashboard, roadmap, org,
   feed, reporting, review, mysquads`) per persona, enforced by `require_capability(cap)`.
   Admin-configurable in **Admin → Personas**. See [ADR-0005](adr/0005-persona-capability-model.md).
3. **Module on/off** (`modulesconfig`) — `require_module(module[,feature])` returns 404 when a feature
   is disabled (a disabled service is indistinguishable from a missing one).

Plus **tribe scoping** (`assert_tribe_scope`, `visible_tribe_id`) and **ownership**
(`assert_can_edit_squad`) for data-level isolation. Every privileged mutation writes to `audit_log`.

## OWASP Top 10 (2021) — quick assessment

| # | Risk | Status |
|---|------|--------|
| A01 Broken Access Control | **Mitigated** — layered server-side guards + tribe scoping + tests (`test_rbac*`, `test_personas`, `test_review_access`). |
| A02 Cryptographic Failures | **Partial** — Argon2 for passwords; **session cookie `https_only=False`** and a **default `secret_key`** must be overridden in prod (see TD/risks). |
| A03 Injection | **Mitigated** — SQLAlchemy ORM/parameterized queries; Pydantic validation; SPA escapes; report HTML uses `html.escape`. |
| A04 Insecure Design | **Mitigated** — explicit RBAC, derived statuses, immutable snapshots. |
| A05 Security Misconfiguration | **Action needed** — prod must set `SECRET_KEY`, `POSTGRES_PASSWORD`, `BREAKGLASS_PASSWORD`, HTTPS, and `https_only` cookie. See `.env.example`. |
| A06 Vulnerable Components | **Process gap** — no dependency scanning/Dependabot yet (CI added; see roadmap). |
| A07 Auth Failures | **Mitigated** — Argon2, session expiry, break-glass guarded; **no account lockout / rate limiting** (tracked). |
| A08 Integrity Failures | **Mitigated** — audit log; immutable snapshots; signed cookie. |
| A09 Logging & Monitoring | **Partial** — `audit_log` + app logs; **no centralized monitoring/alerting** (tracked). |
| A10 SSRF | **Low** — outbound only to configured SMTP/IdP. |

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
credentials — via the orchestrator's secret store (never committed).
</content>
