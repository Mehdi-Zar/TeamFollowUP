# ADR-0006 — Module on/off flags (404 on disabled)

**Status:** Accepted

## Context
Different deployments want different feature sets (e.g. no feed, no weekly report). Features must be
toggleable at runtime, end to end.

## Options Considered
1. **Module registry** (`modulesconfig`) with module + sub-feature booleans; `require_module` dependency
   returns **404** when disabled; SPA hides the corresponding UI.
2. Build-time feature flags.
3. No toggling.

## Decision
Option 1. Modules: `dashboard, org, reporting, feed(+reactions/replies/pin/kinds), review(+notes/
weekly_report), squad_content(+objectives/roadmap/kpis), notifications(+inapp/email), exports_csv,
getting_started`. Backend returns 404 for disabled features; the SPA reads the same config via `/api/config`.

## Rationale
A disabled service should be **indistinguishable from a missing one** (404, not 403) — avoids leaking
the existence of features and keeps the contract clean. Runtime toggling needs no redeploy.

## Consequences
- Same flags drive both UI visibility and server enforcement → no divergence.
- Combined with capabilities (ADR-0005): a section needs its **module on** *and* the persona **capability**.

## Risks
- Toggling a module mid-session requires a client config reload (handled on next `/api/config` fetch).

## Future Evolution
Per-tribe/tenant module overrides if multi-tenancy lands.
</content>
