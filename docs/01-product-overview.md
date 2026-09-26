# 01 - Product Overview

## Vision

**TeamFollowUP** gives a tribe (a group of squads in a scaled-Agile organization) a single,
trustworthy place to consolidate and steer delivery: where each squad stands on its dated
commitments (OTD) and quarterly roadmap, what is blocked or at risk, and what was decided in the last
review (COPIL). It replaces scattered spreadsheets and slide decks with a live, role-aware product.

## Value proposition

- **One source of truth** for squad health, roadmap and commitments (OTD) across the whole tribe.
- **Low-friction reporting** for squad leaders (guided entry, auto-captured progress timeline).
- **Decision support** for tribe leaders / management: dashboard, attention list, weekly review,
  COPIL presentation mode, and one-click HTML/PPTX exports (incl. a "Global Roadmap" swimlane deck).
  An admin can upload a **PowerPoint template** (Admin > Appearance) that every PPTX export is then built
  on, so decks inherit the organisation's master slides, theme and branding.
- **Configurable governance**: turn modules on/off, and control which persona can access which section.

## Personas

| Persona (role) | Goals | Primary surfaces |
|----------------|-------|------------------|
| **Admin** | Configure the whole platform, manage tribes/users/personas, audit | Admin, all sections |
| **Tribe leader** | Steer the tribe, set management OTD, run COPIL, manage squads | Dashboard, Review, My squads, Roadmap |
| **Squad leader** | Report squad roadmap/progress/KPIs weekly, set up their squads (team, budget, committees, contributors) | Reporting (Saisie), My squads |
| **Contributor** | Fill in and submit the reporting of the squads they are named on | Reporting (Saisie) |
| **Member** | Stay informed (dashboard, roadmap, org, feed) | Dashboard, Roadmap, Org, Feed |
| *Custom persona* | Admin-defined, capability-scoped (e.g. "Auditor", "Stakeholder") | Per granted capabilities |

## Scope

In scope: tribe/squad org modelling, dated commitments (OTD), quarterly roadmap (milestones/jalons with
EA/GA stage and dependencies), KPIs, progress-review timeline, COPIL review + action items, feed,
org chart, notifications, weekly report scheduling and exports (HTML/PPTX; CSV for absences),
monthly steering-committee reporting (Steerco one-pager), i18n (FR/EN).

Out of scope (today): real-time collaboration, external ticketing sync (Jira/ADO), per-tenant data
isolation beyond tribe scoping, mobile native apps.

## Capability / feature matrix

| Feature | Module flag | Capability gate | Notes |
|---------|-------------|-----------------|-------|
| Dashboard | `dashboard` | `dashboard` | tribe-scoped for non-admins |
| Roadmap (matrix view) | `squad_content.roadmap` | `roadmap` | in-app swimlane + export |
| Org chart | `org` | `org` | view all tribes; edit = tribe/admin |
| Feed | `feed` (+reactions/replies/pin/kinds) | `feed` | post scope = leaders/everyone |
| Reporting (Saisie) | `reporting` | `reporting` | the squad's leader, co-leaders and contributors fill it in; leading a squad opens it whatever the persona |
| OTD (dated commitments) | - | via reporting / My squads | management OTD set in My squads, squad OTD set in the reporting; read by the whole tribe |
| KPIs | `squad_content.kpis` | via reporting | per-squad on/off |
| Review (COPIL) | `review` (+notes/weekly_report) | `review` | timeline + actions + presentation mode |
| Comitologie (committees) | `committees` (off by default) | via reporting | squad leaders declare recurring governance meetings; tribe-leader oversight |
| Steerco (steering committee) | `steerco` (off by default) | via reporting / `dashboard` | one slide per **platform**, fed by one or more squads, each item owned by one of them; monthly snapshot → auto-built KPI one-pager (HTML/PPTX), see [15](15-steerco.md) |
| My squads | - | `mysquads` (navigation only, see [05](05-security.md)) | management for tribe/squad leaders; the actions are guarded by role and ownership, not by the capability |
| Exports (HTML/PPTX) | via section modules | via section gates | dashboard, weekly, roadmap & dependencies decks (`/api/reports/*`) |
| Weekly report (HTML/PPTX/email) | `review.weekly_report` | - | scheduled + on-demand |
| Notifications | `notifications` (inapp/email) | - | bell + preferences |
| Leave / absences | `leaves` (+overlap_alert) | `leaves` | team calendar, per-tribe approval, CSV; visible to all (tribe-scoped) |
| Getting started | `getting_started` | - | onboarding |

Modules are toggled in **Admin > Modules**; capabilities per persona in **Admin > Personas**.

## Key business rules (explicit)

- **OTD status is derived, not entered**: on track, at risk, late or delivered, from the milestones
  that hold the commitment and its committed date. Squad objectives were retired (see
  [31](31-coherence-saisie-et-reporting.md)); [ADR-0007](adr/0007-derived-objective-status.md) is kept for history.
- **Squad health is quarter-scoped**: a squad's status (`blocked`/`at_risk`/`on_track`) is computed
  from its roadmap items in a quarter - there is no ambiguous all-time status.
- **Milestone (jalon) carries a mandatory EA/GA release stage** and an optional dependency that can
  target a squad, a tribe, or be free text; cross-squad dependencies surface on the target squad.
- **Progress timeline is auto-captured** on meaningful edits (coalesced), weekly, and on review notes.
- **Admin persona always retains access**; deleting a custom persona reassigns its users to `member`.
</content>
