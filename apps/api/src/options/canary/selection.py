"""Phase P6B.0 — canary candidate selection + TradeRequest building (read-only).

Replaces the P6A `_load_promotable_requests` seam. Selects promotable
SHORT_PUT_CREDIT_SPREAD candidates for the canary universe, deterministically
ranked, and builds engine TradeRequests priced from the latest chain
snapshot. Pure reads — opens its own short-lived session(s); never mutates.

Gated upstream: the promotion handler only calls this when
OPTIONS_CANARY_ENABLED is true. Filters mirror the funnel skip-reason
taxonomy (universe / strategy / DTE / confidence / chain availability).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.options.canary import positions as pos
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.engine import TradeRequest
from apps.api.src.options.paper.strategies import LegSpec

STRATEGY_VERSION = "canary-v1"


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def latest_chain_quotes(
    session: Session, symbols: list[str],
) -> dict[str, OptionChainQuote]:
    """Latest snapshot row per option_symbol → OptionChainQuote. Symbols
    absent from the chain are simply omitted (caller treats as unpriced)."""
    syms = sorted({s for s in symbols if s})
    if not syms:
        return {}
    rows = session.execute(text(
        """
        SELECT DISTINCT ON (option_symbol)
               option_symbol, snapshot_at_utc, underlying, expiry, strike,
               option_type, bid, ask, mid, last, volume, open_interest,
               delta, gamma, theta, vega, iv, quote_age_seconds,
               provider, provider_version
        FROM options_chain_snapshot
        WHERE option_symbol = ANY(:syms)
        ORDER BY option_symbol, snapshot_at_utc DESC
        """
    ), {"syms": syms}).mappings().all()
    out: dict[str, OptionChainQuote] = {}
    for r in rows:
        out[r["option_symbol"]] = OptionChainQuote(
            snapshot_at_utc=r["snapshot_at_utc"], underlying=r["underlying"],
            expiry=r["expiry"], strike=_dec(r["strike"]),
            option_type=r["option_type"], option_symbol=r["option_symbol"],
            bid=_dec(r["bid"]), ask=_dec(r["ask"]), mid=_dec(r["mid"]),
            last=_dec(r["last"]), volume=r["volume"],
            open_interest=r["open_interest"], delta=_dec(r["delta"]),
            gamma=_dec(r["gamma"]), theta=_dec(r["theta"]), vega=_dec(r["vega"]),
            iv=_dec(r["iv"]),
            quote_age_seconds=int(r["quote_age_seconds"] or 0),
            provider=r["provider"], provider_version=r["provider_version"],
        )
    return out


def settlement_price(session: Session, underlying: str) -> Decimal | None:
    """Latest daily close for the underlying (expiry settlement source)."""
    v = session.execute(text(
        "SELECT pb.close FROM price_bar pb JOIN asset a ON a.id = pb.asset_id "
        "WHERE a.symbol = :s ORDER BY pb.ts DESC LIMIT 1"
    ), {"s": underlying}).scalar()
    return _dec(v)


def _candidate_legs(session: Session, candidate_id: int) -> list[dict]:
    rows = session.execute(text(
        """
        SELECT role, side, option_type, strike, expiry, option_symbol, entry_mid
        FROM options_candidate_leg
        WHERE candidate_id = :cid
        ORDER BY role
        """
    ), {"cid": candidate_id}).mappings().all()
    return [dict(r) for r in rows]


def _build_request(
    *, underlying: str, strategy: str, legs_rows: list[dict],
    quotes: dict[str, OptionChainQuote],
) -> TradeRequest:
    legs = tuple(
        LegSpec(
            side=r["side"], option_type=r["option_type"],
            strike=Decimal(str(r["strike"])), expiry=r["expiry"],
            qty=1, option_symbol=r["option_symbol"],
        )
        for r in legs_rows
    )
    quotes_by_symbol = {r["option_symbol"]: quotes[r["option_symbol"]]
                        for r in legs_rows}
    return TradeRequest(
        underlying=underlying, strategy_name=strategy,
        strategy_version=STRATEGY_VERSION, legs=legs,
        quotes_by_symbol=quotes_by_symbol,
    )


def _load_promotable_requests(*, portfolio_id, run_date, session_factory):
    """Ranked, eligible (TradeRequest, proposal_hash) pairs for the canary.

    Filters: universe + strategy + DTE window + confidence + all legs priced
    in the latest chain. Deterministic order: confidence desc, composite desc,
    id asc. Liquidity is enforced downstream by the engine's compute_fill;
    here we only require a chain quote (mid) to exist for each leg."""
    universe = settings.OPTIONS_CANARY_UNIVERSE
    strategy = settings.OPTIONS_CANARY_STRATEGY
    min_dte = int(settings.OPTIONS_CANARY_MIN_DTE)
    max_dte = int(settings.OPTIONS_CANARY_MAX_DTE)
    min_conf = float(settings.OPTIONS_CANARY_MIN_CONFIDENCE)

    out: list[tuple[TradeRequest, str]] = []
    with session_factory() as s:
        cands = s.execute(text(
            """
            SELECT id, underlying, rule_id, confidence, composite_score
            FROM options_strategy_candidate
            WHERE underlying = :u AND rule_id = :strat
              AND run_date = :rd AND confidence >= :minc
            ORDER BY confidence DESC, composite_score DESC, id ASC
            """
        ), {"u": universe, "strat": strategy, "rd": run_date,
            "minc": min_conf}).mappings().all()

        for c in cands:
            legs_rows = _candidate_legs(s, c["id"])
            if not legs_rows or any(not lr["option_symbol"] for lr in legs_rows):
                continue   # legs not materialized → skip (no_chain_for_proposal)
            expiries = {lr["expiry"] for lr in legs_rows}
            if len(expiries) != 1:
                continue
            dte = (next(iter(expiries)) - run_date).days
            if not (min_dte <= dte <= max_dte):
                continue
            syms = [lr["option_symbol"] for lr in legs_rows]
            quotes = latest_chain_quotes(s, syms)
            if any(sym not in quotes or quotes[sym].mid is None for sym in syms):
                continue   # unpriced leg → skip
            req = _build_request(underlying=c["underlying"], strategy=strategy,
                                 legs_rows=legs_rows, quotes=quotes)
            phash = pos.proposal_hash(
                portfolio_id=portfolio_id, run_date=run_date,
                underlying=c["underlying"], strategy_name=strategy,
                strategy_version=STRATEGY_VERSION, legs=list(req.legs),
            )
            out.append((req, phash))

    logger.info(
        "canary selection: portfolio={} universe={} strategy={} eligible={}",
        portfolio_id, universe, strategy, len(out),
    )
    return out
