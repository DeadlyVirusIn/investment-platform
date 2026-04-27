"""Options feature engine (Phase 11D).

Pure-fn modules + one orchestrator that performs UPSERT-only writes
into options_feature_daily on the natural key (as_of_date, underlying).

NEVER imports V2 / equity / strategy / execution code.
NEVER reads from non-`options_*` tables.
NEVER produces strategy recommendations or trades.
"""
