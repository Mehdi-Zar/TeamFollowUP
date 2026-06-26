# ADR-0003 — Session-cookie auth with OIDC/SAML/break-glass

**Status:** Accepted

## Context
Single-origin app (ADR-0001) needs authentication for internal users, with enterprise SSO options and
a guaranteed recovery path.

## Options Considered
1. **Signed session cookie** (server session) + Argon2 local passwords + OIDC + SAML + break-glass admin.
2. Stateless JWT in `Authorization` header.
3. Third-party auth (Auth0/Cognito) only.

## Decision
Option 1: Starlette `SessionMiddleware` (itsdangerous-signed cookie); local passwords hashed with
Argon2; OIDC via Authlib; SAML via python3-saml; a bootstrapped break-glass admin.

## Rationale
Same-origin cookies are simple and secure for an SPA (no token storage in JS → reduced XSS token
theft). SSO covers enterprise; break-glass guarantees recovery; local passwords cover small/offline setups.

## Consequences
- No bearer tokens in the browser; auth is automatic via cookie.
- Impersonation ("view as") is implemented by stamping the session.
- Logout/secret rotation invalidates sessions globally.

## Risks
- Cookie must be `Secure`/`https_only` behind TLS in prod (currently `https_only=False`) — see [05](../05-security.md).
- CSRF surface on cookie-auth mutations; `SameSite=Lax` mitigates partially → add CSRF token/Strict for mutations.
- No rate-limiting/lockout on login yet.

## Future Evolution
Enforce `https_only`; add login throttling and optional CSRF tokens; optional MFA.
</content>
