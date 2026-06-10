"""Phase 3 — options promotion/rejection AUDIT (read-only, display-only).

Shows WHY option candidates were promoted or rejected per run_date by
re-deriving the canary selector's gates (universe / strategy / legs / DTE /
confidence / per-leg fillability) over `options_strategy_candidate` +
`options_candidate_leg`, alongside the engine's own
`options_execution_funnel` rows (slot_full / capital_cap / duplicate skips).

Gate values are read from REAL settings (OPTIONS_CANARY_UNIVERSE,
OPTIONS_CANARY_STRATEGY, OPTIONS_CANARY_MIN_DTE / MAX_DTE,
OPTIONS_CANARY_MIN_CONFIDENCE) and fillability reuses the REAL
`compute_fill` + `selection.latest_chain_quotes` — no duplicated thresholds.

The pure parts (`classify_candidate`, `aggregate_audit`) are split out for
unit testing with synthetic fixtures; the DB wrapper (`get_promotion_audit`)
only fetches rows. NO mutation, NO fill, NO lifecycle/canary/execution
change, NO accounting write. Honest: empty when no funnel rows AND no
candidates.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.options.canary import selection
from apps.api.src.options.canary.economics import assess_economics
from apps.api.src.options.paper.fills import compute_fill
from apps.api.src.options.paper.strategies import (
    LegSpec,
    compute_risk,
    net_credit_dollars,
)

# Newest-first rejected candidates returned to the UI are capped.
REJECTED_CAP = 100

# Classification reasons (selector-gate level). Engine-level skips
# (slot_full / capital_cap / duplicate) come from the funnel rows instead.
REASON_WRONG_UNDERLYING = "wrong_underlying"
REASON_WRONG_STRATEGY = "wrong_strategy"
REASON_NO_LEGS = "no_legs"
REASON_DTE_OUT_OF_RANGE = "dte_out_of_range"
REASON_CONFIDENCE_BELOW_GATE = "confidence_below_gate"
REASON_UNFILLABLE_LEG = "unfillable_leg"
REASON_UNECONOMIC = "uneconomic"          # P6D.33A — fails assess_economics
REASON_ELIGIBLE = "eligible"


def _iso(d: Any) -> Any:
    """Date → ISO string (passes through strings/None)."""
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def classify_candidate(
    cand: dict,
    *,
    universe: str,
    strategy: str,
    min_dte: int,
    max_dte: int,
    min_conf: float,
) -> str:
    """Pure: one rejection reason for a candidate, mirroring the REAL
    selector's gate order (selection._load_promotable_requests):
    underlying → strategy → legs → dte → confidence → fillability →
    economics (P6D.33A).

    'eligible' means the candidate passed every selector gate and would have
    been promotable; whether it was actually promoted (or skipped for
    slot_full / capital_cap / duplicate) is reported by the funnel row.
    """
    if cand.get("underlying") != universe:
        return REASON_WRONG_UNDERLYING
    if cand.get("rule_id") != strategy:
        return REASON_WRONG_STRATEGY
    if not cand.get("has_legs"):
        return REASON_NO_LEGS
    dte = cand.get("dte")
    if dte is None or not (min_dte <= dte <= max_dte):
        return REASON_DTE_OUT_OF_RANGE
    conf = cand.get("confidence")
    if conf is None or float(conf) < min_conf:
        return REASON_CONFIDENCE_BELOW_GATE
    if cand.get("legs_fillable") is False:
        return REASON_UNFILLABLE_LEG
    if cand.get("economics_viable") is False:
        return REASON_UNECONOMIC
    return REASON_ELIGIBLE


def aggregate_audit(
    funnel_rows: list[dict], candidates: list[dict],
) -> dict[str, Any]:
    """Pure aggregation. `candidates` are already classified (each dict
    carries a 'reason' key from classify_candidate) plus
    candidate_id / run_date / underlying / rule_id / confidence / dte.

    Honest-empty when there are no funnel rows AND no candidates.
    """
    if not funnel_rows and not candidates:
        return {
            "status": "empty",
            "runs": [],
            "rejected": [],
            "eligible_count": 0,
            "reason_counts": {},
        }

    runs = sorted(
        (
            {
                "run_date": _iso(r.get("run_date")),
                "candidates_total": int(r.get("candidates_total") or 0),
                "promoted": int(r.get("promoted") or 0),
                "filled": int(r.get("filled") or 0),
                "skip_slot_full": int(r.get("skip_slot_full") or 0),
                "skip_over_capital_cap": int(
                    r.get("skip_over_capital_cap") or 0),
                "skip_proposal_duplicate": int(
                    r.get("skip_proposal_duplicate") or 0),
                "skip_other": int(r.get("skip_other") or 0),
            }
            for r in funnel_rows
        ),
        key=lambda r: (r["run_date"] or ""),
        reverse=True,
    )

    reason_counts: dict[str, int] = {}
    for c in candidates:
        reason = c.get("reason") or "unknown"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    eligible_count = reason_counts.get(REASON_ELIGIBLE, 0)

    rejected = sorted(
        (
            {
                "candidate_id": c.get("candidate_id"),
                "run_date": _iso(c.get("run_date")),
                "underlying": c.get("underlying"),
                "strategy": c.get("rule_id"),
                "confidence": (
                    float(c["confidence"])
                    if c.get("confidence") is not None else None),
                "dte": c.get("dte"),
                "reason": c.get("reason"),
            }
            for c in candidates
            if c.get("reason") not in (REASON_ELIGIBLE, "promoted")
        ),
        key=lambda c: ((c["run_date"] or ""), c["candidate_id"] or 0),
        reverse=True,
    )[:REJECTED_CAP]

    return {
        "status": "live",
        "runs": runs,
        "rejected": rejected,
        "eligible_count": eligible_count,
        "reason_counts": reason_counts,
    }


def get_promotion_audit(
    session: Session, portfolio_id: str | None = None, days: int = 14,
) -> dict[str, Any]:
    """Read-only promotion/rejection audit over the last `days`.

    SELECT-only: funnel rows (per run_date, summed across canary portfolios
    unless one is pinned), strategy candidates + legs, latest chain quotes
    for fillability. No writes.
    """
    universe = settings.OPTIONS_CANARY_UNIVERSE
    strategy = settings.OPTIONS_CANARY_STRATEGY
    min_dte = int(settings.OPTIONS_CANARY_MIN_DTE)
    max_dte = int(settings.OPTIONS_CANARY_MAX_DTE)
    min_conf = float(settings.OPTIONS_CANARY_MIN_CONFIDENCE)

    where = ["run_date >= CURRENT_DATE - (:days)::int"]
    params: dict[str, Any] = {"days": days}
    if portfolio_id:
        where.append("portfolio_id = :pid")
        params["pid"] = portfolio_id
    funnel_rows = [dict(r) for r in session.execute(text(
        f"""
        SELECT run_date,
               SUM(candidates_total)        AS candidates_total,
               SUM(promoted)                AS promoted,
               SUM(filled)                  AS filled,
               SUM(skip_slot_full)          AS skip_slot_full,
               SUM(skip_over_capital_cap)   AS skip_over_capital_cap,
               SUM(skip_proposal_duplicate) AS skip_proposal_duplicate,
               SUM(skip_other)              AS skip_other
          FROM options_execution_funnel
         WHERE {' AND '.join(where)}
         GROUP BY run_date ORDER BY run_date DESC
        """
    ), params).mappings().all()]

    cand_rows = session.execute(text(
        """
        SELECT id, run_date, underlying, rule_id, confidence
          FROM options_strategy_candidate
         WHERE run_date >= CURRENT_DATE - (:days)::int
         ORDER BY run_date DESC, id ASC
        """
    ), {"days": days}).mappings().all()

    legs_by_cand: dict[int, list[dict]] = {}
    ids = [r["id"] for r in cand_rows]
    if ids:
        leg_rows = session.execute(text(
            """
            SELECT candidate_id, side, option_type, strike,
                   option_symbol, expiry
              FROM options_candidate_leg
             WHERE candidate_id = ANY(:ids)
             ORDER BY candidate_id, role
            """
        ), {"ids": ids}).mappings().all()
        for lr in leg_rows:
            legs_by_cand.setdefault(lr["candidate_id"], []).append(dict(lr))

    candidates: list[dict] = []
    for r in cand_rows:
        legs = legs_by_cand.get(r["id"], [])
        has_legs = bool(legs) and all(lr["option_symbol"] for lr in legs)
        dte = None
        if has_legs:
            expiries = [lr["expiry"] for lr in legs if lr["expiry"] is not None]
            if expiries:
                dte = (min(expiries) - r["run_date"]).days
        candidates.append({
            "candidate_id": r["id"],
            "run_date": r["run_date"],
            "underlying": r["underlying"],
            "rule_id": r["rule_id"],
            "confidence": (
                float(r["confidence"]) if r["confidence"] is not None
                else None),
            "dte": dte,
            "has_legs": has_legs,
            "legs": legs,
            "legs_fillable": None,
            "economics_viable": None,
        })

    # Fillability is checked ONLY for candidates that already pass every
    # cheap gate (universe/strategy/legs/dte/confidence) — same shape as the
    # real selector; keeps the chain lookup small.
    need_fill = [
        c for c in candidates
        if c["underlying"] == universe and c["rule_id"] == strategy
        and c["has_legs"] and c["dte"] is not None
        and min_dte <= c["dte"] <= max_dte
        and c["confidence"] is not None and c["confidence"] >= min_conf
    ]
    if need_fill:
        syms = sorted({
            lr["option_symbol"] for c in need_fill for lr in c["legs"]})
        quotes = selection.latest_chain_quotes(session, syms)
        for c in need_fill:
            c["legs_fillable"] = all(
                quotes.get(lr["option_symbol"]) is not None
                and compute_fill(
                    quotes[lr["option_symbol"]], side=lr["side"]).accepted
                for lr in c["legs"]
            )
            if not c["legs_fillable"]:
                continue
            # P6D.33A — re-derive the selector's economic viability gate
            # from the SAME conservative fills + half-spreads (pure math,
            # read-only). Malformed shapes stay unclassified (None).
            try:
                leg_specs = [
                    LegSpec(
                        side=lr["side"], option_type=lr["option_type"],
                        strike=Decimal(str(lr["strike"])), expiry=lr["expiry"],
                        qty=1, option_symbol=lr["option_symbol"],
                    )
                    for lr in c["legs"]
                ]
                fills = [
                    compute_fill(
                        quotes[lr["option_symbol"]], side=lr["side"]
                    ).fill_price
                    for lr in c["legs"]
                ]
                econ = assess_economics(
                    entry_credit=net_credit_dollars(leg_specs, fills),
                    max_loss=compute_risk(
                        strategy, leg_specs, fills).max_loss_dollars,
                    leg_half_spreads=[
                        (quotes[lr["option_symbol"]].ask
                         - quotes[lr["option_symbol"]].bid) / Decimal("2")
                        for lr in c["legs"]
                    ],
                    leg_qtys=[l.qty for l in leg_specs],
                    tp_pct=float(settings.OPTIONS_CANARY_TP_PCT),
                    min_credit_multiple=float(
                        settings.OPTIONS_CANARY_MIN_CREDIT_MULTIPLE),
                    min_net_reward_risk=float(
                        settings.OPTIONS_CANARY_MIN_NET_REWARD_RISK),
                )
                c["economics_viable"] = econ.viable
            except (ValueError, StopIteration):
                c["economics_viable"] = None

    for c in candidates:
        c["reason"] = classify_candidate(
            c, universe=universe, strategy=strategy,
            min_dte=min_dte, max_dte=max_dte, min_conf=min_conf)
        c.pop("legs", None)

    out = aggregate_audit(funnel_rows, candidates)
    out["gates"] = {
        "universe": universe,
        "strategy": strategy,
        "min_dte": min_dte,
        "max_dte": max_dte,
        "min_confidence": min_conf,
        "days": days,
    }
    return out
