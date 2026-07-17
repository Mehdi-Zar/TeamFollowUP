# ADR-0005 - Persona → capability authorization model

**Status:** Accepted

## Context
Beyond the four built-in roles, admins need to control **which persona can access which section** and
to create custom personas (e.g. "Auditor", "Stakeholder") assignable to users.

## Options Considered
1. **Persona → capability matrix** (section-access capabilities) on top of role tiers, admin-editable.
2. Hard-coded role checks only.
3. Full ABAC/policy engine (OPA).

## Decision
Option 1. Capabilities = navigable sections (`dashboard, roadmap, org, feed, reporting, review,
mysquads`). Each persona (4 built-ins + custom) maps capability → bool, stored in `app_settings.personas`.
Enforced by `require_capability(cap)` server-side and `useAuth().can(cap)` / `Section` guard client-side.
`users.role` holds the persona key (free string). Admin always retains access; deleting a persona
reassigns its users to `member`.

## Rationale
Gives real, admin-managed governance without a heavy policy engine. Built-in defaults mirror the legacy
navigation so behaviour is unchanged out of the box. Capability list is **forward-compatible** (new
capability defaults to the built-in default for existing personas).

## Consequences
- Three orthogonal layers: role tiers (coarse) + capabilities (section access) + module flags (feature on/off).
- Custom personas are effectively view-scoped (edit actions remain governed by role/ownership checks).

## Risks
- Capabilities cover **section access**, not every micro-action; fine-grained action control still relies
  on role/ownership. Documented; can be extended with action capabilities later.

## Future Evolution
Add action-level capabilities (post_feed, manage_objectives, export…) if needed; consider a personas table.
</content>
