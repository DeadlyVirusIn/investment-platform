"""Walk-forward splits + sample-size gates.

No random k-fold. Time-ordered only. Gate on minimum row count before any
training is attempted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np
import pandas as pd

# From config: keep ground truth in one place so tests can override.
DEFAULT_MIN_TRAINING_ROWS = 1000
DEFAULT_DIAG_FLOOR        = 200   # <200 rows → diagnostics only
DEFAULT_WEAK_FLOOR        = 1000  # 200..1000 → baselines only
DEFAULT_STRONG_FLOOR      = 5000  # ≥5000 → richer experiments allowed


@dataclass(frozen=True)
class WalkForwardConfig:
    train_frac: float = 0.6
    val_frac: float   = 0.2
    test_frac: float  = 0.2
    # If rolling: step forward by `step_frac` after each fold
    rolling: bool = False
    step_frac: float = 0.1
    min_train_rows: int = 100      # per fold
    # PB-3 — Lopez de Prado AFML Ch.7. Purge removes train rows whose
    # label-evaluation window overlaps the test window. Embargo adds a
    # gap immediately AFTER each test fold so post-test info doesn't
    # bleed into next-fold train.
    purge_days: int = 5            # = max label horizon (5d default)
    embargo_days: int = 2


def enough_data_for_ml(
    n_rows: int,
    *,
    min_for_models: int = DEFAULT_MIN_TRAINING_ROWS,
    diag_floor: int = DEFAULT_DIAG_FLOOR,
    weak_floor: int = DEFAULT_WEAK_FLOOR,
    strong_floor: int = DEFAULT_STRONG_FLOOR,
) -> dict:
    """Return tier verdict + ML eligibility for dataset of `n_rows`."""
    if n_rows < diag_floor:
        tier, verdict = "diagnostics_only", False
    elif n_rows < weak_floor:
        tier, verdict = "baselines_only", False
    elif n_rows < strong_floor:
        tier, verdict = "walk_forward_ok", n_rows >= min_for_models
    else:
        tier, verdict = "rich_experiments_allowed", True
    return {
        "n_rows": n_rows,
        "tier": tier,
        "can_train": bool(verdict),
        "min_for_models": min_for_models,
    }


def walk_forward_splits(
    df: pd.DataFrame,
    *,
    cfg: WalkForwardConfig | None = None,
    date_col: str = "as_of_date",
) -> Iterator[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Yield (train_idx, val_idx, test_idx) as numpy index arrays.

    PB-3 — Now applies purge + embargo (AFML Ch.7):
      • Purge: drop train rows whose label-evaluation window overlaps
        any val/test row's time. Default purge = max label horizon (5d).
      • Embargo: drop train rows for embargo_days AFTER each test/val
        block, so future test info doesn't bleed into the next fold.

    Train rows always satisfy:
      train_date + purge_days <= min(val_date_starts)
      AND train_date NOT IN (test_end, test_end + embargo_days)
    """
    cfg = cfg or WalkForwardConfig()
    if date_col not in df.columns:
        raise ValueError(f"{date_col} required for time-ordered split")

    # Sort by time, preserve original positional index
    order = df[date_col].argsort(kind="mergesort").to_numpy()
    total = len(order)
    if total < 10:
        return  # no splits possible

    dates = pd.to_datetime(df[date_col]).to_numpy()
    purge_td = np.timedelta64(int(cfg.purge_days), "D")
    embargo_td = np.timedelta64(int(cfg.embargo_days), "D")

    def _apply_purge_embargo(
        train: np.ndarray, val: np.ndarray, test: np.ndarray,
    ) -> np.ndarray:
        """Remove train indices whose date is within purge_days BEFORE
        any val/test date OR within embargo_days AFTER any test date."""
        if len(train) == 0:
            return train
        # Sets of forbidden date windows
        val_test = np.concatenate([val, test]) if len(val) else test
        if len(val_test) == 0:
            return train
        forbid_starts = dates[val_test] - purge_td
        forbid_ends = dates[val_test]
        # Embargo only applies to TEST tail
        if len(test) > 0:
            test_end = dates[test].max()
            embargo_start = test_end
            embargo_end   = test_end + embargo_td
        else:
            embargo_start = embargo_end = None

        train_dates = dates[train]
        keep = np.ones(len(train), dtype=bool)
        # Vectorized purge — train_date is forbidden if ANY val/test
        # row sits in (train_date, train_date + purge_td]
        for i, td in enumerate(train_dates):
            in_purge = ((forbid_starts <= td) & (td < forbid_ends)).any()
            in_embargo = (
                embargo_start is not None
                and embargo_start <= td <= embargo_end
            )
            if in_purge or in_embargo:
                keep[i] = False
        return train[keep]

    if not cfg.rolling:
        t_end = int(total * cfg.train_frac)
        v_end = int(total * (cfg.train_frac + cfg.val_frac))
        if t_end < cfg.min_train_rows:
            return
        train = order[:t_end]
        val   = order[t_end:v_end]
        test  = order[v_end:]
        train = _apply_purge_embargo(train, val, test)
        yield (train, val, test)
        return

    # Rolling
    step = max(1, int(total * cfg.step_frac))
    train_len = int(total * cfg.train_frac)
    val_len   = int(total * cfg.val_frac)
    test_len  = int(total * cfg.test_frac)
    start = 0
    while start + train_len + val_len + test_len <= total:
        t_end = start + train_len
        v_end = t_end + val_len
        te_end = v_end + test_len
        if train_len < cfg.min_train_rows:
            break
        train = order[start:t_end]
        val   = order[t_end:v_end]
        test  = order[v_end:te_end]
        train = _apply_purge_embargo(train, val, test)
        yield (train, val, test)
        start += step


