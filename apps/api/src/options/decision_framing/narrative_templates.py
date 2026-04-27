"""Deterministic narrative templates (Phase 11J).

Pure-fn module. Stdlib only. NEVER calls LLMs / external APIs. Every
output string is built from frozen-string templates + caller-supplied
factual fields. No probabilistic generation. No "thesis" wording.

Templates are intentionally plain-English so an operator can audit
exactly what the system claims.
"""

from __future__ import annotations

from typing import Any

from apps.api.src.options.decision_support.buckets import (
    BUCKET_DATA_QUALITY_REVIEW,
    BUCKET_EXCLUDED,
    BUCKET_HIGH_REVIEW_PRIORITY,
    BUCKET_LABELS,
    BUCKET_MODEL_LIMITATION_REVIEW,
    BUCKET_NEUTRAL,
)
from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)


REVIEW_CONTEXT_ONLY_FOOTER = (
    "This is review context only. It is not a trade recommendation, "
    "not a signal, and not execution guidance. Human review is "
    "required."
)

PAPER_ONLY_REMINDER = (
    "Paper-only analysis: scores are deterministic rule-based "
    "analytics over historical observations and do not reflect live "
    "trading behavior."
)


# ---------------------------------------------------------------------------
# "Why it appears" — bucket-specific opening sentence
# ---------------------------------------------------------------------------

_BUCKET_WHY_TEMPLATES: dict[str, str] = {
    BUCKET_HIGH_REVIEW_PRIORITY: (
        "This observation appears in the High Review Priority bucket "
        "because total_score={score} >= 75, the rule eligibility "
        "evaluator marked it qualified, no severe model-limitation "
        "flags are present, and no data-quality penalties were "
        "applied."
    ),
    BUCKET_DATA_QUALITY_REVIEW: (
        "This observation appears in the Needs Review — Data Quality "
        "bucket because at least one data-quality penalty "
        "({dq_penalty_codes}) reduced the evaluation score to "
        "{score}/100."
    ),
    BUCKET_MODEL_LIMITATION_REVIEW: (
        "This observation appears in the Needs Review — Model "
        "Limitation bucket because at least one severe flag "
        "({severe_flag_codes}) is present. The recorded payoff is "
        "a model approximation only; outcome uncertainty remains."
    ),
    BUCKET_NEUTRAL: (
        "This observation appears in the Neutral — Needs Human "
        "Review bucket because the score ({score}/100) sits in the "
        "mid-range and no severe flags or data-quality penalties "
        "were triggered."
    ),
    BUCKET_EXCLUDED: (
        "This observation appears in the Excluded by Review Rules "
        "bucket because {exclusion_reason}"
    ),
}


# ---------------------------------------------------------------------------
# "Why caution is still required" — universal disclaimer
# ---------------------------------------------------------------------------

CAUTION_PARAGRAPH = (
    "Human review is still required because evaluation scores are "
    "rule-based paper analytics over a v1 frozen scoring model. "
    "Scores do not reflect current market conditions, real-time "
    "spreads, intraday liquidity changes, or counterparty/assignment "
    "risk beyond the simplified-exit modelling. Verify data freshness "
    "and current chain liquidity before any further inspection."
)


# ---------------------------------------------------------------------------
# Per-flag caveat lines
# ---------------------------------------------------------------------------

