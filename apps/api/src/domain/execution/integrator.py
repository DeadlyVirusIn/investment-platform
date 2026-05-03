"""End-to-end execution integrator.

Flow:
    primary_signal (composite_score, confidence, vol_20d)
        |
        v
    classify_regime(market_prices)   ->  regime + multiplier
        |
        v
    position_sizer (normalized | kelly)  ->  raw_size
        |
        v
    final_size = clip(raw_size * regime.multiplier, 0, max_size)

Pure function. No DB. No mutation.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.api.src.domain.execution.normalize import (
    ensure_annualized_vol,
    normalize_confidence,
)
from apps.api.src.domain.execution.regime import (
    RegimeSignal,
    classify_regime,
)
from apps.api.src.domain.execution.sizing import (
    MAX_POSITION_SIZE,
    SizingDecision,
    kelly_size,
    normalized_size,
)


@dataclass(frozen=True)
class PrimarySignal:
    """Post-normalization contract for the execution layer.

    INVARIANTS (enforced at construction via `from_raw`):
      - composite_score  ∈ [0, 1]
      - confidence       ∈ [0, 1]  (fractional, NOT percent)
      - realized_vol_20d annualized (not daily)

    Use `PrimarySignal.from_raw(...)` at the ingestion boundary. Direct
    construction is permitted but skips normalization — caller is on the
    hook for scale invariants.
    """

    symbol: str
    composite_score: float
    confidence: float
    realized_vol_20d: float

    @classmethod
    def from_raw(
        cls,
        symbol: str,
        composite_score: float | None,
        confidence_raw: float | None,
        vol_raw: float | None,
        *,
        vol_is_daily: bool = False,
    ) -> "PrimarySignal":
        """Apply confidence + volatility normalization at the boundary.

        - `confidence_raw`: accepts 0-100 percent OR 0-1 fractional; auto-detects.
        - `vol_raw`: pass `vol_is_daily=True` if the source is daily vol
          (backfill stores daily std). `realized_vol_20d` from regime_engine
          is already annualized — default `vol_is_daily=False`.
        """
        c = 0.0 if composite_score is None else max(0.0, min(1.0, float(composite_score)))
        conf = normalize_confidence(confidence_raw)
        vol = ensure_annualized_vol(vol_raw, is_daily=vol_is_daily)
        return cls(
            symbol=symbol,
            composite_score=c,
            confidence=conf,
            realized_vol_20d=vol,
        )


@dataclass(frozen=True)
class FinalAction:
    symbol: str
    primary: PrimarySignal
    regime: RegimeSignal
    sizing: SizingDecision
    final_size: float
    capped_at_max: bool


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def execute(
    primary: PrimarySignal,
    market_prices: list[float],
    *,
    method: str = "normalized",
    max_size: float = MAX_POSITION_SIZE,
    sizing_kwargs: dict | None = None,
) -> FinalAction:
    """Compute a FinalAction for a single primary signal.

    method: "normalized" | "kelly"
    sizing_kwargs: optional overrides passed to the sizer
    """
    if method not in ("normalized", "kelly"):
        raise ValueError(f"method must be normalized|kelly, got {method!r}")

    regime = classify_regime(market_prices)

    kwargs = dict(sizing_kwargs or {})
    kwargs.setdefault("max_size", max_size)
    if method == "normalized":
        sizing = normalized_size(
            primary.composite_score, primary.confidence,
            primary.realized_vol_20d, **kwargs,
        )
    else:
        sizing = kelly_size(
            primary.composite_score, primary.confidence,
            primary.realized_vol_20d, **kwargs,
        )

    gated = sizing.raw_size * regime.multiplier
    final = _clip(gated, 0.0, max_size)
    return FinalAction(
        symbol=primary.symbol,
        primary=primary,
        regime=regime,
        sizing=sizing,
        final_size=final,
        capped_at_max=gated >= max_size,
    )


def execute_batch(
    primaries: list[PrimarySignal],
    market_prices: list[float],
    *,
    method: str = "normalized",
    max_size: float = MAX_POSITION_SIZE,
    sizing_kwargs: dict | None = None,
) -> list[FinalAction]:
    """Batch mode — regime classified once, reused across all candidates.

    Market regime is by definition market-wide; classifying per-candidate
    would be wasteful and inconsistent.
    """
    if not primaries:
        return []
    # Classify once
    regime = classify_regime(market_prices)

    out: list[FinalAction] = []
    kwargs = dict(sizing_kwargs or {})
    kwargs.setdefault("max_size", max_size)
    for p in primaries:
        if method == "normalized":
            sizing = normalized_size(
                p.composite_score, p.confidence, p.realized_vol_20d, **kwargs,
            )
        else:
            sizing = kelly_size(
                p.composite_score, p.confidence, p.realized_vol_20d, **kwargs,
            )
        gated = sizing.raw_size * regime.multiplier
        final = _clip(gated, 0.0, max_size)
        out.append(FinalAction(
            symbol=p.symbol,
            primary=p,
            regime=regime,
            sizing=sizing,
            final_size=final,
            capped_at_max=gated >= max_size,
        ))
    return out
