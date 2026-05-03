"""Unit tests: confidence (signal agreement) + RSI override in strong trends."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.features.feature_engine import (
    Series,
    compute_trend_momentum,
)
from apps.api.src.domain.recommendations.recommendation_engine import (
    _compute_confidence,
    _is_stale,
)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def _sig(score: str, weight: str = "1") -> dict[str, object]:
    return {"score": score, "weight": weight, "direction": "neutral"}


def test_confidence_all_aligned_high() -> None:
    sigs = [_sig("0.5"), _sig("0.8"), _sig("0.3")]
    conf, label = _compute_confidence(
        composite=Decimal("0.5"),
        signals=sigs,
        all_families_computable=True,
        stale=False,
    )
    assert conf == Decimal("100.00")
    assert label == "High"


def test_confidence_half_aligned_medium() -> None:
    # 2 positive, 2 negative; composite slightly positive → 2/4 = 50%
    sigs = [_sig("0.5"), _sig("0.3"), _sig("-0.3"), _sig("-0.4")]
    conf, label = _compute_confidence(
        composite=Decimal("0.05"),
        signals=sigs,
        all_families_computable=True,
        stale=False,
    )
    assert conf == Decimal("50.00")
    assert label == "Medium"


def test_confidence_penalty_missing_families() -> None:
    sigs = [_sig("0.5"), _sig("0.3")]
    conf_ok, _ = _compute_confidence(
        Decimal("0.4"), sigs, all_families_computable=True, stale=False
    )
    conf_missing, _ = _compute_confidence(
        Decimal("0.4"), sigs, all_families_computable=False, stale=False
    )
    assert conf_missing == conf_ok - Decimal("20.00")


def test_confidence_stale_penalty() -> None:
    # Mixed signals so fresh score lands Medium and stale drops to Low.
    sigs = [_sig("0.5"), _sig("0.3"), _sig("-0.4"), _sig("-0.2")]
    conf_fresh, _ = _compute_confidence(
        Decimal("0.05"), sigs, all_families_computable=True, stale=False
    )
    conf_stale, label = _compute_confidence(
        Decimal("0.05"), sigs, all_families_computable=True, stale=True
    )
    assert conf_stale == conf_fresh - Decimal("30.00")
    assert label == "Low"


def test_confidence_zero_signals_returns_low() -> None:
    conf, label = _compute_confidence(
        Decimal("0"), [_sig("0")], True, False
    )
    assert conf == Decimal("0")
    assert label == "Low"


def test_confidence_label_boundaries() -> None:
    # agreement=0.6 → 60 → High
    sigs = [_sig("0.5")] * 3 + [_sig("-0.5")] * 2
    conf, label = _compute_confidence(
        Decimal("0.1"), sigs, all_families_computable=True, stale=False
    )
    assert conf == Decimal("60.00")
    assert label == "High"


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def test_is_stale_none_series() -> None:
    assert _is_stale(None) is True


def test_is_stale_fresh_bar() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    s = Series(
        ts=[now - dt.timedelta(hours=6)],
        close=[Decimal("100")],
        high=[Decimal("100")],
        low=[Decimal("100")],
    )
    assert _is_stale(s) is False


def test_is_stale_old_bar() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    s = Series(
        ts=[now - dt.timedelta(days=10)],
        close=[Decimal("100")],
        high=[Decimal("100")],
        low=[Decimal("100")],
    )
    assert _is_stale(s) is True


# ---------------------------------------------------------------------------
# RSI override in strong uptrend
# ---------------------------------------------------------------------------


def _monotonic_up(n: int = 250, start: float = 100.0, step: float = 0.5) -> Series:
    base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    closes = [Decimal(str(start + i * step)) for i in range(n)]
    return Series(
        ts=[base + dt.timedelta(days=i) for i in range(n)],
        close=closes,
        high=[c + Decimal("0.5") for c in closes],
        low=[c - Decimal("0.5") for c in closes],
    )


def _tm_cfg() -> dict:
    return {
        "signals": {
            "ema_crossover": {"weight": 0.35},
            "rsi": {"weight": 0.30, "period": 14, "oversold": 35, "overbought": 68},
            "macd_signal": {"weight": 0.35},
        }
    }


def test_rsi_override_neutralizes_in_strong_uptrend() -> None:
    series = _monotonic_up()
    fam = compute_trend_momentum(series, _tm_cfg())
    rsi_sig = next(s for s in fam.signals if s.factor_key == "rsi_14")
    # RSI=100 would normally score -0.8; override neutralizes to 0.
    assert rsi_sig.score == Decimal("0")
    assert "override" in rsi_sig.narrative.lower()


def test_trend_strength_signal_present_and_bullish_uptrend() -> None:
    series = _monotonic_up()
    fam = compute_trend_momentum(series, _tm_cfg())
    ts_sig = next(s for s in fam.signals if s.factor_key == "trend_strength")
    assert ts_sig.score == Decimal("1")
    assert ts_sig.direction == "bullish"


def test_trend_strength_bearish_in_downtrend() -> None:
    down = _monotonic_up(start=200, step=-0.5)
    fam = compute_trend_momentum(down, _tm_cfg())
    ts_sig = next(s for s in fam.signals if s.factor_key == "trend_strength")
    assert ts_sig.score == Decimal("-1")
    assert ts_sig.direction == "bearish"


def test_strong_uptrend_family_score_clearly_positive() -> None:
    """Fix for the original RSI-saturation bug: uptrend now lands clearly bullish."""
    series = _monotonic_up()
    fam = compute_trend_momentum(series, _tm_cfg())
    assert fam.score >= Decimal("0.45")  # previously ~0.24 with RSI penalty
