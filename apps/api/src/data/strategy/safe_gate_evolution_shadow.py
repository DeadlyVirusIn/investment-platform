"""Phase 11X — safe gate-evolution shadow evaluator.

Read-only diagnostic. Evaluates whether a hypothetical "partial
gate" pilot WOULD have opened a paper trade on a date when the
production selector returned `engine=none, fire=False`. NEVER
modifies production state. NEVER writes to paper_trade,
paper_position, paper_run_log, candidate_idea, or any execution
surface.

Output is a single row per `run_date` in
`safe_gate_evolution_shadow`:

  * `would_trade = True`  → eligible buy in the top decile under
                            partial gate alignment; row carries
                            symbol/score/confidence.
  * `would_trade = False` → no eligible candidate (either gates 0/4,
                            price regime unfavorable, no top-decile
                            buy, or production already opened a
                            trade); row is summary-only.

Hard caps:
  * Max 1 shadow row per day (UNIQUE constraint enforces).
  * Hypothetical size multiplier frozen at 0.25.
  * Side frozen at "Buy" (no shorts in v1 shadow).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


PRODUCTION_GATE_NAMES: tuple[str, ...] = (
    "rates_calm", "vrp_supportive", "credit_stable",
    "liquidity_expanding",
)


HYPOTHETICAL_SIZE_MULTIPLIER = Decimal("0.25")


@dataclass(frozen=True)
class ShadowEvalResult:
    run_date: dt.date
    would_trade: bool
    symbol: str | None
    side: str | None
    composite_score: Decimal | None
    confidence: Decimal | None
    macro_favorable_count: int
    failed_macro_gates: list[str]
    price_regime: dict[str, Any]
    original_selector_reason: str | None
    shadow_reason: str
    hypothetical_size_multiplier: Decimal


# ---------------------------------------------------------------------------
# Read-only helpers
# ---------------------------------------------------------------------------


def _read_macro_gates(
    session: Session, run_date: dt.date,
) -> tuple[int, list[str]]:
    """Return (favorable_count, failed_gate_names) for the four
    production gates on the latest <= run_date row per gate name.
    Mirrors `scripts/run_paper_daily._read_gates_from_context_daily`
    semantics but read-only here."""
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (context_name)
                   context_name, value_bool
            FROM context_daily
            WHERE context_name = ANY(:names)
              AND as_of_date <= :run_date
              AND status = 'production'
            ORDER BY context_name, as_of_date DESC
            """
        ),
        {
            "names": list(PRODUCTION_GATE_NAMES),
            "run_date": run_date,
        },
    ).mappings().all()
    by_name = {r["context_name"]: bool(r["value_bool"]) for r in rows}
    favorable = sum(1 for n in PRODUCTION_GATE_NAMES if by_name.get(n))
    failed = [n for n in PRODUCTION_GATE_NAMES if not by_name.get(n)]
    return favorable, failed


