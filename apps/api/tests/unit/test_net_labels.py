"""PA-2 — net-of-cost labels.

Verifies:
  * gross positive but net negative → label_win_net = 0
  * fwd_ret_net = fwd_ret − cost_frac
  * Missing forward bars → both gross AND net stay NaN (no silent fallback)
  * Trainer default ML_SHADOW_LABEL points at net column
"""

from __future__ import annotations

import datetime as dt
import pandas as pd
import pytest

from apps.api.src.ml.labels import LabelConfig, attach_labels


def _bars(n: int, start_close: float = 100.0, drift: float = 0.0):
    """Synthetic ES daily bars."""
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(n)]
    closes = [start_close + drift * i for i in range(n)]
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "symbol": "ES",
        "open":  closes,
        "high":  [c + 0.5 for c in closes],
        "low":   [c - 0.5 for c in closes],
        "close": closes,
    })


def _decision(date: dt.date):
    return pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date": [pd.Timestamp(date)],
        "symbol": ["ES"],
    })


def test_net_label_is_zero_when_gross_positive_but_below_cost():
    """Gross +5bps, cost 10bps round-trip → net −5bps → label_win_net=0."""
    # 8 bars: decision day + 7 forward.
    # Force ~5 bps drift over 5 days = ~1 bp/day = 100 * 0.0001 = 0.01
    bars = _bars(8, start_close=100.0, drift=0.005)   # ~5bps over 5 steps
    decisions = _decision(dt.date(2026, 1, 1))
    cfg = LabelConfig(horizons=(5,), cost_bps_round_trip=10.0)
    out = attach_labels(decisions, bars, cfg=cfg)
    gross = out["fwd_ret_5d"].iloc[0]
    net = out["fwd_ret_net_5d"].iloc[0]
    assert gross > 0, f"setup expected gross>0, got {gross}"
    assert gross < 10.0 / 1e4, "drift should give modest gross"
    assert net == pytest.approx(gross - 10.0 / 1e4)
    # Net is below win threshold (0) → label 0
    assert out["label_win_net_5d"].iloc[0] in (False, 0, 0.0)
    # Gross was positive → gross label 1 (proves divergence)
    assert out["label_win_5d"].iloc[0] in (True, 1, 1.0)


def test_net_label_one_when_gross_clearly_above_cost():
    bars = _bars(8, start_close=100.0, drift=2.0)   # huge drift
    decisions = _decision(dt.date(2026, 1, 1))
    cfg = LabelConfig(horizons=(5,), cost_bps_round_trip=10.0)
    out = attach_labels(decisions, bars, cfg=cfg)
    assert out["label_win_net_5d"].iloc[0] in (True, 1, 1.0)


def test_net_label_nan_when_forward_bars_missing():
    """No silent gross fallback when net is unavailable."""
    bars = _bars(2)  # only 2 bars, can't compute 5-day forward
    decisions = _decision(dt.date(2026, 1, 1))
    cfg = LabelConfig(horizons=(5,), cost_bps_round_trip=10.0)
    out = attach_labels(decisions, bars, cfg=cfg)
    assert pd.isna(out["fwd_ret_5d"].iloc[0])
    assert pd.isna(out["fwd_ret_net_5d"].iloc[0])
    assert pd.isna(out["label_win_5d"].iloc[0])
    assert pd.isna(out["label_win_net_5d"].iloc[0])


def test_net_subtracts_cost_exactly():
    bars = _bars(8, start_close=100.0, drift=0.05)
    decisions = _decision(dt.date(2026, 1, 1))
    cfg = LabelConfig(horizons=(5,), cost_bps_round_trip=20.0)
    out = attach_labels(decisions, bars, cfg=cfg)
    diff = out["fwd_ret_5d"].iloc[0] - out["fwd_ret_net_5d"].iloc[0]
    assert diff == pytest.approx(20.0 / 1e4, abs=1e-9)


def test_default_cost_matches_paper_pipeline_assumption():
    """Default cost_bps_round_trip should be 10.0 = entry 5bps + exit 5bps,
    matching PAPER_SLIPPAGE_BPS in config."""
    cfg = LabelConfig()
    assert cfg.cost_bps_round_trip == 10.0


def test_settings_default_label_is_net():
    """Production trainer should consume net-of-cost label by default."""
    from apps.api.src.config import settings
    assert settings.ML_SHADOW_LABEL == "label_win_net_5d"
