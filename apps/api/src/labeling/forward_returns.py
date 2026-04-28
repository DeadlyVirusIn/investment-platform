"""Phase 11P.5 - deterministic forward-return label math.

Pure functions. No I/O. No DB. No model. NEVER imports broker / live
/ execution modules.

Frozen formulas:
  return_h(p_entry, p_exit)        = (p_exit - p_entry) / p_entry
  classify(r, threshold_pct)
      'positive' if r >  threshold_pct
      'negative' if r < -threshold_pct
      'neutral'  otherwise
  label_confidence(r, threshold)   = clip(|r|/threshold, 0, 1)
  mae(p_entry, prices)             = min((p_t - p_entry)/p_entry over t)
  mfe(p_entry, prices)             = max((p_t - p_entry)/p_entry over t)

Every formula deterministic — same inputs always yield identical
output. Bumping `LABEL_VERSION` would require a registry-review (a new
label_version creates new rows alongside existing labels and never
overwrites them).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence


LABEL_VERSION = "label-v1.0.0"
DEFAULT_THRESHOLD_PCT = Decimal("0.005")     # 50 bps deadband


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HorizonReturns:
    return_1d:  Decimal | None
    return_3d:  Decimal | None
    return_5d:  Decimal | None
    return_10d: Decimal | None
    return_20d: Decimal | None


@dataclass(frozen=True)
class ExcursionMetrics:
    mae: Decimal | None
    mfe: Decimal | None


@dataclass(frozen=True)
class OutcomeLabel:
    return_h: Decimal | None
    outcome_class: str | None     # 'positive' | 'negative' | 'neutral'
    label_confidence: Decimal | None
    threshold_pct: Decimal


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def compute_return_h(
    entry_price: Decimal | None,
    exit_price: Decimal | None,
) -> Decimal | None:
    """Frozen formula: simple percent return. Returns None when either
    price is missing or entry_price is zero."""
    if entry_price is None or exit_price is None:
        return None
    if entry_price == 0:
        return None
    return (exit_price - entry_price) / entry_price


def compute_mae_mfe(
    entry_price: Decimal | None,
    prices_window: Sequence[Decimal],
) -> ExcursionMetrics:
    """Compute Max Adverse Excursion (worst drawdown) and Max Favorable
    Excursion (best run-up) over a forward price window. Both as
    fractions of entry. Returns None/None when entry missing or window
    empty."""
    if entry_price is None or entry_price == 0 or not prices_window:
        return ExcursionMetrics(mae=None, mfe=None)
    rs: list[Decimal] = []
    for p in prices_window:
        if p is None:
            continue
        rs.append((p - entry_price) / entry_price)
    if not rs:
        return ExcursionMetrics(mae=None, mfe=None)
    return ExcursionMetrics(mae=min(rs), mfe=max(rs))


def classify_outcome(
    return_h: Decimal | None,
    threshold_pct: Decimal = DEFAULT_THRESHOLD_PCT,
) -> str | None:
    """Deadband classifier. Returns None when return_h is None."""
    if return_h is None:
        return None
    if return_h > threshold_pct:
        return "positive"
    if return_h < -threshold_pct:
        return "negative"
    return "neutral"


def compute_label_confidence(
    return_h: Decimal | None,
    threshold_pct: Decimal = DEFAULT_THRESHOLD_PCT,
) -> Decimal | None:
    """clip(|return_h|/threshold, 0, 1). Pure deterministic."""
    if return_h is None or threshold_pct == 0:
        return None
    raw = abs(return_h) / threshold_pct
    if raw < Decimal("0"):
        return Decimal("0")
    if raw > Decimal("1"):
        return Decimal("1")
    return raw


def compute_horizon_returns(
    entry_price: Decimal | None,
    prices_by_horizon: dict[int, Decimal | None],
) -> HorizonReturns:
    """Build a HorizonReturns dataclass from per-horizon exit prices."""
    return HorizonReturns(
        return_1d=compute_return_h(entry_price, prices_by_horizon.get(1)),
        return_3d=compute_return_h(entry_price, prices_by_horizon.get(3)),
        return_5d=compute_return_h(entry_price, prices_by_horizon.get(5)),
        return_10d=compute_return_h(
            entry_price, prices_by_horizon.get(10),
        ),
        return_20d=compute_return_h(
            entry_price, prices_by_horizon.get(20),
        ),
    )


def label_for_observation(
    *,
    entry_price: Decimal | None,
    prices_by_horizon: dict[int, Decimal | None],
    prices_full_window: Sequence[Decimal],
    threshold_pct: Decimal = DEFAULT_THRESHOLD_PCT,
    primary_horizon: int = 20,
) -> dict:
    """Build a single label dict from forward-price inputs. Pure-fn."""
    horizons = compute_horizon_returns(entry_price, prices_by_horizon)
    excursion = compute_mae_mfe(entry_price, prices_full_window)
    primary_return = prices_by_horizon.get(primary_horizon)
    primary_r = compute_return_h(entry_price, primary_return)
    outcome = classify_outcome(primary_r, threshold_pct)
    confidence = compute_label_confidence(primary_r, threshold_pct)
    return {
        "return_1d":  horizons.return_1d,
        "return_3d":  horizons.return_3d,
        "return_5d":  horizons.return_5d,
        "return_10d": horizons.return_10d,
        "return_20d": horizons.return_20d,
        "max_adverse_excursion":  excursion.mae,
        "max_favorable_excursion": excursion.mfe,
        "outcome_class": outcome,
        "outcome_threshold_pct": threshold_pct,
        "label_confidence": confidence,
        "label_version": LABEL_VERSION,
    }
