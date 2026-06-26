# ADR-0001 — Monolith serves the SPA (single deployable)

**Status:** Accepted

## Context
A small team needs a simple, reproducible deployment of a React SPA + FastAPI backend for an internal
tool, with minimal moving parts.

## Options Considered
1. Separate frontend (CDN/static host) + backend service + CORS.
2. **Single image**: FastAPI serves the API and the built SPA (`/assets` static + `index.html` fallback).
3. SSR framework (Next.js).

## Decision
Option 2. A multi-stage Docker build compiles the SPA into `app/static`; FastAPI serves it and falls
back to `index.html` for client-side routes. `docker compose` adds Postgres.

## Rationale
One artifact, one origin (no CORS/cookie complexity), trivial ops, fast iteration. SSR is unnecessary
for an authenticated internal app.

## Consequences
- Single deployable, single origin → session cookie "just works".
- Frontend and backend versions are always in lockstep.
- Scaling = replicate the same image behind a proxy.

## Risks
- Couples FE/BE release cadence. Mitigated by CI building both.
- Static assets served by the app process (fine at this scale; a CDN can front it later).

## Future Evolution
Front with a reverse proxy/CDN for caching; optionally split the SPA to a static host if independent
release cadence becomes valuable.
</content>
