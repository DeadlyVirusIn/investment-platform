"""CB-1 — ES bar fallback in _load_bars.

Verifies:
  * ES trade can receive label_win_5d once forward bars exist
  * ES trade does NOT receive label before 5 forward bars exist
  * Missing bars → NaN, never a fake label
  * _load_bars emits the correct OHLC column set
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from apps.api.src.ml import dataset as ds
from apps.api.src.ml.labels import LabelConfig, attach_labels


def _es_bars_df(n_days: int, start: dt.date) -> pd.DataFrame:
    """Synthetic monotonically-increasing ES OHLC frame."""
    dates = [start + dt.timedelta(days=i) for i in range(n_days)]
    close = [100.0 + i for i in range(n_days)]
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "symbol": "ES",
        "open":  close,
        "high":  [c + 0.5 for c in close],
        "low":   [c - 0.5 for c in close],
        "close": close,
    })


def _empty_session():
    s = MagicMock()
    # Both SQL queries return empty
    empty_mapping = MagicMock()
    empty_mapping.all.return_value = []
    s.execute.return_value.mappings.return_value = empty_mapping
    return s


# ---------------------------------------------------------------------------

def test_load_bars_returns_es_bars_via_fallback(monkeypatch):
    """When price_bar + market_series_observation are empty, ES falls
    back through _fetch_es_bars_cached and returns usable OHLC rows."""
    decisions = pd.DataFrame({"instrument": ["ES", "ES"]})
    fake = _es_bars_df(n_days=10, start=dt.date(2026, 4, 14))
    monkeypatch.setattr(ds, "_fetch_es_bars_cached", lambda: fake)

    s = _empty_session()
    out = ds._load_bars(s, decisions, {})
    assert not out.empty
    assert set(out.columns) >= {"date", "symbol", "close", "high", "low"}
    assert out["symbol"].eq("ES").all()
    assert len(out) == 10


def test_load_bars_returns_empty_when_fallback_unavailable(monkeypatch):
    """No fake data if yfinance fallback fails. Empty in = empty out."""
    decisions = pd.DataFrame({"instrument": ["ES"]})
    monkeypatch.setattr(ds, "_fetch_es_bars_cached", lambda: None)

    s = _empty_session()
    out = ds._load_bars(s, decisions, {})
    assert out.empty


def test_label_attaches_when_forward_bars_present(monkeypatch):
    """ES decision from 2026-04-14 gets label_win_5d once 5 fwd bars exist."""
    decisions = pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date":  [pd.Timestamp("2026-04-14")],
        "symbol":      ["ES"],
    })
    # 8 bars: decision day + 7 forward trading-like days
    bars = _es_bars_df(n_days=8, start=dt.date(2026, 4, 14))
    out = attach_labels(decisions, bars, cfg=LabelConfig(horizons=(5,)))
    assert "label_win_5d" in out.columns
    assert out["label_win_5d"].iloc[0] in (True, 1.0)   # monotonic → win
    assert not pd.isna(out["fwd_ret_5d"].iloc[0])


def test_label_stays_nan_when_forward_bars_missing():
    """Decision with fewer than 5 forward bars → label stays NaN, not fake."""
    decisions = pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date":  [pd.Timestamp("2026-04-14")],
        "symbol":      ["ES"],
    })
    # Only 2 bars (decision day + 1 forward) → cannot compute 5d return
    bars = _es_bars_df(n_days=2, start=dt.date(2026, 4, 14))
    out = attach_labels(decisions, bars, cfg=LabelConfig(horizons=(5,)))
    assert pd.isna(out["fwd_ret_5d"].iloc[0])
    # label_win_5d is NaN when fwd_ret is NaN — pd.isna captures both
    # NaN and <NA>.
    assert pd.isna(out["label_win_5d"].iloc[0])


def test_label_stays_nan_when_bars_empty():
    """Empty bars frame → no fabricated labels."""
    decisions = pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date":  [pd.Timestamp("2026-04-14")],
        "symbol":      ["ES"],
    })
    bars = pd.DataFrame(columns=["date", "symbol", "close", "high", "low"])
    out = attach_labels(decisions, bars, cfg=LabelConfig(horizons=(5,)))
    assert pd.isna(out["fwd_ret_5d"].iloc[0])
    assert pd.isna(out["label_win_5d"].iloc[0])
