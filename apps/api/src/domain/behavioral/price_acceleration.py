"""price_acceleration_v1 — today's return normalized by realized daily vol.

Trigger when |return_zscore| > Z_SCORE_MIN. Direction = sign of return.

Return z-score uses trailing-20-day realized DAILY vol as the denominator
(not annualized — we're comparing a single-day move to single-day vol).
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
    daily_returns,
    safe_std,
)

# Thresholds (documented, not tuned)
LOOKBACK_BARS: int = 20
Z_SCORE_MIN: float = 2.0
MIN_DAILY_VOL: float = 1e-4   # below this vol, zscore undefined / noisy
SIGNAL_STRENGTH_SATURATION: float = 5.0   # z-score at which strength=1.0


class PriceAccelerationV1(BehavioralSignalProvider):
    strategy_id: str = "price_acceleration_v1"

    def generate(
        self,
        as_of_date: dt.date,
        universe: list[AssetHistory],
        market_context: MarketContext,
    ) -> list[BehavioralSignal]:
        out: list[BehavioralSignal] = []
        ts = dt.datetime.combine(as_of_date, dt.time(22, 0), dt.timezone.utc)

        for asset in universe:
            if len(asset.bars) < LOOKBACK_BARS + 1:
                continue
            closes = asset.closes(LOOKBACK_BARS + 1)
            if len(closes) < LOOKBACK_BARS + 1:
                continue

            prior_closes = closes[:-1]   # trailing window excludes today
            prior_rets = daily_returns(prior_closes)
            if len(prior_rets) < LOOKBACK_BARS - 2:
                continue

            daily_vol = safe_std(prior_rets)
            if daily_vol < MIN_DAILY_VOL:
                continue

            yesterday = prior_closes[-1]
            if yesterday <= 0:
                continue
            today_close = closes[-1]
            today_ret = (today_close - yesterday) / yesterday
            z = today_ret / daily_vol

            if abs(z) < Z_SCORE_MIN:
                continue

            direction = DIRECTION_LONG if z > 0 else DIRECTION_SHORT
            strength = clip01(abs(z) / SIGNAL_STRENGTH_SATURATION)
            # Confidence grows with z-magnitude, capped at 1.0
            confidence = clip01(abs(z) / (Z_SCORE_MIN * 2.0))

            explanation = (
                f"Today return {today_ret*100:+.2f}% vs daily vol "
                f"{daily_vol*100:.2f}% -> z={z:+.2f} -> {direction} signal."
            )
            metadata = {
                "return_zscore": round(z, 4),
                "today_return_pct": round(today_ret * 100.0, 4),
                "daily_vol_20d": round(daily_vol, 6),
                "lookback_bars": LOOKBACK_BARS,
                "thresholds": {
                    "z_score_min": Z_SCORE_MIN,
                    "min_daily_vol": MIN_DAILY_VOL,
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
