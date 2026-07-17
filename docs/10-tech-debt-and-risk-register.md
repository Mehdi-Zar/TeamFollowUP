# 10 - Technical Debt & Risk Register

Severity: **P0** (block prod) · **P1** (before scale) · **P2** (continuous improvement).

## Technical debt register

Legend: ✅ done · ◑ partial · ⬜ open.

| ID | Area | Item | Sev | Status / action |
|----|------|------|-----|------------------|
| TD-OPS-1 | Ops | No automated DB backup | P0 | ✅ `pg_dump` backup sidecar + rotation (compose `backup` profile) |
| TD-OPS-2 | Ops | No monitoring/metrics/alerting | P1 | ⬜ Prometheus/OTel + uptime + error alerting |
| TD-OPS-3 | Ops | Single-replica scheduler in-process | P1 | ✅ Postgres advisory lock → multi-replica safe (`main.py`) |
| TD-SEC-1 | Security | Default secrets / cookie not https_only | P0 | ◑ startup warning + **env-driven** `COOKIE_SECURE`/`SameSite` (set in prod) |
| TD-SEC-2 | Security | No login rate-limiting/lockout | P1 | ✅ per-IP throttle on `/api/auth/login` |
| TD-SEC-3 | Security | No dependency CVE scanning | P1 | ✅ Dependabot + `pip-audit`/`npm audit` CI job |
| TD-TEST-1 | Testing | No frontend/E2E tests | P1 | ◑ Vitest added + CI; Playwright E2E still open |
| TD-TEST-2 | Testing | No coverage threshold | P2 | ⬜ add coverage gate |
| TD-PERF-1 | Performance | Potential N+1 on dashboard/report at scale | P2 | ✅ `selectinload` eager-loading |
| TD-PERF-2 | Performance | Single JS bundle (no code-splitting) | P2 | ✅ route-level `React.lazy` (initial bundle 384→246 KB) |
| TD-DATA-1 | Data | `users.role` free string, personas in app_settings (no FK) | P2 | ⬜ admin PUT reassigns orphans; consider personas table |
| TD-DATA-2 | Data | `objectives.rag_status` retained but unauthoritative | P2 | ◑ documented |
| TD-DATA-3 | Data | No retention/rotation for audit_log | P2 | ✅ opt-in purge (`maintenance.py`, `AUDIT_RETENTION_DAYS`) |
| TD-CODE-1 | Code | `AdminPage.tsx` (~1.3k lines), `report.py` large | P2 | ⬜ split into sub-modules |
| TD-UI-1 | UI | Spacing/typography not tokenized | P2 | ⬜ introduce CSS tokens |
| TD-A11Y-1 | A11y | Admin form inputs lack `htmlFor`/`id` | P2 | ◑ user-creation form associated (+ password now masked); finish remaining forms |
| TD-API-1 | API | OpenAPI not snapshotted/diffed | P2 | ◑ `docs/openapi.json` committed; CI diff still open |

## Risk register

| ID | Risk | Likelihood | Impact | Priority | Owner | Mitigation |
|----|------|-----------|--------|----------|-------|------------|
| R-1 | Data loss (no backups) | Med | **Critical** | P0 | Ops | TD-OPS-1 |
| R-2 | Prod run with default secrets | Med | **Critical** | P0 | Security | TD-SEC-1 + startup guard |
| R-3 | Duplicate/lost scheduled emails if scaled >1 replica | Med | Med | P1 | Platform | TD-OPS-3 |
| R-4 | Brute-force/credential stuffing on login | Med | High | P1 | Security | TD-SEC-2 |
| R-5 | Unknown CVE in dependency | Med | High | P1 | Security | TD-SEC-3 |
| R-6 | Undetected regression (no FE/E2E tests) | Med | Med | P1 | QA | TD-TEST-1 |
| R-7 | Slow dashboard/report at large scale | Low | Med | P2 | Eng | TD-PERF-1 |
| R-8 | Operational blind spots (no monitoring) | Med | Med | P1 | SRE | TD-OPS-2 |

## Already remediated (recent loops) - for context
Capability gating coherence (feed/org write paths), silent-error blank screens, a11y (modal/keyboard/
status text/aria-labels), empty states, mobile drawer, i18n parity gate, dead-code removal, derived
objective status, EA/GA + dependency model, in-app roadmap, ⌘K palette, COPIL presentation mode.
</content>
