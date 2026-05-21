"""Phase G — AI Approach composition service.

Per-approach regime-fit live read. Honest "fits now" classification
grounded in named signals — never a marketing-style certainty.
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


# ---------------------------------------------------------------------------
# Universe / row readers
# ---------------------------------------------------------------------------


def list_approaches(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(text("""
        SELECT slug, name, one_liner, thematic_summary,
               suitability, typical_strategies, iv_regime_preference,
               risk_character
        FROM options_ai_playbook
        ORDER BY slug
    """)).mappings().all()
    return [{
        "slug":                 str(r["slug"]),
        "name":                 str(r["name"]),
        "one_liner":            str(r["one_liner"]),
        "thematic_summary":     str(r["thematic_summary"]),
        "suitability":          list(r["suitability"] or []),
        "typical_strategies":   list(r["typical_strategies"] or []),
        "iv_regime_preference": str(r["iv_regime_preference"]),
        "risk_character":       str(r["risk_character"]),
    } for r in rows]


def get_approach(session: Session, slug: str) -> dict[str, Any] | None:
    r = session.execute(text("""
        SELECT slug, name, one_liner, thematic_summary,
               when_it_fits, when_it_doesnt,
               suitability, typical_strategies,
               iv_regime_preference, typical_dte_range,
               risk_character, profit_taking_guidance,
               theta_expectations, iv_behavior_explainer,
               risk_expansion_scenarios,
               educational_overlay_basic, educational_overlay_advanced,
               regime_signals, transparency_note, source
        FROM options_ai_playbook WHERE slug = :s
    """), {"s": slug}).mappings().first()
    if r is None: return None
    return {
        "slug":                       str(r["slug"]),
        "name":                       str(r["name"]),
        "one_liner":                  str(r["one_liner"]),
        "thematic_summary":           str(r["thematic_summary"]),
        "when_it_fits":               r["when_it_fits"] or [],
        "when_it_doesnt":             r["when_it_doesnt"] or [],
        "suitability":                list(r["suitability"] or []),
        "typical_strategies":         list(r["typical_strategies"] or []),
        "iv_regime_preference":       str(r["iv_regime_preference"]),
        "typical_dte_range":          r["typical_dte_range"] or {},
        "risk_character":             str(r["risk_character"]),
        "profit_taking_guidance":     r["profit_taking_guidance"],
        "theta_expectations":         r["theta_expectations"],
        "iv_behavior_explainer":      r["iv_behavior_explainer"],
        "risk_expansion_scenarios":   r["risk_expansion_scenarios"] or [],
        "educational_overlay_basic":  r["educational_overlay_basic"],
        "educational_overlay_advanced": r["educational_overlay_advanced"],
        "regime_signals":             r["regime_signals"] or [],
        "transparency_note":          str(r["transparency_note"]),
        "source":                     str(r["source"]),
    }


# ---------------------------------------------------------------------------
# Regime fit
# ---------------------------------------------------------------------------


def _universe_iv_mean(session: Session) -> tuple[float | None, int]:
    """Average iv_rank_252d across the most recent feature_daily row per
    underlying. Returns (mean, n_with_data)."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (underlying) iv_rank_252d
        FROM options_feature_daily
        WHERE as_of_date >= CURRENT_DATE - 7
        ORDER BY underlying, as_of_date DESC
    """)).all()
    values = [float(r[0]) for r in rows if r[0] is not None]
    if not values: return None, 0
    return sum(values) / len(values), len(values)


def _events_in_window(
    session: Session, days: int,
) -> list[dict[str, Any]]:
    rows = session.execute(text("""
        SELECT event_type, event_date, importance, title
        FROM market_event_calendar
        WHERE event_date >= CURRENT_DATE
          AND event_date <= CURRENT_DATE + :n
        ORDER BY event_date ASC
        LIMIT 5
    """), {"n": days}).mappings().all()
    import datetime as dt
    today = dt.date.today()
    return [{
        "event_type": str(r["event_type"]),
        "event_date": r["event_date"].isoformat(),
        "importance": str(r["importance"]),
        "title":      str(r["title"]),
        "days_away":  (r["event_date"] - today).days,
    } for r in rows]


def _candidate_overlay(
    session: Session, rule_ids: list[str], *, limit: int = 8,
) -> list[dict[str, Any]]:
    if not rule_ids: return []
    rows = session.execute(text("""
        SELECT c.id, c.rule_id, c.underlying, c.composite_score,
               c.bias, c.why_emitted,
               c.earliest_event_type, c.earliest_event_date,
               c.event_days_away
        FROM options_strategy_candidate c
        WHERE c.rule_id = ANY(:rules)
          AND c.run_date >= CURRENT_DATE - 7
        ORDER BY c.composite_score DESC NULLS LAST
        LIMIT :n
    """), {"rules": rule_ids, "n": limit}).mappings().all()
    return [{
        "candidate_id":    int(r["id"]),
        "rule_id":         str(r["rule_id"]),
        "underlying":      str(r["underlying"]),
        "composite_score": _to_float(r["composite_score"]),
        "bias":            str(r["bias"]),
        "why_emitted":     str(r["why_emitted"]),
        "earliest_event_type": (
            str(r["earliest_event_type"])
            if r["earliest_event_type"] else None
        ),
        "earliest_event_date": (
            r["earliest_event_date"].isoformat()
            if r["earliest_event_date"] else None
        ),
        "event_days_away": r["event_days_away"],
    } for r in rows]


def _classify_iv_tier(iv_mean: float | None) -> str:
    if iv_mean is None: return "unknown"
    if iv_mean >= 70: return "high"
    if iv_mean >= 50: return "moderate_to_high"
    if iv_mean >= 30: return "moderate"
    if iv_mean >= 15: return "low_to_moderate"
    return "low"


def _iv_pref_aligns(approach_pref: str, current_tier: str) -> bool:
    """Honest mapping: approach iv_regime_preference vs current
    classified tier. 'any' always aligns; 'unknown' tier means 'cannot
    classify' — returns False so the UI shows honest uncertainty."""
    if current_tier == "unknown":   return False
    if approach_pref == "any":      return True
    # Strict equality is intentional — partial matches surface as
    # 'partial fit' rather than 'fits' in the UI.
    if approach_pref == current_tier: return True
    # Adjacent acceptable when one side is "_to_" merged.
    if approach_pref == "moderate_to_high" and current_tier in ("moderate", "high"):
        return True
    if approach_pref == "low_to_moderate" and current_tier in ("low", "moderate"):
        return True
    return False


