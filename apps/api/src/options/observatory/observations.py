"""Strategy observations — historical, on-the-fly aggregation (Phase 11G).

For a given window, walk available chain snapshot dates and emit a
list of observation records (one per (date, symbol, rule)). Each
record reports whether the rule QUALIFIED at that point in time, plus
per-criterion checks. NEVER opens a trade.

Pure read. Computed on-demand from existing options_chain_snapshot +
options_feature_daily; no new persistence layer.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.data.liquidity_filter import filter_chain
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.observatory.rules import (
    evaluate_rules,
    serialise_evaluation,
)


DEFAULT_LIST_LIMIT = 50
DEFAULT_LOOKBACK_DAYS = 14


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


def _read_day(session: Session, *, symbol: str, day: datetime.date) -> list[OptionChainQuote]:
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
          AND snapshot_at_utc::date = :day
        ORDER BY underlying, expiry, strike, option_type,
                 snapshot_at_utc DESC
        """
    ), {"symbol": symbol, "day": day}).all()
    return [_to_quote(r) for r in rows]


def _observation_id(symbol: str, day: datetime.date, rule_id: str) -> str:
    """Stable, content-addressable id (no DB sequence needed)."""
    return f"{symbol}:{day.isoformat()}:{rule_id}"


def _decode_observation_id(obs_id: str) -> tuple[str, datetime.date, str] | None:
    parts = obs_id.split(":", 2)
    if len(parts) != 3:
        return None
    sym, day_s, rule_id = parts
    try:
        day = datetime.date.fromisoformat(day_s)
    except ValueError:
        return None
    return sym, day, rule_id


def list_observations(
    session: Session,
    *,
    underlying: str | None = None,
    qualified_only: bool = False,
    rule_id: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    limit: int = DEFAULT_LIST_LIMIT,
) -> dict[str, Any]:
    """Walk distinct (symbol, day) pairs in the lookback window and run
    `evaluate_rules` for each. Each (symbol, day, rule) tuple is one
    observation record."""
    cutoff = datetime.date.today() - datetime.timedelta(days=int(lookback_days))
    where = ["snapshot_at_utc::date >= :cutoff"]
    params: dict[str, Any] = {"cutoff": cutoff}
    if underlying is not None:
        where.append("underlying = :underlying")
        params["underlying"] = underlying
    where_sql = " AND ".join(where)

    pairs = session.execute(text(
        f"""
        SELECT DISTINCT underlying, snapshot_at_utc::date AS d
        FROM options_chain_snapshot
        WHERE {where_sql}
        ORDER BY underlying, d DESC
        """
    ), params).all()

    out: list[dict[str, Any]] = []
    for p in pairs:
        if len(out) >= limit:
            break
        quotes = _read_day(session, symbol=p.underlying, day=p.d)
        accepted = list(filter_chain(quotes).accepted)
        evals = evaluate_rules(accepted, as_of=p.d)
        for ev in evals:
            if rule_id is not None and ev.rule_id != rule_id:
                continue
            if qualified_only and not ev.qualified:
                continue
            obs_id = _observation_id(p.underlying, p.d, ev.rule_id)
            out.append({
                "id": obs_id,
                "underlying": p.underlying,
                "as_of_date": p.d.isoformat(),
                "rule_id": ev.rule_id,
                "rule_name": ev.name,
                "qualified": ev.qualified,
                "n_passed": ev.n_passed,
                "n_criteria": ev.n_criteria,
                "n_chain_accepted": len(accepted),
            })
            if len(out) >= limit:
                break

    return {
        "count": len(out),
        "observations": out,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
    }


def get_observation(
    session: Session, *, observation_id: str,
) -> dict[str, Any] | None:
    """Re-evaluate a single (symbol, day, rule) observation deterministically."""
    decoded = _decode_observation_id(observation_id)
    if decoded is None:
        return None
    sym, day, rule_id = decoded
    quotes = _read_day(session, symbol=sym, day=day)
    if not quotes:
        # No chain rows ingested on that day — observation does not exist.
        return None
    accepted = list(filter_chain(quotes).accepted)
    evals = evaluate_rules(accepted, as_of=day)
    selected = next((e for e in evals if e.rule_id == rule_id), None)
    if selected is None:
        return None
    return {
        "id": observation_id,
        "underlying": sym,
        "as_of_date": day.isoformat(),
        "n_chain_accepted": len(accepted),
        "evaluation": serialise_evaluation(selected),
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
    }
