"""Decision Support Layer (Phase 11I).

Read-only filtering, ranking, and computed shortlist views on top of
the Phase 11H evaluation scores. Output is OBSERVATIONAL — never a
recommendation, never an execution decision, never a "best trade".

NEVER imports V2 / equity / governance / ML / paper.engine mutation
modules. NEVER writes to any DB table. NEVER persists shortlists
server-side.

Modules:
  * buckets    — frozen bucket-classification rules
  * ranking    — deterministic sort key + tie-breaker explanation
  * review_queue — compute-on-read assembly of ranked rows
  * diagnostics — exclusion drivers + bucket counts
"""
