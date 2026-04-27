"""Options paper-trading engine (Phase 11E).

Trade simulation + lifecycle tracking + multi-leg defined-risk support.

Hard rules (DB + module-level):
  * paper_only = TRUE invariant enforced at DB level
  * NEVER imports V2 / equity / governance / live execution code
  * NEVER calls API / UI / ML modules
  * NEVER triggers external orders
  * Defined-risk strategies only — naked short legs are rejected at
    the open path
  * v1 assignment recorded for audit only — does NOT create synthetic
    equity positions

Conservative fill model — see `paper.fills` for invariants.
"""
