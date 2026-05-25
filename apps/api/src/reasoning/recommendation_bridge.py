"""Phase L recommendation feature bridge.

Translates RecommendationEvidence rows into the same
factor_breakdown / regime_snapshot shape the signal extractor
already consumes for CandidateIdea.

This unblocks envelope generation on the LIVE decision path (where
paper_trade.recommendation_id points to a real Recommendation row,
unlike historical replay which sources from CandidateIdea).

Source evidence shape (one row per evidence_type):
    evidence_type   : 'trend_strength', 'rsi_14', 'sma_20_vs_50', ...
    summary (jsonb) : {"value": "...", "direction": "bullish|...",
                       "score": "...", "narrative": "...",
                       "threshold": "..."}

Target factor_breakdown shape (what the extractor expects):
    {"values": {"trend_strength_20d": "...", ...},
     "missing_components": [...],
     "confidence_label": "Low|Medium|High"}

Translation rules (deterministic, name-mapped):
    evidence_type      -> factor_breakdown.values key
    -------------------  -----------------------------------
    trend_strength     -> trend_strength_20d (score field)
    sma_20_vs_50       -> trend_strength_20d  (fallback if trend_strength absent)
    price_vs_sma_long  -> price_vs_200sma
    atr_pct_14         -> atr_percent_14
    rsi_14             -> rsi_14 (informational; not currently
                                   consumed by extractor)
    max_drawdown       -> max_drawdown (informational)

Regime snapshot synthesis — extracted from evidence narratives is
NOT safe (would amount to fabrication). We populate only the fields
we can derive deterministically:
    * From evidence directions: if trend_strength.direction is
      'bullish', infer market_trend='uptrend'. If 'bearish' ->
      'downtrend'. If 'neutral' -> 'sideways'. This is a thin proxy
      and clearly named as such.
    * sma50_over_sma200: derived from sma_20_vs_50 direction
      (CAVEAT: this is sma20/sma50, NOT sma50/sma200 — labeled as
      proxy. The extractor treats both fields independently so the
      semantic difference does not flow into a false signal.)
    * realized_vol_20d, vol_regime, atr_pctile_1y: NOT available
      from RecommendationEvidence. Left absent — extractor will not
      fire iv_compression/iv_expansion. Honest absence.

If no usable evidence rows resolve, returns (None, None) — caller
respects honest absence and emits no envelope.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session


# Evidence_type -> factor_breakdown.values key. Order matters for
# tie-breaking (first match wins per target key).
_EVIDENCE_TO_FACTOR_KEY: list[tuple[str, str]] = [
    ("trend_strength", "trend_strength_20d"),
    ("sma_20_vs_50", "trend_strength_20d"),
    ("price_vs_sma_long", "price_vs_200sma"),
    ("atr_pct_14", "atr_percent_14"),
    ("rsi_14", "rsi_14"),
    ("max_drawdown", "max_drawdown"),
]


# Direction -> market_trend (proxy mapping, see module doc)
_DIRECTION_TO_TREND: dict[str, str] = {
    "bullish": "uptrend",
    "bearish": "downtrend",
    "neutral": "sideways",
}


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    return s if s else None


def _is_numeric(v: Any) -> bool:
    if v is None:
        return False
    try:
        Decimal(str(v))
        return True
    except (InvalidOperation, ValueError, TypeError):
        return False


def assemble_features_from_recommendation(
    session: Session, recommendation_id: str,
) -> Tuple[Optional[Mapping[str, Any]], Optional[Mapping[str, Any]]]:
    """Returns (factor_breakdown, regime_snapshot) or (None, None) on no usable data.

    Pure read. Joins recommendation_evidence (per-recommendation features)
    with regime_snapshot (per-date authoritative regime context) when both
    exist. Authoritative regime data takes precedence over evidence-derived
    proxies. Honest absence preserved if either source is unavailable.

    Never raises out.
    """
    try:
        rows = session.execute(
            text(
                "SELECT evidence_type, summary FROM recommendation_evidence "
                "WHERE recommendation_id = :rid"
            ),
            {"rid": recommendation_id},
        ).all()
    except Exception:
        return None, None

    if not rows:
        return None, None

    # Index evidence rows by type for deterministic lookup.
    by_type: dict[str, Mapping[str, Any]] = {}
    for r in rows:
        # summary is JSONB; SQLA may return dict or str depending on driver.
        s = r.summary
        if isinstance(s, str):
            try:
                import json as _json
                s = _json.loads(s)
            except Exception:
                continue
        if isinstance(s, dict):
            by_type[str(r.evidence_type)] = s

    if not by_type:
        return None, None

    # Build values dict — prefer score field over raw value because
    # score is normalized to [-1, 1] and matches the extractor's
    # thresholds (which were calibrated against composite scores).
    # If score absent, fall back to value.
    values: dict[str, Any] = {}
    for ev_type, target_key in _EVIDENCE_TO_FACTOR_KEY:
        if ev_type not in by_type or target_key in values:
            continue
        summ = by_type[ev_type]
        score = summ.get("score")
        if _is_numeric(score):
            values[target_key] = str(score)
            continue
        v = summ.get("value")
        if _is_numeric(v):
            values[target_key] = str(v)

    # Enrich with raw factor_snapshot values where available. These
    # are the engine's actual computed features (not score proxies),
    # keyed on (asset_id, generated_at::date). When a factor_snapshot
    # row exists for the recommendation's asset on its date, its raw
    # values OVERRIDE the evidence-derived score proxies.
    try:
        fs_row = session.execute(
            text(
                "SELECT fs.trend_strength_20d, fs.residual_momentum_20d, "
                "       fs.residual_momentum_60d, fs.sector_relative_rank, "
                "       fs.price_vs_200sma, fs.atr_percent_14, "
                "       fs.earnings_proximity_days, fs.avg_dollar_volume_20d "
                "FROM factor_snapshot fs "
                "JOIN recommendation r "
                "  ON fs.as_of_date = DATE(r.generated_at) "
                " AND fs.asset_id = r.asset_id "
                "WHERE r.id = :rid "
                "LIMIT 1"
            ),
            {"rid": recommendation_id},
        ).first()
    except Exception:
        fs_row = None

    # Note: even if `values` was empty from evidence alone, a fresh
    # factor_snapshot row provides enough features to build a
    # factor_breakdown. So we delay the empty-check until after
    # the merge.
    if fs_row is not None:
        # Override / fill from authoritative raw values.
        if fs_row.trend_strength_20d is not None:
            values["trend_strength_20d"] = str(fs_row.trend_strength_20d)
        if fs_row.residual_momentum_20d is not None:
            values["residual_momentum_20d"] = str(fs_row.residual_momentum_20d)
        if fs_row.residual_momentum_60d is not None:
            values["residual_momentum_60d"] = str(fs_row.residual_momentum_60d)
        if fs_row.sector_relative_rank is not None:
            values["sector_relative_rank"] = str(fs_row.sector_relative_rank)
        if fs_row.price_vs_200sma is not None:
            values["price_vs_200sma"] = str(fs_row.price_vs_200sma)
        if fs_row.atr_percent_14 is not None:
            values["atr_percent_14"] = str(fs_row.atr_percent_14)
        if fs_row.avg_dollar_volume_20d is not None:
            values["avg_dollar_volume_20d"] = str(fs_row.avg_dollar_volume_20d)

    # Honest absence: if no features were resolvable from EITHER source.
    if not values:
        return None, None

    # Missing_components: evidence types the mapping covers but that
    # were absent from this recommendation's evidence rows.
    expected = {pair[0] for pair in _EVIDENCE_TO_FACTOR_KEY}
    missing = sorted(expected - by_type.keys())

    # Confidence label: derive coarsely from how many key features
    # resolved. No fabrication.
    if len(values) >= 4:
        conf_label = "High"
    elif len(values) >= 2:
        conf_label = "Medium"
    else:
        conf_label = "Low"

    factor_breakdown = {
        "values": values,
        "missing_components": missing,
        "confidence_label": conf_label,
    }

    # Regime — proxy derivation. ONLY fields we can support.
    regime_snapshot: dict[str, Any] = {}
    trend_dir = (
        _safe_str(by_type.get("trend_strength", {}).get("direction"))
        if isinstance(by_type.get("trend_strength"), dict)
        else None
    )
    if trend_dir in _DIRECTION_TO_TREND:
        regime_snapshot["market_trend"] = _DIRECTION_TO_TREND[trend_dir]

    sma_dir = (
        _safe_str(by_type.get("sma_20_vs_50", {}).get("direction"))
        if isinstance(by_type.get("sma_20_vs_50"), dict)
        else None
    )
    if sma_dir == "bullish":
        regime_snapshot["sma50_over_sma200"] = True
    elif sma_dir == "bearish":
        regime_snapshot["sma50_over_sma200"] = False
    # 'neutral' -> field omitted (honest absence)

    # Vol regime / realized_vol / atr_pctile: not available from
    # RecommendationEvidence directly. Try to enrich from
    # regime_snapshot keyed on the recommendation's generated_at date.
    try:
        rs_row = session.execute(
            text(
                "SELECT rs.market_trend, rs.vol_regime, rs.breadth_regime, "
                "       rs.sma50_over_sma200, rs.realized_vol_20d, "
                "       rs.atr_pctile_1y "
                "FROM regime_snapshot rs "
                "JOIN recommendation r "
                "  ON rs.as_of_date = DATE(r.generated_at) "
                "WHERE r.id = :rid "
                "LIMIT 1"
            ),
            {"rid": recommendation_id},
        ).first()
    except Exception:
        rs_row = None

    if rs_row is not None:
        # Authoritative regime fields override evidence-derived proxies.
        # `market_trend` from regime_snapshot is the canonical source;
        # the evidence-derived value was only a fallback.
        if rs_row.market_trend is not None:
            regime_snapshot["market_trend"] = rs_row.market_trend
        if rs_row.sma50_over_sma200 is not None:
            regime_snapshot["sma50_over_sma200"] = bool(rs_row.sma50_over_sma200)
        # New fields only available from regime_snapshot — never from evidence.
        if rs_row.vol_regime is not None:
            regime_snapshot["vol_regime"] = rs_row.vol_regime
        if rs_row.realized_vol_20d is not None:
            regime_snapshot["realized_vol_20d"] = str(rs_row.realized_vol_20d)
        if rs_row.atr_pctile_1y is not None:
            regime_snapshot["atr_pctile_1y"] = str(rs_row.atr_pctile_1y)
        if rs_row.breadth_regime is not None:
            regime_snapshot["breadth_regime"] = rs_row.breadth_regime

    return factor_breakdown, regime_snapshot if regime_snapshot else None