def split_report(
    df: pd.DataFrame,
    *,
    cfg: WalkForwardConfig | None = None,
    date_col: str = "as_of_date",
    label_col: str | None = None,
) -> list[dict]:
    """PB-3 — emit a per-fold dict with train/val/test ranges, purge,
    embargo, row counts, labeled-row counts. For diagnostics + tests."""
    cfg = cfg or WalkForwardConfig()
    out: list[dict] = []
    dates = pd.to_datetime(df[date_col])
    fold = 0
    for train_idx, val_idx, test_idx in walk_forward_splits(
        df, cfg=cfg, date_col=date_col,
    ):
        fold += 1
        def _rng(idx: np.ndarray) -> tuple[str, str]:
            if len(idx) == 0:
                return ("—", "—")
            return (
                str(dates.iloc[idx].min().date()),
                str(dates.iloc[idx].max().date()),
            )
        tr_min, tr_max = _rng(train_idx)
        v_min, v_max = _rng(val_idx)
        te_min, te_max = _rng(test_idx)
        # Purge / embargo dates are derived from val/test bounds
        purge_start = v_min if len(val_idx) else te_min
        embargo_end_dt = (
            (dates.iloc[test_idx].max()
             + pd.Timedelta(days=int(cfg.embargo_days)))
            if len(test_idx) else None
        )
        labeled = None
        if label_col and label_col in df.columns:
            labeled = int(
                df.iloc[train_idx][label_col].notna().sum(),
            )
        out.append({
            "fold": fold,
            "train": {"start": tr_min, "end": tr_max,
                       "rows": int(len(train_idx)),
                       "labeled": labeled},
            "val":   {"start": v_min, "end": v_max,
                       "rows": int(len(val_idx))},
            "test":  {"start": te_min, "end": te_max,
                       "rows": int(len(test_idx))},
            "purge_days":   int(cfg.purge_days),
            "embargo_days": int(cfg.embargo_days),
            "purge_window_start_before": purge_start,
            "embargo_until": (
                str(embargo_end_dt.date())
                if embargo_end_dt is not None else None
            ),
        })
    return out
