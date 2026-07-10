"""Purged temporal walk-forward folds for the Experiment Lab.

Folds are calendar periods (quarter by default). For each eval period,
train rows are those whose date + embargo_days lies strictly BEFORE the
eval period start — rows inside the embargo band are EXCLUDED, never
shifted. Everything is a pure function of (dates, period, embargo_days):
no shuffling, no randomness of any kind. Every returned fold passes an
explicit leakage self-check (assert_no_leakage) before it leaves this
module.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_PERIOD = "Q"
DEFAULT_EMBARGO_DAYS = 10


class LeakageError(ValueError):
    """A train row's date + embargo reaches into its eval window."""


def assert_no_leakage(
    train_dates,
    eval_start,
    embargo_days: int,
) -> None:
    """Raise LeakageError if any train date + embargo_days >= eval_start.

    Public so studies composing their own folds can run the same check.
    """
    ts = pd.to_datetime(pd.Series(list(train_dates)))
    if ts.empty:
        return
    latest = ts.max()
    boundary = pd.Timestamp(eval_start)
    if latest + pd.Timedelta(days=embargo_days) >= boundary:
        raise LeakageError(
            f"train date {latest.date()} + embargo {embargo_days}d reaches "
            f"eval window starting {boundary.date()}"
        )


def purged_walk_forward_folds(
    df: pd.DataFrame,
    date_col: str = "as_of_date",
    *,
    period: str = DEFAULT_PERIOD,
    embargo_days: int = DEFAULT_EMBARGO_DAYS,
    min_train_rows: int = 1,
    min_eval_rows: int = 1,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return [(train_idx, eval_idx), ...] positional indices into df.

    period: pandas period alias ("Q" quarter default; "M", "Y", "W" also
    valid). Embargo is measured against the eval period's calendar start,
    not the first observed row — the stricter, data-independent boundary.
    Folds with too few train or eval rows are dropped, not padded.
    """
    if date_col not in df.columns:
        raise KeyError(f"{date_col} missing from df")
    if embargo_days < 0:
        raise ValueError(f"embargo_days must be >= 0, got {embargo_days}")

    dates = pd.to_datetime(df[date_col]).reset_index(drop=True)
    if dates.isna().any():
        raise ValueError(f"{date_col} contains unparseable/NaT values")
    periods = dates.dt.to_period(period)

    folds: list[tuple[np.ndarray, np.ndarray]] = []
    # skip the earliest period: nothing strictly before it can train
    for p in sorted(periods.unique())[1:]:
        eval_start = p.start_time
        eval_mask = (periods == p).to_numpy()
        train_mask = (
            dates + pd.Timedelta(days=embargo_days) < eval_start
        ).to_numpy()

        train_idx = np.flatnonzero(train_mask)
        eval_idx = np.flatnonzero(eval_mask)
        if len(train_idx) < min_train_rows or len(eval_idx) < min_eval_rows:
            continue

        assert_no_leakage(dates.iloc[train_idx], eval_start, embargo_days)
        folds.append((train_idx, eval_idx))

    if not folds:
        raise ValueError(
            f"no usable folds: {periods.nunique()} period(s) of {period!r}, "
            f"embargo_days={embargo_days} — need at least one eval period "
            "with embargoed history before it"
        )
    return folds
