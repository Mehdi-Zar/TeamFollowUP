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
- **Typography**: no em dash (U+2014) and no middot (U+00B7) **anywhere in the repository**,
  with no allowlist. They read as machine-written. Use a comma, a colon, parentheses, a line
  break or a plain space, whichever the sentence wants. The scope is the whole repo rather
  than "anything a user reads" because that boundary needed adjudicating every time and
  nobody did it: the weekly report shipped the middot as its separator, the API reference used
  it 92 times, and 105 em dashes sat in router docstrings, which FastAPI publishes as endpoint
  descriptions into Swagger UI and the committed OpenAPI snapshot. Three guards, all in the
  normal suites: `backend/tests/test_typography.py` (whole repo), `frontend/src/typography.test.ts`
  (fast frontend feedback), and `backend/tests/test_report_typography.py`, which reads the HTML
  and PPTX documents actually produced, since no source-level check can prove what an f-string
  assembles.
- **Gates (run before commit)**: `cd frontend && npm test` carries the i18n checks (FR/EN key
  parity, plus `i18n.usage.test.ts`: every key the code asks for exists, and every key in the
  dictionary is reachable) and the typography guard; `cd backend && pytest` carries the backend
  ones. CI runs the same two commands, so there is nothing to keep in sync by hand.
- **Adding a translation key**: add it to **both** dictionaries and use it in the same change.
  A key nobody reaches fails the suite, which is deliberate: 142 dead labels had accumulated
  from screens that were redesigned, and they read as an inventory of what the product does.
  A key built dynamically (`` t(`leaves.status.${s}`) ``) is protected automatically, because
  the test discovers those prefixes from the template literals in the source.

## Definition of done (per change)

1. `tsc --noEmit` clean, 2. `npm run build` ok, 3. backend `pytest` green, 4. i18n FR/EN parity,
5. migration added if schema changed, 6. docs updated if behaviour/contract changed.
</content>
