"""Cross-signal analytics: stock <-> options outcome comparison.

Pure read of `candidate_idea`, `price_bar`, `regime_snapshot`,
`options_feature_daily`, and `options_strategy_outcome`. NO writes.
NO execution side-effects. NEVER fabricates a quote, label, or
forward return — windows that lack data are surfaced as
`insufficient_data` and are excluded from edge computation.

Bucket frozen vocabularies (mirror PRD):
  Score buckets: strong_buy / moderate_buy / neutral /
                 moderate_sell / strong_sell
  Gate buckets:  strict_pass / soft_gate_relaxed / hard_blocked /
                 data_blocked
  Trend buckets: uptrend / sideways / downtrend
  IV buckets:    low_iv / medium_iv / high_iv / unknown_iv
  Strategy:      stock_only / long_call / bull_call_spread /
                 long_put / bear_put_spread / credit_spread /
                 iron_condor

Decision hint:
  * relative_edge_pct = options_avg_return_pct - stock_avg_return_pct
  * confidence:
      low    sample_count < 20
      medium sample_count >= 20
      high   sample_count >= 50 AND >= 2 horizons agree on sign
  * recommendation:
      prefer_options    edge >= +0.5%, confidence != low
      prefer_stock      edge <= -0.5%, confidence != low
      insufficient_data otherwise (always for confidence=low)
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Frozen vocabularies
# ---------------------------------------------------------------------------

SCORE_BUCKETS = (
    "strong_buy", "moderate_buy", "neutral",
    "moderate_sell", "strong_sell",
)
GATE_BUCKETS = (
    "strict_pass", "soft_gate_relaxed", "hard_blocked", "data_blocked",
)
TREND_BUCKETS = ("uptrend", "sideways", "downtrend")
IV_BUCKETS = ("low_iv", "medium_iv", "high_iv", "unknown_iv")
STRATEGY_BUCKETS = (
    "stock_only", "long_call", "bull_call_spread",
    "long_put", "bear_put_spread", "credit_spread", "iron_condor",
)

# Mirror of the soft-gate set used by the daily-suggestions /
# suggestion-quality endpoints. Kept here as a string tuple so this
# module has no import-cycle with performance_paper.py.
_SOFT_GATES = (
    "extended_from_sma200", "idiosyncratic_vol_high",
    "topn_overflow", "high_vol_topn_overflow", "below_long_trend",
)

# DB strategy_name (UPPER) -> public bucket name (lower).
_DB_STRATEGY_TO_BUCKET = {
    "LONG_CALL": "long_call",
    "BULL_CALL_SPREAD": "bull_call_spread",
    "LONG_PUT": "long_put",
    "BEAR_PUT_SPREAD": "bear_put_spread",
    "SHORT_CALL_CREDIT_SPREAD": "credit_spread",
    "SHORT_PUT_CREDIT_SPREAD": "credit_spread",
    "IRON_CONDOR": "iron_condor",
}

# Confidence thresholds.
_CONF_MEDIUM_MIN_N = 20
_CONF_HIGH_MIN_N = 50
_EDGE_PREFER_PCT = 0.005   # 0.5%

# Forward-return outcome thresholds (mirror suggestion-quality).
_STOCK_GOOD_PCT = 0.02
_STOCK_BAD_PCT = -0.02


# ---------------------------------------------------------------------------
# Pure bucketing helpers
# ---------------------------------------------------------------------------

def score_bucket(score: float | None) -> str:
    if score is None:
        return "neutral"
    s = float(score)
    if s >= 0.30:
        return "strong_buy"
    if s >= 0.10:
        return "moderate_buy"
    if s > -0.10:
        return "neutral"
    if s > -0.30:
        return "moderate_sell"
    return "strong_sell"


def gate_bucket(
    status: str, rejection_reason: str | None,
) -> str:
    """Maps `candidate_idea.(status, rejection_reason)` to a bucket."""
    if status == "accepted":
        return "strict_pass"
    if status == "rejected":
        if rejection_reason in _SOFT_GATES:
            return "soft_gate_relaxed"
        if rejection_reason in (
            "stale_data", "execution_failure",
            "insufficient_history",
        ):
            return "data_blocked"
        return "hard_blocked"
    return "data_blocked"


def trend_bucket(market_trend: str | None) -> str:
    """Map `regime_snapshot.market_trend` → public bucket. Unknown
    values fall through to 'sideways' (least claim, never fabricates
    a direction)."""
    if not market_trend:
        return "sideways"
    t = market_trend.lower()
    if "up" in t or t in ("bull", "bullish"):
        return "uptrend"
    if "down" in t or t in ("bear", "bearish"):
        return "downtrend"
    return "sideways"


def iv_bucket(atm_iv: float | None) -> str:
    if atm_iv is None:
        return "unknown_iv"
    iv = float(atm_iv)
    if iv < 0.25:
        return "low_iv"
    if iv < 0.45:
        return "medium_iv"
    return "high_iv"


def strategy_bucket_from_db_name(db_name: str | None) -> str:
    if not db_name:
        return "stock_only"
    return _DB_STRATEGY_TO_BUCKET.get(db_name.upper(), "stock_only")


# ---------------------------------------------------------------------------
# Stock fwd-return per (asset, as_of, horizon)
# ---------------------------------------------------------------------------

def _stock_fwd_return(
    bars: list[tuple[dt.date, float, float, float]],
    horizon_days: int,
) -> tuple[float | None, float | None, float | None, int]:
    """Returns (forward_return_pct, mfe_pct, mae_pct, bars_seen).

    Walks at most `horizon_days` bars after the entry bar (bars[0]).
    Never extrapolates; missing future data → forward_return None and
    bars_seen reflects what was actually observed.
    """
    if not bars:
        return None, None, None, 0
    entry_px = bars[0][1]
    if entry_px <= 0:
        return None, None, None, 0
    window = bars[1: 1 + horizon_days]
    if not window:
        return None, None, None, 0
    closes = [b[1] for b in window]
    lows = [b[2] for b in window]
    highs = [b[3] for b in window]
    bars_seen = len(window)
    fr = None
    if bars_seen >= horizon_days:
        fr = (closes[-1] - entry_px) / entry_px
    mfe = (max(highs) - entry_px) / entry_px if highs else None
    mae = (min(lows) - entry_px) / entry_px if lows else None
    return fr, mfe, mae, bars_seen


def _load_stock_outcomes(
    session: Session,
    *, as_of_from: dt.date, as_of_to: dt.date,
    horizon_days: int,
) -> list[dict[str, Any]]:
    """Per-(date, asset) stock candidate row + computed forward return.

    Returns rows with: as_of_date, underlying, score, status,
    rejection_reason, score_bucket, gate_bucket, trend_bucket,
    iv_bucket, fwd_return, mfe, mae, bars_seen.
    """
    cands = session.execute(text("""
        SELECT
          c.as_of_date,
          a.symbol AS underlying, a.id AS asset_id,
          c.status, c.action, c.rejection_reason,
          c.composite_score::float AS score
        FROM candidate_idea c
        JOIN asset a ON a.id = c.asset_id
        WHERE c.as_of_date BETWEEN :a AND :b
    """), {"a": as_of_from, "b": as_of_to}).mappings().all()

    if not cands:
        return []

    asset_ids = sorted({c["asset_id"] for c in cands})
    bars_rows = session.execute(text("""
        SELECT asset_id, ts::date AS bar_date,
               coalesce(adjusted_close, close)::float AS px,
               low::float AS lo, high::float AS hi
        FROM price_bar
        WHERE asset_id = ANY(:ids)
          AND timeframe = '1d'
          AND ts::date BETWEEN :a
                  AND (:b + (:h * interval '1 day'))::date
        ORDER BY asset_id, ts ASC
    """), {
        "ids": asset_ids, "a": as_of_from, "b": as_of_to,
        "h": int(horizon_days * 2 + 5),  # liberal upper to count bars
    }).all()
    bars_by_asset: dict[str, list[tuple[dt.date, float, float, float]]] = {}
    for asset_id, bar_date, px, lo, hi in bars_rows:
        bars_by_asset.setdefault(asset_id, []).append(
            (bar_date, px, lo, hi),
        )
    for arr in bars_by_asset.values():
        arr.sort(key=lambda r: r[0])

    # Regime per as_of_date
    reg_rows = session.execute(text("""
        SELECT as_of_date, market_trend
        FROM regime_snapshot
        WHERE as_of_date BETWEEN :a AND :b
    """), {"a": as_of_from, "b": as_of_to}).all()
    regime_by_date = {r[0]: r[1] for r in reg_rows}

    # Options ATM IV per (as_of_date, underlying)
    iv_rows = session.execute(text("""
        SELECT as_of_date, underlying, atm_iv::float AS iv
        FROM options_feature_daily
        WHERE as_of_date BETWEEN :a AND :b
    """), {"a": as_of_from, "b": as_of_to}).all()
    iv_by_key: dict[tuple[dt.date, str], float | None] = {
        (d, u): iv for d, u, iv in iv_rows
    }

    out: list[dict[str, Any]] = []
    for c in cands:
        aid = c["asset_id"]
        as_of = c["as_of_date"]
        bars = [
            b for b in bars_by_asset.get(aid, []) if b[0] >= as_of
        ]
        fr, mfe, mae, bars_seen = _stock_fwd_return(bars, horizon_days)
        out.append({
            "as_of_date": as_of,
            "underlying": c["underlying"],
            "asset_id": aid,
            "score": c["score"],
            "status": c["status"],
            "rejection_reason": c["rejection_reason"],
            "score_bucket": score_bucket(c["score"]),
            "gate_bucket": gate_bucket(
                c["status"], c["rejection_reason"],
            ),
            "trend_bucket": trend_bucket(regime_by_date.get(as_of)),
            "iv_bucket": iv_bucket(iv_by_key.get((as_of, c["underlying"]))),
            "fwd_return_pct": fr,
            "mfe_pct": mfe,
            "mae_pct": mae,
            "bars_seen": bars_seen,
        })
    return out


# ---------------------------------------------------------------------------
# Options outcomes per (as_of, underlying, strategy, horizon)
# ---------------------------------------------------------------------------

def _load_options_outcomes(
    session: Session,
    *, as_of_from: dt.date, as_of_to: dt.date, horizon: str,
) -> list[dict[str, Any]]:
    """Per-row options outcomes; outcome_label is preserved verbatim."""
    rows = session.execute(text("""
        SELECT as_of_date, underlying, strategy_name, mode, source,
               forward_return_pct, mfe_pct, mae_pct, outcome_label
        FROM options_strategy_outcome
        WHERE as_of_date BETWEEN :a AND :b
          AND horizon = :h
    """), {"a": as_of_from, "b": as_of_to, "h": horizon}).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "as_of_date": r["as_of_date"],
            "underlying": r["underlying"],
            "strategy_name": r["strategy_name"],
            "strategy_bucket": strategy_bucket_from_db_name(
                r["strategy_name"],
            ),
            "mode": r["mode"], "source": r["source"],
            "fwd_return_pct": (
                float(r["forward_return_pct"])
                if r["forward_return_pct"] is not None else None
            ),
            "mfe_pct": (
                float(r["mfe_pct"]) if r["mfe_pct"] is not None else None
            ),
            "mae_pct": (
                float(r["mae_pct"]) if r["mae_pct"] is not None else None
            ),
            "outcome_label": r["outcome_label"],
        })
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _confidence(
    sample_count: int, *, multi_horizon_agree: bool,
) -> str:
    if sample_count < _CONF_MEDIUM_MIN_N:
        return "low"
    if sample_count >= _CONF_HIGH_MIN_N and multi_horizon_agree:
        return "high"
    return "medium"


def _recommendation(
    edge_pct: float | None, confidence: str,
) -> str:
    if edge_pct is None or confidence == "low":
        return "insufficient_data"
    if edge_pct >= _EDGE_PREFER_PCT:
        return "prefer_options"
    if edge_pct <= -_EDGE_PREFER_PCT:
        return "prefer_stock"
    return "insufficient_data"


def _agg_avg(values: list[float]) -> float | None:
    finite = [v for v in values if v is not None]
    if not finite:
        return None
    return sum(finite) / len(finite)


def _hit_rate_stock(stock_rows: list[dict]) -> float | None:
    """Fraction with fwd_return_pct >= +2%. None if no finalized rows."""
    finalized = [
        r for r in stock_rows if r.get("fwd_return_pct") is not None
    ]
    if not finalized:
        return None
    good = sum(
        1 for r in finalized
        if r["fwd_return_pct"] >= _STOCK_GOOD_PCT
    )
    return good / len(finalized)


def _hit_rate_options(opt_rows: list[dict]) -> float | None:
    finalized = [
        r for r in opt_rows if r.get("fwd_return_pct") is not None
    ]
    if not finalized:
        return None
    good = sum(
        1 for r in finalized if r["outcome_label"] == "good"
    )
    return good / len(finalized)


def _multi_horizon_agreement(
    session: Session, *, as_of_from: dt.date, as_of_to: dt.date,
    underlying: str | None, strategy_db_name: str | None,
    target_horizon: str,
) -> bool:
    """True iff at least 2 horizons (target + one more) agree on the
    sign of the avg forward_return_pct for the same (underlying,
    strategy)."""
    candidate_horizons = ("3D", "5D", "10D")
    if target_horizon not in candidate_horizons:
        candidate_horizons = (target_horizon, "5D", "10D")

    where = ["as_of_date BETWEEN :a AND :b", "horizon = :h"]
    params: dict[str, Any] = {"a": as_of_from, "b": as_of_to}
    if underlying:
        where.append("underlying = :u")
        params["u"] = underlying
    if strategy_db_name:
        where.append("strategy_name = :s")
        params["s"] = strategy_db_name
    base_where = " AND ".join(where)

    signs: list[int] = []
    for h in candidate_horizons:
        params["h"] = h
        row = session.execute(text(f"""
            SELECT avg(forward_return_pct)::float
            FROM options_strategy_outcome
            WHERE {base_where} AND forward_return_pct IS NOT NULL
        """), params).first()
        if row and row[0] is not None:
            v = float(row[0])
            signs.append(1 if v >= 0 else -1)
    if len(signs) < 2:
        return False
    return all(s == signs[0] for s in signs)


def build_strategy_map(
    session: Session,
    *, as_of_from: dt.date, as_of_to: dt.date,
    horizon: str = "5D",
) -> list[dict[str, Any]]:
    """Build the cross-signal strategy map (Phase 3)."""
    if horizon not in ("1D", "3D", "5D", "10D", "20D"):
        raise ValueError(
            f"horizon must be one of 1D/3D/5D/10D/20D, got {horizon!r}"
        )
    horizon_days = int(horizon[:-1])

    stock_rows = _load_stock_outcomes(
        session,
        as_of_from=as_of_from, as_of_to=as_of_to,
        horizon_days=horizon_days,
    )
    opt_rows = _load_options_outcomes(
        session,
        as_of_from=as_of_from, as_of_to=as_of_to, horizon=horizon,
    )

    # Stock context lookup keyed by (date, underlying) — used to
    # attach signal/gate/trend/iv buckets to options rows that don't
    # have stock candidates of their own.
    stock_ctx: dict[tuple[dt.date, str], dict[str, Any]] = {}
    for r in stock_rows:
        stock_ctx[(r["as_of_date"], r["underlying"])] = r

    # Group key: (signal, gate, trend, iv, strategy_bucket)
    GroupKey = tuple[str, str, str, str, str]
    groups_stock: dict[GroupKey, list[dict]] = defaultdict(list)
    groups_options: dict[GroupKey, list[dict]] = defaultdict(list)

    # Stock-only group: every stock row contributes; strategy_bucket
    # = stock_only.
    for r in stock_rows:
        k: GroupKey = (
            r["score_bucket"], r["gate_bucket"],
            r["trend_bucket"], r["iv_bucket"], "stock_only",
        )
        groups_stock[k].append(r)

    # Options groups: per options row, look up stock context (or
    # neutral defaults if no stock candidate that day).
    for r in opt_rows:
        ctx = stock_ctx.get((r["as_of_date"], r["underlying"]))
        if ctx is None:
            sig = "neutral"
            gate = "data_blocked"
            trend = "sideways"
            iv = "unknown_iv"
        else:
            sig = ctx["score_bucket"]
            gate = ctx["gate_bucket"]
            trend = ctx["trend_bucket"]
            iv = ctx["iv_bucket"]
        k = (sig, gate, trend, iv, r["strategy_bucket"])
        groups_options[k].append(r)
        # Same-key stock comparator: rebuild stock side at
        # (sig,gate,trend,iv,stock_only) so the items align.
        if ctx is not None:
            sk: GroupKey = (sig, gate, trend, iv, "stock_only")
            # No double-counting — already added in the stock loop.

    # Keys for output — every key with options data, plus pure
    # stock-only keys.
    all_keys = set(groups_options.keys()) | set(groups_stock.keys())
    out: list[dict[str, Any]] = []
    for key in sorted(all_keys):
        sig, gate, trend, iv, strat = key
        stock_pop = groups_stock.get(
            (sig, gate, trend, iv, "stock_only"), [],
        )
        opt_pop = groups_options.get(key, [])

        stock_avg = _agg_avg([
            r["fwd_return_pct"] for r in stock_pop
            if r.get("fwd_return_pct") is not None
        ])
        opt_avg = _agg_avg([
            r["fwd_return_pct"] for r in opt_pop
            if r.get("fwd_return_pct") is not None
        ])
        stock_hr = _hit_rate_stock(stock_pop)
        opt_hr = _hit_rate_options(opt_pop)

        opt_mae = _agg_avg([
            r["mae_pct"] for r in opt_pop if r.get("mae_pct") is not None
        ])
        opt_mfe = _agg_avg([
            r["mfe_pct"] for r in opt_pop if r.get("mfe_pct") is not None
        ])

        # Sample count = options sample count when comparing options;
        # otherwise stock count.
        if strat == "stock_only":
            n = len(stock_pop)
        else:
            n = len(opt_pop)

        # Multi-horizon agreement: only ask the DB when this is an
        # options strategy bucket (irrelevant for stock_only).
        multi_horizon = False
        if strat != "stock_only" and n >= _CONF_HIGH_MIN_N:
            db_name = next(
                (db for db, b in _DB_STRATEGY_TO_BUCKET.items()
                 if b == strat),
                None,
            )
            multi_horizon = _multi_horizon_agreement(
                session,
                as_of_from=as_of_from, as_of_to=as_of_to,
                underlying=None, strategy_db_name=db_name,
                target_horizon=horizon,
            )
        confidence = _confidence(n, multi_horizon_agree=multi_horizon)

        edge_pct = None
        if (
            strat != "stock_only"
            and stock_avg is not None and opt_avg is not None
        ):
            edge_pct = opt_avg - stock_avg
        recommendation = (
            _recommendation(edge_pct, confidence)
            if strat != "stock_only" else "n/a"
        )

        out.append({
            "signal_bucket": sig,
            "gate_bucket": gate,
            "trend_bucket": trend,
            "iv_bucket": iv,
            "strategy": strat,
            "sample_count": n,
            "stock_sample_count": len(stock_pop),
            "options_sample_count": len(opt_pop),
            "stock_avg_return_pct": stock_avg,
            "options_avg_return_pct": opt_avg,
            "stock_hit_rate": stock_hr,
            "options_hit_rate": opt_hr,
            "relative_edge_pct": edge_pct,
            "avg_mae_pct": opt_mae,
            "avg_mfe_pct": opt_mfe,
            "confidence": confidence,
            "recommendation": recommendation,
        })

    # Sort: options groups by abs(edge) desc, stock_only last.
    def _sort_key(it: dict[str, Any]) -> tuple:
        is_stock = it["strategy"] == "stock_only"
        edge = it["relative_edge_pct"]
        return (
            1 if is_stock else 0,
            -abs(edge) if edge is not None else 0,
            -it["sample_count"],
        )
    out.sort(key=_sort_key)
    return out


# ---------------------------------------------------------------------------
# Daily decision assistant (Phase 4)
# ---------------------------------------------------------------------------

def build_today_assistant(
    session: Session,
    *, as_of: dt.date, lookback_days: int = 90, limit: int = 25,
) -> list[dict[str, Any]]:
    """For each top stock suggestion on `as_of`, attach the best
    matching options strategy + historical edge."""
    today = session.execute(text("""
        SELECT a.symbol AS underlying,
               c.composite_score::float AS score,
               c.status, c.action, c.rejection_reason
        FROM candidate_idea c
        JOIN asset a ON a.id = c.asset_id
        WHERE c.as_of_date = :d
          AND (c.status = 'accepted'
               OR (c.status = 'rejected'
                   AND c.rejection_reason = ANY(:soft)))
        ORDER BY c.composite_score DESC NULLS LAST
        LIMIT :n
    """), {
        "d": as_of, "soft": list(_SOFT_GATES), "n": limit,
    }).mappings().all()

    if not today:
        return []

    history_from = as_of - dt.timedelta(days=lookback_days)
    strategy_map = build_strategy_map(
        session,
        as_of_from=history_from, as_of_to=as_of,
        horizon="5D",
    )

    # Index strategy_map for quick lookup by
    # (sig, gate, trend, iv, strategy).
    map_idx: dict[tuple, dict] = {}
    for it in strategy_map:
        k = (
            it["signal_bucket"], it["gate_bucket"],
            it["trend_bucket"], it["iv_bucket"], it["strategy"],
        )
        map_idx[k] = it

    # Resolve today's regime + IV for each underlying.
    reg = session.execute(text("""
        SELECT market_trend FROM regime_snapshot WHERE as_of_date = :d
    """), {"d": as_of}).first()
    today_trend = trend_bucket(reg[0] if reg else None)

    underlyings = sorted({r["underlying"] for r in today})
    iv_rows = session.execute(text("""
        SELECT underlying, atm_iv::float
        FROM options_feature_daily
        WHERE as_of_date = :d AND underlying = ANY(:u)
    """), {"d": as_of, "u": underlyings}).all()
    iv_by_underlying = {u: iv for u, iv in iv_rows}

    out: list[dict[str, Any]] = []
    for r in today:
        u = r["underlying"]
        sig = score_bucket(r["score"])
        gate = gate_bucket(r["status"], r["rejection_reason"])
        ivb = iv_bucket(iv_by_underlying.get(u))

        # Pick best strategy for this bucket.
        best_strategy = None
        best_edge = None
        best_meta = None
        for strat in STRATEGY_BUCKETS:
            if strat == "stock_only":
                continue
            it = map_idx.get((sig, gate, today_trend, ivb, strat))
            if it is None:
                continue
            edge = it["relative_edge_pct"]
            if edge is None:
                continue
            if best_edge is None or edge > best_edge:
                best_edge = edge
                best_strategy = strat
                best_meta = it

        decision_hint = "insufficient_data"
        reason = "no historical evidence in this bucket"
        evidence: dict[str, Any] = {
            "sample_count": 0,
            "stock_avg_return_pct": None,
            "options_avg_return_pct": None,
            "relative_edge_pct": None,
            "confidence": "low",
        }
        if best_meta is not None:
            decision_hint = best_meta["recommendation"]
            evidence = {
                "sample_count": best_meta["sample_count"],
                "stock_avg_return_pct":
                    best_meta["stock_avg_return_pct"],
                "options_avg_return_pct":
                    best_meta["options_avg_return_pct"],
                "relative_edge_pct":
                    best_meta["relative_edge_pct"],
                "confidence": best_meta["confidence"],
            }
            reason = (
                f"{sig.replace('_', '-')} + "
                f"{ivb.replace('_', '-')} {best_strategy} edge="
                f"{best_meta['relative_edge_pct']:+.4f} "
                f"({best_meta['confidence']} confidence, "
                f"n={best_meta['sample_count']}) over 5D."
            )

        # Today status — reuse strict_pass mapping.
        status = (
            "trade_ready" if r["status"] == "accepted"
            else "watchlist_candidate"
        )

        out.append({
            "underlying": u,
            "stock_signal": sig,
            "stock_score": r["score"],
            "stock_status": status,
            "trend_bucket": today_trend,
            "iv_bucket": ivb,
            "best_options_strategy": best_strategy,
            "historical_edge": evidence,
            "decision_hint": decision_hint,
            "reason": reason,
        })
    return out
