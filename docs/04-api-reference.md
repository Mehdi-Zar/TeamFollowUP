# 04 - API Reference

All endpoints are under `/api`. Humans authenticate with a **signed session cookie** (sent
automatically by the SPA with `credentials: include`). Machines authenticate with an **API key**
(`Authorization: Bearer trt_…`) on the read-only routes that opted in - see *Machine access* below.
The live, always-accurate contract is the FastAPI-generated **OpenAPI** at `/openapi.json` and
Swagger UI at `/docs` (linked from **Administration → API**, with a step-by-step guide). Swagger
exposes an **Authorize** button (`ApiKeyAuth`): paste an API key and it is sent as
`Authorization: Bearer …` on every "Try it out" call; a logged-in admin's session cookie is also
sent automatically (same origin). This page is a curated map.

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
`GET /config`; `POST /login`; `POST /logout`; `GET /me`; `GET /me/permissions` (role, admin tabs,
assignable roles, **capabilities**, impersonation); OIDC: `GET /oidc/login`,`GET /oidc/callback`;
SAML: `GET /saml/metadata`,`GET /saml/login`,`POST /saml/acs`; `POST /impersonate`; `POST /stop-impersonation`

### tribes (`/api/tribes`)
`GET ""`; `GET /org-overview`; `POST ""` (admin); `PUT /{id}`; `DELETE /{id}` (admin)

### squads (`/api/squads`)
`GET ""`; `GET /{id}` (detail); `GET /{id}/dependents`; `GET /{id}/roadmap.pptx`; `GET /{id}/roadmap.html`;
`POST ""`; `PUT /{id}`; `DELETE /{id}`; `PUT /{id}/quarter-progress`.

`PUT /{id}/quarter-progress` records the quarter's **comment**. The percentage is
derived from that quarter's milestones (`status.year_progress`) and is what every
screen displays; it is stored alongside so the row matches what was shown. A caller
that still sends `progress_pct` overrides it, which is the only reason the field is
still accepted. `co_leader_user_ids` on `PUT /{id}` replaces the squad's co-leaders
(structural: tribe leader or admin).

### dashboard (`/api/dashboard`)
`GET ""` - consolidated cards + summary. Gated by module `dashboard` + capability `dashboard`.

### roadmapview (`/api/roadmap`)
`GET /matrix` - in-app global roadmap matrix. Gated by `squad_content.roadmap` module + `roadmap` capability.

### org (`/api/org`)  - module `org` + capability `org`
`GET ""`; `POST ""`; `PUT /{id}`; `DELETE /{id}` (edit = tribe/admin)

### initiatives (`/api/initiatives`)
`GET ""`; `POST ""`; `PUT /{id}`; `DELETE /{id}` (manage = admin/tribe).
`GET /candidate-jalons?squad_id=&year=` - les jalons d'une squad, chacun avec
l'initiative qui le prend deja. `PUT /{id}/jalons` - pose l'ensemble des jalons qui
servent l'initiative (remplace le precedent). C'est le **seul** endroit ou ce lien
se pose, comme `PUT /api/otds/{id}/jalons` l'est pour un engagement : il ne figure
pas dans l'edition d'un jalon, ou deux ecrans finiraient par se contredire.

### otds (`/api/otds`)
`GET ""` - les engagements de l'annee, avec leur statut derive et leurs jalons.
`POST ""`; `PUT /{id}`; `DELETE /{id}`; `PUT /{id}/jalons`;
`GET /candidate-jalons?year=&tribe_id=&squad_id=`.

Deux portees, deux proprietaires. `scope="management"` est ecrit par le tribe
leader ou l'admin, sur sa tribe. `scope="squad"` exige `squad_id` et n'est ecrit
que par un leader de cette squad, tribe leader compris **exclu** : un engagement
qu'un tiers peut corriger n'est plus l'engagement de celui qui l'a pris. La portee
n'est pas dans `OtdUpdate`, donc elle ne se modifie pas apres coup.

Lecture : le tribe leader et l'admin voient tout ce qui concerne leur tribe, les
deux portees comprises, puisque leurs rapports les montrent. Un squad leader voit
les siens, plus les engagements management qui lui sont assignes ou qui embarquent
un de ses jalons. Les autres n'en voient aucun.

`PUT /{id}/jalons` ecrit le lien de SA portee (`roadmap_items.otd_id` pour le
management, `squad_otd_id` pour la squad), donc rattacher d'un cote ne detache
jamais rien de l'autre. Un engagement management accepte les jalons de sa tribe,
un engagement de squad seulement ceux de sa squad.

### roadmap (`/api/roadmap-items`) - module `squad_content.roadmap`
`POST ""`; `PUT /{id}`; `DELETE /{id}` (writer + can-edit-squad). Normalizes EA/GA + dependency.

