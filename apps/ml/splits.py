"""Purged-embargoed-grouped CV splits for time-series ML.

Groups are as_of_date. Purge = remove train samples whose label window
overlaps the validation fold. Embargo = skip N days after fold end before
next train period.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from loguru import logger


def purged_embargoed_group_folds(
    df: pd.DataFrame,
    group_col: str = "as_of_date",
    n_splits: int = 5,
    purge_days: int = 20,
    embargo_days: int = 2,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Yields (train_idx, val_idx) arrays of row-indices.

    Folds partition the sorted unique group values into n_splits contiguous
    chunks. purge_days removes rows from train whose label-horizon overlaps
    val. embargo_days skips days after val end before re-admitting train rows.
    """
    if group_col not in df.columns:
        raise KeyError(f"{group_col} missing from df")

    ordered = df.sort_values(group_col).reset_index(drop=True)
    groups = ordered[group_col].values
    unique_groups = pd.Index(sorted(pd.unique(groups)))
    n_groups = len(unique_groups)
    if n_groups < n_splits + 1:
        raise ValueError(
            f"too few groups ({n_groups}) for n_splits={n_splits}"
        )

    fold_size = n_groups // n_splits
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for k in range(n_splits):
        val_start = k * fold_size
        val_end = (k + 1) * fold_size if k < n_splits - 1 else n_groups
        val_groups = unique_groups[val_start:val_end]

        val_min = pd.Timestamp(val_groups.min())
        val_max = pd.Timestamp(val_groups.max())

        purge_lo = val_min - pd.Timedelta(days=purge_days)
        embargo_hi = val_max + pd.Timedelta(days=embargo_days)

        group_ts = pd.to_datetime(ordered[group_col])
        val_mask = group_ts.between(val_min, val_max)
        purge_mask = group_ts.between(purge_lo, val_min - pd.Timedelta(days=1))
        embargo_mask = group_ts.between(
            val_max + pd.Timedelta(days=1), embargo_hi,
        )
        train_mask = ~(val_mask | purge_mask | embargo_mask)

        train_idx = np.where(train_mask.to_numpy())[0]
        val_idx = np.where(val_mask.to_numpy())[0]
        logger.info(
            "[splits] fold={} val={}..{} train={} val={} purge_days={} embargo_days={}",
            k, val_min.date(), val_max.date(),
            len(train_idx), len(val_idx), purge_days, embargo_days,
        )
        folds.append((train_idx, val_idx))
    return folds
