"""Unit tests for recommendation engine scoring logic. Pure-function only."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.features.feature_engine import (
    Series,
    _atr,
    _max_drawdown,
    _rsi,
    _sma,
    compute_trend_momentum,
    compute_volatility_risk,
)
from apps.api.src.domain.recommendations.recommendation_engine import (
    _map_score_to_action,
    _snapshot_hash,
    load_engine_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _uptrend_series(n: int = 250, start: float = 100.0, step: float = 0.5) -> Series:
    base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    closes = [Decimal(str(start + i * step)) for i in range(n)]
    highs = [c + Decimal("0.5") for c in closes]
    lows = [c - Decimal("0.5") for c in closes]
    ts = [base + dt.timedelta(days=i) for i in range(n)]
    return Series(ts=ts, close=closes, high=highs, low=lows)


def _downtrend_series(n: int = 250) -> Series:
    base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    closes = [Decimal(str(200 - i * 0.5)) for i in range(n)]
    highs = [c + Decimal("0.5") for c in closes]
    lows = [c - Decimal("0.5") for c in closes]
    ts = [base + dt.timedelta(days=i) for i in range(n)]
    return Series(ts=ts, close=closes, high=highs, low=lows)


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------


def test_sma_basic() -> None:
    vals = [Decimal(str(v)) for v in range(1, 11)]  # 1..10
    assert _sma(vals, 5) == Decimal("8")  # avg(6,7,8,9,10)


def test_sma_insufficient() -> None:
    assert _sma([Decimal("1")], 5) is None


def test_rsi_strong_uptrend_high() -> None:
    vals = [Decimal(str(100 + i)) for i in range(20)]
    rsi = _rsi(vals, 14)
    assert rsi is not None
    assert rsi >= Decimal("60")  # Steady gains → RSI high


def test_rsi_strong_downtrend_low() -> None:
    vals = [Decimal(str(100 - i)) for i in range(20)]
    rsi = _rsi(vals, 14)
    assert rsi is not None
    assert rsi <= Decimal("40")


def test_max_drawdown_50_pct() -> None:
    vals = [Decimal("100"), Decimal("200"), Decimal("150"), Decimal("100")]
    assert _max_drawdown(vals) == Decimal("0.5")  # 200 → 100


def test_atr_shape() -> None:
    s = _uptrend_series(50)
    atr = _atr(s, 14)
    assert atr is not None
    assert atr > Decimal("0")


# ---------------------------------------------------------------------------
# Action mapping
# ---------------------------------------------------------------------------


def test_score_to_action_mapping() -> None:
    thr = {
        "BUY": Decimal("0.25"),
        "HOLD": Decimal("-0.25"),
        "REDUCE": Decimal("-0.65"),
    }
    assert _map_score_to_action(Decimal("0.80"), thr) == "Buy"
    assert _map_score_to_action(Decimal("0.25"), thr) == "Buy"
    assert _map_score_to_action(Decimal("0"), thr) == "Hold"
    assert _map_score_to_action(Decimal("-0.24"), thr) == "Hold"
    assert _map_score_to_action(Decimal("-0.50"), thr) == "Trim"
    assert _map_score_to_action(Decimal("-0.80"), thr) == "Sell"


# ---------------------------------------------------------------------------
# Family scoring
# ---------------------------------------------------------------------------


def _tm_cfg() -> dict:
    return {
        "signals": {
            "ema_crossover": {"weight": 0.35},
            "rsi": {"weight": 0.30, "period": 14, "oversold": 35, "overbought": 68},
            "macd_signal": {"weight": 0.35},
        }
    }


def _vr_cfg() -> dict:
    return {
        "signals": {
            "atr_pct": {"weight": 0.40, "period": 14},
            "beta": {"weight": 0.35},
            "max_drawdown": {"weight": 0.25, "lookback_days": 252},
        }
    }


def test_trend_momentum_uptrend_positive() -> None:
    fam = compute_trend_momentum(_uptrend_series(), _tm_cfg())
    assert fam.computable is True
    assert fam.score > Decimal("0")
    assert len(fam.signals) >= 2  # at least sma_vs_long + sma_20_vs_50


def test_trend_momentum_downtrend_negative() -> None:
    fam = compute_trend_momentum(_downtrend_series(), _tm_cfg())
    assert fam.computable is True
    assert fam.score < Decimal("0")


def test_trend_momentum_too_short_not_computable() -> None:
    short = _uptrend_series(n=10)
    fam = compute_trend_momentum(short, _tm_cfg())
    assert fam.computable is False


def test_volatility_risk_quiet_market_near_zero() -> None:
    # Very small step = low volatility, near-zero drawdown
    s = _uptrend_series(n=260, start=100, step=0.01)
    fam = compute_volatility_risk(s, _vr_cfg())
    assert fam.computable is True
    # atr_pct small, drawdown ~0 → score close to 0 (bounded)
    assert fam.score >= Decimal("-0.1")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_engine_config_loads() -> None:
    cfg = load_engine_config()
    assert cfg.version
    assert cfg.family_weights
    assert cfg.action_thresholds
    assert "trend_momentum" in cfg.family_weights
    assert cfg.config_hash
    assert len(cfg.config_hash) == 16


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_snapshot_hash_deterministic() -> None:
    inputs = {"a": 1, "b": "x", "c": Decimal("0.5")}
    h1 = _snapshot_hash(inputs)
    h2 = _snapshot_hash(inputs)
    assert h1 == h2
    assert len(h1) == 16


def test_snapshot_hash_changes_on_input_change() -> None:
    h1 = _snapshot_hash({"a": 1})
    h2 = _snapshot_hash({"a": 2})
    assert h1 != h2
