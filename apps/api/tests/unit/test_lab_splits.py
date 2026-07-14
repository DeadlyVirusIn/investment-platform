"""Unit tests — apps.ml.lab.splits purged temporal walk-forward folds.

Covers: embargo purge correctness (calendar boundary exact), determinism,
absence of any shuffling/randomness in the module source, and the
leakage self-check raising on violation.
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from apps.ml.lab import splits as lab_splits
from apps.ml.lab.splits import (
    LeakageError,
    assert_no_leakage,
    purged_walk_forward_folds,
)


def _weekly_df(start: str = "2023-01-02", periods: int = 78) -> pd.DataFrame:
    """~18 months of weekly rows spanning 6+ quarters."""
    dates = pd.date_range(start, periods=periods, freq="7D")
    return pd.DataFrame({
        "as_of_date": dates.date,  # datetime.date, like historical_label
        "x": np.arange(periods, dtype=float),
    })


def test_no_train_date_within_embargo_of_eval_start():
    df = _weekly_df()
    embargo = 10
    folds = purged_walk_forward_folds(df, embargo_days=embargo, period="Q")
    assert len(folds) >= 4
    dates = pd.to_datetime(df["as_of_date"])
    for train_idx, eval_idx in folds:
        eval_dates = dates.iloc[eval_idx]
        eval_start = eval_dates.min().to_period("Q").start_time
        # purge rule: every train date + embargo strictly before eval start
        train_dates = dates.iloc[train_idx]
        assert (train_dates + pd.Timedelta(days=embargo) < eval_start).all()
        # train/eval disjoint; eval confined to one quarter
        assert set(train_idx).isdisjoint(eval_idx)
        assert eval_dates.dt.to_period("Q").nunique() == 1


def test_embargo_boundary_is_exclusive_at_exact_touch():
    # eval quarter starts 2023-04-01; embargo 10d:
    #   2023-03-22 + 10d == 2023-04-01  -> EXCLUDED (>= eval start)
    #   2023-03-21 + 10d == 2023-03-31  -> included
    df = pd.DataFrame({"as_of_date": pd.to_datetime([
        "2023-01-05", "2023-03-21", "2023-03-22", "2023-04-03", "2023-04-10",
    ])})
    folds = purged_walk_forward_folds(df, embargo_days=10, period="Q")
    (train_idx, eval_idx), = folds
    assert list(train_idx) == [0, 1]   # 03-22 purged
    assert list(eval_idx) == [3, 4]


def test_deterministic_same_folds_twice():
    df = _weekly_df()
    a = purged_walk_forward_folds(df, embargo_days=5)
    b = purged_walk_forward_folds(df, embargo_days=5)
    assert len(a) == len(b)
    for (tr_a, ev_a), (tr_b, ev_b) in zip(a, b):
        assert np.array_equal(tr_a, tr_b)
        assert np.array_equal(ev_a, ev_b)


def test_no_shuffle_or_randomness_in_module_source():
    src = inspect.getsource(lab_splits)
    for forbidden in ("shuffle", "random_state", "np.random", "randint", "sample("):
        assert forbidden not in src, f"{forbidden!r} found in lab.splits source"


def test_leakage_self_check_raises_on_violation():
    # train date + embargo lands exactly on eval start -> violation
    with pytest.raises(LeakageError):
        assert_no_leakage(
            [pd.Timestamp("2023-03-22")],
            eval_start=pd.Timestamp("2023-04-01"),
            embargo_days=10,
        )
    # ... and reaching past it
    with pytest.raises(LeakageError):
        assert_no_leakage(
            [pd.Timestamp("2023-03-30")],
            eval_start=pd.Timestamp("2023-04-01"),
            embargo_days=10,
        )
    # strictly before the boundary is fine
    assert_no_leakage(
        [pd.Timestamp("2023-03-21")],
        eval_start=pd.Timestamp("2023-04-01"),
        embargo_days=10,
    )
    # empty train never leaks
    assert_no_leakage([], eval_start=pd.Timestamp("2023-04-01"), embargo_days=10)


def test_single_period_raises_no_usable_folds():
    df = pd.DataFrame(
        {"as_of_date": pd.date_range("2023-01-02", periods=10, freq="D")}
    )
    with pytest.raises(ValueError, match="no usable folds"):
        purged_walk_forward_folds(df, period="Q")


def test_configurable_period_monthly():
    df = _weekly_df(periods=30)
    q = purged_walk_forward_folds(df, period="Q", embargo_days=5)
    m = purged_walk_forward_folds(df, period="M", embargo_days=5)
    assert len(m) > len(q)  # finer calendar → more folds
    dates = pd.to_datetime(df["as_of_date"])
    for _, ev_idx in m:
        assert dates.iloc[ev_idx].dt.to_period("M").nunique() == 1


def test_rejects_missing_column_and_negative_embargo():
    df = _weekly_df()
    with pytest.raises(KeyError):
        purged_walk_forward_folds(df, date_col="nope")
    with pytest.raises(ValueError, match="embargo_days"):
        purged_walk_forward_folds(df, embargo_days=-1)
