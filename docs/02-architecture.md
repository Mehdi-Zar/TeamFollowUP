# 02 — Architecture

## Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, TypeScript 5, React Router 6, Vite 5 (no UI framework; custom CSS design system in `theme.css`) |
| Backend | FastAPI 0.115, Pydantic 2, SQLAlchemy 2, Uvicorn |
| Database | PostgreSQL 16 |
| Migrations | Alembic 1.14 |
| Auth | Starlette SessionMiddleware (itsdangerous), Argon2 (argon2-cffi), Authlib (OIDC), python3-saml (SAML), PyJWT |
| Reporting | python-pptx (PPTX), hand-rendered HTML |
| Packaging | Multi-stage Docker (node build → python runtime serving the SPA) |

## C4 — System context

```mermaid
flowchart TB
  subgraph Users
    A[Admin]
    TL[Tribe leader]
    SL[Squad leader]
    M[Member]
  end
  Users -->|HTTPS, session cookie| APP[Tribe Cockpit\nFastAPI + SPA]
  APP -->|SQL| DB[(PostgreSQL)]
  APP -->|SMTP| MAIL[(Mail server)]
  APP -->|OIDC / SAML| IDP[(Identity Provider)]
```

## C4 — Containers / deployment

```mermaid
flowchart LR
  subgraph docker-compose
    direction LR
    APP["app container\n(python:3.12-slim)\nUvicorn :8000\nserves /api + built SPA"]
    DB[("db container\npostgres:16-alpine\nvolume db_data")]
  end
  APP -->|psycopg2| DB
  Browser -->|:8080 -> :8000| APP
```

- A single **app** image is built in two stages (Dockerfile): stage 1 `npm run build` produces the
  SPA into `frontend/dist`, copied into `app/static`; stage 2 is the Python runtime.
- `docker-entrypoint.sh`: waits for DB → `alembic upgrade head` → `python -m app.init_db` (break-glass
  admin + demo seed) → `uvicorn app.main:app`.
- The API serves the SPA: `/assets` via `StaticFiles`, every other non-`/api` path falls back to
  `index.html` (client-side routing). See [ADR-0001](adr/0001-monolith-serves-spa.md).

## Backend module map

```mermaid
flowchart TB
  main[main.py\nFastAPI app + routers + startup scheduler]
  main --> routers[19 routers\nauth, tribes, squads, dashboard, org,\nobjectives, roadmap, roadmapview, kpis,\nmembers, snapshots, exports, feed,\nnotifications, admin, audit, progress, reports, actions]
  routers --> deps[deps.py\nauth + RBAC + capability + module guards]
  routers --> serializers[serializers.py]
  routers --> schemas[schemas.py\nPydantic DTOs]
  serializers --> status[status.py\nhealth/progress/derived status]
  serializers --> models[models.py\nSQLAlchemy ORM]
  routers --> domain[Domain services\nprogress.py, report.py, status.py,\nsubscriptions.py, notify.py]
  config[Config stores in app_settings\ngeneralconfig, modulesconfig, personasconfig,\nsmtpconfig, reportconfig, authconfig] --> deps
  models --> db[(database.py\nSQLAlchemy engine/session)]
```

### Layering / separation of concerns
- **Routers** = HTTP boundary (validation via Pydantic schemas, dependency-injected guards).
- **deps.py** = cross-cutting access control: `get_current_user`, `require_admin/_writer/_tribe_or_admin`,
  `require_module(module[,feature])`, `require_capability(cap)`, `assert_can_edit_squad`, etc.
- **serializers.py** = ORM → DTO assembly (and derived values like objective status).
- **status.py / progress.py / report.py** = domain logic (health, progress timeline, rendering).
- **\*config.py** = typed accessors over the `app_settings` JSON key/value store ([ADR-0004](adr/0004-app-settings-json-config.md)).

## Background scheduler

```mermaid
sequenceDiagram
  participant U as Uvicorn startup
  participant L as async loop (every 3600s)
  participant DB as Postgres
  U->>L: spawn task (after 20s)
  loop hourly
    L->>DB: ensure_weekly() (weekly progress points)
    L->>DB: send_due_weekly_reports() (scheduled email, idempotent per ISO week)
    L->>DB: send_personal_subscriptions() (per-user cadence)
    L->>L: sleep 3600s
  end
```

In-process, single-instance scheduler started in `main.py` `@app.on_event("startup")`. It is
**not** distributed — see risks in [10](10-tech-debt-and-risk-register.md) and [ADR-0009](adr/0009-in-process-scheduler.md).

## Request → response sequence (typical authenticated read)

```mermaid
sequenceDiagram
  participant B as Browser (SPA)
  participant API as FastAPI router
  participant G as Guards (deps.py)
  participant S as Serializer/Domain
  participant DB as Postgres
  B->>API: GET /api/dashboard (cookie)
  API->>G: get_current_user + require_module + require_capability
  G-->>API: User (or 401/403/404)
  API->>S: squad_card()/status computations
  S->>DB: SELECT squads, roadmap, progress
  DB-->>S: rows
  S-->>API: DTOs
  API-->>B: JSON
```

## Frontend architecture

- **SPA** with React Router. `App.tsx` declares routes wrapped by guards: `Protected` (auth/admin),
  `ModuleGuard` and `Section` (module + persona capability).
- **Cross-cutting context**: `auth.tsx` (user, effective role, **capabilities**, impersonation),
  `config.tsx` (public config + modules), `i18n.tsx` (FR/EN, 540 keys, parity-checked).
- **Layout** = sidebar nav (mobile drawer) + topbar (page chrome, ⌘K command palette, notifications).
- **Design system**: `components/ui.tsx` (Modal, EmptyState, Spinner, Dot, StatusBadge, Collapsible…)
  + `theme.css` (CSS variables). See [04 UI in the audit](09-audit-report.md).
- **API client**: `api.ts` thin fetch wrapper (credentials: include, JSON, typed errors).
</content>
