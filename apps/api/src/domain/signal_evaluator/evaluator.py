"""Pure label + return computation for Phase 1 signal_outcome.

No I/O. No DB. Deterministic. All policy constants declared here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

# ---------------------------------------------------------------------------
# Policy constants (locked — Phase 1)
# ---------------------------------------------------------------------------

# Absolute-return threshold below which outcome is 'breakeven'.
BREAKEVEN_THRESHOLD = Decimal("0.002")   # 0.2%

# Age multiplier beyond holding_period_bars before signal is timeout-labeled.
MAX_WAIT_MULTIPLIER = 2

OUTCOME_WIN = "win"
OUTCOME_LOSS = "loss"
OUTCOME_BREAKEVEN = "breakeven"
OUTCOME_TIMEOUT = "timeout"


@dataclass(frozen=True)
class EvaluationResult:
    realized_return: Decimal         # fractional, e.g. 0.034 == +3.4%
    max_drawdown: Decimal | None     # fractional, negative or zero
    entry_price: Decimal
    outcome_label: str


def label_outcome(
    realized_return: Decimal, signal_direction: str,
) -> str:
    """Apply threshold + direction labeling. No sign-based shortcut."""
    if abs(realized_return) < BREAKEVEN_THRESHOLD:
        return OUTCOME_BREAKEVEN

    direction = signal_direction.lower()
    positive = realized_return > 0

    if direction == "long":
        return OUTCOME_WIN if positive else OUTCOME_LOSS
    if direction == "short":
        return OUTCOME_LOSS if positive else OUTCOME_WIN
    # neutral — any material move is a loss (signal meant 'no move')
    return OUTCOME_LOSS


def is_timeout(
    signal_age_bars: int, holding_period_bars: int,
) -> bool:
    """True when signal has waited longer than MAX_WAIT_MULTIPLIER × horizon."""
    if holding_period_bars <= 0:
        return False
    return signal_age_bars > MAX_WAIT_MULTIPLIER * holding_period_bars


def compute_realized_return(
    entry_price: Decimal, exit_price: Decimal,
) -> Decimal:
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    return (exit_price - entry_price) / entry_price


def compute_max_drawdown(
    closes_over_window: Sequence[Decimal],
    entry_price: Decimal,
    signal_direction: str,
) -> Decimal | None:
    """Max adverse excursion within the holding window, expressed as a
    non-positive fraction (e.g. -0.045 == 4.5% drawdown against the signal).

    Long: worst low = min(closes)  → drawdown = (min - entry) / entry
    Short: worst high = max(closes) → drawdown = (entry - max) / entry
    Neutral: max |close - entry| / entry as magnitude (always negative)
    """
    if not closes_over_window or entry_price <= 0:
        return None
    direction = signal_direction.lower()

    if direction == "long":
        worst = min(closes_over_window)
        dd = (worst - entry_price) / entry_price
    elif direction == "short":
        worst = max(closes_over_window)
        dd = (entry_price - worst) / entry_price
    else:
        worst_delta = max(abs(c - entry_price) for c in closes_over_window)
        dd = -worst_delta / entry_price

    # Clamp to non-positive (drawdown never improves; 0 is best case).
    return dd if dd < 0 else Decimal("0")


def evaluate(
    *,
    entry_price: Decimal,
    exit_price: Decimal,
    closes_over_window: Sequence[Decimal],
    signal_direction: str,
    signal_age_bars: int,
    holding_period_bars: int,
) -> EvaluationResult:
    """Run full labeling pipeline — timeout check first, then threshold."""
    realized = compute_realized_return(entry_price, exit_price)
    dd = compute_max_drawdown(closes_over_window, entry_price, signal_direction)

    if is_timeout(signal_age_bars, holding_period_bars):
        label = OUTCOME_TIMEOUT
    else:
        label = label_outcome(realized, signal_direction)

    return EvaluationResult(
        realized_return=realized,
        max_drawdown=dd,
        entry_price=entry_price,
        outcome_label=label,
    )
