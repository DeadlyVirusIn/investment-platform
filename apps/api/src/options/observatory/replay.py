"""Scenario replay (Phase 11G).

For a given (symbol, as_of_date), reconstruct what the paper engine
would have OBSERVED:
  * latest accepted chain snapshot for that day
  * feature row for that day
  * rule eligibility per defined-risk strategy (with per-criterion
    pass/fail + reason text)
  * any paper trades in that underlying that opened, closed, expired,
    or were assigned within ±3 days of the as_of_date — for context

NEVER opens a trade. NEVER produces a recommendation. Output is
explicitly observational; UI surfaces an "Observation only" banner.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy.orm import Session

from apps.api.src.options.observatory.rules import (
    evaluate_rules,
    serialise_evaluation,
)
from apps.api.src.options.service_readonly import (
    get_chain,
    get_latest_features,
)
from apps.api.src.options.data.liquidity_filter import filter_chain
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from sqlalchemy import text


REPLAY_TRADE_WINDOW_DAYS = 3


def _to_quote(row) -> OptionChainQuote:
    return OptionChainQuote(
        snapshot_at_utc=row.snapshot_at_utc,
        underlying=row.underlying,
        expiry=row.expiry,
        strike=row.strike,
        option_type=row.option_type,
        option_symbol=row.option_symbol,
        bid=row.bid, ask=row.ask, mid=row.mid, last=row.last,
        volume=row.volume, open_interest=row.open_interest,
        delta=row.delta, gamma=row.gamma,
        theta=row.theta, vega=row.vega, iv=row.iv,
        quote_age_seconds=row.quote_age_seconds,
        provider=row.provider, provider_version=row.provider_version,
    )


def replay(
    session: Session,
    *,
    symbol: str,
    as_of_date: datetime.date,
) -> dict[str, Any]:
    """Reconstruct the engine's observation for one (symbol, day).

    Picks the chain at the LATEST snapshot for the day across ALL
    expiries, applies the same liquidity filter the engine would use,
    runs the rule evaluator, and returns:

        chain_summary, feature_row, rule_evaluations, nearby_trades,
        notice (observation-only), flags
    """
    rows = session.execute(text(
        """
        SELECT DISTINCT ON
           (underlying, expiry, strike, option_type)
           snapshot_at_utc, underlying, expiry, strike, option_type,
           option_symbol, bid, ask, mid, last,
           volume, open_interest,
           delta, gamma, theta, vega, iv,
           quote_age_seconds, provider, provider_version
        FROM options_chain_snapshot
        WHERE underlying = :symbol
          AND snapshot_at_utc::date = :as_of
        ORDER BY underlying, expiry, strike, option_type,
                 snapshot_at_utc DESC
        """
    ), {"symbol": symbol, "as_of": as_of_date}).all()

    raw_quotes = [_to_quote(r) for r in rows]
    accepted = list(filter_chain(raw_quotes).accepted)

    feature = get_latest_features(session, symbol=symbol)

    rule_evals = evaluate_rules(accepted, as_of=as_of_date)

    # Nearby trades: any trade in this underlying touching the window
    # via opened_at OR closed_at within ±REPLAY_TRADE_WINDOW_DAYS.
    nearby = session.execute(text(
        """
        SELECT id, strategy_name, status, opened_at, closed_at,
               realized_pnl_dollars
        FROM options_paper_trade
        WHERE underlying = :symbol
          AND (
              opened_at::date BETWEEN :lo AND :hi
              OR closed_at::date BETWEEN :lo AND :hi
          )
        ORDER BY COALESCE(opened_at, closed_at) DESC
        LIMIT 50
        """
    ), {
        "symbol": symbol,
        "lo": as_of_date - datetime.timedelta(days=REPLAY_TRADE_WINDOW_DAYS),
        "hi": as_of_date + datetime.timedelta(days=REPLAY_TRADE_WINDOW_DAYS),
    }).all()

    chain_summary = {
        "n_raw": len(raw_quotes),
        "n_accepted": len(accepted),
        "n_calls_accepted": sum(1 for q in accepted if q.option_type == "CALL"),
        "n_puts_accepted":  sum(1 for q in accepted if q.option_type == "PUT"),
        "expiries_accepted": sorted({q.expiry.isoformat() for q in accepted}),
    }

    flags: list[str] = []
    if not accepted:
        flags.append("NO_ACCEPTED_QUOTES")
    if feature is None:
        flags.append("NO_FEATURE_ROW")

    return {
        "symbol": symbol,
        "as_of_date": as_of_date.isoformat(),
        "chain_summary": chain_summary,
        "feature_row": feature,
        "rule_evaluations": [serialise_evaluation(e) for e in rule_evals],
        "nearby_trades": [
            {
                "id": int(r.id),
                "strategy_name": r.strategy_name,
                "status": r.status,
                "opened_at": r.opened_at.isoformat() if r.opened_at else None,
                "closed_at": r.closed_at.isoformat() if r.closed_at else None,
                "realized_pnl_dollars":
                    str(r.realized_pnl_dollars) if r.realized_pnl_dollars is not None else None,
            }
            for r in nearby
        ],
        "data_quality_flags": flags,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
    }
