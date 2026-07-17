# 04 - API Reference

All endpoints are under `/api`. Humans authenticate with a **signed session cookie** (sent
automatically by the SPA with `credentials: include`). Machines authenticate with an **API key**
(`Authorization: Bearer trt_…`) on the read-only routes that opted in - see *Machine access* below.
The live, always-accurate contract is the FastAPI-generated **OpenAPI** at `/openapi.json` and
Swagger UI at `/docs`. This page is a curated map.

## Conventions / guards

| Guard | Meaning |
|-------|---------|
| `get_current_user` | 401 if no valid session (**cookie only** - an API key is refused) |
| `require_admin` | role == admin |
| `require_tribe_or_admin` | admin or tribe_leader |
| `require_writer` | admin / tribe_leader / squad_leader |
| `require_module(m[,feature])` | 404 if the module/feature is disabled |
| `require_capability(cap)` | 403 if the caller's persona lacks the section capability |
| `caller(scope, capability)` | cookie **or** API key: a human is gated by `capability`, a key by `scope` |
| `assert_can_edit_squad` | admin/tribe, or the squad's leader |
| `assert_tribe_scope` | resource must be within the caller's tribe (non-admin) |

## Machine access (API keys)

Keys are minted in **Administration → API** (ADR-0011). They are **read-only**: a key can never
write, and can never reach `/api/admin/*`. A route is reachable by a key only if it declares
`caller(...)` - every other route stays cookie-only, so key auth is opt-in per route, never global.

```bash
curl -H "Authorization: Bearer trt_ab12cd34_<secret>" \
     "https://tribe.example/api/reports/dashboard.pptx?since_days=7" -o dashboard.pptx
```

| Scope | Opens |
|---|---|
| `dashboard:read` | `GET /api/reports/dashboard.{html,pptx}` |
| `roadmap:read` | `GET /api/reports/roadmap.{html,pptx}`, `GET /api/reports/dependencies.{html,pptx}` |
| `reports:read` | `GET /api/reports/weekly.{html,pptx}` |
| `org:read` | reserved for the org exports |
| `budget:read` | **modifier, not a route**: without it, budget figures are stripped from every document served to the key |

A key also carries a **tribe scope** (or "all tribes"). Out-of-scope data is `404`, not `403` - it
is invisible, not merely forbidden.

Responses: `401` unknown/expired/revoked key (or no credential at all), `403` valid key without the
required scope.

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
`GET ""` - consolidated cards + summary. Gated by module `dashboard` + capability `dashboard`.

### roadmapview (`/api/roadmap`)
`GET /matrix` - in-app global roadmap matrix. Gated by `squad_content.roadmap` module + `roadmap` capability.

### org (`/api/org`)  - module `org` + capability `org`
`GET ""` · `POST ""` · `PUT /{id}` · `DELETE /{id}` (edit = tribe/admin)

### objectives (`/api/objectives`) - module `squad_content.objectives`
`POST ""` · `PUT /{id}` · `DELETE /{id}` (manage = admin/tribe). Status is derived; not settable.

### roadmap (`/api/roadmap-items`) - module `squad_content.roadmap`
`POST ""` · `PUT /{id}` · `DELETE /{id}` (writer + can-edit-squad). Normalizes EA/GA + dependency.

### kpis (`/api/kpis`) - module `squad_content.kpis`
`POST ""` · `PUT /{id}` · `DELETE /{id}`

### members (`/api/members`)
`POST ""` · `PUT /{id}` · `DELETE /{id}`

### snapshots (`/api/squads/{id}/snapshots`) - module `reporting`
`POST ""` (submit cycle) · `GET ""` · `GET /{snapId}` · `GET /{snapId}/compare`

### progress (`/api`) - module `review`
`GET /squads/{id}/progress` · `POST /squads/{id}/progress` (review note, module `review.notes`) ·
`GET /progress/review` (**capability `review`**, tribe-scoped) · `POST /admin/progress/run-weekly` (admin)

### feed (`/api/feed`) - module `feed` + capability `feed`
`GET ""` · `POST ""` · `DELETE /{id}` · `PUT /{id}/pin` (feature `pin`) · `POST /{id}/replies` (feature
`replies`) · `DELETE /replies/{id}` · `POST /{id}/reactions` (feature `reactions`)

### notifications (`/api/notifications`) - module `notifications.inapp`
`GET ""` · `POST /{id}/read` · `POST /read-all` · `GET /me/preferences` · `PUT /me/preferences`

### reports (`/api/reports`) - module `review.weekly_report`
`GET /weekly.html` · `GET /weekly.pptx` · `GET /roadmap.html` · `GET /roadmap.pptx` (supports `squad_ids`)
· `GET /dependencies.html` · `GET /dependencies.pptx` (milestone dependencies grouped by the entity waited on; `mode=cross_tribe`\|`all`, supports `tribe_id`/`squad_ids`/`year`; module `squad_content.roadmap`)
· `POST /weekly/email` · `GET /subscriptions` · `GET /subscription` · `PUT /subscription`

### leaves CSV export
`GET /api/leaves/export.csv` - absences export (scoped to the caller's tribe); part of the `leaves` module.

### actions (`/api`) - review action items
`GET /squads/{id}/actions` · `POST /squads/{id}/actions` · `PUT /actions/{id}` · `DELETE /actions/{id}`

### leaves (`/api/leaves`) - module `leaves` + capability `leaves`
Types: `GET /types` (`?include_inactive`) · `POST /types` · `PUT /types/{id}` · `DELETE /types/{id}` (admin) ·
Config (per tribe): `GET /config` · `PUT /config` (tribe_leader/admin) · People picker: `GET /people` ·
Leaves: `GET ""` (filters `from/to/user_id/squad_id/status/mine`) · `POST ""` · `PUT /{id}` ·
`POST /{id}/decision` (approve/reject, leaders) · `DELETE /{id}` · `GET /overlaps` (`from/to`, module
`leaves.overlap_alert`) · `GET /export.csv`. Visibility is tribe-scoped (admins: all); the motif is
returned only to the person, their leader and admins.

### admin (`/api/admin`) - `require_admin` (users also tribe_leader)
Users: `GET/POST /users`, `PUT/DELETE /users/{id}` · Settings: `GET/PUT /settings` · Auth config:
`GET/PUT /auth-config` · Modules: `GET/PUT /modules-config` · **Personas: `GET/PUT /personas`** ·
SMTP: `GET/PUT /smtp-config`, `POST /smtp-config/test` · Report: `GET/PUT /report-config`,
`POST /report-config/test` · Log export: `GET/PUT /log-export-config`,
`POST /log-export-config/test`, `POST /log-export-config/flush` (syslog / GCS / BigQuery; GCP auth is
keyless by default - ADC/WIF/impersonation, JSON key last - see [ADR-0012](adr/0012-gcp-auth-keyless.md))

### audit (`/api/audit-log`) - admin
`GET ""`

## Generate a static OpenAPI file

```bash
curl -sk https://localhost:8443/openapi.json > docs/openapi.json   # snapshot the live contract (-k: self-signed cert)
```

> Recommendation (industrialization): commit `openapi.json` in CI and diff it to detect breaking
> API changes. Tracked as a quick win in [11](11-roadmap-and-enterprise-readiness.md).
</content>
