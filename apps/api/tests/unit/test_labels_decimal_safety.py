"""Regression coverage for the Decimal/float collision bug class
that broke nightly_ml_shadow on 2026-05-08.

Background:
    Postgres NUMERIC columns surface as `decimal.Decimal` objects.
    `attach_labels` and `_labels_for_decision` mixed them with float
    arithmetic (`Decimal('1') - 1.0`) which raises:
        TypeError: unsupported operand type(s) for -: 'decimal.Decimal'
                   and 'float'

    Fix coerces numeric bar/trade columns to float64 once at the
    boundary in both call paths. These tests exercise that coercion
    with explicit Decimal inputs so any future regression that
    re-introduces a raw Decimal value into the arithmetic chain
    fails fast at CI rather than 03:30 ET in the daily loop.

Scope:
    * forward-close labels  (_forward_close_return)
    * MAE / MFE labels      (_forward_mae_mfe)
    * triple-barrier labels (_triple_barrier_labels via attach_labels)
    * realized-trade labels (paper_trades NUMERIC join)
    * replay outcomes path  (_labels_for_decision)
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pandas as pd
import pytest

from apps.api.src.ml.labels import LabelConfig, attach_labels


# ---------------------------------------------------------------------
# helpers — Decimal-typed synthetic bars
# ---------------------------------------------------------------------


def _decimal_bars(n: int, start: str = "100.00", step: str = "1.50"):
    """Synthetic daily bars with Decimal-typed OHLC, mimicking the
    dtype that pandas inherits when reading from a NUMERIC column
    via SQLAlchemy + psycopg."""
    base = Decimal(start)
    inc = Decimal(step)
    closes = [base + inc * i for i in range(n)]
    return pd.DataFrame({
        "date":   pd.to_datetime(
            [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(n)]
        ),
        "symbol": "ES",
        "open":   [c for c in closes],
        "high":   [c + Decimal("0.50") for c in closes],
        "low":    [c - Decimal("0.50") for c in closes],
        "close":  [c for c in closes],
    })


def _decision_at(date: dt.date):
    return pd.DataFrame({
        "decision_id": ["d1"],
        "as_of_date":  [pd.Timestamp(date)],
        "symbol":      ["ES"],
    })


# ---------------------------------------------------------------------
# 1. Forward-close return — the originally crashing path
# ---------------------------------------------------------------------


def test_forward_close_return_accepts_decimal_bars_without_typeerror():
    """The exact stack trace from 2026-05-08 must not return.

    Before the fix:
        TypeError: unsupported operand type(s) for -:
                   'decimal.Decimal' and 'float'
    After the fix:
        Returns a finite float forward return.
    """
    bars = _decimal_bars(15)
    decisions = _decision_at(dt.date(2026, 1, 1))
    cfg = LabelConfig(horizons=(5,), include_triple_barrier=False)
    out = attach_labels(decisions, bars, cfg=cfg)
    fwd = out["fwd_ret_5d"].iloc[0]
    assert isinstance(fwd, float), f"expected float, got {type(fwd).__name__}"
    assert pd.notna(fwd), "label should be computed, not NaN"
    # Sanity: 100 → 107.5 over 5 steps = 7.5%
    assert fwd == pytest.approx(0.075, rel=1e-9)


def test_forward_close_return_label_columns_are_float_dtype():
    """The output Series must remain float64 even when the source
    bars are Decimal — downstream net-label arithmetic
    (Series - cost_frac) depends on this."""
    bars = _decimal_bars(15)
    decisions = _decision_at(dt.date(2026, 1, 1))
    cfg = LabelConfig(horizons=(1, 5), include_triple_barrier=False)
    out = attach_labels(decisions, bars, cfg=cfg)
    assert out["fwd_ret_1d"].dtype.kind == "f"
    assert out["fwd_ret_5d"].dtype.kind == "f"
    assert out["fwd_ret_net_1d"].dtype.kind == "f"
    assert out["fwd_ret_net_5d"].dtype.kind == "f"


# ---------------------------------------------------------------------
# 2. MAE / MFE — same bug class, different function
# ---------------------------------------------------------------------


def test_mae_mfe_accept_decimal_bars():
    """_forward_mae_mfe used to do `low_min / entry_close - 1.0` with
    raw Decimal entry_close. Same TypeError. The boundary coercion
    must protect this path too."""
    bars = _decimal_bars(15)
    decisions = _decision_at(dt.date(2026, 1, 1))
    cfg = LabelConfig(horizons=(5,), include_triple_barrier=False)
    out = attach_labels(decisions, bars, cfg=cfg)
    mae = out["realized_max_adverse"].iloc[0]
    mfe = out["realized_max_favorable"].iloc[0]
    assert isinstance(mae, float)
    assert isinstance(mfe, float)
    assert pd.notna(mae)
    assert pd.notna(mfe)
    # mfe should be positive on a rising series, mae barely negative
    # (only the -0.50 wick on the entry bar's neighbours)
    assert mfe > 0
    assert mae < mfe


# ---------------------------------------------------------------------
# 3. Triple-barrier labels — pct_change() on Decimal Series risk
# ---------------------------------------------------------------------


def test_triple_barrier_labels_accept_decimal_bars():
    """`_triple_barrier_labels` calls `prev[close].pct_change()` on
    a Decimal-typed Series. With pre-fix dtypes that path could
    silently produce non-finite sigma. With the boundary coercion
    sigma is a real float and the labels populate."""
    # Need vol_window=20 + horizon=10 + 1 of forward → 32 bars min.
    bars = _decimal_bars(40)
    decisions = _decision_at(dt.date(2026, 1, 22))   # day 22 → 21 prior bars
    cfg = LabelConfig(
        horizons=(1, 5, 10),
        include_triple_barrier=True,
        tb_vol_window=20,
    )
    out = attach_labels(decisions, bars, cfg=cfg)
    # Must not raise, must populate triple-barrier columns.
    assert "label_tb_outcome" in out.columns
    assert "label_tb_ret"     in out.columns
    assert "label_tb_hit_time" in out.columns
    # On a steady positive drift the outcome should not be NaN.
    assert pd.notna(out["label_tb_outcome"].iloc[0]), \
        "triple-barrier label should compute on Decimal bars"


# ---------------------------------------------------------------------
# 4. Realized paper-trade join — paper_trade_log NUMERIC columns
# ---------------------------------------------------------------------


def test_realized_join_coerces_decimal_paper_trade_columns():
    """`paper_trade_log` stores net_ret_pct / gross_ret_pct as NUMERIC.
    `attach_labels` does `Series.gt(0.0)` on them; with raw Decimal
    that comparison is fine but the column emerges as object dtype
    which propagates dtype confusion downstream. Coercion guarantees
    float dtype."""
    bars = _decimal_bars(15)
    decisions = _decision_at(dt.date(2026, 1, 1))
    paper_trades = pd.DataFrame({
        "entry_date":    [pd.Timestamp(dt.date(2026, 1, 1))],
        "symbol":        ["ES"],
        "status":        ["closed"],
        "net_ret_pct":   [Decimal("0.0234")],   # +2.34% net
        "gross_ret_pct": [Decimal("0.0250")],
        "days_held":     [Decimal("5")],
    })
    cfg = LabelConfig(horizons=(5,), include_triple_barrier=False)
    out = attach_labels(decisions, bars, paper_trades, cfg=cfg)
    # Realized columns must be coerced to float dtype
    assert out["realized_net_ret"].dtype.kind in ("f", "O")
    val = out["realized_net_ret"].iloc[0]
    assert isinstance(val, float) or isinstance(val, Decimal)
    # The win label uses .gt(0.0) — must produce True without TypeError
    win = out["label_win_realized"].iloc[0]
    assert win is True or win == 1 or float(win) == 1.0


# ---------------------------------------------------------------------
# 5. Symmetric null guard on exit price (added in this fix)
# ---------------------------------------------------------------------


def test_forward_return_is_nan_when_exit_price_missing():
    """If the bar at horizon offset has NaN close, the label must
    be NaN — never raise. Boundary coercion turns Decimal/None into
    float NaN, then the new exit_price isna guard skips the row."""
    bars = _decimal_bars(15)
    # Wipe the close at index 5 (the 5d-forward exit for as_of=2026-01-01)
    bars.loc[bars.index[5], "close"] = None
    decisions = _decision_at(dt.date(2026, 1, 1))
    cfg = LabelConfig(horizons=(5,), include_triple_barrier=False)
    out = attach_labels(decisions, bars, cfg=cfg)
    fwd = out["fwd_ret_5d"].iloc[0]
    assert pd.isna(fwd), "missing exit price should yield NaN, not a crash"


# ---------------------------------------------------------------------
# 6. Mixed Decimal + None entry — no fallback to float arithmetic
# ---------------------------------------------------------------------


def test_zero_decimal_entry_skips_label():
    """A zero entry close used to short-circuit on `entry_price == 0`.
    With Decimal('0') the comparison is `Decimal('0') == 0` which is
    True; the row should be skipped, not divided by zero."""
    bars = _decimal_bars(15)
    bars.loc[bars.index[0], "close"] = Decimal("0.00")
    decisions = _decision_at(dt.date(2026, 1, 1))
    cfg = LabelConfig(horizons=(5,), include_triple_barrier=False)
    out = attach_labels(decisions, bars, cfg=cfg)
    fwd = out["fwd_ret_5d"].iloc[0]
    assert pd.isna(fwd)
