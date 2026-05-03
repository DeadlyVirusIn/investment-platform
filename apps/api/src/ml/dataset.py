"""ML dataset builder — join decision_log + paper_trade_log + price bars.

One row per decision. Columns constrained to the FEATURE_COLUMNS /
LABEL_COLUMNS whitelists (see features.py) so the leakage guard can
mechanically reject violations.

Design notes:
  * Pulls raw rows via SQL — no ORM coupling.
  * Flattens `inputs_used`, `context_values`, `catalyst`, `data_quality`
    JSONB blobs into plain columns.
  * Price bars come from `market_series_observation` keyed on instrument
    (best-effort). If bars are empty, forward labels are NaN but row still
    emitted — the trainer filters later.
  * Returns DatasetResult carrying both the frame and a build-diagnostic
    dict so callers can explain "why is this empty?" without re-querying.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.ml.features import (
    FEATURE_COLUMNS, IDENTITY_COLUMNS,
)
from apps.api.src.ml.labels import LabelConfig, attach_labels


@dataclass
class DatasetResult:
    df: pd.DataFrame
    n_rows: int
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def empty(self) -> bool:
        return self.n_rows == 0


def build_dataset(
    session: Session,
    *,
    bar_symbol_map: dict[str, str] | None = None,
    label_cfg: LabelConfig | None = None,
    limit: int | None = None,
    source: str = "real",                # real | replay | combined
    replay_run_ids: list[str] | None = None,
    replay_weight: float = 0.25,
) -> DatasetResult:
    """Assemble the supervised dataset.

    Parameters
    ----------
    source : "real" | "replay" | "combined"
        * "real"     — decision_log + paper_trade_log (default behaviour)
        * "replay"   — ml_replay_decision + ml_replay_outcome
        * "combined" — both; rows tagged with source_type; replay rows get
                        sample_weight = replay_weight
    replay_run_ids : optional list of specific runs to include; else every
        run with status in {'completed'}.
    """
    if source not in {"real", "replay", "combined"}:
        raise ValueError(f"unknown source='{source}'")

    # Safety gate for replay inclusion (ML-2.6).
    # Only allow replay rows if:
    #   * caller explicitly set source="replay" or "combined"
    #   * run_id explicit OR ML_DATASET_INCLUDE_REPLAY=true
    # Otherwise silently drop replay even if asked for combined.
    from apps.api.src.config import settings as _settings    # local import
    env_allow = bool(getattr(_settings, "ML_DATASET_INCLUDE_REPLAY", False))
    caller_forced = bool(replay_run_ids)
    if source == "combined" and not (env_allow or caller_forced):
        # Downgrade silently to real-only; surface via diagnostics.
        source = "real"
        replay_blocked_reason = ("ML_DATASET_INCLUDE_REPLAY=false and no "
                                   "explicit replay_run_ids — replay skipped")
    elif source == "replay" and not (env_allow or caller_forced):
        # Still allow pure replay queries — research path. But mark the
        # diagnostic so callers know this is not gated by the env flag.
        replay_blocked_reason = None
    else:
        replay_blocked_reason = None

    diag: dict[str, Any] = {}
    if replay_blocked_reason:
        diag["replay_blocked_reason"] = replay_blocked_reason
    frames: list[pd.DataFrame] = []

    if source in {"real", "combined"}:
        decisions = _load_decisions(session, limit=limit)
        paper_trades = _load_paper_trades(session)
        bars = _load_bars(session, decisions, bar_symbol_map or {})
        diag["n_decisions_raw"] = len(decisions)
        diag["n_paper_trades"]  = len(paper_trades)
        diag["n_bars_real"]     = len(bars)
        if not decisions.empty:
            flat = _flatten_json_columns(decisions)
            feats = _derive_features(flat)
            # PD-5 — compute non-endogenous market features from bars
            feats = _derive_market_features(feats, bars)
            labelled = attach_labels(feats, bars, paper_trades, cfg=label_cfg)
            labelled["source_type"] = "real"
            labelled["replay_run_id"] = None
            labelled["sample_weight"] = 1.0
            frames.append(labelled)

    if source in {"replay", "combined"}:
        replay_df = _load_replay_dataset(
            session, run_ids=replay_run_ids, label_cfg=label_cfg,
        )
        diag["n_replay_rows"] = int(len(replay_df))
        if not replay_df.empty:
            replay_df["source_type"] = "replay"
            replay_df["sample_weight"] = float(replay_weight)
            frames.append(replay_df)

    if not frames:
        return DatasetResult(
            df=pd.DataFrame(columns=list(IDENTITY_COLUMNS)
                            + list(FEATURE_COLUMNS)
                            + ["source_type", "replay_run_id",
                               "sample_weight"]),
            n_rows=0,
            diagnostics={**diag, "reason": "no rows from requested source"},
        )

    df = pd.concat(frames, ignore_index=True, sort=False)
    diag["n_rows_with_fwd_5d"] = int(
        df.get("fwd_ret_5d", pd.Series(dtype=float)).notna().sum()
    )
    diag["n_rows_with_realized"] = int(
        df.get("realized_net_ret", pd.Series(dtype=float)).notna().sum()
    )
    diag["source_counts"] = (
        df["source_type"].value_counts().to_dict()
        if "source_type" in df.columns else {}
    )
    return DatasetResult(df=df, n_rows=len(df), diagnostics=diag)


# ---------------------------------------------------------------------------
# replay loaders
# ---------------------------------------------------------------------------

def _load_replay_dataset(
    session: Session, *,
    run_ids: list[str] | None,
    label_cfg: LabelConfig | None,
) -> pd.DataFrame:
    """Load replay decisions + joined outcomes, mapped onto FEATURE_COLUMNS."""
    if run_ids:
        id_filter = "AND replay_run_id::text = ANY(:ids)"
        params: dict[str, Any] = {"ids": list(run_ids)}
    else:
        id_filter = ("AND replay_run_id IN "
                     "(SELECT id FROM ml_replay_run "
                     "WHERE status = 'completed')")
        params = {}
    dec_rows = session.execute(text(f"""
        SELECT id::text AS decision_id,
               replay_run_id::text AS replay_run_id,
               as_of_date, decision_ts, symbol AS instrument,
               symbol,
               engine,
               decision AS action,
               confidence,
               features AS inputs_used,
               regime AS context_values,
               data_quality,
               catalyst,
               skip_reason,
               missing_features
        FROM ml_replay_decision
        WHERE 1=1 {id_filter}
        ORDER BY as_of_date ASC
    """), params).mappings().all()
    if not dec_rows:
        return pd.DataFrame()
    dec = pd.DataFrame(dec_rows)
    # Replay selector doesn't track a decision_version — stamp one
    dec["decision_version"] = "replay-v1.0.0"
    # Flatten JSONB columns the same way real decisions go through
    flat = _flatten_json_columns(dec)
    feats = _derive_features(flat)

    # Attach replay outcomes as the label columns expected downstream.
    out_rows = session.execute(text(f"""
        SELECT o.replay_decision_id::text AS decision_id,
               o.label_horizon,
               o.forward_return,
               o.max_adverse,
               o.max_favorable,
               o.win_label
        FROM ml_replay_outcome o
        JOIN ml_replay_decision d ON d.id = o.replay_decision_id
        WHERE 1=1 {id_filter.replace("replay_run_id", "d.replay_run_id")}
    """), params).mappings().all()
    if out_rows:
        out = pd.DataFrame(out_rows)
        pivot = out.pivot_table(
            index="decision_id",
            columns="label_horizon",
            values="forward_return",
            aggfunc="last",
        )
        pivot.columns = [f"fwd_ret_{int(h)}d" for h in pivot.columns]
        pivot = pivot.reset_index()
        feats = feats.merge(pivot, on="decision_id", how="left")
        # Win labels
        for h in (1, 3, 5, 10):
            col = f"fwd_ret_{h}d"
            if col in feats.columns:
                feats[f"label_win_{h}d"] = (
                    feats[col].gt(0.0)
                             .where(feats[col].notna(), other=np.nan)
                )
    # Replay doesn't produce realized paper outcomes
    for c in (
        "realized_net_ret", "realized_days_held", "realized_gross_ret",
        "realized_max_adverse", "realized_max_favorable",
        "label_win_realized", "hit_target", "hit_stop",
    ):
        if c not in feats.columns:
            feats[c] = np.nan
    return feats


# ---------------------------------------------------------------------------
# SQL loaders
# ---------------------------------------------------------------------------

def _load_decisions(session: Session, *, limit: int | None) -> pd.DataFrame:
    sql = """
        SELECT
          id::text                         AS decision_id,
          as_of_date,
          decision_ts,
          engine,
          action,
          instrument                       AS symbol,
          inputs_used,
          context_values,
          decision_version,
          reason,
          blocked_by,
          diagnostic_snapshot,
          data_quality,
          catalyst,
          feature_confidence,
          skip_reason,
          missing_features
        FROM decision_log
        ORDER BY as_of_date ASC, decision_ts ASC
    """
    if limit:
        sql += f"\nLIMIT {int(limit)}"
    rows = session.execute(text(sql)).mappings().all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["instrument"] = df["symbol"]
    return df


def _load_paper_trades(session: Session) -> pd.DataFrame:
    # `days_held` was never added as a stored column — derive it from
    # (exit_date - entry_date) so the dataset builder stays schema-agnostic.
    sql = """
        SELECT
          entry_date,
          exit_date,
          engine,
          instrument                       AS symbol,
          status,
          gross_ret_pct,
          net_ret_pct,
          (COALESCE(exit_date, CURRENT_DATE) - entry_date) AS days_held,
          catalyst_snapshot,
          data_confidence,
          near_earnings
        FROM paper_trade_log
    """
    try:
        rows = session.execute(text(sql)).mappings().all()
    except Exception:
        # Fallback for very old DB snapshots lacking catalyst_snapshot etc.
        # Postgres leaves a failed query in aborted-txn state — rollback
        # first so subsequent writes (ml_model_run insert) don't error out.
        session.rollback()
        rows = session.execute(text("""
            SELECT entry_date, exit_date, engine, instrument AS symbol,
                   status, gross_ret_pct, net_ret_pct,
                   (COALESCE(exit_date, CURRENT_DATE) - entry_date) AS days_held
            FROM paper_trade_log
        """)).mappings().all()
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["entry_date", "symbol", "engine", "status",
                 "gross_ret_pct", "net_ret_pct", "days_held"]
    )


def _load_bars(
    session: Session,
    decisions: pd.DataFrame,
    instrument_to_series_key: dict[str, str],
) -> pd.DataFrame:
    """Load OHLC bars spanning the decision window for the symbols we need.

    Priority per symbol:
      1. price_bar ↔ asset.symbol (equities/ETFs)
      2. market_series_observation (PIT macro/market series)
      3. ES-specific fallback → `fetch_es_daily()` (yfinance continuous
         front-month). Cached at module scope with TTL so the nightly ML
         job doesn't re-hit yfinance during a single run.

    Never fabricates bars. If every source returns empty for a symbol,
    that symbol contributes zero rows and label_win_Xd stays NaN.
    """
    cols = ["date", "symbol", "open", "high", "low", "close"]
    if decisions.empty:
        return pd.DataFrame(columns=cols)
    symbols = sorted(set(decisions["instrument"].dropna().unique()))
    out_frames: list[pd.DataFrame] = []
    for sym in symbols:
        series_key = instrument_to_series_key.get(sym, sym)
        rows: list[dict[str, Any]] = []
        # (1) price_bar via asset.symbol
        try:
            rows = session.execute(text("""
                SELECT pb.ts::date AS date,
                       pb.open, pb.high, pb.low, pb.close
                FROM price_bar pb
                JOIN asset a ON a.id = pb.asset_id
                WHERE a.symbol = :s AND pb.timeframe = '1d'
                ORDER BY pb.ts ASC
            """), {"s": sym}).mappings().all()
        except Exception:
            rows = []
        # (2) market_series_observation fallback
        if not rows:
            try:
                rows = session.execute(text("""
                    SELECT observation_date AS date,
                           close_value AS close,
                           close_value AS high,
                           close_value AS low,
                           close_value AS open
                    FROM market_series_observation
                    WHERE series_id = :k
                    ORDER BY observation_date ASC
                """), {"k": series_key}).mappings().all()
            except Exception:
                rows = []
        # (3) ES-specific yfinance fallback (paper_daily uses same fn)
        if not rows and sym == "ES":
            es_df = _fetch_es_bars_cached()
            if es_df is not None and not es_df.empty:
                frame = es_df.copy()
                frame["symbol"] = "ES"
                out_frames.append(frame[cols])
                continue
        if not rows:
            continue
        frame = pd.DataFrame(rows)
        frame["symbol"] = sym
        for c in ("open", "high", "low", "close"):
            if c not in frame.columns:
                frame[c] = pd.NA
        out_frames.append(frame[cols])
    if not out_frames:
        return pd.DataFrame(columns=cols)
    return pd.concat(out_frames, ignore_index=True)


# ---------------------------------------------------------------------------
# ES bar cache — one yfinance call per process, 1h TTL
# ---------------------------------------------------------------------------

_ES_BAR_CACHE: dict[str, Any] = {"ts": 0.0, "df": None}
_ES_BAR_CACHE_TTL = 60 * 60   # 1 hour


def _fetch_es_bars_cached() -> pd.DataFrame | None:
    """Fetch ES=F continuous front-month OHLC. Cached per-process."""
    import time as _time
    now = _time.time()
    cached = _ES_BAR_CACHE.get("df")
    if cached is not None and (now - _ES_BAR_CACHE["ts"]) < _ES_BAR_CACHE_TTL:
        return cached
    try:
        # Import here to avoid module-load-time yfinance cost
        from scripts.run_phase12_price_action import fetch_es_daily
        raw = fetch_es_daily(start="2020-01-01")
    except Exception as e:
        from loguru import logger as _log
        _log.warning("dataset: ES bar fetch failed: {}", e)
        return None
    df = raw.reset_index().rename(columns={"index": "date"})
    df["date"] = pd.to_datetime(df["date"])
    for c in ("open", "high", "low", "close"):
        if c in df.columns:
            df[c] = df[c].astype(float)
    _ES_BAR_CACHE["ts"] = now
    _ES_BAR_CACHE["df"] = df
    return df


# ---------------------------------------------------------------------------
# JSON flattening
# ---------------------------------------------------------------------------

_JSON_COLUMNS = ("inputs_used", "context_values", "data_quality",
                 "catalyst", "missing_features")


def _flatten_json_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in _JSON_COLUMNS:
        if col in out.columns:
            out[col] = out[col].apply(_ensure_dict_or_list)
    return out


def _ensure_dict_or_list(v: Any):
    if v is None or isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (TypeError, ValueError):
            return None
    return v


# ---------------------------------------------------------------------------
# Feature derivation — whitelisted, no future data
# ---------------------------------------------------------------------------

def _derive_market_features(
    df: pd.DataFrame, bars: pd.DataFrame,
) -> pd.DataFrame:
    """PD-5 — append non-endogenous market features to the decision frame.

    Joins each decision row to its (symbol, as_of_date) bar history.
    Computes:
      ret_z_5d/20d/60d  : trailing-N return z-score (TS-momentum)
      rvol_20d          : 20-day stdev of daily returns × sqrt(252)
      vol_of_vol_20d    : rolling stdev of realized_vol over 20 days
      log_atr_20d       : ln(20-day true range / close)

    Missing data → NaN (never fabricated). Trainer drops rows where the
    label is NaN; market features can stay NaN and the model imputes 0.
    """
    out = df.copy()
    NEW = [
        "ret_z_5d", "ret_z_20d", "ret_z_60d",
        "rvol_20d", "vol_of_vol_20d", "log_atr_20d",
    ]
    for c in NEW:
        out[c] = np.nan

    if bars is None or bars.empty or "symbol" not in df.columns:
        return out

    bars = bars.copy()
    bars["date"] = pd.to_datetime(bars["date"]).dt.normalize()
    by_sym = {
        sym: g.sort_values("date").reset_index(drop=True)
        for sym, g in bars.groupby("symbol", sort=False)
    }

    out["as_of_date"] = pd.to_datetime(out["as_of_date"]).dt.normalize()

    for idx, row in out[["symbol", "as_of_date"]].iterrows():
        sym = row["symbol"]
        asof = row["as_of_date"]
        g = by_sym.get(sym)
        if g is None or g.empty:
            continue
        # Use bars on or before as_of_date — point-in-time guarantee
        g_pit = g[g["date"] <= asof]
        if len(g_pit) < 21:
            continue
        closes = g_pit["close"].astype(float)
        rets = closes.pct_change().dropna()
        if len(rets) < 60:
            # Allow shorter for 5d/20d if 60d unavailable
            pass

        # TS-momentum z-scores
        for h, col in ((5, "ret_z_5d"), (20, "ret_z_20d"),
                       (60, "ret_z_60d")):
            if len(rets) >= h:
                window = rets.iloc[-h:]
                mu = float(window.mean())
                sd = float(window.std())
                if sd > 0 and np.isfinite(sd):
                    # Z-score of cumulative return / sigma scaled by sqrt(h)
                    cum = float((1.0 + window).prod() - 1.0)
                    out.at[idx, col] = cum / (sd * np.sqrt(h))

        # Realized vol (annualized) over last 20 trading days
        if len(rets) >= 20:
            sd20 = float(rets.iloc[-20:].std()) * np.sqrt(252.0)
            if np.isfinite(sd20):
                out.at[idx, "rvol_20d"] = sd20

        # Vol-of-vol — stdev of trailing 20 daily realized-vol values
        if len(rets) >= 40:
            rolling_std = rets.rolling(window=20).std().dropna()
            if len(rolling_std) >= 20:
                vov = float(rolling_std.iloc[-20:].std())
                if np.isfinite(vov):
                    out.at[idx, "vol_of_vol_20d"] = vov

        # log ATR / close (range-vol proxy)
        if len(g_pit) >= 21 and {"high", "low", "close"}.issubset(
            g_pit.columns,
        ):
            hi = g_pit["high"].astype(float).iloc[-21:]
            lo = g_pit["low"].astype(float).iloc[-21:]
            cl = g_pit["close"].astype(float).iloc[-21:]
            prev_close = cl.shift(1)
            tr = pd.concat([
                (hi - lo).abs(),
                (hi - prev_close).abs(),
                (lo - prev_close).abs(),
            ], axis=1).max(axis=1)
            atr = tr.dropna().tail(20).mean()
            last_close = cl.iloc[-1]
            if (
                np.isfinite(atr) and atr > 0
                and np.isfinite(last_close) and last_close > 0
            ):
                out.at[idx, "log_atr_20d"] = float(
                    np.log(atr / last_close),
                )
    return out


def _derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the final feature frame conforming to FEATURE_COLUMNS."""
    out = df.copy()

    # Engine one-hots
    eng = out["engine"].fillna("none").astype(str).str.upper()
    out["engine_is_a"] = eng.eq("A").astype(int)
    out["engine_is_b"] = eng.eq("B").astype(int)
    out["engine_is_c"] = eng.eq("C").astype(int)

    # Regime flags from context_values
    out["regime_stress"]       = _ctx_flag(out, "stress_regime")
    out["regime_directional"]  = _ctx_flag(out, "directional_regime")
    out["regime_neutral"]      = (
        1 - (out["regime_stress"] | out["regime_directional"])
    ).astype(int)

    # Gates favorable
    out["gates_favorable"] = out["context_values"].apply(_gates_favorable_count)

    # Data quality
    out["missing_field_count"] = out["data_quality"].apply(
        lambda d: len((d or {}).get("missing_fields", [])) if isinstance(d, dict) else 0
    )
    out["stale_field_count"] = out["data_quality"].apply(
        lambda d: len((d or {}).get("stale_fields", [])) if isinstance(d, dict) else 0
    )
    # Bucketize feature_confidence
    conf = pd.to_numeric(out["feature_confidence"], errors="coerce").fillna(0.0)
    out["feature_confidence"] = conf.astype(float)
    out["data_confidence_bucket"] = pd.cut(
        conf, bins=[-0.01, 0.3, 0.6, 0.85, 1.01],
        labels=[0, 1, 2, 3],
    ).astype("Int64").fillna(0).astype(int)

    # Catalyst features
    out["catalyst_score"]   = out["catalyst"].apply(_cat_field, args=("catalyst_score",))
    out["event_risk_score"] = out["catalyst"].apply(_cat_field, args=("event_risk_score",))
    out["days_to_earnings"] = out["catalyst"].apply(_cat_field, args=("days_to_earnings",))
    out["has_earnings_soon"] = out["catalyst"].apply(
        _cat_field, args=("has_earnings_soon",)
    ).astype("Int64").fillna(0).astype(int)

    # Trade policy one-hots
    tp = out["catalyst"].apply(_cat_field, args=("trade_policy",)).fillna("neutral")
    out["trade_policy_neutral"] = tp.eq("neutral").astype(int)
    out["trade_policy_reduce"]  = tp.eq("reduce_size").astype(int)
    out["trade_policy_confirm"] = tp.eq("require_confirmation").astype(int)
    out["trade_policy_block"]   = tp.eq("block_new_entry").astype(int)
    out["trade_policy_watch"]   = tp.eq("watch_only").astype(int)

    # Selector inputs from inputs_used — all gates safe at decision time
    for fk in (
        "rates_calm", "vrp_supportive", "credit_stable",
        "liquidity_expanding", "vol_elevated", "vol_expanding",
        "range_loose",
    ):
        out[f"input_{fk}"] = out["inputs_used"].apply(
            _input_bool, args=(fk,)
        ).astype(int)
    for fk in ("z_score", "atr_ratio"):
        out[f"input_{fk}"] = out["inputs_used"].apply(
            _input_number, args=(fk,)
        ).astype(float)

    # Ensure identity columns exist + typed
    for col in IDENTITY_COLUMNS:
        if col not in out.columns:
            out[col] = None

    return out


def _ctx_flag(df: pd.DataFrame, key: str) -> pd.Series:
    return df["context_values"].apply(
        lambda d: int(bool((d or {}).get(key, False)))
                  if isinstance(d, dict) else 0
    )


def _gates_favorable_count(d: Any) -> int:
    if not isinstance(d, dict):
        return 0
    gates = ("rates_calm", "vrp_supportive", "credit_stable",
             "liquidity_expanding")
    return int(sum(1 for g in gates if d.get(g) is True))


def _cat_field(d: Any, key: str):
    if not isinstance(d, dict):
        return np.nan
    v = d.get(key)
    return v if v is not None else np.nan


def _input_bool(d: Any, key: str) -> int:
    if not isinstance(d, dict):
        return 0
    v = d.get(key)
    return 1 if bool(v) else 0


def _input_number(d: Any, key: str) -> float:
    if not isinstance(d, dict):
        return float("nan")
    v = d.get(key)
    try:
        return float(v) if v is not None else float("nan")
    except (TypeError, ValueError):
        return float("nan")