def _read_regime(
    session: Session, run_date: dt.date,
) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT benchmark_symbol, market_trend, vol_regime,
                   sma50_over_sma200, realized_vol_20d, atr_pctile_1y
            FROM regime_snapshot WHERE as_of_date = :d
            """
        ),
        {"d": run_date},
    ).mappings().first()
    if row is None:
        return {}
    return {
        "benchmark_symbol": row["benchmark_symbol"],
        "market_trend": row["market_trend"],
        "vol_regime": row["vol_regime"],
        "sma50_above_sma200": bool(row["sma50_over_sma200"]),
        "realized_vol_20d": (
            float(row["realized_vol_20d"])
            if row["realized_vol_20d"] is not None else None
        ),
        "atr_pctile_1y": (
            float(row["atr_pctile_1y"])
            if row["atr_pctile_1y"] is not None else None
        ),
    }


def _price_regime_favorable(regime: dict[str, Any]) -> bool:
    if not regime:
        return False
    return (
        regime.get("market_trend") == "uptrend"
        and regime.get("vol_regime") in ("low", "normal")
        and bool(regime.get("sma50_above_sma200"))
    )


def _read_top_decile_buy_above_median(
    session: Session, run_date: dt.date,
) -> tuple[dict[str, Any] | None, str]:
    """Return (candidate_dict, blocked_reason). Selects the highest-
    composite_score Buy that is in the top decile of accepted buys
    AND whose confidence is at least the median accepted-buy
    confidence for the day. Returns (None, reason) when no candidate
    qualifies."""
    accepted = session.execute(
        text(
            """
            SELECT c.id, a.symbol, c.composite_score, c.confidence
            FROM candidate_idea c JOIN asset a ON a.id = c.asset_id
            WHERE c.as_of_date = :d
              AND c.status = 'accepted'
              AND c.action = 'Buy'
            ORDER BY c.composite_score DESC NULLS LAST
            """
        ),
        {"d": run_date},
    ).mappings().all()
    if not accepted:
        return None, "no_accepted_buys"

    # Confidence median over accepted buys (deterministic).
    confs = sorted(
        [float(r["confidence"]) for r in accepted if r["confidence"] is not None]
    )
    if not confs:
        return None, "no_confidence_data"
    n = len(confs)
    median_conf = (
        confs[n // 2] if n % 2 == 1
        else (confs[n // 2 - 1] + confs[n // 2]) / 2
    )

    # Top-decile cutoff over composite_score (deterministic). Use
    # ceil(n/10) to keep at least 1 candidate eligible when n>=1.
    top_decile_size = max(1, (n + 9) // 10)
    top_decile = accepted[:top_decile_size]

    for cand in top_decile:
        if cand["confidence"] is None:
            continue
        if float(cand["confidence"]) >= median_conf:
            return (
                {
                    "symbol": cand["symbol"],
                    "composite_score": cand["composite_score"],
                    "confidence": cand["confidence"],
                },
                "ok",
            )
    return None, "top_decile_below_median_confidence"


def _production_opened_trade(
    session: Session, run_date: dt.date,
) -> bool:
    """Returns True if any production paper trade was opened on
    run_date. Reads paper_trade_log (strict-engine path) and
    paper_trade (auto-trader path); ignores closes. Resilient to
    missing tables (e.g., test schemas where paper_trade_log is not
    materialized)."""
    from sqlalchemy.exc import ProgrammingError

    n_strict = 0
    n_auto = 0
    try:
        n_strict = int(session.execute(
            text(
                "SELECT count(*) FROM paper_trade_log "
                "WHERE entry_date = :d AND action IN ('Buy','BUY','OPEN')"
            ),
            {"d": run_date},
        ).scalar_one() or 0)
    except ProgrammingError:
        session.rollback()
    try:
        n_auto = int(session.execute(
            text(
                "SELECT count(*) FROM paper_trade "
                "WHERE fill_ts::date = :d AND side = 'buy'"
            ),
            {"d": run_date},
        ).scalar_one() or 0)
    except ProgrammingError:
        session.rollback()
    return n_strict > 0 or n_auto > 0


def _read_selector_reason(
    session: Session, run_date: dt.date,
) -> str | None:
    """Most recent decision_log.reason for run_date. Resilient to
    missing decision_log table (e.g., test schemas that don't
    materialize raw-SQL tables)."""
    from sqlalchemy.exc import ProgrammingError

    try:
        row = session.execute(
            text(
                """
                SELECT reason FROM decision_log
                WHERE as_of_date = :d
                ORDER BY decision_ts DESC
                LIMIT 1
                """
            ),
            {"d": run_date},
        ).mappings().first()
        return row["reason"] if row else None
    except ProgrammingError:
        session.rollback()
        return None


# ---------------------------------------------------------------------------
# Top-level evaluator
# ---------------------------------------------------------------------------


def evaluate(
    session: Session, run_date: dt.date,
) -> ShadowEvalResult:
    """Pure-fn evaluation. Read-only. Returns a ShadowEvalResult; the
    persister (separate function) writes one row to
    safe_gate_evolution_shadow."""
    favorable, failed_gates = _read_macro_gates(session, run_date)
    regime = _read_regime(session, run_date)
    selector_reason = _read_selector_reason(session, run_date)

    base = {
        "run_date": run_date,
        "macro_favorable_count": favorable,
        "failed_macro_gates": failed_gates,
        "price_regime": regime,
        "original_selector_reason": selector_reason,
        "hypothetical_size_multiplier": HYPOTHETICAL_SIZE_MULTIPLIER,
    }

    # Hard cap 1: favorable=0 → summary only, no shadow candidate.
    if favorable == 0:
        return ShadowEvalResult(
            **base,
            would_trade=False,
            symbol=None, side=None,
            composite_score=None, confidence=None,
            shadow_reason="macro_favorable_count_zero",
        )

    # Production must have stayed flat — by construction the shadow
    # only fires on production-flat days. If a real trade opened we
    # record summary-only.
    if _production_opened_trade(session, run_date):
        return ShadowEvalResult(
            **base,
            would_trade=False,
            symbol=None, side=None,
            composite_score=None, confidence=None,
            shadow_reason="production_trade_opened",
        )

    # Spec: at least one of rates_calm or credit_stable must be True.
    if not (
        "rates_calm" not in failed_gates
        or "credit_stable" not in failed_gates
    ):
        return ShadowEvalResult(
            **base,
            would_trade=False,
            symbol=None, side=None,
            composite_score=None, confidence=None,
            shadow_reason="neither_rates_calm_nor_credit_stable",
        )

    if not _price_regime_favorable(regime):
        return ShadowEvalResult(
            **base,
            would_trade=False,
            symbol=None, side=None,
            composite_score=None, confidence=None,
            shadow_reason="price_regime_unfavorable",
        )

    cand, why = _read_top_decile_buy_above_median(session, run_date)
    if cand is None:
        return ShadowEvalResult(
            **base,
            would_trade=False,
            symbol=None, side=None,
            composite_score=None, confidence=None,
            shadow_reason=f"no_eligible_buy:{why}",
        )

    return ShadowEvalResult(
        **base,
        would_trade=True,
        symbol=cand["symbol"],
        side="Buy",
        composite_score=cand["composite_score"],
        confidence=cand["confidence"],
        shadow_reason="eligible_top_decile_buy_above_median_confidence",
    )


# ---------------------------------------------------------------------------
# Persister — INSERT ON CONFLICT DO NOTHING
# ---------------------------------------------------------------------------


def upsert_shadow(
    session: Session, result: ShadowEvalResult,
) -> bool:
    """Insert one row into safe_gate_evolution_shadow. Idempotent
    via UNIQUE (run_date) — re-running for the same date is a
    no-op. Returns True when a new row landed, False otherwise."""
    import json

    out = session.execute(
        text(
            """
            INSERT INTO safe_gate_evolution_shadow
              (run_date, symbol, side, composite_score, confidence,
               macro_favorable_count, failed_macro_gates,
               price_regime, original_selector_reason, shadow_reason,
               hypothetical_size_multiplier, would_trade)
            VALUES
              (:run_date, :symbol, :side, :score, :conf,
               :favorable, CAST(:failed AS jsonb),
               CAST(:regime AS jsonb), :sel_reason, :shadow_reason,
               :size_mult, :would_trade)
            ON CONFLICT ON CONSTRAINT ux_safe_gate_evolution_shadow_run_date
              DO NOTHING
            RETURNING id
            """
        ),
        {
            "run_date": result.run_date,
            "symbol": result.symbol,
            "side": result.side,
            "score": result.composite_score,
            "conf": result.confidence,
            "favorable": result.macro_favorable_count,
            "failed": json.dumps(result.failed_macro_gates),
            "regime": json.dumps(result.price_regime, default=str),
            "sel_reason": result.original_selector_reason,
            "shadow_reason": result.shadow_reason,
            "size_mult": result.hypothetical_size_multiplier,
            "would_trade": result.would_trade,
        },
    ).first()
    session.commit()
    return out is not None


def evaluate_and_persist(
    session: Session, run_date: dt.date,
) -> tuple[ShadowEvalResult, bool]:
    """Evaluate + upsert in one call. Returns (result, inserted)."""
    result = evaluate(session, run_date)
    inserted = upsert_shadow(session, result)
    return result, inserted
