# 09 - Consolidated Audit Report

This is a point-in-time assessment across product, UX, UI, code, architecture, performance and
DevOps. Many findings from earlier audit loops have already been **remediated** (noted ✅); residual
items feed the [debt/risk register](10-tech-debt-and-risk-register.md) and [roadmap](11-roadmap-and-enterprise-readiness.md).

## Executive summary

The product is **functionally coherent and well-factored** for a mid-size internal tool: clean router
layering, server-side defense-in-depth, derived business rules, immutable snapshots, i18n, and a
recently modernized UX (in-app roadmap, mobile drawer, ⌘K palette, COPIL presentation mode, guided
reporting). The main gaps to "enterprise-grade" are **operational/industrial** (CI/CD, monitoring,
backups, frontend/E2E tests, secret hardening, horizontal-scale of the scheduler) rather than product.

**Overall maturity: solid product, early-stage industrialization.**

## Product audit
- ✅ Coherent capability/feature matrix; modules + personas give real governance.
- ✅ Business rules made explicit (derived objective status, quarter-scoped health, EA/GA, dependencies).
- Residual: no external tool sync (Jira/ADO); no multi-tenant isolation beyond tribe scoping; objective
  has no per-objective progress (status derived from squad annual %) - acceptable, documented.

## UX audit
- ✅ Empty states unified (`EmptyState`), error surfacing (Audit/Review), guided reporting section-nav,
  global roadmap view, command palette, COPIL presentation mode, anti-double-submit on cycle submit.
- ✅ Navigation: capability-driven, no infinite-redirect (capability denial → `/preferences`).
- Residual: deeper onboarding wizard (create first tribe/squad) - proposed; not built.

## UI audit
- ✅ Single CSS design system (`theme.css` + `ui.tsx`), consistent badges/dots/buttons; responsive
  drawer + matrices + modals (mobile width capped).
- Residual (P2): formalize spacing/typography **tokens**; finish `htmlFor` associations on a few admin
  forms; consolidate remaining inline-style duplications into classes.

## Code audit
- ✅ Clear separation (routers / deps / serializers / domain / config). Dead code removed (`whiteSelect`,
  unused render branch). Constants used over string literals where it matters.
- ✅ i18n: 0 missing keys, FR/EN parity enforced.
- Residual: a few large components (`AdminPage.tsx` ~1.3k lines) could be split; `report.py` is large
  (rendering) - readable but a candidate for module split.

## Architecture audit
- ✅ Simple, debuggable monolith serving the SPA; module/persona/role layering; Alembic migrations.
- Bottlenecks/SPOFs: **single app replica assumption** (in-process scheduler, sticky-less sessions are
  fine but scheduler isn't); DB is the single state store (acceptable; needs backups + HA for prod).

## Performance audit
- Reads compute health/progress per squad in Python (`status.py`) over loaded relationships. Fine at
  tribe scale (tens of squads). At larger scale, watch N+1 on dashboard/report (`db.scalars(select(Squad))`
  then per-squad relationship access). Quick wins: eager-load (`selectinload`) on dashboard/report
  queries; cache `app_settings` reads per request; paginate audit log.
- Frontend bundle ~384 KB / ~108 KB gzip (single chunk). Quick win: route-based code-splitting.

## DevOps audit
- ✅ Reproducible multi-stage Docker build; idempotent entrypoint (migrate + seed).
- Gaps (now partly addressed): **CI pipeline added** (`.github/workflows/ci.yml`); still missing
  automated backups, monitoring/alerting, image scanning, environment promotion (dev→staging→prod),
  and externalized scheduler for multi-replica.

## Top recommendations (see roadmap for full list)
1. **P0 security hardening**: enforce non-default `SECRET_KEY`/DB password/break-glass; `https_only` cookie behind TLS.
2. **P0/P1 ops**: automated DB backups; basic monitoring/alerting; CI gates (done) + image scan.
3. **P1 testing**: Vitest + Playwright; CI coverage gate.
4. **P1 scale**: externalize the scheduler (or leader-election) before running >1 app replica.
5. **P2 UI/code**: design tokens, split large components, route code-splitting, eager-loading.
</content>
