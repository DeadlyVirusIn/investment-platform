"""Cross-signal stock<->options analytics (read-only, paper-only)."""

from .strategy_map import (
    SCORE_BUCKETS, GATE_BUCKETS, TREND_BUCKETS, IV_BUCKETS,
    STRATEGY_BUCKETS,
    score_bucket, gate_bucket, trend_bucket, iv_bucket,
    strategy_bucket_from_db_name,
    build_strategy_map, build_today_assistant,
)

__all__ = [
    "SCORE_BUCKETS", "GATE_BUCKETS", "TREND_BUCKETS", "IV_BUCKETS",
    "STRATEGY_BUCKETS",
    "score_bucket", "gate_bucket", "trend_bucket", "iv_bucket",
    "strategy_bucket_from_db_name",
    "build_strategy_map", "build_today_assistant",
]
