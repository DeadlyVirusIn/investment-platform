"""Layer 2 — normalized feature computation.

Each feature module exposes compute_* pure functions keyed on as_of_date.
Features write to features_daily table (one row per date × name × version).
"""
