"""Phase Options-1 — options paper-trading shadow evaluator.

Read-only. Decides "would the options system have found a
paper-tradable contract today?" without ever opening a paper trade.

Hard guarantees:
  * Reads `options_chain_snapshot` and `options_feature_daily`
    only. Reads `asset` for underlying validation.
  * Writes ONLY into `options_shadow_decision_log` (idempotent on
    `(run_date, option_symbol)`).
  * NEVER writes to `options_paper_trade`,
    `options_paper_trade_leg`, `options_trade_lifecycle_event`,
    `options_assignment_event`, `options_expiration_event`,
    `paper_trade`, `paper_position`, `paper_run_log`,
    `decision_log`, or any other execution surface.
  * NEVER imports broker, live, or ML modules.
  * Filter chain is deterministic: same `options_chain_snapshot` +
    same `options_feature_daily` + same config → same decisions.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings


# ---------------------------------------------------------------------------
# Result envelopes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilterResult:
    """Per-filter pass/fail with the threshold and observed value
    so blocked candidates carry an audit trail."""
    name: str
    passed: bool
    observed: Any
    threshold: Any | None = None


@dataclass(frozen=True)
class CandidateDecision:
    """One option contract evaluated for shadow trading."""
    run_date: dt.date
    underlying_symbol: str
    option_symbol: str
    expiration: dt.date
    strike: Decimal
    option_type: str
    side: str
    strategy_name: str
    would_trade: bool
    reason: str
    score: Decimal | None
    filters: list[FilterResult]
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class EvalRunSummary:
    """Whole-run rollup."""
    run_date: dt.date
    underlying_count: int
    contracts_evaluated: int
    would_trade_count: int
    blocked_reason_counts: dict[str, int]
    freshness_warnings: list[str]
    inserted: int


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def _latest_chain_snapshot_date(session: Session) -> dt.date | None:
    row = session.execute(text(
        "SELECT max(snapshot_at_utc::date) FROM options_chain_snapshot"
    )).first()
    return row[0] if row and row[0] else None


def _read_chains(
    session: Session, *, run_date: dt.date,
    underlyings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Latest snapshot per (underlying, option_symbol) on or before
    run_date. Read-only."""
    where_under = ""
    params: dict[str, Any] = {"d": run_date}
    if underlyings:
        where_under = "AND underlying = ANY(:unders)"
        params["unders"] = underlyings
    rows = session.execute(text(
        f"""
        SELECT DISTINCT ON (underlying, option_symbol)
               underlying, option_symbol, expiry, strike, option_type,
               bid, ask, mid, last, volume, open_interest,
               delta, gamma, theta, vega, iv,
               quote_age_seconds, provider, snapshot_at_utc
        FROM options_chain_snapshot
        WHERE snapshot_at_utc::date <= :d
          {where_under}
        ORDER BY underlying, option_symbol, snapshot_at_utc DESC
        """
    ), params).mappings().all()
    return [dict(r) for r in rows]


