"""Phase 16 Phase 2 — Intraday ML shadow data collection.

This subpackage ships the durable observation-writer layer for the
intraday ML shadow. It does NOT include trainer / scorer / UI code —
those live in later phases gated on §3 quantitative gates (per
docs/research/INTRADAY_ML_SHADOW.md).
"""

from apps.api.src.ml.intraday.observation_writer import (
    TIME_OF_DAY_BUCKETS,
    derive_observation,
    feature_hash,
    time_of_day_bucket,
    write_observation,
)

__all__ = [
    "TIME_OF_DAY_BUCKETS",
    "derive_observation",
    "feature_hash",
    "time_of_day_bucket",
    "write_observation",
]
