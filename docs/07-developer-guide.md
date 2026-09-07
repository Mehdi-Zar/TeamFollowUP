# 07 - Developer Guide

## Prerequisites

Docker + Docker Compose. For local frontend dev: Node 22+. For local backend tests: Python 3.12
(see note below - the global interpreter may be 3.14 which lacks wheels).

## Run the whole app (recommended)

```bash
docker compose up -d --build      # http://localhost:8000 (single port, plain HTTP)
```
Demo data is seeded on first boot (`SEED_DEMO=true`). Break-glass admin: `admin@local` (password from
`BREAKGLASS_PASSWORD`, or the random one printed in the app logs at first boot).

Compose serves plain HTTP and leaves TLS to the infrastructure (`TLS_ENABLED=false`,
the recommended model, see `docs/06` §Topology). Set `TLS_ENABLED=true` +
`APP_HTTPS_PORT=8443` to have the app terminate TLS itself on `https://localhost:8443`.

## Frontend dev (hot reload)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to the compose backend (http://localhost:8000)
npm run build      # production build (also the CI gate)
npx tsc --noEmit   # type-check
```

> **Login fails on http://localhost:5173?** Check `COOKIE_SECURE` in `.env`: a browser
> will not send a `Secure` cookie over a plain-HTTP origin, so it must be `false` for
> local dev (the shipped default) and `true` once the app is published over HTTPS.

## SSO URLs while developing

Nothing to configure: with `PUBLIC_BASE_URL` empty the app derives the OIDC redirect
URI and the SAML entity ID / ACS URL from the request it receives, so they follow
whatever host you browse (`http://localhost:8000/api/auth/oidc/callback`, and so on).
**Administration → Authentification** shows the resolved values. See `docs/05` for the
derivation rules and `docs/12` §2.1 for what to set when deploying.

## Backend tests

Tests use an in-memory SQLite DB + FastAPI `TestClient` (no Postgres needed). **Use a Python 3.12
venv** - the repo ships one at `backend/.venv-test` (the global interpreter is 3.14 and lacks some wheels):

```bash
cd backend
./.venv-test/Scripts/python.exe -m pytest -p no:warnings -q     # Windows (Git Bash)
# or, fresh venv:  uv venv --python 3.12 .venv-test && uv pip install -r requirements.txt
```
200 tests across 22 modules. They run fully offline.

## Project structure

```
backend/alembic/versions/  migrations (0001..0026)
backend/app/
  main.py            FastAPI app, router registration, startup scheduler, SPA serving
  routers/           23 HTTP routers (one per bounded area)
  deps.py            auth + RBAC + capability + module guards
  models.py          SQLAlchemy ORM (27 tables)
  schemas.py         Pydantic DTOs
  serializers.py     ORM -> DTO assembly (+ derived values)
  status.py          health/progress/derived-status domain logic
  report.py          weekly report + roadmap rendering (HTML/PPTX)
  *config.py         typed accessors over app_settings (general/modules/personas/smtp/report/auth)
  rbac.py            role constants, admin tabs, permissions payload
backend/tests/       pytest suite (+ conftest fixtures)
frontend/src/
  pages/             route-level screens (17)
  components/        Layout, ui.tsx (design system), CommandPalette, ExportMenu, ...
  auth.tsx config.tsx i18n.tsx   cross-cutting contexts
  api.ts types.ts perms.ts labels.ts theme.css
```

## Conventions

- **Backend**: one router per bounded area; access control via dependencies (never ad-hoc in handlers);
  config read through `*config.py` accessors; every model change needs an Alembic migration; mutations
  call `record_audit`.
- **Frontend**: typed API via `api.ts`; **all UI strings via `i18n.tsx`** (FR + EN must stay in parity -
  CI/parity script enforces it); section access via `useAuth().can(cap)` and the `Section` guard; reuse
  `ui.tsx` primitives (`EmptyState`, `Modal`, `StatusBadge`, `Spinner`) instead of re-implementing.
- **Typography**: no em dash and no middot in anything a user reads (UI labels, FR/EN
  translations, generated HTML/PPTX, emails, titles, tooltips). They read as machine-written.
  Use a comma, a colon, parentheses, a line break or a plain space. Two guards enforce it and
  run with the normal suites: `backend/tests/test_typography.py` inspects every non-docstring
  string literal under `backend/app` (developer prose is exempt on purpose), and
  `frontend/src/typography.test.ts` scans `frontend/src` outside comment lines.
- **Gates (run before commit)**: `cd frontend && npm test` carries both the i18n FR/EN parity
  check and the typography guard, and `cd backend && pytest` carries the backend one. CI runs
  the same two commands, so there is nothing to keep in sync by hand.

## Definition of done (per change)

1. `tsc --noEmit` clean · 2. `npm run build` ok · 3. backend `pytest` green · 4. i18n FR/EN parity ·
5. migration added if schema changed · 6. docs updated if behaviour/contract changed.
</content>
