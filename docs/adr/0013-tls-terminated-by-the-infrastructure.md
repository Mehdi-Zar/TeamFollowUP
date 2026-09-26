# ADR-0013 - TLS is terminated by the infrastructure, never by the app

**Status:** Accepted, **Date:** 2026-09-10

## Context

The application shipped with **two serving modes**, selected by `TLS_ENABLED`
plus a toggle stored in `app_settings` and read at boot:

- **plain HTTP on `:8000`**, TLS terminated upstream by the Gateway/ALB. This is
  what `docker-compose.yml`, the Kubernetes bench and every real deployment use.
- **HTTPS on `:8443`**, uvicorn holding an `SSLContext` built from a certificate
  the administrator generated (self-signed) or imported (PEM/PFX) in
  **Admin → HTTPS**. This was the **default in code** (`tls_enabled: bool = True`)
  and, in practice, the path nobody ran.

The second mode carried a cost out of proportion to its use:

- **The unencrypted private key lived in the database**, in the `tls`
  `app_settings` blob, so it followed every `pg_dump` into the backups taken by
  the `backup` compose profile.
- **Two ports, two topologies, two runbooks.** The deployment guide carried a
  full §6.9 and §6.10 plus a comparison table for one application.
- **A toggle that could not apply itself.** The listener is bound at boot, so
  flipping it left `tls_enabled != tls_running`, which is where the "pending
  restart" banner, the `restart_pending` field and part of the Ops restart button
  came from.
- **A footgun**: flipping the toggle on a Gateway-fronted deployment moves the
  pod from 8000 to 8443 at the next restart, in front of a Gateway that still
  expects 8000. And the cookie policy (`COOKIE_SECURE`) has to follow a mode an
  administrator can change from a web page they are authenticated on.

In front of that, no benefit: a load balancer, a Gateway, an Envoy or any reverse
proxy terminates TLS better (rotation, ACME, ciphers, HTTP/2) and one is already
present everywhere the app runs.

**What is not in question** is the *outbound* trust store (`trust.py`): a
deployment behind a load balancer still calls an internal IdP, an internal SMTP
relay and a log sink, routinely issued by a private authority. That store is
independent of who terminates the inbound TLS and stays managed from the UI.

## Options Considered

1. **Keep both modes, flip the default to plain HTTP.** Cheapest change, but the
   private key stays in the database and the second topology stays in the docs.
2. **Keep in-app TLS for standalone installs, read the material from files
   only.** Removes the key from the database but keeps the two listeners, the
   toggle, and the restart dance.
3. **Serve plain HTTP only, TLS is the infrastructure's job.** Chosen.

## Decision

**The application serves plain HTTP on `HTTP_PORT` (default 8000) and never
terminates TLS.** `app/server.py` binds a single listener with `proxy_headers` +
`forwarded_allow_ips`, so `X-Forwarded-Proto` / `-Host` still give the app the
original scheme and host for redirects, SSO callbacks and secure cookies.
HTTP→HTTPS redirection is the infrastructure's job too.

Consequently:

- `TLS_ENABLED`, `HTTPS_PORT`, `APP_HTTPS_PORT` and the Admin toggle are gone,
  along with self-signed generation, PEM/PFX import and the served-chain
  assembly. `tls.py` / `tlsconfig.py` are replaced by `certinfo.py` (reading
  certificates) and `trustconfig.py` (the store).
- **Admin → Certificate authorities** keeps exactly one job: the authorities used
  to verify the app's outbound calls. The API moves from `/api/admin/tls-config`
  to `/api/admin/trust-store`.
- Migration `0028_trust_store` rewrites the settings row, keeping only the
  authorities. **The certificate and its private key are dropped**, which is the
  point: they leave the database and every future backup.

## Rationale

The removal deletes roughly a thousand lines, one port, one listener, one toggle
and one class of secret, and it deletes the only screen in the app from which an
administrator could break their own deployment's routing. Nothing is lost that a
load balancer does not already do, and what genuinely needed the UI, trusting a
private authority, is untouched.

## Consequences

- **Breaking for anyone running `TLS_ENABLED=true`.** They must put a proxy in
  front, or accept plain HTTP on a trusted network. Locally this is already the
  default: `http://localhost:8000`.
- **`COOKIE_SECURE=true` becomes deployment configuration**, set once behind the
  load balancer, rather than something that has to track a runtime toggle.
- **A stored certificate is not recoverable after the migration.** An operator
  who kept their only copy of a certificate in the app must export it before
  upgrading.
- `CERT_DIR` survives, now solely as the scratch directory for the outbound
  trust bundle.

## Risks

- A deployment that upgrades **without** putting TLS in front serves the login
  form over plain HTTP. The Ops panel's insecure-defaults check already flags a
  non-Secure cookie once `PUBLIC_BASE_URL` is set, which is the honest signal
  that this is not somebody's laptop.
- `forwarded_allow_ips="*"` trusts `X-Forwarded-*` from any peer, which is only
  sound because the container is meant to be reachable through its proxy alone.
  Exposing the port directly to clients would let them forge the scheme.

## Future Evolution

- Narrow `forwarded_allow_ips` to the proxy's range if the pod ever becomes
  directly reachable.
- If a standalone, proxy-less install is ever required again, ship a reverse
  proxy beside the app (a ten-line Caddy service) rather than putting the
  listener back in the application.
