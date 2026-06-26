# ADR-0004 — Runtime config as JSON in `app_settings`

**Status:** Accepted

## Context
Admins must change branding, modules, personas, SMTP, report schedule and auth toggles **at runtime**
without redeploys, and the set of settings evolves.

## Options Considered
1. **Single key/value table `app_settings`** with JSON blobs, wrapped by typed accessors (`*config.py`).
2. Dedicated normalized tables per config domain.
3. Environment variables / config files only.

## Decision
Option 1. Each domain (`general`, `modules`, `personas`, `smtp`, `weekly_report`, `auth_config`) is one
JSON row, read/written through a `*config.py` module that applies defaults, validation and sanitization.

## Rationale
Flexible and migration-light: adding a setting is a code change in the accessor (with defaults),
not a schema migration. Accessors centralize validation and **forward-compatibility** (e.g. a newly
added persona capability defaults sensibly for existing stored personas).

## Consequences
- Bootstrap/infra config stays in env vars; product config is in DB and admin-editable.
- No referential integrity between config and entities (e.g. `users.role` → personas) — handled in code.

## Risks
- Schema-less blobs can drift; mitigated by typed accessors + defaults + sanitization on read.
- Out-of-band edits could create orphans (admin PUT reconciles, e.g. reassigning users of a deleted persona).

## Future Evolution
Promote high-traffic/strongly-related config (personas) to a table with FKs if integrity needs grow.
</content>
