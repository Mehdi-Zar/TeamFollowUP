# 07 - Developer Guide

## Prerequisites

Docker + Docker Compose. For local frontend dev: Node 22+. For local backend tests: Python 3.12
(see note below - the global interpreter may be 3.14 which lacks wheels).

## Run the whole app (recommended)

```bash
docker compose up -d --build      # https://localhost:8443 (single port, self-signed cert)
```
Demo data is seeded on first boot (`SEED_DEMO=true`). Break-glass admin: `admin@local` (password from
`BREAKGLASS_PASSWORD`, or the random one printed in the app logs at first boot).

## Frontend dev (hot reload)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to the compose backend (https://localhost:8443)
npm run build      # production build (also the CI gate)
npx tsc --noEmit   # type-check
```

> **Login fails on http://localhost:5173?** The compose backend marks the session
> cookie `Secure` (`COOKIE_SECURE=true` by default). Chrome/Firefox accept Secure
> cookies on `localhost`, but some browsers (e.g. Safari) drop them on a plain-HTTP
> origin. Fix: set `COOKIE_SECURE=false` in `.env` for local dev, or use the
> compose app directly at `https://localhost:8443`.

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
- **i18n parity gate** (run before commit):
  ```bash
  cd frontend && node -e "/* see CI workflow */"   # or the snippet in .github/workflows/ci.yml
  ```

## Definition of done (per change)

1. `tsc --noEmit` clean · 2. `npm run build` ok · 3. backend `pytest` green · 4. i18n FR/EN parity ·
5. migration added if schema changed · 6. docs updated if behaviour/contract changed.
</content>
