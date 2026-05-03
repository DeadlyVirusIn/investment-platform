"""Horizon-based label construction.

Labels are resolved from close-price bars *strictly after* each decision's
`decision_ts`. Uses daily OHLC; intraday labels (MAE/MFE inside the day)
require minute bars which aren't in the free-tier stack yet.

Two label families:
  * forward-close returns at {1,3,5,10} trading days
  * realized paper-trade outcomes when a matching trade closed

Win labels are binary: fwd_return > 0.

Guarantees:
  * label_date > decision_date for forward returns
  * realized labels only populated where paper_trade_log row status='closed'
  * no in-place mutation of the caller's frame

This module is IO-free. Pass in pre-fetched price bars as a pandas.DataFrame
with columns [date, symbol, close, high, low]. Missing bar data yields NaN
labels, which are filtered by the trainer.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

LABEL_HORIZONS: tuple[int, ...] = (1, 3, 5, 10)


@dataclass
class LabelConfig:
    horizons: tuple[int, ...] = LABEL_HORIZONS
    close_col: str = "close"
    high_col: str = "high"
    low_col: str = "low"
    date_col: str = "date"
    symbol_col: str = "symbol"
    # Small-return jitter; classify 0..+X bps as neutral to avoid noise
    win_threshold_bps: float = 0.0
    # PA-2 — round-trip cost in basis points (entry slip + exit slip).
    # Matches paper trading default (PAPER_SLIPPAGE_BPS=5.0 each side
    # = 10bps round-trip). Override via env or constructor.
    cost_bps_round_trip: float = 10.0
    # PC-4 — Triple-barrier configuration. Disabled by default for
    # backwards compat; enable via include_triple_barrier=True.
    include_triple_barrier: bool = True
    tb_pt_sigma: float = 2.0
    tb_sl_sigma: float = 2.0
    tb_vol_window: int = 20

    @property
    def max_horizon(self) -> int:
        return max(self.horizons) if self.horizons else 1


def attach_labels(
    decisions: pd.DataFrame,
    bars: pd.DataFrame,
    paper_trades: pd.DataFrame | None = None,
    *,
    cfg: LabelConfig | None = None,
) -> pd.DataFrame:
    """Return a *new* DataFrame with label columns appended.

    Parameters
    ----------
    decisions : DataFrame
        Rows with at least [decision_id, as_of_date, symbol].
    bars : DataFrame
        Daily OHLC rows: [date, symbol, close, high, low]. Sorted or not.
    paper_trades : DataFrame | None
        Optional trade log rows: [entry_date, symbol, engine, status,
        net_ret_pct, gross_ret_pct, days_held].

    Raises
    ------
    ValueError
        If `decisions` or `bars` is missing required columns.
    """
    cfg = cfg or LabelConfig()
    _require_cols(decisions, ["as_of_date", "symbol"])
    _require_cols(
        bars,
        [cfg.date_col, cfg.symbol_col, cfg.close_col,
         cfg.high_col, cfg.low_col],
    )

    out = decisions.copy()

    # Normalize types
    out["as_of_date"] = pd.to_datetime(out["as_of_date"]).dt.normalize()
    bars = bars.copy()
    bars[cfg.date_col] = pd.to_datetime(bars[cfg.date_col]).dt.normalize()

    # Build per-symbol sorted index once
    bars = bars.sort_values([cfg.symbol_col, cfg.date_col])

    # --- Forward close returns + win labels ---
    # PA-2: emit BOTH gross and net columns. Net subtracts the configured
    # round-trip cost in basis points from the forward return *before*
    # the win threshold. Production trainer should consume net labels;
    # gross labels stay for diagnostics so we can compare drift.
    cost_frac = float(cfg.cost_bps_round_trip) / 1e4
    for h in cfg.horizons:
        ret_col      = f"fwd_ret_{h}d"          # gross (legacy)
        ret_net_col  = f"fwd_ret_net_{h}d"      # net of cost (PA-2)
        win_col      = f"label_win_{h}d"        # gross win (legacy)
        win_net_col  = f"label_win_net_{h}d"    # net win (PA-2 production)
        out[ret_col] = _forward_close_return(
            out, bars, horizon_days=h, cfg=cfg,
        )
        out[ret_net_col] = out[ret_col] - cost_frac
        out[win_col] = (
            out[ret_col]
            .gt(cfg.win_threshold_bps / 1e4)
            .where(out[ret_col].notna(), other=np.nan)
        )
        # Net win label — propagates NaN, never falls back to gross.
        out[win_net_col] = (
            out[ret_net_col]
            .gt(cfg.win_threshold_bps / 1e4)
            .where(out[ret_net_col].notna(), other=np.nan)
        )

    # --- Forward MAE / MFE over max_horizon window ---
    mae, mfe = _forward_mae_mfe(out, bars, horizon_days=cfg.max_horizon, cfg=cfg)
    out["realized_max_adverse"]  = mae
    out["realized_max_favorable"] = mfe

    # --- PC-4 Triple-barrier labels (path-dependent, AFML Ch.3) ---
    if cfg.include_triple_barrier:
        tb = _triple_barrier_labels(
            out, bars,
            horizon_days=cfg.max_horizon, cfg=cfg,
            pt_sigma=cfg.tb_pt_sigma, sl_sigma=cfg.tb_sl_sigma,
            vol_window=cfg.tb_vol_window,
        )
        for k, v in tb.items():
            out[k] = v

    # --- Realized paper-trade outcome join ---
    if paper_trades is not None and not paper_trades.empty:
        pt = paper_trades.copy()
        pt["entry_date"] = pd.to_datetime(pt["entry_date"]).dt.normalize()
        # Keep only closed trades for outcome labels
        closed = pt[pt["status"].eq("closed")]
        merge_cols = ["entry_date", "symbol"]
        if "engine" in pt.columns and "engine" in out.columns:
            merge_cols.append("engine")
        rename_map = {
            "net_ret_pct":   "realized_net_ret",
            "gross_ret_pct": "realized_gross_ret",
            "days_held":     "realized_days_held",
        }
        closed = closed.rename(columns=rename_map)
        keep = merge_cols + [c for c in rename_map.values()
                             if c in closed.columns]
        closed = closed[keep].drop_duplicates(merge_cols)
        # Attach via as_of_date <-> entry_date
        out = out.merge(
            closed,
            how="left",
            left_on=[c if c != "entry_date" else "as_of_date" for c in merge_cols],
            right_on=merge_cols,
            suffixes=("", "_trade"),
        )
        # Drop accidental duplicate merge key columns
        for c in merge_cols:
            if c in out.columns and c != "as_of_date" and c != "engine":
                out = out.drop(columns=[c])

    # Ensure standard label columns exist even when trades absent
    for c in (
        "realized_net_ret", "realized_days_held", "realized_gross_ret",
    ):
        if c not in out.columns:
            out[c] = np.nan

    out["label_win_realized"] = (
        out["realized_net_ret"].gt(0.0)
          .where(out["realized_net_ret"].notna(), other=np.nan)
    )

    # Optional stop/target hit flags: only available when we have explicit
    # fields in paper_trade_log. Placeholder for future richer audit path.
    for c in ("hit_target", "hit_stop"):
        if c not in out.columns:
            out[c] = np.nan

    return out


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _require_cols(df: pd.DataFrame, cols: Iterable[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")


def _forward_close_return(
    dec: pd.DataFrame, bars: pd.DataFrame, *,
    horizon_days: int, cfg: LabelConfig,
) -> pd.Series:
    """Close[t+h] / Close[t] - 1 where t = as_of_date, using trading-day bars."""
    # Build per-symbol indexed close Series for O(1) lookups
    out = pd.Series(np.nan, index=dec.index, dtype="float64")
    by_sym = {
        sym: g.set_index(cfg.date_col)
        for sym, g in bars.groupby(cfg.symbol_col, sort=False)
    }
    for idx, row in dec[["symbol", "as_of_date"]].iterrows():
        sym = row["symbol"]
        asof = row["as_of_date"]
        g = by_sym.get(sym)
        if g is None or g.empty:
            continue
        # Entry close at the decision date (or next available bar)
        future = g.loc[g.index >= asof]
        if len(future) <= horizon_days:
            continue
        entry_price = future[cfg.close_col].iloc[0]
        exit_price  = future[cfg.close_col].iloc[horizon_days]
        if entry_price is None or entry_price == 0 or pd.isna(entry_price):
            continue
        out.at[idx] = (exit_price / entry_price) - 1.0
    return out


# ---------------------------------------------------------------------------
# PC-4 — Triple-barrier labels (AFML Ch.3).
# Path-dependent: walk forward bar-by-bar, return on first barrier hit.
# Profit-take = +pt_sigma * realized_vol * sqrt(horizon)
# Stop-loss   = -sl_sigma * realized_vol * sqrt(horizon)
# Time barrier= max horizon (cfg.max_horizon trading days)
# ---------------------------------------------------------------------------

def _triple_barrier_labels(
    dec: pd.DataFrame, bars: pd.DataFrame, *,
    horizon_days: int, cfg: LabelConfig,
    pt_sigma: float, sl_sigma: float, vol_window: int,
) -> dict[str, pd.Series]:
    """Compute path-dependent triple-barrier labels.

    Returns a dict of pandas Series aligned to `dec.index`:
      * label_tb_outcome   in {-1, 0, +1, NaN}
            +1 = profit-take hit first
            -1 = stop-loss hit first
             0 = time barrier (no hit)
           NaN = insufficient forward bars
      * label_tb_ret       realized return on the bar that closed the trade
      * label_tb_hit_time  trading-day index when barrier hit (1..horizon)
                            or `horizon` when time barrier; NaN if missing
      * label_tb_barrier   one of {profit_take, stop_loss, time, none}
    """
    n = len(dec)
    out_outcome = pd.Series(np.nan, index=dec.index, dtype="float64")
    out_ret     = pd.Series(np.nan, index=dec.index, dtype="float64")
    out_hit     = pd.Series(np.nan, index=dec.index, dtype="float64")
    out_barrier = pd.Series("none", index=dec.index, dtype="object")
    out_barrier[:] = pd.NA

    by_sym = {
        sym: g.sort_values(cfg.date_col).reset_index(drop=True)
        for sym, g in bars.groupby(cfg.symbol_col, sort=False)
    }

    for idx, row in dec[["symbol", "as_of_date"]].iterrows():
        sym = row["symbol"]
        asof = pd.Timestamp(row["as_of_date"]).normalize()
        g = by_sym.get(sym)
        if g is None or g.empty:
            continue
        # Find the first bar AT or AFTER as_of as the entry
        future_mask = g[cfg.date_col] >= asof
        if not future_mask.any():
            continue
        start_pos = int(future_mask.idxmax())
        # Need horizon_days forward bars after entry
        need = start_pos + horizon_days
        if need >= len(g):
            continue
        # Realized vol over (vol_window) bars BEFORE entry
        if start_pos < vol_window:
            continue
        prev = g.iloc[max(0, start_pos - vol_window):start_pos]
        if len(prev) < 2:
            continue
        rets = prev[cfg.close_col].pct_change().dropna()
        if rets.empty:
            continue
        sigma = float(rets.std())
        if not np.isfinite(sigma) or sigma <= 0:
            continue

        scale = float(np.sqrt(horizon_days))
        pt = pt_sigma * sigma * scale
        sl = sl_sigma * sigma * scale

        entry_close = float(g[cfg.close_col].iloc[start_pos])
        if entry_close <= 0 or pd.isna(entry_close):
            continue

        outcome = 0
        ret_at_hit = 0.0
        hit_at = horizon_days
        barrier = "time"
        # Walk bars 1..horizon
        for k in range(1, horizon_days + 1):
            high = float(g[cfg.high_col].iloc[start_pos + k])
            low  = float(g[cfg.low_col].iloc[start_pos + k])
            close = float(g[cfg.close_col].iloc[start_pos + k])
            up_ret = (high - entry_close) / entry_close
            dn_ret = (low - entry_close) / entry_close
            if up_ret >= pt and dn_ret <= -sl:
                # Both hit same bar — use close direction as tie-break
                close_ret = (close - entry_close) / entry_close
                if close_ret >= 0:
                    outcome, ret_at_hit, barrier = 1, pt, "profit_take"
                else:
                    outcome, ret_at_hit, barrier = -1, -sl, "stop_loss"
                hit_at = k
                break
            if up_ret >= pt:
                outcome, ret_at_hit, barrier = 1, pt, "profit_take"
                hit_at = k
                break
            if dn_ret <= -sl:
                outcome, ret_at_hit, barrier = -1, -sl, "stop_loss"
                hit_at = k
                break
        else:
            # Time barrier — close-based outcome
            close_h = float(g[cfg.close_col].iloc[start_pos + horizon_days])
            ret_at_hit = (close_h - entry_close) / entry_close

        out_outcome.at[idx] = float(outcome)
        out_ret.at[idx]     = float(ret_at_hit)
        out_hit.at[idx]     = float(hit_at)
        out_barrier.at[idx] = barrier

    return {
        "label_tb_outcome":     out_outcome,
        "label_tb_ret":         out_ret,
        "label_tb_hit_time":    out_hit,
        "label_tb_barrier_type": out_barrier,
    }


def _forward_mae_mfe(
    dec: pd.DataFrame, bars: pd.DataFrame, *,
    horizon_days: int, cfg: LabelConfig,
) -> tuple[pd.Series, pd.Series]:
    """Max adverse / favorable excursion within horizon window, pct of entry."""
    mae = pd.Series(np.nan, index=dec.index, dtype="float64")
    mfe = pd.Series(np.nan, index=dec.index, dtype="float64")
    by_sym = {
        sym: g.set_index(cfg.date_col)
        for sym, g in bars.groupby(cfg.symbol_col, sort=False)
    }
    for idx, row in dec[["symbol", "as_of_date"]].iterrows():
        sym = row["symbol"]
        asof = row["as_of_date"]
        g = by_sym.get(sym)
        if g is None or g.empty:
            continue
        future = g.loc[g.index >= asof]
        if len(future) < 2:
            continue
        window = future.iloc[: horizon_days + 1]
        entry_close = window[cfg.close_col].iloc[0]
        if entry_close in (0, None) or pd.isna(entry_close):
            continue
        low_min  = window[cfg.low_col].iloc[1:].min()
        high_max = window[cfg.high_col].iloc[1:].max()
        if pd.notna(low_min):
            mae.at[idx] = (low_min / entry_close) - 1.0
        if pd.notna(high_max):
            mfe.at[idx] = (high_max / entry_close) - 1.0
    return mae, mfe