def get_approach_live(
    session: Session, slug: str,
) -> dict[str, Any] | None:
    base = get_approach(session, slug)
    if base is None: return None

    iv_mean, n_with_data = _universe_iv_mean(session)
    current_tier = _classify_iv_tier(iv_mean)
    iv_pref_match = _iv_pref_aligns(base["iv_regime_preference"], current_tier)

    # DTE for event check uses approach's typical_dte_range max if known.
    dte_max = int((base["typical_dte_range"] or {}).get("max", 45))
    events = _events_in_window(session, days=dte_max)
    high_importance_events = [e for e in events if e["importance"] == "high"]

    # Three-tier fit classification — calm, honest:
    #   "fits_now"          — IV preference matches AND event compatible
    #   "fits_with_caveat"  — IV matches but caveats (events, low data)
    #   "doesnt_fit_now"    — IV preference mismatched
    #   "uncertain"         — insufficient data to classify
    if current_tier == "unknown":
        fit_label = "uncertain"
        fit_reason = (
            "Universe IV-rank not available — feature engine pending data. "
            "Cannot honestly classify regime fit."
        )
    elif iv_pref_match and not high_importance_events:
        fit_label = "fits_now"
        fit_reason = (
            f"Universe IV mean {iv_mean:.0f} aligns with "
            f"'{base['iv_regime_preference']}' preference. "
            "No high-importance catalysts inside the typical DTE window."
        )
    elif iv_pref_match and high_importance_events:
        fit_label = "fits_with_caveat"
        ev = high_importance_events[0]
        fit_reason = (
            f"Universe IV mean {iv_mean:.0f} aligns with the approach, "
            f"but {ev['event_type']} on {ev['event_date']} "
            f"(T-{ev['days_away']}d) is a meaningful catalyst inside "
            "the typical DTE window. Read 'Risk expansion scenarios'."
        )
    else:
        fit_label = "doesnt_fit_now"
        fit_reason = (
            f"Universe IV mean {iv_mean:.0f} classifies as "
            f"'{current_tier}'; approach prefers "
            f"'{base['iv_regime_preference']}'. Premium environment "
            "is mismatched."
        )

    candidates = _candidate_overlay(
        session, base["typical_strategies"], limit=8,
    )

    base["live"] = {
        "fit_label":         fit_label,
        "fit_reason":        fit_reason,
        "iv_universe_mean":  iv_mean,
        "iv_universe_tier":  current_tier,
        "iv_underlying_count": n_with_data,
        "upcoming_events":   events,
        "high_importance_events_in_window": len(high_importance_events),
        "matched_candidates": candidates,
    }
    return base
