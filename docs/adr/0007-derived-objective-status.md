# ADR-0007 - Objective RAG status is derived, not entered

**Status:** Accepted

## Context
Hand-entered objective statuses drift from reality (leaders forget to update them) and invite gaming.
Stakeholders asked for a status that reflects actual advancement.

## Options Considered
1. **Derive** RAG from the squad's annual advancement vs. the time elapsed toward the objective's
   optional deadline (`target_date`).
2. Keep manual RAG entry.
3. Remove status entirely.

## Decision
Option 1. `status.objective_status(objective, squad, now)` computes green/amber/red from
`annual_progress` vs. expected pace (linear to `target_date`, or year-end if none): on/ahead → green,
10-25 pts behind → amber, >25 pts behind or past deadline & incomplete → red. The `rag_status` column is
retained for storage but **overridden on read** everywhere (serializers, counts, snapshots, exports, report).

## Rationale
Status becomes objective and tamper-resistant, and automatically reflects deadlines. Input schemas drop
`rag_status`; the UI shows it read-only.

## Consequences
- All objectives of a squad share the squad's advancement, differentiated by their deadline - acceptable
  given there is no per-objective progress metric.
- Consistent status across dashboard, detail, exports and history.

## Risks
- Coarse (squad-level) granularity. Documented; could be refined if per-objective progress is added.

## Future Evolution
Optionally derive from the roadmap items in the deadline's quarter, or add per-objective progress.
</content>
