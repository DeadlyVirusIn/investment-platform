"""Cross-signal stock<->options analytics (read-only, paper-only)."""

from .strategy_map import (
    SCORE_BUCKETS, GATE_BUCKETS, TREND_BUCKETS, IV_BUCKETS,
    STRATEGY_BUCKETS,
    score_bucket, gate_bucket, trend_bucket, iv_bucket,
    strategy_bucket_from_db_name,
    build_strategy_map, build_today_assistant,
)
from .router import (
    RoutingThresholds, RoutingCaps, RouteCandidate,
    VALID_ROUTE_HINTS,
    decide_route, apply_caps, mark_executable,
    build_route_candidates, candidate_to_dict,
)

__all__ = [
    "SCORE_BUCKETS", "GATE_BUCKETS", "TREND_BUCKETS", "IV_BUCKETS",
    "STRATEGY_BUCKETS",
    "score_bucket", "gate_bucket", "trend_bucket", "iv_bucket",
    "strategy_bucket_from_db_name",
    "build_strategy_map", "build_today_assistant",
    "RoutingThresholds", "RoutingCaps", "RouteCandidate",
    "VALID_ROUTE_HINTS",
    "decide_route", "apply_caps", "mark_executable",
    "build_route_candidates", "candidate_to_dict",
]
