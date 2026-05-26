"""Phase Opt-C2 Pre-Canary 0 — canary scaffolding package.

Modules:
  funnel        — write/read helpers for options_execution_funnel
  routes        — read-only HTTP endpoints for funnel + portfolio state

Discipline:
  * Read-only API surface.
  * Writes to options_execution_funnel happen exclusively from
    apps.worker.src.jobs.options_canary_promotion (Phase 1A) and
    options_lifecycle_check (Phase 1B). No HTTP route mutates.
"""