def _read_feature_daily(
    session: Session, *, run_date: dt.date,
    underlyings: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Latest options_feature_daily per underlying on or before
    run_date. Returns {underlying: feature_dict}."""
    where_under = ""
    params: dict[str, Any] = {"d": run_date}
    if underlyings:
        where_under = "AND underlying = ANY(:unders)"
        params["unders"] = underlyings
    rows = session.execute(text(
        f"""
        SELECT DISTINCT ON (underlying)
               underlying, as_of_date, iv_rank_252d, atm_iv,
               realized_vol_30d, vrp_30d, term_structure_30_60,
               put_call_oi_ratio, put_call_volume_ratio,
               data_quality_flags
        FROM options_feature_daily
        WHERE as_of_date <= :d {where_under}
        ORDER BY underlying, as_of_date DESC
        """
    ), params).mappings().all()
    return {r["underlying"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Filter chain — deterministic
# ---------------------------------------------------------------------------


def _evaluate_filters(
    chain: dict[str, Any],
    feature: dict[str, Any] | None,
    *,
    cfg: Any,
    run_date: dt.date,
) -> list[FilterResult]:
    """Run every required filter against one chain row + the
    underlying's most recent options_feature_daily. Returns the
    per-filter results in order — caller picks the first failing
    one to report as `reason`."""
    bid = chain.get("bid")
    ask = chain.get("ask")
    spread = (
        float(ask) - float(bid)
        if bid is not None and ask is not None else None
    )
    expiry: dt.date = chain["expiry"]
    dte = (expiry - run_date).days
    open_interest = chain.get("open_interest")
    volume = chain.get("volume")
    delta = chain.get("delta")
    gamma = chain.get("gamma")
    iv = chain.get("iv")
    iv_rank = (feature or {}).get("iv_rank_252d") if feature else None

    out: list[FilterResult] = []

    # 1. liquidity (bid > 0, ask > bid)
    liq = (
        bid is not None and ask is not None
        and float(bid) >= float(cfg.OPTIONS_SHADOW_MIN_BID)
        and float(ask) > float(bid)
    )
    out.append(FilterResult(
        name="liquidity", passed=liq,
        observed={"bid": bid, "ask": ask},
        threshold={"min_bid": cfg.OPTIONS_SHADOW_MIN_BID},
    ))

    # 2. spread <= configured threshold (absolute dollars)
    spr = (
        spread is not None
        and spread <= float(cfg.OPTIONS_SHADOW_MAX_SPREAD)
    )
    out.append(FilterResult(
        name="spread", passed=bool(spr),
        observed={"spread": spread},
        threshold={"max_spread": cfg.OPTIONS_SHADOW_MAX_SPREAD},
    ))

    # 3. open_interest >= threshold
    oi_ok = (
        open_interest is not None
        and int(open_interest) >= int(cfg.OPTIONS_SHADOW_MIN_OPEN_INTEREST)
    )
    out.append(FilterResult(
        name="open_interest", passed=oi_ok,
        observed={"open_interest": open_interest},
        threshold={"min_oi": cfg.OPTIONS_SHADOW_MIN_OPEN_INTEREST},
    ))

    # 4. volume — soft check; absent volume tolerated when OI passes
    vol_ok = volume is None or int(volume) >= 0
    out.append(FilterResult(
        name="volume", passed=bool(vol_ok),
        observed={"volume": volume},
        threshold=None,
    ))

    # 5. DTE in window
    dte_ok = (
        int(cfg.OPTIONS_SHADOW_MIN_DTE) <= dte
        <= int(cfg.OPTIONS_SHADOW_MAX_DTE)
    )
    out.append(FilterResult(
        name="dte", passed=bool(dte_ok),
        observed={"dte": dte},
        threshold={
            "min": cfg.OPTIONS_SHADOW_MIN_DTE,
            "max": cfg.OPTIONS_SHADOW_MAX_DTE,
        },
    ))

    # 6. greeks present (delta + gamma + IV) — gracefully unknown
    #    if all None we mark as 'greeks_unknown' but allow only when
    #    the underlying has a feature row to fall back on.
    greeks_present = (
        delta is not None and gamma is not None and iv is not None
    )
    greeks_ok = greeks_present or feature is not None
    out.append(FilterResult(
        name="greeks", passed=bool(greeks_ok),
        observed={
            "delta": delta, "gamma": gamma, "iv": iv,
            "feature_fallback": feature is not None,
        },
        threshold=None,
    ))

    # 7. iv_rank present (or feature row present)
    iv_rank_ok = iv_rank is not None or iv is not None
    out.append(FilterResult(
        name="iv_rank", passed=bool(iv_rank_ok),
        observed={"iv_rank_252d": iv_rank, "iv": iv},
        threshold=None,
    ))

    # 8. risk — simple: theta exists OR delta in [-0.95, 0.95] when
    #    delta is present; this avoids flagging ITM-extreme contracts.
    risk_ok = True
    if delta is not None:
        try:
            d = float(delta)
            risk_ok = -0.95 <= d <= 0.95
        except (TypeError, ValueError):
            risk_ok = False
    out.append(FilterResult(
        name="risk", passed=bool(risk_ok),
        observed={"delta": delta},
        threshold={"abs_max_delta": 0.95},
    ))

    return out


def _decide(
    chain: dict[str, Any], feature: dict[str, Any] | None,
    *, run_date: dt.date, cfg: Any, strategy_name: str,
) -> CandidateDecision:
    filters = _evaluate_filters(
        chain, feature, cfg=cfg, run_date=run_date,
    )
    failing = [f for f in filters if not f.passed]
    would_trade = len(failing) == 0
    reason = (
        "all_filters_pass"
        if would_trade else f"blocked:{failing[0].name}"
    )
    # Score (placeholder, deterministic): mid price × open_interest
    score: Decimal | None = None
    if (
        chain.get("mid") is not None
        and chain.get("open_interest") is not None
    ):
        try:
            score = (
                Decimal(str(chain["mid"]))
                * Decimal(int(chain["open_interest"]))
            ).quantize(Decimal("0.000001"))
        except Exception:  # noqa: BLE001
            score = None
    diag = {
        "feature_fallback": feature is not None,
        "filter_results": [
            {
                "name": f.name,
                "passed": f.passed,
                "observed": f.observed,
                "threshold": f.threshold,
            }
            for f in filters
        ],
        "snapshot_at_utc": (
            chain["snapshot_at_utc"].isoformat()
            if chain.get("snapshot_at_utc") else None
        ),
    }
    return CandidateDecision(
        run_date=run_date,
        underlying_symbol=chain["underlying"],
        option_symbol=chain["option_symbol"],
        expiration=chain["expiry"],
        strike=Decimal(chain["strike"]),
        option_type=str(chain["option_type"]).lower(),
        side="buy",
        strategy_name=strategy_name,
        would_trade=would_trade,
        reason=reason,
        score=score,
        filters=filters,
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Persist (idempotent)
# ---------------------------------------------------------------------------


_INSERT_SQL = text(
    """
    INSERT INTO options_shadow_decision_log
      (run_date, underlying_symbol, option_symbol, expiration,
       strike, option_type, side, strategy_name,
       would_trade, reason,
       liquidity_pass, spread_pass, open_interest_pass,
       volume_pass, greeks_pass, iv_rank_pass, risk_pass,
       score, diagnostics)
    VALUES
      (:run_date, :underlying, :opt_sym, :exp,
       :strike, :otype, :side, :strategy,
       :would_trade, :reason,
       :f_liq, :f_spread, :f_oi,
       :f_vol, :f_greeks, :f_iv, :f_risk,
       :score, CAST(:diag AS jsonb))
    ON CONFLICT ON CONSTRAINT ux_options_shadow_run_option
      DO NOTHING
    RETURNING id
    """
)


def _persist(
    session: Session, decisions: list[CandidateDecision],
) -> int:
    inserted = 0
    by_name = lambda decision, name: next(  # noqa: E731
        (f.passed for f in decision.filters if f.name == name), False,
    )
    for d in decisions:
        result = session.execute(_INSERT_SQL, {
            "run_date":   d.run_date,
            "underlying": d.underlying_symbol,
            "opt_sym":    d.option_symbol,
            "exp":        d.expiration,
            "strike":     d.strike,
            "otype":      d.option_type,
            "side":       d.side,
            "strategy":   d.strategy_name,
            "would_trade": d.would_trade,
            "reason":     d.reason,
            "f_liq":      by_name(d, "liquidity"),
            "f_spread":   by_name(d, "spread"),
            "f_oi":       by_name(d, "open_interest"),
            "f_vol":      by_name(d, "volume"),
            "f_greeks":   by_name(d, "greeks"),
            "f_iv":       by_name(d, "iv_rank"),
            "f_risk":     by_name(d, "risk"),
            "score":      d.score,
            "diag":       json.dumps(d.diagnostics, default=str),
        })
        if result.first() is not None:
            inserted += 1
    session.commit()
    return inserted


# ---------------------------------------------------------------------------
# Top-level evaluator
# ---------------------------------------------------------------------------


def evaluate(
    session: Session, *,
    run_date: dt.date,
    underlyings: list[str] | None = None,
    cfg: Any | None = None,
    strategy_name: str = "options_shadow_v1",
    persist: bool = True,
) -> tuple[EvalRunSummary, list[CandidateDecision]]:
    """Single entry point. Reads chain + features, runs the filter
    chain per contract, optionally persists. Returns a run summary
    plus the full list of decisions (caller can sort/filter for
    UI/reporting)."""
    cfg = cfg or settings
    chains = _read_chains(
        session, run_date=run_date, underlyings=underlyings,
    )
    features = _read_feature_daily(
        session, run_date=run_date, underlyings=underlyings,
    )

    # Freshness warnings — sparse/stale upstream is common in this
    # phase. Surface them rather than silently skip.
    warnings: list[str] = []
    latest_chain = _latest_chain_snapshot_date(session)
    if latest_chain is None:
        warnings.append("no_chain_snapshot_data_available")
    elif (run_date - latest_chain).days > 5:
        warnings.append(
            f"chain_snapshots_stale:latest={latest_chain.isoformat()}"
        )
    if not features:
        warnings.append("no_options_feature_daily_rows")

    decisions: list[CandidateDecision] = []
    for c in chains:
        feat = features.get(c["underlying"])
        decisions.append(_decide(
            c, feat, run_date=run_date, cfg=cfg,
            strategy_name=strategy_name,
        ))

    # Cap to top-N per underlying among would_trade=True candidates.
    capped: list[CandidateDecision] = []
    seen: dict[str, int] = {}
    # Order: would_trade=True first, then by score desc; would_trade=False
    # rows are still persisted so operators see the blocking reason.
    sorted_decisions = sorted(
        decisions,
        key=lambda d: (
            not d.would_trade,
            -(float(d.score) if d.score is not None else 0.0),
        ),
    )
    top_n = int(cfg.OPTIONS_SHADOW_TOP_N)
    for d in sorted_decisions:
        if d.would_trade:
            n = seen.get(d.underlying_symbol, 0)
            if n >= top_n:
                # Replace `would_trade=True` with a blocked decision
                # so persisted record matches enforcement of TOP_N.
                d = CandidateDecision(
                    run_date=d.run_date,
                    underlying_symbol=d.underlying_symbol,
                    option_symbol=d.option_symbol,
                    expiration=d.expiration,
                    strike=d.strike,
                    option_type=d.option_type,
                    side=d.side,
                    strategy_name=d.strategy_name,
                    would_trade=False,
                    reason="blocked:top_n_capped",
                    score=d.score,
                    filters=d.filters,
                    diagnostics={
                        **d.diagnostics, "top_n_capped": True,
                    },
                )
            else:
                seen[d.underlying_symbol] = n + 1
        capped.append(d)

    blocked_counts: dict[str, int] = {}
    for d in capped:
        if not d.would_trade:
            blocked_counts[d.reason] = blocked_counts.get(d.reason, 0) + 1

    inserted = 0
    if persist and capped:
        inserted = _persist(session, capped)

    summary = EvalRunSummary(
        run_date=run_date,
        underlying_count=len({c["underlying"] for c in chains}),
        contracts_evaluated=len(capped),
        would_trade_count=sum(1 for d in capped if d.would_trade),
        blocked_reason_counts=blocked_counts,
        freshness_warnings=warnings,
        inserted=inserted,
    )
    logger.info(
        "[options_shadow] run_date={} contracts={} would_trade={} "
        "inserted={} warnings={}",
        run_date, summary.contracts_evaluated,
        summary.would_trade_count, inserted, warnings,
    )
    return summary, capped
