"""Options strategy outcome scoring (read-only, paper-only)."""

from .outcome import (
    HORIZONS, OUTCOME_GOOD_PCT, OUTCOME_BAD_PCT,
    compute_strategy_outcomes,
    upsert_outcomes,
)

__all__ = [
    "HORIZONS", "OUTCOME_GOOD_PCT", "OUTCOME_BAD_PCT",
    "compute_strategy_outcomes", "upsert_outcomes",
]
