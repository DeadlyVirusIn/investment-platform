"""PB-3 — purged + embargoed walk-forward splits.

Verifies:
  * train rows cannot overlap test label horizon
  * embargo removes post-test leakage
  * folds are chronological
  * split_report exposes train/test/purge/embargo ranges
"""

from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
import pytest

from apps.api.src.ml.splits import (
    WalkForwardConfig, walk_forward_splits, split_report,
)


def _frame(n_days: int) -> pd.DataFrame:
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i)
             for i in range(n_days)]
    return pd.DataFrame({
        "as_of_date": pd.to_datetime(dates),
        "x": np.arange(n_days, dtype=float),
        "label_win_net_5d": np.where(np.arange(n_days) % 2 == 0, 1, 0),
    })


def test_purge_removes_train_dates_within_horizon_of_test_start():
    """No train row may fall within `purge_days` BEFORE any val/test row."""
    df = _frame(200)
    cfg = WalkForwardConfig(
        train_frac=0.6, val_frac=0.2, test_frac=0.2,
        purge_days=5, embargo_days=2, min_train_rows=10,
    )
    [(train, val, test)] = list(walk_forward_splits(df, cfg=cfg))
    train_dates = pd.to_datetime(df.iloc[train]["as_of_date"]).to_numpy()
    val_dates   = pd.to_datetime(df.iloc[val]["as_of_date"]).to_numpy()
    earliest_val = val_dates.min()
    purge_cutoff = earliest_val - np.timedelta64(5, "D")
    assert (train_dates < purge_cutoff).all() | (
        train_dates >= earliest_val
    ).all(), "purge violated"
    # All train rows must be strictly before earliest_val OR after embargo
    in_window = (train_dates >= purge_cutoff) & (train_dates < earliest_val)
    assert not in_window.any(), (
        f"{in_window.sum()} train row(s) inside purge window"
    )


def test_embargo_excludes_post_test_period_from_train():
    """Train rolling fold should not include rows in
    [test_end, test_end + embargo_days]."""
    df = _frame(400)
    cfg = WalkForwardConfig(
        train_frac=0.4, val_frac=0.2, test_frac=0.2,
        rolling=True, step_frac=0.1,
        purge_days=5, embargo_days=3, min_train_rows=10,
    )
    folds = list(walk_forward_splits(df, cfg=cfg))
    assert len(folds) >= 2
    # For each fold AFTER the first, no train date should fall in the
    # previous fold's embargo window.
    prev_test_end = None
    for (train, _val, test) in folds:
        if prev_test_end is not None:
            train_dates = pd.to_datetime(
                df.iloc[train]["as_of_date"]
            ).to_numpy()
            embargo_start = prev_test_end
            embargo_end = prev_test_end + np.timedelta64(3, "D")
            in_embargo = (
                (train_dates >= embargo_start)
                & (train_dates <= embargo_end)
            )
            # Some train rows may legitimately be far AFTER the embargo,
            # but none should sit inside it.
            # (For rolling forward folds the new train mostly comes
            # AFTER prev_test_end, so this checks the embargo gap.)
            assert not in_embargo.any(), (
                f"{in_embargo.sum()} train row(s) in embargo of prior test"
            )
        prev_test_end = pd.to_datetime(
            df.iloc[test]["as_of_date"]
        ).max().to_numpy().astype("datetime64[D]")


def test_folds_are_chronological():
    df = _frame(300)
    cfg = WalkForwardConfig(
        train_frac=0.4, val_frac=0.2, test_frac=0.2,
        rolling=True, step_frac=0.1,
        purge_days=5, embargo_days=2, min_train_rows=10,
    )
    last_test_max = None
    for fold, (train, val, test) in enumerate(walk_forward_splits(df, cfg=cfg)):
        train_max = pd.to_datetime(df.iloc[train]["as_of_date"]).max()
        val_min   = pd.to_datetime(df.iloc[val]["as_of_date"]).min()
        test_min  = pd.to_datetime(df.iloc[test]["as_of_date"]).min()
        # Train precedes val; val precedes test
        assert train_max < val_min, "train must precede val"
        assert val_min < test_min, "val must precede test"
        if last_test_max is not None:
            current_test_max = pd.to_datetime(
                df.iloc[test]["as_of_date"]
            ).max()
            assert current_test_max >= last_test_max, "folds went backwards"
        last_test_max = pd.to_datetime(df.iloc[test]["as_of_date"]).max()


def test_split_report_emits_required_fields():
    df = _frame(200)
    cfg = WalkForwardConfig(
        train_frac=0.6, val_frac=0.2, test_frac=0.2,
        purge_days=5, embargo_days=2, min_train_rows=10,
    )
    rpt = split_report(df, cfg=cfg, label_col="label_win_net_5d")
    assert len(rpt) >= 1
    f0 = rpt[0]
    assert {"train", "val", "test", "purge_days",
             "embargo_days", "embargo_until"}.issubset(f0.keys())
    assert {"start", "end", "rows"}.issubset(f0["train"].keys())
    assert f0["purge_days"] == 5
    assert f0["embargo_days"] == 2
    assert f0["train"]["labeled"] is not None


def test_purge_zero_means_no_dropping():
    """purge_days=0 + embargo_days=0 should reproduce naive behavior."""
    df = _frame(100)
    cfg = WalkForwardConfig(
        train_frac=0.6, val_frac=0.2, test_frac=0.2,
        purge_days=0, embargo_days=0, min_train_rows=10,
    )
    [(train, val, test)] = list(walk_forward_splits(df, cfg=cfg))
    # All rows accounted for, no purge dropouts
    assert len(train) + len(val) + len(test) == len(df)