_FLAG_CAVEAT_LINES: dict[str, str] = {
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME: (
        "Pin risk: settlement landed within $0.05 of a strike. "
        "Real-world assignment behaviour is settlement-time-dependent; "
        "the recorded payoff is a model approximation."
    ),
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT: (
        "Assignment — simplified exit: v1 paper engine treats "
        "assignment as terminal at intrinsic value; no synthetic "
        "equity position is created."
    ),
    FLAG_MISSING_SETTLEMENT: (
        "Missing settlement: an expiration event lacked settlement "
        "price. Recorded PnL must not be treated as final."
    ),
    "MISSING_GREEKS": (
        "Missing Greeks: at least one selected leg lacked "
        "delta/gamma/theta/vega; risk surface is incomplete."
    ),
    "MISSING_IV": (
        "Missing IV: at least one selected leg lacked implied "
        "volatility; volatility-context inputs are partial."
    ),
    "NO_PRICE_HISTORY": (
        "Insufficient realized volatility history: realized_vol_20d "
        "and vrp_30d unavailable; the volatility-context component "
        "could not score those inputs."
    ),
    "INSUFFICIENT_IV_HISTORY": (
        "Insufficient IV history: iv_rank_252d and "
        "iv_percentile_252d unavailable; IV-richness context is "
        "partial."
    ),
    "INSUFFICIENT_VOLUME_HISTORY": (
        "Insufficient volume history: unusual-volume z-scores "
        "unavailable."
    ),
    "NO_OPEN_INTEREST": (
        "Naive gamma exposure proxy: open interest base data is "
        "missing; the gamma exposure value is not equivalent to "
        "dealer GEX."
    ),
}


def caveat_for_flag(code: str) -> str | None:
    return _FLAG_CAVEAT_LINES.get(code)


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def _list_codes(items: list, key: str = "code") -> str:
    if not items:
        return "none"
    return ", ".join(str(i.get(key)) if isinstance(i, dict) else str(i)
                     for i in items)


def render_why(row: dict[str, Any]) -> str:
    bucket = row.get("bucket")
    score = int(row.get("total_score") or 0)
    severe = [f for f in (row.get("flags") or [])
              if f in (FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
                       FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
                       FLAG_MISSING_SETTLEMENT)]
    dq_codes = [
        p.get("code") for p in (row.get("penalties") or [])
        if p.get("code") in _FLAG_CAVEAT_LINES
        and p.get("code") not in (
            FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
            FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
            FLAG_MISSING_SETTLEMENT,
        )
    ]
    template = _BUCKET_WHY_TEMPLATES.get(
        bucket, _BUCKET_WHY_TEMPLATES[BUCKET_NEUTRAL],
    )
    return template.format(
        score=score,
        severe_flag_codes=", ".join(severe) if severe else "none",
        dq_penalty_codes=", ".join(dq_codes) if dq_codes else "none",
        exclusion_reason=row.get("inclusion_reason")
            or "the row failed the inclusion cascade.",
    )


def render_caveats(row: dict[str, Any]) -> list[str]:
    """Return unique caveat lines for the flags + penalties on a row.
    Order: flags first (preserved), then penalty codes not already
    seen via flags."""
    out: list[str] = []
    seen_codes: set[str] = set()
    for f in row.get("flags") or []:
        if f in seen_codes:
            continue
        line = caveat_for_flag(f)
        if line:
            out.append(line)
            seen_codes.add(f)
    for p in row.get("penalties") or []:
        code = p.get("code")
        if code and code in _FLAG_CAVEAT_LINES and code not in seen_codes:
            line = caveat_for_flag(code)
            if line:
                out.append(line)
                seen_codes.add(code)
    return out


def render_narrative(row: dict[str, Any]) -> dict[str, Any]:
    """Build the full deterministic narrative block for one row.
    Returns a dict the route layer surfaces verbatim — no LLM, no
    randomness, no probabilistic phrasing."""
    why = render_why(row)
    caveats = render_caveats(row)
    return {
        "id": row.get("id"),
        "bucket": row.get("bucket"),
        "bucket_label": row.get("bucket_label")
            or BUCKET_LABELS.get(str(row.get("bucket")), "Unknown bucket"),
        "underlying": row.get("underlying"),
        "rule_id": row.get("rule_id"),
        "as_of_date": row.get("as_of_date"),
        "total_score": row.get("total_score"),
        "qualified": row.get("qualified"),
        "rank_position": row.get("rank_position"),
        "why_it_appears": why,
        "caution_paragraph": CAUTION_PARAGRAPH,
        "caveats": caveats,
        "flags": list(row.get("flags") or []),
        "non_action_footer": REVIEW_CONTEXT_ONLY_FOOTER,
        "paper_only_reminder": PAPER_ONLY_REMINDER,
    }
