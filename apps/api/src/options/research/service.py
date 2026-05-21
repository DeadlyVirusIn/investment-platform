"""Phase D — Research conviction service.

Composes the per-underlying AI strategist read from existing data.
Pure read-only. No new tables. No new state.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


# ----- helpers --------------------------------------------------------------


def _to_float(v: Any) -> float | None:
    if v is None: return None
    if isinstance(v, Decimal): return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _premium_tier(iv_rank: float | None) -> str:
    if iv_rank is None: return "unknown"
    if iv_rank >= 75: return "rich"
    if iv_rank >= 50: return "elevated"
    if iv_rank >= 25: return "average"
    return "cheap"


def _posture_from_mix(
    counts: dict[str, int], best_composite: dict[str, float | None],
) -> tuple[str, str]:
    """Distill bias mix into one of:
      bullish-leaning / bearish-leaning / neutral-leaning /
      event-driven / mixed / unknown
    """
    if not counts:
        return "unknown", "No strategy candidates yet for this underlying."
    total = sum(counts.values())
    parts = sorted(counts.items(), key=lambda kv: -kv[1])
    top_bias, top_n = parts[0]
    top_pct = top_n / total
    second_n = parts[1][1] if len(parts) > 1 else 0
    spread = (top_n - second_n) / total
    # Strong lean: top bias > 60% of candidates
    if top_pct >= 0.6:
        return (
            f"{top_bias}-leaning",
            f"{top_n}/{total} candidates are {top_bias}; "
            f"dominant posture by {top_pct * 100:.0f}%.",
        )
    # Moderate lean
    if spread >= 0.20:
        return (
            f"{top_bias}-leaning",
            f"{top_bias} leads at {top_pct * 100:.0f}%; "
            f"{spread * 100:.0f}% gap over the next bias.",
        )
    # Event takes precedence when tied/close
    if "event" in counts and counts["event"] >= total * 0.30:
        return (
            "event-driven",
            f"{counts['event']}/{total} candidates are event-bias; "
            "catalyst risk dominates direction.",
        )
    return (
        "mixed",
        "No single bias dominates — competing directional reads.",
    )


# ----- DB readers -----------------------------------------------------------


def _list_universe_symbols(session: Session) -> list[str]:
    """Underlyings with at least one shadow observation OR one event."""
    rows = session.execute(text("""
        SELECT DISTINCT u FROM (
          SELECT underlying_symbol AS u FROM options_shadow_decision_log
          UNION
          SELECT unnest(affected_symbols) FROM market_event_calendar
        ) x
        ORDER BY u
    """)).all()
    return [str(r[0]) for r in rows]


def _spot(session: Session, symbol: str) -> tuple[float | None, str | None]:
    row = session.execute(text("""
        SELECT close, ts FROM price_bar
        WHERE asset_id IN (
          SELECT id FROM asset WHERE symbol = :s LIMIT 1
        ) AND timeframe = '1d'
        ORDER BY ts DESC LIMIT 1
    """), {"s": symbol}).first()
    if row is None: return None, None
    return _to_float(row[0]), row[1].date().isoformat() if row[1] else None


def _feature_daily(session: Session, symbol: str) -> dict[str, Any] | None:
    row = session.execute(text("""
        SELECT as_of_date, iv_rank_252d, iv_percentile_252d,
               atm_iv, realized_vol_30d, vrp_30d,
               term_structure_30_60, skew_25d,
               put_call_oi_ratio, put_call_volume_ratio,
               data_quality_flags
        FROM options_feature_daily
        WHERE underlying = :s
        ORDER BY as_of_date DESC LIMIT 1
    """), {"s": symbol}).mappings().first()
    if row is None: return None
    return dict(row)


def _bias_mix(session: Session, symbol: str) -> tuple[dict[str, int], dict[str, float | None]]:
    """Return (bias → count, bias → best composite_score)."""
    rows = session.execute(text("""
        SELECT bias, COUNT(*) AS n,
               MAX(composite_score) AS best
        FROM options_strategy_candidate
        WHERE underlying = :s
          AND run_date >= CURRENT_DATE - 7
        GROUP BY bias
    """), {"s": symbol}).mappings().all()
    counts = {str(r["bias"]): int(r["n"]) for r in rows}
    best = {str(r["bias"]): _to_float(r["best"]) for r in rows}
    return counts, best


def _strategy_family_fit(
    session: Session, symbol: str,
) -> list[dict[str, Any]]:
    """Rank rule_ids by average composite_score over last 7 days."""
    rows = session.execute(text("""
        SELECT c.rule_id,
               c.bias                     AS bias,
               c.risk_profile             AS risk_profile,
               COUNT(*)                   AS n,
               AVG(c.composite_score)     AS avg_score,
               MAX(c.composite_score)     AS best_score,
               MIN(c.directional_view)    AS view
        FROM options_strategy_candidate c
        WHERE c.underlying = :s
          AND c.run_date >= CURRENT_DATE - 7
        GROUP BY c.rule_id, c.bias, c.risk_profile
        ORDER BY AVG(c.composite_score) DESC NULLS LAST
        LIMIT 8
    """), {"s": symbol}).mappings().all()
    return [{
        "rule_id":      str(r["rule_id"]),
        "bias":         str(r["bias"]) if r["bias"] else "developing",
        "risk_profile": str(r["risk_profile"]) if r["risk_profile"] else "defined",
        "directional_view": str(r["view"]) if r["view"] else "",
        "candidate_count": int(r["n"]),
        "avg_composite":   _to_float(r["avg_score"]),
        "best_composite":  _to_float(r["best_score"]),
    } for r in rows]


def _catalyst_timeline(
    session: Session, symbol: str,
) -> list[dict[str, Any]]:
    rows = session.execute(text("""
        SELECT event_type, event_date, event_time, title,
               importance, source, explanation
        FROM market_event_calendar
        WHERE :s = ANY(affected_symbols)
          AND event_date >= CURRENT_DATE
        ORDER BY event_date ASC
        LIMIT 12
    """), {"s": symbol}).mappings().all()
    today = dt.date.today()
    return [{
        "event_type":  str(r["event_type"]),
        "event_date":  r["event_date"].isoformat(),
        "event_time":  str(r["event_time"]) if r["event_time"] else None,
        "title":       str(r["title"]),
        "importance":  str(r["importance"]),
        "source":      str(r["source"]),
        "explanation": str(r["explanation"]),
        "days_away":   (r["event_date"] - today).days,
    } for r in rows]


def _expected_move(
    feature: dict[str, Any] | None, spot: float | None,
    *, horizon_days: int,
) -> float | None:
    """Crude expected-move: spot × atm_iv × sqrt(days/365).

    Returns dollar magnitude (one-standard-deviation). None when
    inputs unavailable.
    """
    if feature is None or spot is None: return None
    atm = _to_float(feature.get("atm_iv"))
    if atm is None or atm <= 0: return None
    return spot * atm * math.sqrt(horizon_days / 365.0)


def _top_opportunities(
    session: Session, symbol: str, *, limit: int = 5,
) -> list[dict[str, Any]]:
    """Top strategy candidates by composite_score for this underlying."""
    rows = session.execute(text("""
        SELECT c.id, c.rule_id, c.bias, c.composite_score,
               c.directional_view, c.why_emitted, c.triggering_rule,
               c.earliest_event_type, c.earliest_event_date,
               c.event_days_away,
               s.option_symbol, s.expiration, s.strike, s.option_type
        FROM options_strategy_candidate c
        JOIN options_shadow_decision_log s
          ON s.id = c.shadow_observation_id
        WHERE c.underlying = :s
          AND c.run_date >= CURRENT_DATE - 7
        ORDER BY c.composite_score DESC NULLS LAST
        LIMIT :n
    """), {"s": symbol, "n": limit}).mappings().all()
    return [{
        "candidate_id":      int(r["id"]),
        "rule_id":           str(r["rule_id"]),
        "bias":              str(r["bias"]),
        "composite_score":   _to_float(r["composite_score"]),
        "directional_view":  str(r["directional_view"]),
        "why_emitted":       str(r["why_emitted"]),
        "triggering_rule":   str(r["triggering_rule"]),
        "option_symbol":     str(r["option_symbol"]),
        "expiry":            r["expiration"].isoformat() if r["expiration"] else None,
        "strike":            _to_float(r["strike"]),
        "option_type":       str(r["option_type"]),
        "earliest_event_type": (
            str(r["earliest_event_type"])
            if r["earliest_event_type"] else None
        ),
        "earliest_event_date": (
            r["earliest_event_date"].isoformat()
            if r["earliest_event_date"] else None
        ),
        "event_days_away":   r["event_days_away"],
    } for r in rows]


def _open_positions(
    session: Session, symbol: str,
) -> list[dict[str, Any]]:
    rows = session.execute(text("""
        SELECT id, strategy_name, status, opened_at,
               max_loss_dollars, max_profit_dollars,
               breakeven_lower, breakeven_upper
        FROM options_paper_trade
        WHERE underlying = :s
          AND status IN ('PROPOSED','FILLED','OPEN')
          AND paper_only = TRUE
        ORDER BY opened_at DESC NULLS LAST
        LIMIT 8
    """), {"s": symbol}).mappings().all()
    return [{
        "trade_id":       int(r["id"]),
        "strategy_name":  str(r["strategy_name"]),
        "status":         str(r["status"]),
        "opened_at":      r["opened_at"].isoformat() if r["opened_at"] else None,
        "max_loss_dollars":   _to_float(r["max_loss_dollars"]),
        "max_profit_dollars": _to_float(r["max_profit_dollars"]),
        "breakeven_lower":    _to_float(r["breakeven_lower"]),
        "breakeven_upper":    _to_float(r["breakeven_upper"]),
    } for r in rows]


# ----- composition ----------------------------------------------------------


def underlying_research(
    session: Session, symbol: str,
) -> dict[str, Any]:
    """Compose the full per-underlying AI conviction view."""
    spot, spot_as_of = _spot(session, symbol)
    feat = _feature_daily(session, symbol)
    counts, best = _bias_mix(session, symbol)
    posture, posture_reason = _posture_from_mix(counts, best)
    strategy_fit = _strategy_family_fit(session, symbol)
    catalysts = _catalyst_timeline(session, symbol)
    top_opps = _top_opportunities(session, symbol, limit=5)
    open_pos = _open_positions(session, symbol)

    iv_rank = _to_float(feat.get("iv_rank_252d")) if feat else None
    atm_iv = _to_float(feat.get("atm_iv")) if feat else None
    realized_vol = _to_float(feat.get("realized_vol_30d")) if feat else None
    vrp = _to_float(feat.get("vrp_30d")) if feat else None
    premium_tier = _premium_tier(iv_rank)

    em_1w = _expected_move(feat, spot, horizon_days=7)
    em_1m = _expected_move(feat, spot, horizon_days=30)

    iv_reason = (
        f"IV rank {iv_rank:.0f} ({premium_tier}). "
        + (f"Realized vol 30d {realized_vol * 100:.1f}%. "
           if realized_vol else "")
        + (f"VRP {vrp * 100:+.1f}%. "
           if vrp is not None else "")
    ) if iv_rank is not None else (
        "IV-rank unavailable — feature engine pending IV history. "
        "Premium environment cannot be classified."
    )
    em_reason = (
        f"1-week expected move ≈ ±${em_1w:.2f}. 1-month ≈ ±${em_1m:.2f}."
        if em_1w is not None and em_1m is not None
        else "Expected move not measurable — atm_iv unavailable."
    )

    # Single calm sentence summarizing the strategist's read on this name.
    calm = (
        f"AI posture on {symbol} is {posture}. "
        + (f"Premium is {premium_tier}. " if premium_tier != "unknown" else "")
        + (f"Next catalyst: {catalysts[0]['event_type']} on "
           f"{catalysts[0]['event_date']} (T-{catalysts[0]['days_away']}d). "
           if catalysts else "No catalysts in calendar window. ")
    )

    return {
        "symbol":       symbol,
        "spot":         spot,
        "spot_as_of":   spot_as_of,
        "calm_sentence": calm,
        "ai_posture": {
            "label":  posture,
            "reason": posture_reason,
            "bias_mix": counts,
        },
        "volatility_regime": {
            "premium_tier":     premium_tier,
            "iv_rank_252d":     iv_rank,
            "atm_iv":           atm_iv,
            "realized_vol_30d": realized_vol,
            "vrp_30d":          vrp,
            "explanation":      iv_reason,
        },
        "expected_move": {
            "one_week":  em_1w,
            "one_month": em_1m,
            "explanation": em_reason,
        },
        "strategy_family_fit": strategy_fit,
        "catalyst_timeline":   catalysts,
        "top_opportunities":   top_opps,
        "open_positions":      open_pos,
        "thesis_invalidators": [
            (
                f"Spot breaches the dominant breakeven on the wrong side."
                if open_pos else
                "No active position — invalidator framing applies when one exists."
            ),
            (
                f"{catalysts[0]['event_type']} surprise on "
                f"{catalysts[0]['event_date']} reprices premium beyond "
                "expected move."
                if catalysts else
                "Surprise macro event (no calendar event in current window)."
            ),
            (
                "IV-rank regime flips: rich → cheap or cheap → rich invalidates "
                "the strategy-family fit above."
            ),
        ],
        "diagnostics": {
            "candidate_count_total": sum(counts.values()),
            "events_in_window":      len(catalysts),
            "open_positions_count":  len(open_pos),
        },
    }


def universe_summary(
    session: Session,
) -> dict[str, Any]:
    """Lightweight summary across every known underlying for the
    universe overview surface."""
    symbols = _list_universe_symbols(session)
    rows = []
    for sym in symbols:
        spot, _ = _spot(session, sym)
        feat = _feature_daily(session, sym)
        counts, _best = _bias_mix(session, sym)
        posture, _ = _posture_from_mix(counts, _best)
        iv_rank = _to_float(feat.get("iv_rank_252d")) if feat else None
        # Earliest upcoming catalyst (high importance preferred).
        nxt = session.execute(text("""
            SELECT event_type, event_date, importance, title
            FROM market_event_calendar
            WHERE :s = ANY(affected_symbols)
              AND event_date >= CURRENT_DATE
            ORDER BY event_date ASC, importance DESC, id ASC
            LIMIT 1
        """), {"s": sym}).mappings().first()
        next_event = None
        if nxt:
            next_event = {
                "event_type": str(nxt["event_type"]),
                "event_date": nxt["event_date"].isoformat(),
                "importance": str(nxt["importance"]),
                "title":      str(nxt["title"]),
                "days_away":  (nxt["event_date"] - dt.date.today()).days,
            }
        rows.append({
            "symbol":           sym,
            "spot":             spot,
            "ai_posture":       posture,
            "iv_rank_252d":     iv_rank,
            "premium_tier":     _premium_tier(iv_rank),
            "candidate_count":  sum(counts.values()),
            "next_event":       next_event,
        })
    # Order: catalyst within 14 days first, then by candidate count.
    def _sort_key(r: dict[str, Any]) -> tuple[int, int]:
        nxt = r.get("next_event")
        nxt_days = nxt["days_away"] if nxt else 9999
        return (0 if nxt_days <= 14 else 1, -r["candidate_count"])
    rows.sort(key=_sort_key)
    return {"count": len(rows), "rows": rows}