### kpis (`/api/kpis`) - module `squad_content.kpis`
`POST ""`; `PUT /{id}`; `DELETE /{id}`

### members (`/api/members`)
`POST ""`; `PUT /{id}`; `DELETE /{id}`

### snapshots (`/api/squads/{id}/snapshots`) - module `reporting`
`POST ""` (submit cycle); `GET ""`; `GET /{snapId}`; `GET /{snapId}/compare`
La saisie figee porte ce que les documents relisent: objectifs, jalons (avec leurs
rattachements d'engagement), avancement, KPI, engagements OTD, initiatives, messages cles,
moral et statut de la squad. **Pas le budget**: la saisie se lit par tout utilisateur qui
voit la squad, ses chiffres de budget non.

### progress (`/api`) - module `review`
`GET /squads/{id}/progress`; `POST /squads/{id}/progress` (review note, module `review.notes`);
`GET /progress/review` (**capability `review`**, tribe-scoped); `POST /admin/progress/run-weekly` (admin)

### feed (`/api/feed`) - module `feed` + capability `feed`
`GET ""`; `POST ""`; `DELETE /{id}`; `PUT /{id}/pin` (feature `pin`); `POST /{id}/replies` (feature
`replies`); `DELETE /replies/{id}`; `POST /{id}/reactions` (feature `reactions`)
Feature `kinds` gates no route of its own, it gates a field: with it off, `POST ""` stores
`info` whatever kind was sent and the `?kind=` filter on `GET ""` is ignored, so the switch
removes the taxonomy instead of only hiding its selector.

### notifications (`/api/notifications`) - module `notifications.inapp`
`GET ""`; `POST /{id}/read`; `POST /read-all`; `GET /me/preferences`; `PUT /me/preferences`

### reports (`/api/reports`) - module `review.weekly_report`
`GET /weekly.html`; `GET /weekly.pptx`; `GET /roadmap.html`; `GET /roadmap.pptx` (supports `squad_ids`);
`GET /dependencies.html`; `GET /dependencies.pptx` (milestone dependencies grouped by the entity waited on; `mode=all` **par defaut**, `mode=cross_tribe` ne garde que celles qui pointent hors de la tribu de la squad source et le document le dit alors en sous-titre. Le defaut valait `cross_tribe`, et une installation d'une seule tribu n'en a aucune: l'export s'ouvrait sur « Aucune dependance » alors que les jalons en portaient. Supporte `tribe_id`/`squad_ids`/`year`; module `squad_content.roadmap`);
`POST /weekly/email`; `GET /subscriptions`; `GET /subscription`; `PUT /subscription`;
`GET /versions` (les journees ou une squad du perimetre a fige sa saisie, avec le nombre de
squads concernees; capability `dashboard` **ou** `roadmap`, module `reporting`, puisque c'est
lui qui produit les saisies figees)

**Versions.** `weekly.{html,pptx}`, `dashboard.{html,pptx}`, `roadmap.{html,pptx}` et
`POST /weekly/email` acceptent `as_of` (`AAAA-MM-JJ`, pris en fin de journee, ou un
horodatage ISO): le document est alors rejoue depuis la derniere saisie figee de chaque
squad anterieure a cette date, et il porte la mention `version du ...`. Une squad sans
saisie a cette date sort du document et son nom est compte. Une valeur illisible rend
**422**, jamais le document du jour. Le perimetre de lecture reste celui d'aujourd'hui.
Voir [29 - Les versions d'un document](29-versions-des-documents.md) et
[ADR 0016](adr/0016-a-version-is-a-day-replayed-from-frozen-submissions.md).

### leaves CSV export
`GET /api/leaves/export.csv` - absences export (scoped to the caller's tribe); part of the `leaves` module.

### leaves (`/api/leaves`) - module `leaves` + capability `leaves`
Types: `GET /types` (`?include_inactive`); `POST /types`; `PUT /types/{id}`; `DELETE /types/{id}` (admin);
Config (per tribe): `GET /config`; `PUT /config` (tribe_leader/admin); People picker: `GET /people`;
Leaves: `GET ""` (filters `from/to/user_id/squad_id/status/mine`); `POST ""`; `PUT /{id}`;
`POST /{id}/decision` (approve/reject, leaders); `DELETE /{id}`; `GET /overlaps` (`from/to`, module
`leaves.overlap_alert`, and with that feature off the SPA does not call it at all, so the banner
simply never appears); `GET /export.csv`. Visibility is tribe-scoped (admins: all); the motif is
returned only to the person, their leader and admins.

### steerco (`/api/steerco`) - module `steerco` (off by default)
The reporting unit is the **platform**, fed by one or more squads ([15](15-steerco.md)).
Platforms: `GET /platforms` (any signed-in caller: a contributor must see the whole slide);
`POST /platforms`, `PUT /platforms/{id}`, `DELETE /platforms/{id}` (**`require_tribe_or_admin`**,
tribe-scoped; the tribe is taken from the payload, the caller, or the first contributing squad).
Snapshots: `GET /platform/{id}?period=` (data + template + what the caller owns + who is missing);
`PUT /platform/{id}?period=` (writes **only the items the caller owns**, the rest is kept);
`GET /platform/{id}/history?period=`; `PUT /platform/{id}/history` (backfill, same ownership rule);
`POST /platform/{id}/preview.html?period=` (renders the **unsaved** body, persists nothing,
contributor accessible); Documents
(**`require_tribe_or_admin`**, tribe-scoped): `GET /entries?period=`; `GET /onepager.html?platform_id=&period=`;
`GET /document.html?period=`; `GET /document.pptx?period=` (`501` without `python-pptx`).
All documents accept `lang=fr|en` (default English). `period` is `YYYY-MM`; every window (charts,
history, SLA average) is the report's calendar year, January to December, so the charts always start
in January. Admin Excel template/import (`/api/admin/import-steerco*`) use the same year window. See
[15](15-steerco.md).

### admin (`/api/admin`) - `require_admin` (users also tribe_leader)
Users: `GET/POST /users`, `PUT/DELETE /users/{id}`; Settings: `GET/PUT /settings`; Auth config:
`GET/PUT /auth-config`, `POST /auth-config/test` (probe the IdP: body `{provider: "oidc"|"saml",
config?: {...}}`; `config` layers unsaved form values over the stored ones so a change can be checked
before it is committed, returns `{ok, checks[], hint}`, read-only);
Modules: `GET/PUT /modules-config`; **Personas: `GET/PUT /personas`**;
SMTP: `GET/PUT /smtp-config`, `POST /smtp-config/test`; Report: `GET/PUT /report-config`,
`POST /report-config/test`; Log export: `GET/PUT /log-export-config`,
`POST /log-export-config/test`, `POST /log-export-config/flush` (syslog / GCS / BigQuery; GCP auth is
keyless by default - ADC/WIF/impersonation, JSON key last - see [ADR-0012](adr/0012-gcp-auth-keyless.md));
Imports: `GET /import-org/template`, `POST /import-org` ([14](14-import-organisation.md)),
`GET /import-steerco/template`, `POST /import-steerco` ([15](15-steerco.md)); API keys:
`GET/POST /api-keys`, `POST /api-keys/{id}/revoke`, `DELETE /api-keys/{id}`;
Ops: `GET /runtime`, `POST /restart`, `GET /logs`,
`GET /logs/download`, `POST /logs/clear`, `POST /log-level`;
PPTX export template: `GET /pptx-template` (status), `POST /pptx-template` (upload a `.pptx`),
`GET /pptx-template/download`, `DELETE /pptx-template` - when set, every PPTX export is built on it
(masters/theme/branding); see `app/pptxtpl.py`

**Trusted certificate authorities** (`/api/admin/trust-store`, admin only, every mutation audited
as `trust_store.*`). These are the authorities the app verifies its **outbound** calls against:
OIDC, SAML, SMTP, log export.
`GET ""` lists the store, split into `roots` and `intermediates`, without the PEM bodies.
`POST /ca` (multipart: `ca` file or `ca_pem` text, optional `name`) imports one or more
authorities; a PEM that holds several certificates adds them all, and duplicates are ignored.
`DELETE /ca/{id}` removes one, `GET /ca/{id}/download` returns its PEM as an attachment.
Add and remove are effective on the next outbound call, without a restart
([05](05-security.md)).

### audit (`/api/audit-log`) - admin
`GET ""` - one page, newest first: `?limit` (1..500, default 50) `&offset` `&action` (case-insensitive
substring) `&entity` (exact) `&user_id` `&since` `&until` (ISO timestamps). Returns
`{items, total, limit, offset}`, where **`total` counts the filtered set, not the page**. Each item
carries the acting user's `user_email` / `user_name`, resolved server-side and null when that
account has since been deleted.

## Generate a static OpenAPI file

```bash
python backend/scripts/dump_openapi.py            # rewrite docs/openapi.json (no server needed)
python backend/scripts/dump_openapi.py --check    # fail if the snapshot is stale (what CI runs)
```

> The snapshot is checked on every push: the **Backend** CI job runs `dump_openapi.py --check`
> and fails when the committed file no longer matches the routes, so an unintended
> contract change shows up in the pull request instead of reaching a client.
</content>
