"""Phase F — Playbook composition service.

Composes the canonical Strategy Playbook payload from
options_strategy_playbook + options_strategy_bias. Optional
overlays add live candidates + open positions tagged with the rule.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _to_float(v: Any) -> float | None:
    if v is None: return None
    if isinstance(v, Decimal): return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def list_playbooks(session: Session) -> list[dict[str, Any]]:
    """All playbooks joined with bias for the library view."""
    rows = session.execute(text("""
        SELECT
          p.rule_id, p.executive_summary, p.source,
          p.related_concepts,
          b.bias, b.directional_view, b.risk_profile
        FROM options_strategy_playbook p
        LEFT JOIN options_strategy_bias b ON b.rule_id = p.rule_id
        ORDER BY
          CASE WHEN b.bias = 'bullish' THEN 0
               WHEN b.bias = 'bearish' THEN 1
               WHEN b.bias = 'neutral' THEN 2
               WHEN b.bias = 'event'   THEN 3
               ELSE 4 END,
          p.rule_id ASC
    """)).mappings().all()
    return [{
        "rule_id":           str(r["rule_id"]),
        "executive_summary": str(r["executive_summary"]),
        "source":            str(r["source"]),
        "related_concepts":  list(r["related_concepts"] or []),
        "bias":              str(r["bias"]) if r["bias"] else "developing",
        "directional_view":  str(r["directional_view"]) if r["directional_view"] else "",
        "risk_profile":      str(r["risk_profile"]) if r["risk_profile"] else "defined",
        "is_stub":           "stub" in str(r["source"] or ""),
    } for r in rows]


def get_playbook(session: Session, rule_id: str) -> dict[str, Any] | None:
    """Full playbook for one rule_id, joined with bias taxonomy."""
    r = session.execute(text("""
        SELECT
          p.rule_id, p.executive_summary,
          p.when_to_use, p.when_not_to_use,
          p.market_environment_fit, p.iv_regime_fit,
          p.theta_behavior, p.vega_behavior, p.delta_behavior,
          p.typical_dte_range, p.lifecycle_expectations,
          p.risk_summary,
          p.educational_overlay_basic, p.educational_overlay_advanced,
          p.related_concepts, p.source,
          b.bias, b.directional_view, b.risk_profile,
          b.regime_fit, b.notes
        FROM options_strategy_playbook p
        LEFT JOIN options_strategy_bias b ON b.rule_id = p.rule_id
        WHERE p.rule_id = :r
    """), {"r": rule_id}).mappings().first()
    if r is None:
        return None
    return {
        "rule_id":           str(r["rule_id"]),
        "executive_summary": str(r["executive_summary"]),
        "when_to_use":       r["when_to_use"] or [],
        "when_not_to_use":   r["when_not_to_use"] or [],
        "market_environment_fit": r["market_environment_fit"] or {},
        "iv_regime_fit":     r["iv_regime_fit"] or {},
        "theta_behavior":    r["theta_behavior"],
        "vega_behavior":     r["vega_behavior"],
        "delta_behavior":    r["delta_behavior"],
        "typical_dte_range": r["typical_dte_range"] or {},
        "lifecycle_expectations": r["lifecycle_expectations"] or {},
        "risk_summary":      r["risk_summary"],
        "educational_overlay_basic":    r["educational_overlay_basic"],
        "educational_overlay_advanced": r["educational_overlay_advanced"],
        "related_concepts":  list(r["related_concepts"] or []),
        "source":            str(r["source"]),
        "is_stub":           "stub" in str(r["source"] or ""),
        "bias":              str(r["bias"]) if r["bias"] else "developing",
        "directional_view":  str(r["directional_view"]) if r["directional_view"] else "",
        "risk_profile":      str(r["risk_profile"]) if r["risk_profile"] else "defined",
        "bias_regime_fit":   r["regime_fit"] or {},
        "bias_notes":        r["notes"],
    }


def get_playbook_live(
    session: Session, rule_id: str,
) -> dict[str, Any] | None:
    """Playbook + live overlay (candidates + open trades for this rule)."""
    base = get_playbook(session, rule_id)
    if base is None:
        return None
    # Top 5 live candidates
    cands = session.execute(text("""
        SELECT c.id, c.underlying, c.run_date, c.composite_score,
               c.why_emitted, c.earliest_event_type,
               c.earliest_event_date, c.event_days_away,
               s.option_symbol, s.expiration, s.strike, s.option_type
        FROM options_strategy_candidate c
        JOIN options_shadow_decision_log s ON s.id = c.shadow_observation_id
        WHERE c.rule_id = :r
          AND c.run_date >= CURRENT_DATE - 7
        ORDER BY c.composite_score DESC NULLS LAST
        LIMIT 5
    """), {"r": rule_id}).mappings().all()
    # Open paper trades for this rule
    trades = session.execute(text("""
        SELECT id, underlying, status, opened_at,
               max_loss_dollars, max_profit_dollars
        FROM options_paper_trade
        WHERE strategy_name = :r
          AND status IN ('PROPOSED','FILLED','OPEN')
          AND paper_only = TRUE
        ORDER BY opened_at DESC NULLS LAST
        LIMIT 8
    """), {"r": rule_id}).mappings().all()
    base["live"] = {
        "candidates": [{
            "candidate_id":    int(c["id"]),
            "underlying":      str(c["underlying"]),
            "run_date":        c["run_date"].isoformat() if c["run_date"] else None,
            "composite_score": _to_float(c["composite_score"]),
            "why_emitted":     str(c["why_emitted"]),
            "option_symbol":   str(c["option_symbol"]),
            "expiry":          c["expiration"].isoformat() if c["expiration"] else None,
            "strike":          _to_float(c["strike"]),
            "option_type":     str(c["option_type"]),
            "earliest_event_type": (
                str(c["earliest_event_type"])
                if c["earliest_event_type"] else None
            ),
            "earliest_event_date": (
                c["earliest_event_date"].isoformat()
                if c["earliest_event_date"] else None
            ),
            "event_days_away": c["event_days_away"],
        } for c in cands],
        "open_trades": [{
            "trade_id":           int(t["id"]),
            "underlying":         str(t["underlying"]),
            "status":             str(t["status"]),
            "opened_at":          t["opened_at"].isoformat() if t["opened_at"] else None,
            "max_loss_dollars":   _to_float(t["max_loss_dollars"]),
            "max_profit_dollars": _to_float(t["max_profit_dollars"]),
        } for t in trades],
    }
    return base
