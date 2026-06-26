# Tribe Cockpit — Documentation

> Outil de pilotage de tribe (organisation Agile à l'échelle) : consolidation de l'avancement
> des squads, roadmap, objectifs, KPIs, revue (COPIL), fil d'actualité, organigramme et exports.

This documentation set is designed so that a new engineer, CTO, auditor, operator or client can
understand, run, operate and extend the product **without further explanation**.

## Index

| # | Document | Audience |
|---|----------|----------|
| 01 | [Product Overview](01-product-overview.md) | Everyone / Exec / PM |
| 02 | [Architecture](02-architecture.md) | Engineers / Architects |
| 03 | [Data Model & Dictionary](03-data-model.md) | Engineers / DBA |
| 04 | [API Reference](04-api-reference.md) | Engineers / Integrators |
| 05 | [Security Model](05-security.md) | Security / Engineers |
| 06 | [Operations Runbook](06-operations-runbook.md) | Ops / SRE |
| 07 | [Developer Guide](07-developer-guide.md) | Engineers |
| 08 | [Testing Strategy](08-testing-strategy.md) | QA / Engineers |
| 09 | [Audit Report (consolidated)](09-audit-report.md) | Exec / Tech leads |
| 10 | [Technical Debt & Risk Register](10-tech-debt-and-risk-register.md) | Tech leads |
| 11 | [Roadmap & Enterprise Readiness](11-roadmap-and-enterprise-readiness.md) | Exec / Architects |
| 12 | [Deployment Guide (VMware · GCP · S3NS · AWS · Azure)](12-deployment-guide.md) | Ops / Architects |
| — | [Architecture Decision Records (ADR)](adr/README.md) | Engineers / Architects |

## At a glance

- **Stack**: FastAPI (Python 3.12) + SQLAlchemy 2 + PostgreSQL 16 · React 18 + TypeScript + Vite (SPA).
- **Packaging**: single Docker image (multi-stage) — the API also serves the built SPA. `docker compose` adds Postgres.
- **Auth**: signed session cookie · local password (Argon2) · OIDC (Authlib) · SAML (python3-saml) · break-glass admin.
- **Authorization**: role tiers + a configurable **persona → capability** matrix + per-module on/off switches.
- **Per squad**: products & hardware, OTD (committed annual objectives), detailed roadmap, curated key messages, and **budget tracking** (total / spent / forecast → on-track / at-risk / over), visible only to admin, the tribe leader and the squad's own leader.
- **Size**: ~8k LOC backend, ~9k LOC frontend, 20 API routers, 21 tables, 15 migrations, 14 backend test modules. Single-squad **HTML & PPTX exports** mirror the squad page.

See [01-product-overview](01-product-overview.md) for the full picture.
</content>
