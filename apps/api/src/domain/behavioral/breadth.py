"""breadth_v1 — market participation confirmation / divergence.

Per-symbol signal fires only when universe breadth (pct above 50-SMA)
meaningfully supports OR contradicts the symbol's own trend state
relative to its own 50-SMA.

Inputs:
  - market_context.pct_above_ma50  (breadth proxy, [0, 1])
  - per-asset 50-bar history for own SMA comparison
"""

from __future__ import annotations

import datetime as dt

from apps.api.src.domain.behavioral.base import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    AssetHistory,
    BehavioralSignal,
    BehavioralSignalProvider,
    MarketContext,
    clip01,
    safe_mean,
)

# Thresholds (documented, not tuned)
SMA_WINDOW: int = 50
BREADTH_BULL_THRESHOLD: float = 0.65   # % above MA50 >= 65% → bullish breadth
BREADTH_BEAR_THRESHOLD: float = 0.35   # <= 35% → bearish breadth
# Anything in [0.35, 0.65] = ambiguous → no signal


class BreadthV1(BehavioralSignalProvider):
    strategy_id: str = "breadth_v1"

    def generate(
        self,
        as_of_date: dt.date,
        universe: list[AssetHistory],
        market_context: MarketContext,
    ) -> list[BehavioralSignal]:
        breadth = market_context.pct_above_ma50
        if breadth is None:
            return []

        bullish_breadth = breadth >= BREADTH_BULL_THRESHOLD
        bearish_breadth = breadth <= BREADTH_BEAR_THRESHOLD
        if not (bullish_breadth or bearish_breadth):
            return []   # ambiguous breadth — no signal

        ts = dt.datetime.combine(as_of_date, dt.time(22, 0), dt.timezone.utc)
        out: list[BehavioralSignal] = []

        # Distance from neutral (0.5); deeper extremes → stronger signal
        distance_from_neutral = abs(breadth - 0.5) * 2.0   # [0, 1]

        for asset in universe:
            if len(asset.bars) < SMA_WINDOW + 1:
                continue
            closes = asset.closes(SMA_WINDOW)
            if len(closes) < SMA_WINDOW:
                continue
            sma50 = safe_mean(closes)
            today = asset.latest
            if today is None or today.close <= 0 or sma50 <= 0:
                continue

            above_own_ma = today.close > sma50
            below_own_ma = today.close < sma50

            # Emit only on confirmation (breadth agrees with individual stance)
            if bullish_breadth and above_own_ma:
                direction = DIRECTION_LONG
                reason = (
                    f"breadth={breadth:.2%} >= {BREADTH_BULL_THRESHOLD:.0%} "
                    f"AND close {today.close:.2f} > SMA50 {sma50:.2f}"
                )
            elif bearish_breadth and below_own_ma:
                direction = DIRECTION_SHORT
                reason = (
                    f"breadth={breadth:.2%} <= {BREADTH_BEAR_THRESHOLD:.0%} "
                    f"AND close {today.close:.2f} < SMA50 {sma50:.2f}"
                )
            else:
                # Divergence / no confirmation — skip (per spec: only confirm)
                continue

            # Signal strength = distance from neutral breadth; confidence scales
            # with breadth magnitude plus own close-to-SMA relative distance
            strength = clip01(distance_from_neutral)
            own_dist = abs(today.close - sma50) / sma50
            confidence = clip01(distance_from_neutral * 0.5 + clip01(own_dist / 0.10) * 0.5)

            explanation = f"Breadth confirmation: {reason} -> {direction} signal."
            metadata = {
                "breadth_pct_above_ma50": round(breadth, 4),
                "asset_close": round(today.close, 4),
                "asset_sma50": round(sma50, 4),
                "asset_distance_from_sma50_pct": round(own_dist * 100, 4),
                "universe_size": market_context.universe_size,
                "thresholds": {
                    "breadth_bull": BREADTH_BULL_THRESHOLD,
                    "breadth_bear": BREADTH_BEAR_THRESHOLD,
                    "sma_window": SMA_WINDOW,
                },
            }
            out.append(BehavioralSignal(
                symbol=asset.symbol,
                timestamp=ts,
                strategy_id=self.strategy_id,
                signal_direction=direction,
                signal_strength=strength,
                confidence=confidence,
                explanation=explanation,
                metadata=metadata,
            ))
        return out
