# ADR-0011 — API keys and scopes (machine access)

**Status:** Accepted · **Date:** 2026-07-13

## Context

The API only ever accepted a **session cookie** (`deps.get_current_user_any_status`).
A script or a BI tool that needed the data had exactly one option: log in as a real
human with their password and carry their cookie. That is a personal credential
used as a machine credential — it dies when the person leaves, it carries *all*
their rights, and it is invisible in any audit ("who pulled this export?" → "a
human, apparently").

We need machine access (Power BI, reporting scripts) that is deliberate,
revocable and least-privileged.

## Decision

**API keys are service credentials, not users, and they are strictly read-only.**

1. **A key is not a user.** It belongs to the organisation and survives its
   creator (`api_keys` table, ADR-0010 migration `0026`). It is minted, and later
   revoked, from **Admin → API**.

2. **The secret is shown once.** We generate `trt_<prefix>_<secret>`, store only
   the **argon2 hash** of the secret plus the non-secret `prefix`. The prefix is
   the handle: it is what the admin UI displays and what we look the key up by,
   so a call costs one hash verification, not one per row. A lost key is not
   recoverable — it is replaced.

3. **Authority = scopes ∩ tribe.** `scopes` (`dashboard:read`, `roadmap:read`,
   `reports:read`, `org:read`, `budget:read`) say *which resources*; `tribe_id`
   says *whose data* (NULL = all tribes). Both are chosen at creation.

4. **Scopes are not personas.** A persona gates a *human navigating sections*; a
   scope gates a *credential reading a resource*. Conflating them would mean
   inventing a fake user for every integration, and would let a "read-only"
   integration write as soon as its persona could.

5. **A key opens only the routes that opted in.** Routes take `deps.caller(scope,
   capability)`, which accepts a cookie (gated by the persona capability, as
   before) **or** a key (gated by its scope). Every other route is unchanged and
   therefore cookie-only. This is the safety property: adding key auth to the
   single identity choke point would have lit up all ~170 routes at once; instead,
   opening a route to machines is an explicit, reviewable act.

6. **Budgets need their own scope.** Budget figures ride inside the report
   payloads. A key with no tribe reads across tribes, so without a dedicated
   `budget:read` scope it would collect every squad's budget as a side effect of
   `dashboard:read`. Keys without that scope get `viewer=None`, which strips the
   budget block from the rendered documents.

## Consequences

- Machine access is now **read-only by construction**. There is no write scope; a
  future one means deliberately opening a write route, not flipping a flag.
- Revocation is immediate (`revoked_at`) and the row is **kept**, so the audit
  trail survives the key. `last_used_at` makes dormant keys visible.
- Keys are auditable: `api_key.create` / `api_key.revoke` / `api_key.delete` land
  in `audit_log` like any other admin action.
- `POST /api/admin/api-keys` is the **only** endpoint that ever returns a secret,
  and only in the response that creates it.

## Not done (deliberately)

- **Rate limiting / quotas per key.** The existing login throttle is an in-memory
  per-IP counter (`auth.py`), which is already wrong under multiple replicas. A
  real limiter needs shared state; doing it badly per-key would add a false sense
  of protection. Tracked separately.
- **`/docs` and `/openapi.json` are still public.** Unrelated to keys, but it
  means the API surface is world-readable. Tracked separately.
- **Write scopes**, IP allow-listing, and key rotation with overlapping validity —
  all standard next steps once a real write use-case exists.
