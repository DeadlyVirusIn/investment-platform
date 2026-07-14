"""Experiment Lab — reproducible offline research tooling (Sprint 5).

Submodules:
  registry    — RegistryClient writing research_run ledger rows (migration 109)
  splits      — purged temporal walk-forward folds (no shuffling anywhere)
  metrics     — calibration / classification / trading metrics, edge-guarded
  benchmarks  — naive baselines every study must be compared against
  costs       — commission + half-spread-proxy slippage, gross vs net

Discipline (docs/architecture/RESEARCH_RUN_REGISTRY_SPEC.md): every run is
keyed by git SHA + config hash + data hash + seed; metrics are append-only
while running and frozen once terminal. Metrics only — nothing in this
package makes or implies performance claims.
"""
