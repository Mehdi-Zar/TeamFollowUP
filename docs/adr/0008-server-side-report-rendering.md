# ADR-0008 — Server-side report/roadmap rendering (HTML + PPTX)

**Status:** Accepted

## Context
Leaders need shareable, branded reports: a weekly review and a "Global Roadmap" deck, downloadable and
emailable, consistent whether generated on-demand or by the scheduler.

## Options Considered
1. **Server-side rendering** in `report.py`: hand-built HTML + `python-pptx` decks.
2. Client-side export (browser print / JS pptx libs).
3. Headless-browser PDF service.

## Decision
Option 1. `report.py` builds a data model (`build_report_data`) then renders HTML (`render_html`,
`render_roadmap_html`) and PPTX (`render_pptx`, `render_roadmap_pptx`). The roadmap deck is a swimlane
matrix (quarters × squads, EA/GA, status colours) that always fits **one slide** via dynamic sizing.

## Rationale
Same renderer powers on-demand downloads, email attachments and the scheduler — one source of truth.
No browser dependency; deterministic output; i18n-aware.

## Consequences
- Reports work headless (cron/email) and in tests (`test_report` asserts structure + single-slide guarantee).
- The in-app roadmap view (`RoadmapPage`) mirrors the export's matrix for on-screen parity.

## Risks
- Hand-built HTML/PPTX is verbose; large rendering code in `report.py` (refactor candidate, TD-CODE-1).
- `python-pptx` optional at import; endpoints degrade gracefully (501/HTML-only) if missing.

## Future Evolution
Extract rendering into a sub-package; consider a templating layer; optional PDF output.
</content>
