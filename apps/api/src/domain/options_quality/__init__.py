"""Options strategy outcome scoring + promotion (read-only, paper-only)."""

from .outcome import (
    HORIZONS, OUTCOME_GOOD_PCT, OUTCOME_BAD_PCT,
    compute_strategy_outcomes,
    upsert_outcomes,
)
from .promotion import (
    PromotionThresholds, SizingConfig, PromotionCandidate,
    VALID_UNITS, VALID_HORIZONS, STRATEGY_DIRECTION,
    evaluate_promotions, candidate_to_dict,
    strategy_direction, iv_bucket_from_atm,
)

__all__ = [
    "HORIZONS", "OUTCOME_GOOD_PCT", "OUTCOME_BAD_PCT",
    "compute_strategy_outcomes", "upsert_outcomes",
    "PromotionThresholds", "SizingConfig", "PromotionCandidate",
    "VALID_UNITS", "VALID_HORIZONS", "STRATEGY_DIRECTION",
    "evaluate_promotions", "candidate_to_dict",
    "strategy_direction", "iv_bucket_from_atm",
]
