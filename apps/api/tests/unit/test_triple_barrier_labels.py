"""PC-4 — triple-barrier labels (AFML Ch.3).

Verifies:
  * profit barrier hit first → outcome +1, barrier=profit_take
  * stop barrier hit first → outcome -1, barrier=stop_loss
  * neither hit → outcome 0, barrier=time
  * insufficient forward bars → all NaN labels (no fake)
  * label_win_5d preserved for backwards compatibility
"""

from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
import pytest

from apps.api.src.ml.labels import LabelConfig, attach_labels


def _bars(opens, highs, lows, closes, start=dt.date(2026, 1, 1)):
    n = len(closes)
    dates = [start + dt.timedelta(days=i) for i in range(n)]
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "symbol": "ES",
        "open":  opens,
        "high":  highs,
        "low":   lows,
        "close": closes,
    })


def _decision(date: dt.date):
    return pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date": [pd.Timestamp(date)],
        "symbol": ["ES"],
    })


def _cfg(**over):
    base = dict(
        horizons=(5,),
        cost_bps_round_trip=10.0,
        include_triple_barrier=True,
        tb_pt_sigma=2.0,
        tb_sl_sigma=2.0,
        tb_vol_window=20,
    )
    base.update(over)
    return LabelConfig(**base)


def test_profit_barrier_hit_first_yields_positive_outcome():
    """Pre-entry vol low → 2σ PT achievable. Forward path rallies fast."""
    # 20 pre-entry bars: tight oscillation around 100 (low vol)
    pre_close = [100 + 0.05 * np.sin(i) for i in range(20)]
    pre_high  = [c + 0.05 for c in pre_close]
    pre_low   = [c - 0.05 for c in pre_close]
    pre_open  = pre_close

    # 6 post-entry bars: jump up sharply on bar 2
    post_close = [100.0, 100.5, 102.5, 102.6, 102.7, 102.8]
    post_high  = [c + 0.1 for c in post_close]
    post_low   = [c - 0.1 for c in post_close]
    post_open  = post_close

    bars = _bars(
        opens=pre_open + post_open,
        highs=pre_high + post_high,
        lows=pre_low + post_low,
        closes=pre_close + post_close,
    )
    decision_date = bars["date"].iloc[20].date()
    decisions = _decision(decision_date)
    out = attach_labels(decisions, bars, cfg=_cfg())
    row = out.iloc[0]
    assert row["label_tb_outcome"] == 1.0
    assert row["label_tb_barrier_type"] == "profit_take"
    assert row["label_tb_hit_time"] >= 1
    assert row["label_tb_ret"] > 0


def test_stop_barrier_hit_first_yields_negative_outcome():
    pre_close = [100 + 0.05 * np.sin(i) for i in range(20)]
    pre_high  = [c + 0.05 for c in pre_close]
    pre_low   = [c - 0.05 for c in pre_close]
    pre_open  = pre_close

    # Sharp drop on bar 2
    post_close = [100.0, 99.5, 97.0, 96.9, 96.8, 96.7]
    post_high  = [c + 0.1 for c in post_close]
    post_low   = [c - 0.1 for c in post_close]
    post_open  = post_close

    bars = _bars(
        opens=pre_open + post_open,
        highs=pre_high + post_high,
        lows=pre_low + post_low,
        closes=pre_close + post_close,
    )
    decision_date = bars["date"].iloc[20].date()
    decisions = _decision(decision_date)
    out = attach_labels(decisions, bars, cfg=_cfg())
    row = out.iloc[0]
    assert row["label_tb_outcome"] == -1.0
    assert row["label_tb_barrier_type"] == "stop_loss"
    assert row["label_tb_ret"] < 0


def test_time_barrier_when_neither_hit():
    """Flat-ish forward path so neither PT nor SL trips → time barrier."""
    pre_close = [100 + 0.05 * np.sin(i) for i in range(20)]
    pre_high  = [c + 0.05 for c in pre_close]
    pre_low   = [c - 0.05 for c in pre_close]
    pre_open  = pre_close

    # Tiny drift, no spike
    post_close = [100.0, 100.02, 100.05, 100.04, 100.06, 100.07]
    post_high  = [c + 0.02 for c in post_close]
    post_low   = [c - 0.02 for c in post_close]
    post_open  = post_close

    bars = _bars(
        opens=pre_open + post_open,
        highs=pre_high + post_high,
        lows=pre_low + post_low,
        closes=pre_close + post_close,
    )
    decision_date = bars["date"].iloc[20].date()
    decisions = _decision(decision_date)
    out = attach_labels(decisions, bars, cfg=_cfg())
    row = out.iloc[0]
    assert row["label_tb_outcome"] == 0.0
    assert row["label_tb_barrier_type"] == "time"
    assert row["label_tb_hit_time"] == 5


def test_insufficient_forward_bars_yields_nan_labels():
    """Decision near end of bar series → no triple-barrier label."""
    # 20 pre + only 1 forward (insufficient for 5-day horizon)
    pre_close = [100 + 0.05 * np.sin(i) for i in range(20)]
    pre_high  = [c + 0.05 for c in pre_close]
    pre_low   = [c - 0.05 for c in pre_close]
    pre_open  = pre_close
    post_close = [100.0, 100.1]
    post_high  = [c + 0.05 for c in post_close]
    post_low   = [c - 0.05 for c in post_close]
    bars = _bars(
        opens=pre_open + post_close,
        highs=pre_high + post_high,
        lows=pre_low + post_low,
        closes=pre_close + post_close,
    )
    decision_date = bars["date"].iloc[20].date()
    decisions = _decision(decision_date)
    out = attach_labels(decisions, bars, cfg=_cfg())
    row = out.iloc[0]
    assert pd.isna(row["label_tb_outcome"])
    assert pd.isna(row["label_tb_ret"])
    assert pd.isna(row["label_tb_hit_time"])


def test_label_win_5d_still_emitted_for_backwards_compat():
    """PC-4 must NOT remove the legacy fixed-horizon label."""
    pre_close = [100 + 0.05 * np.sin(i) for i in range(20)]
    pre_high  = [c + 0.05 for c in pre_close]
    pre_low   = [c - 0.05 for c in pre_close]
    pre_open  = pre_close
    post_close = [100.0, 100.5, 102.5, 102.6, 102.7, 102.8]
    post_high  = [c + 0.1 for c in post_close]
    post_low   = [c - 0.1 for c in post_close]
    bars = _bars(
        opens=pre_open + post_close,
        highs=pre_high + post_high,
        lows=pre_low + post_low,
        closes=pre_close + post_close,
    )
    decision_date = bars["date"].iloc[20].date()
    decisions = _decision(decision_date)
    out = attach_labels(decisions, bars, cfg=_cfg())
    assert "label_win_5d" in out.columns
    assert "label_win_net_5d" in out.columns
    # Triple-barrier should additionally be present
    assert "label_tb_outcome" in out.columns
    assert "label_tb_barrier_type" in out.columns
