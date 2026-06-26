# 04 — API Reference

All endpoints are under `/api`. Auth is a **signed session cookie** (sent automatically by the SPA
with `credentials: include`). The live, always-accurate contract is the FastAPI-generated
**OpenAPI** at `/openapi.json` and Swagger UI at `/docs`. This page is a curated map.

## Conventions / guards

| Guard | Meaning |
|-------|---------|
| `get_current_user` | 401 if no valid session |
| `require_admin` | role == admin |
| `require_tribe_or_admin` | admin or tribe_leader |
| `require_writer` | admin / tribe_leader / squad_leader |
| `require_module(m[,feature])` | 404 if the module/feature is disabled |
| `require_capability(cap)` | 403 if the caller's persona lacks the section capability |
| `assert_can_edit_squad` | admin/tribe, or the squad's leader |
| `assert_tribe_scope` | resource must be within the caller's tribe (non-admin) |

## Endpoint map (by router)

### auth (`/api/auth`)
`GET /config` · `POST /login` · `POST /logout` · `GET /me` · `GET /me/permissions` (role, admin tabs,
assignable roles, **capabilities**, impersonation) · OIDC: `GET /oidc/login`,`GET /oidc/callback` ·
SAML: `GET /saml/metadata`,`GET /saml/login`,`POST /saml/acs` · `POST /impersonate` · `POST /stop-impersonation`

### tribes (`/api/tribes`)
`GET ""` · `GET /org-overview` · `POST ""` (admin) · `PUT /{id}` · `DELETE /{id}` (admin)

### squads (`/api/squads`)
`GET ""` · `GET /{id}` (detail) · `GET /{id}/dependents` · `GET /{id}/roadmap.pptx` · `GET /{id}/roadmap.html`
· `POST ""` · `PUT /{id}` · `DELETE /{id}` · `PUT /{id}/quarter-progress`

### dashboard (`/api/dashboard`)
`GET ""` — consolidated cards + summary. Gated by module `dashboard` + capability `dashboard`.

### roadmapview (`/api/roadmap`)
`GET /matrix` — in-app global roadmap matrix. Gated by `squad_content.roadmap` module + `roadmap` capability.

### org (`/api/org`)  — module `org` + capability `org`
`GET ""` · `POST ""` · `PUT /{id}` · `DELETE /{id}` (edit = tribe/admin)

### objectives (`/api/objectives`) — module `squad_content.objectives`
`POST ""` · `PUT /{id}` · `DELETE /{id}` (manage = admin/tribe). Status is derived; not settable.

### roadmap (`/api/roadmap-items`) — module `squad_content.roadmap`
`POST ""` · `PUT /{id}` · `DELETE /{id}` (writer + can-edit-squad). Normalizes EA/GA + dependency.

### kpis (`/api/kpis`) — module `squad_content.kpis`
`POST ""` · `PUT /{id}` · `DELETE /{id}`

### members (`/api/members`)
`POST ""` · `PUT /{id}` · `DELETE /{id}`

### snapshots (`/api/squads/{id}/snapshots`) — module `reporting`
`POST ""` (submit cycle) · `GET ""` · `GET /{snapId}` · `GET /{snapId}/compare`

### progress (`/api`) — module `review`
`GET /squads/{id}/progress` · `POST /squads/{id}/progress` (review note, module `review.notes`) ·
`GET /progress/review` (**capability `review`**, tribe-scoped) · `POST /admin/progress/run-weekly` (admin)

### feed (`/api/feed`) — module `feed` + capability `feed`
`GET ""` · `POST ""` · `DELETE /{id}` · `PUT /{id}/pin` (feature `pin`) · `POST /{id}/replies` (feature
`replies`) · `DELETE /replies/{id}` · `POST /{id}/reactions` (feature `reactions`)

### notifications (`/api/notifications`) — module `notifications.inapp`
`GET ""` · `POST /{id}/read` · `POST /read-all` · `GET /me/preferences` · `PUT /me/preferences`

### reports (`/api/reports`) — module `review.weekly_report`
`GET /weekly.html` · `GET /weekly.pptx` · `GET /roadmap.html` · `GET /roadmap.pptx` (supports `squad_ids`)
· `POST /weekly/email` · `GET /subscriptions` · `GET /subscription` · `PUT /subscription`

### exports (`/api/exports`) — module `exports_csv`
`GET /dashboard.csv` · `POST /dashboard/email` · `GET /squad/{id}.csv` · `POST /squad/{id}/email`

### actions (`/api`) — review action items
`GET /squads/{id}/actions` · `POST /squads/{id}/actions` · `PUT /actions/{id}` · `DELETE /actions/{id}`

### admin (`/api/admin`) — `require_admin` (users also tribe_leader)
Users: `GET/POST /users`, `PUT/DELETE /users/{id}` · Settings: `GET/PUT /settings` · Auth config:
`GET/PUT /auth-config` · Modules: `GET/PUT /modules-config` · **Personas: `GET/PUT /personas`** ·
SMTP: `GET/PUT /smtp-config`, `POST /smtp-config/test` · Report: `GET/PUT /report-config`,
`POST /report-config/test` · Log export: `GET/PUT /log-export-config`, `POST /log-export/run`

### audit (`/api/audit-log`) — admin
`GET ""`

## Generate a static OpenAPI file

```bash
curl -s http://localhost:8080/openapi.json > docs/openapi.json   # snapshot the live contract
```

> Recommendation (industrialization): commit `openapi.json` in CI and diff it to detect breaking
> API changes. Tracked as a quick win in [11](11-roadmap-and-enterprise-readiness.md).
</content>
