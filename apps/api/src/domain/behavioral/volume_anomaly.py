"""volume_anomaly_v1 — today's volume vs trailing 20-bar mean.

Trigger when volume ratio exceeds VOLUME_RATIO_MIN AND today's return
magnitude exceeds MIN_ABS_RETURN_PCT. Direction = sign of today's return.

No tuning. Thresholds are round numbers per spec; revise only after
observation-phase results.
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
    safe_std,
)

# Thresholds (documented, not tuned)
LOOKBACK_BARS: int = 20           # rolling window for volume mean/std
VOLUME_RATIO_MIN: float = 2.0     # today vol / 20d mean must exceed this
Z_SCORE_MIN: float = 2.0          # z-score alt trigger
MIN_ABS_RETURN_PCT: float = 0.005 # 0.5% — filter out high-vol + flat-price noise
SIGNAL_STRENGTH_SATURATION: float = 5.0   # volume ratio at which strength=1.0


class VolumeAnomalyV1(BehavioralSignalProvider):
    strategy_id: str = "volume_anomaly_v1"

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
            today = asset.latest
            if today is None or today.close <= 0:
                continue

            closes = asset.closes(LOOKBACK_BARS + 1)
            volumes = asset.volumes(LOOKBACK_BARS + 1)
            # Trailing window excludes today
            prior_vols = volumes[:-1]
            prior_closes = closes[:-1]

            mean_vol = safe_mean(prior_vols)
            std_vol = safe_std(prior_vols)
            today_vol = volumes[-1]
            if mean_vol <= 0 or today_vol <= 0:
                continue

            ratio = today_vol / mean_vol
            z_score = (today_vol - mean_vol) / std_vol if std_vol > 0 else 0.0

            yesterday_close = prior_closes[-1]
            if yesterday_close <= 0:
                continue
            today_return = (today.close - yesterday_close) / yesterday_close

            # Trigger gate
            if ratio < VOLUME_RATIO_MIN and z_score < Z_SCORE_MIN:
                continue
            if abs(today_return) < MIN_ABS_RETURN_PCT:
                continue

            direction = DIRECTION_LONG if today_return > 0 else DIRECTION_SHORT
            # Strength: saturates at 5x volume
            strength = clip01(ratio / SIGNAL_STRENGTH_SATURATION)
            # Confidence: higher z → higher confidence, capped at 1.0
            confidence = clip01(z_score / (Z_SCORE_MIN * 2.0))

            explanation = (
                f"Volume {ratio:.2f}x 20d-mean (z={z_score:.2f}), "
                f"{today_return*100:+.2f}% move same bar -> "
                f"{direction} behavioral signal."
            )
            metadata = {
                "volume_ratio": round(ratio, 4),
                "volume_zscore": round(z_score, 4),
                "today_volume": round(today_vol, 2),
                "mean_volume_20d": round(mean_vol, 2),
                "today_return_pct": round(today_return * 100.0, 4),
                "lookback_bars": LOOKBACK_BARS,
                "thresholds": {
                    "volume_ratio_min": VOLUME_RATIO_MIN,
                    "z_score_min": Z_SCORE_MIN,
                    "min_abs_return_pct": MIN_ABS_RETURN_PCT,
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
