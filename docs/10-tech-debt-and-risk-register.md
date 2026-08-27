# 10 - Technical Debt & Risk Register

Severity: **P0** (block prod) · **P1** (before scale) · **P2** (continuous improvement).

## Technical debt register

Legend: ✅ done · ◑ partial · ⬜ open.

| ID | Area | Item | Sev | Status / action |
|----|------|------|-----|------------------|
| TD-OPS-1 | Ops | No automated DB backup | P0 | ✅ `pg_dump` sidecar + rotation, **dump verified before it is published** and retried on failure; restore procedure executed and written up ([19](19-plan-de-reprise.md)) |
| TD-OPS-2 | Ops | No monitoring/metrics/alerting | P1 | ✅ `/metrics` (Prometheus) + 7 alert rules + local Grafana stack ([17](17-observabilite.md)); external uptime probe still open |
| TD-OPS-3 | Ops | Single-replica scheduler in-process | P1 | ✅ Postgres advisory lock → multi-replica safe (`main.py`) |
| TD-SEC-1 | Security | Default secrets / cookie not https_only | P0 | ✅ startup warning + env-driven `COOKIE_SECURE`/`SameSite` + **the list is shown in Admin > Ops**, severity raised to critical once `PUBLIC_BASE_URL` says this is a deployment |
| TD-SEC-2 | Security | No login rate-limiting/lockout | P1 | ✅ per-IP throttle on `/api/auth/login` |
| TD-SEC-3 | Security | No dependency CVE scanning | P1 | ✅ Dependabot + `pip-audit`/`npm audit` CI job |
| TD-TEST-1 | Testing | No frontend/E2E tests | P1 | ✅ Vitest + **Playwright (12 tests) against the real stack in CI** ([18](18-tests-e2e.md)) + the K8s/SSO bench ([16](16-banc-kubernetes-sso.md)) |
| TD-TEST-2 | Testing | No coverage threshold | P2 | ✅ `pytest-cov` + `fail_under` ratchet (74%) enforced in CI |
| TD-PERF-1 | Performance | Potential N+1 on dashboard/report at scale | P2 | ✅ `selectinload` eager-loading |
| TD-PERF-2 | Performance | Single JS bundle (no code-splitting) | P2 | ✅ route-level `React.lazy` (initial bundle 384→246 KB) |
| TD-DATA-1 | Data | `users.role` free string, personas in app_settings (no FK) | P2 | ⬜ admin PUT reassigns orphans; consider personas table |
| TD-DATA-2 | Data | `objectives.rag_status` retained but unauthoritative | P2 | ◑ documented |
| TD-DATA-3 | Data | No retention/rotation for audit_log | P2 | ✅ opt-in purge for the audit log **and the feed** (`maintenance.py`); what is stored, for how long, and how to answer an access or erasure request: [20](20-donnees-personnelles-et-retention.md) |
| TD-CODE-1 | Code | `AdminPage.tsx`, `report.py` large | P2 | ✅ `AdminPage.tsx` 3085 → **152** (shell) + `pages/admin/*`; `report.py` 2440 → **1400** + `reportpptx` (the four decks) + `reportcommon` (the eleven names both formats share). Both moves were made behind a smoke test written first |
| TD-UI-1 | UI | Spacing/typography not tokenized | P2 | ⬜ introduce CSS tokens |
| TD-A11Y-1 | A11y | Form controls without an accessible name | P2 | ◑ **every control in `AdminPage.tsx` now has one** (visible `<label>` mirrored into `aria-label`, `aria-label` on inline table editors). Remaining: the other pages, and `htmlFor`/`id` pairing so clicking a label focuses its field |
| TD-API-1 | API | OpenAPI not snapshotted/diffed | P2 | ✅ `docs/openapi.json` committed + CI check (`dump_openapi.py --check`) |

## Risk register

| ID | Risk | Likelihood | Impact | Priority | Owner | Mitigation |
|----|------|-----------|--------|----------|-------|------------|
| R-1 | Data loss (no backups) | Low | **Critical** | P1 | Ops | TD-OPS-1 + a tested restore ([19](19-plan-de-reprise.md)). Residual: backups sit on the same host, unencrypted, and nothing alerts on repeated failures ([19](19-plan-de-reprise.md) §8) |
| R-2 | Prod run with default secrets | Low | **Critical** | P1 | Security | TD-SEC-1: the startup guard, plus a permanent notice in Admin > Ops naming each default still in use |
| R-3 | Duplicate/lost scheduled emails if scaled >1 replica | Med | Med | P1 | Platform | TD-OPS-3 |
| R-4 | Brute-force/credential stuffing on login | Med | High | P1 | Security | TD-SEC-2 |
| R-5 | Unknown CVE in dependency | Med | High | P1 | Security | TD-SEC-3 |
| R-6 | Undetected regression (no FE/E2E tests) | Low | Med | P2 | QA | TD-TEST-1 (Vitest + Playwright in CI) |
| R-7 | Slow dashboard/report at large scale | Low | Med | P2 | Eng | TD-PERF-1 |
| R-8 | Operational blind spots (no monitoring) | Low | Med | P2 | SRE | TD-OPS-2 (metrics + alerts shipped) |

## Already remediated (recent loops) - for context
Capability gating coherence (feed/org write paths), silent-error blank screens, a11y (modal/keyboard/
status text/aria-labels), empty states, mobile drawer, i18n parity gate, dead-code removal, derived
objective status, EA/GA + dependency model, in-app roadmap, ⌘K palette, COPIL presentation mode.
</content>
