# 01 — Product Overview

## Vision

**Tribe Cockpit** gives a tribe (a group of squads in a scaled-Agile organization) a single,
trustworthy place to consolidate and steer delivery: where each squad stands on its annual
objectives and quarterly roadmap, what is blocked or at risk, and what was decided in the last
review (COPIL). It replaces scattered spreadsheets and slide decks with a live, role-aware product.

## Value proposition

- **One source of truth** for squad health, roadmap and objectives across the whole tribe.
- **Low-friction reporting** for squad leaders (guided entry, auto-captured progress timeline).
- **Decision support** for tribe leaders / management: dashboard, attention list, weekly review,
  COPIL presentation mode, and one-click HTML/PPTX exports (incl. a "Global Roadmap" swimlane deck).
- **Configurable governance**: turn modules on/off, and control which persona can access which section.

## Personas

| Persona (role) | Goals | Primary surfaces |
|----------------|-------|------------------|
| **Admin** | Configure the whole platform, manage tribes/users/personas, audit | Admin, all sections |
| **Tribe leader** | Steer the tribe, set objectives, run COPIL, manage squads | Dashboard, Review, My squads, Roadmap |
| **Squad leader** | Report squad roadmap/progress/KPIs/team weekly | Reporting (Saisie), My squads |
| **Member** | Stay informed (dashboard, roadmap, org, feed) | Dashboard, Roadmap, Org, Feed |
| *Custom persona* | Admin-defined, capability-scoped (e.g. "Auditor", "Stakeholder") | Per granted capabilities |

## Scope

In scope: tribe/squad org modelling, annual objectives, quarterly roadmap (milestones/jalons with
EA/GA stage and dependencies), KPIs, progress-review timeline, COPIL review + action items, feed,
org chart, notifications, weekly report scheduling and exports (CSV/HTML/PPTX), i18n (FR/EN).

Out of scope (today): real-time collaboration, external ticketing sync (Jira/ADO), per-tenant data
isolation beyond tribe scoping, mobile native apps.

## Capability / feature matrix

| Feature | Module flag | Capability gate | Notes |
|---------|-------------|-----------------|-------|
| Dashboard | `dashboard` | `dashboard` | tribe-scoped for non-admins |
| Roadmap (matrix view) | `squad_content.roadmap` | `roadmap` | in-app swimlane + export |
| Org chart | `org` | `org` | view all tribes; edit = tribe/admin |
| Feed | `feed` (+reactions/replies/pin/kinds) | `feed` | post scope = leaders/everyone |
| Reporting (Saisie) | `reporting` | `reporting` | squad leaders edit their squad |
| Objectives | `squad_content.objectives` | via reporting | status auto-derived from advancement |
| KPIs | `squad_content.kpis` | via reporting | per-squad on/off |
| Review (COPIL) | `review` (+notes/weekly_report) | `review` | timeline + actions + presentation mode |
| My squads | — | `mysquads` | management for tribe/squad leaders |
| Exports (CSV) | `exports_csv` | — | dashboard & squad CSV |
| Weekly report (HTML/PPTX/email) | `review.weekly_report` | — | scheduled + on-demand |
| Notifications | `notifications` (inapp/email) | — | bell + preferences |
| Leave / absences | `leaves` (+overlap_alert) | `leaves` | team calendar, per-tribe approval, CSV; visible to all (tribe-scoped) |
| Getting started | `getting_started` | — | onboarding |

Modules are toggled in **Admin → Modules**; capabilities per persona in **Admin → Personas**.

## Key business rules (explicit)

- **Objective RAG status is derived, not entered**: green/amber/red is computed from the squad's
  annual advancement vs. the time elapsed toward the objective's optional deadline (`target_date`).
  See [ADR-0007](adr/0007-derived-objective-status.md).
- **Squad health is quarter-scoped**: a squad's status (`blocked`/`at_risk`/`on_track`) is computed
  from its roadmap items in a quarter — there is no ambiguous all-time status.
- **Milestone (jalon) carries a mandatory EA/GA release stage** and an optional dependency that can
  target a squad, a tribe, or be free text; cross-squad dependencies surface on the target squad.
- **Progress timeline is auto-captured** on meaningful edits (coalesced), weekly, and on review notes.
- **Admin persona always retains access**; deleting a custom persona reassigns its users to `member`.
</content>
