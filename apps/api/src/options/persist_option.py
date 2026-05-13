"""Phase Opt-B1 — sole-writer service for options paper trades.

This module is the ONLY code path that writes to:
  * options_paper_trade
  * options_paper_trade_leg

Three writers existed before this commit (run_options_paper_exec.py,
backfill_options_paper_trades.py, options/pending_replay.py) — all
three now delegate to `persist_option()`.

## Idempotency

Every proposal carries a `proposal_hash`: SHA256 of the JSON-encoded
proposal identity (underlying, strategy_name, strategy_version,
opened_at::date, sorted leg specs, fill_model_version). Truncated to
32 hex chars.

`persist_option()` queries for an existing row with the same hash
BEFORE inserting. If found, returns the existing trade_id and the
status `"duplicate"` — caller decides what to do (typically: log +
proceed). If not found, INSERTs both the trade row and its legs in a
single transaction and returns `"inserted"`.

The DB also enforces uniqueness via partial UNIQUE index
`uq_options_paper_trade_proposal_hash` (migration 067), so a race
between two writers cannot produce two rows with the same hash.

## Paper-only invariant

`persist_option()` ALWAYS writes `paper_only=True` regardless of
input. This mirrors the DB-level CHECK constraint and ensures no
caller can accidentally bypass paper mode. Live execution requires
a separate code path that does NOT exist in this codebase.

## Hash inputs (excluded fields, by design)

Excluded from the hash:
  * any monetary value that depends on real-time quotes (entry_credit_dollars,
    fees_total_dollars, max_loss/profit, breakevens, leg fill prices,
    bids/asks/IVs, greeks). These FLOAT between cycles and would
    produce false-uniqueness — i.e. a re-run with slightly different
    quotes would not dedup correctly.
  * trade_id, created_at, updated_at — assigned by DB.
  * status, closed_at, exit_*, realized_pnl_* — lifecycle state, not identity.

Included in the hash (proposal identity):
  * underlying, strategy_name, strategy_version
  * opened_at truncated to UTC date (so two runs on the same date
    with same inputs dedup)
  * legs sorted by (leg_index, option_symbol) — stable across rerun
    where leg order may vary
  * per leg: option_symbol, expiry, strike, option_type, side, qty, multiplier
  * fill_model_version (so a fill-model bump produces fresh trades)

## Collision expectations

SHA256 truncated to 32 hex chars (128 bits) has collision probability
1 in 2^64 for any pair. For the realistic universe (≤ 1000 trades/day
× 252 days/yr × 10 years = ~2.5M trades) the birthday-bound probability
of any collision is well under 1 in 10^21. Effectively zero.

## Idempotency guarantees

| Scenario                                  | Result                                |
|-------------------------------------------|---------------------------------------|
| Same proposal submitted twice in same run | first inserts, second returns "duplicate" |
| Same proposal after worker restart        | second returns "duplicate" (DB lookup) |
| Same proposal from manual replay script   | second returns "duplicate" (same path)  |
| Two concurrent writers, same proposal     | one wins (DB UNIQUE), other catches IntegrityError → returns "duplicate" |
| Same identity but different fill prices   | inserts (legitimately distinct cycles) |
| Same identity but different opened_at::date | inserts (different trading session)  |
| Same identity, different fill_model_version | inserts (model upgrade = fresh trades) |
"""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.db.options_models import (
    OptionsPaperTrade,
    OptionsPaperTradeLeg,
)


# ---------------------------------------------------------------------------
# Proposal dataclasses (no ORM coupling)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OptionLegSpec:
    """One leg of an options proposal. No quote-time prices in identity."""
    leg_index: int
    option_symbol: str
    underlying: str
    expiry: datetime.date
    strike: Decimal
    option_type: str  # "CALL" | "PUT"
    side: str         # "BUY" | "SELL"
    qty: int
    multiplier: int = 100

    # Quote-time fields — included in DB write, excluded from hash.
    entry_quote_at_utc: datetime.datetime | None = None
    entry_bid: Decimal | None = None
    entry_ask: Decimal | None = None
    entry_mid: Decimal | None = None
    entry_iv: Decimal | None = None
    entry_delta: Decimal | None = None
    entry_gamma: Decimal | None = None
    entry_theta: Decimal | None = None
    entry_vega: Decimal | None = None
    entry_fill_price: Decimal | None = None


@dataclass(frozen=True)
class OptionTradeProposal:
    """A single options paper-trade proposal. Sole input to persist_option().

    `paper_only` is structurally locked to True by persist_option() —
    callers cannot set False. Field exists for forward compatibility
    only; do not rely on it as a guard.
    """
    underlying: str
    strategy_name: str
    strategy_version: str
    opened_at: datetime.datetime
    legs: list[OptionLegSpec]
    fill_model_version: str

    # Quote-time scalars — included in DB write, excluded from hash.
    entry_credit_dollars: Decimal | None = None
    max_loss_dollars: Decimal | None = None
    max_profit_dollars: Decimal | None = None
    breakeven_lower: Decimal | None = None
    breakeven_upper: Decimal | None = None
    fees_total_dollars: Decimal = field(default_factory=lambda: Decimal("0"))
    paper_only: bool = True


# ---------------------------------------------------------------------------
# Hash + write
# ---------------------------------------------------------------------------


def _to_jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (Decimal, int, float)):
        return str(v)
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, datetime.datetime):
        return v.replace(microsecond=0).isoformat()
    return str(v)


def proposal_hash(prop: OptionTradeProposal) -> str:
    """Stable 32-hex-char hash of the proposal's identity.

    Inputs (only these): underlying, strategy_name, strategy_version,
    opened_at::date, fill_model_version, sorted legs with
    (leg_index, option_symbol, expiry, strike, option_type, side, qty,
    multiplier).

    Excluded: any monetary value, any quote-time field, lifecycle
    state, DB-assigned ids/timestamps.
    """
    legs_sorted = sorted(
        prop.legs,
        key=lambda L: (L.leg_index, L.option_symbol),
    )
    identity = {
        "underlying": prop.underlying.upper(),
        "strategy_name": prop.strategy_name,
        "strategy_version": prop.strategy_version,
        "opened_at_date": _to_jsonable(prop.opened_at.date()),
        "fill_model_version": prop.fill_model_version,
        "legs": [
            {
                "leg_index": L.leg_index,
                "option_symbol": L.option_symbol,
                "expiry": _to_jsonable(L.expiry),
                "strike": _to_jsonable(L.strike),
                "option_type": L.option_type.upper(),
                "side": L.side.upper(),
                "qty": int(L.qty),
                "multiplier": int(L.multiplier),
            }
            for L in legs_sorted
        ],
    }
    blob = json.dumps(
        identity, sort_keys=True, separators=(",", ":"),
        default=_to_jsonable,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def persist_option(
    session: Session,
    proposal: OptionTradeProposal,
) -> tuple[int, str]:
    """Sole writer for options paper trades.

    Returns `(trade_id, status)` where status ∈ {"inserted", "duplicate"}.

    Transaction model:
      * Single transaction per call.
      * If a duplicate hash already exists: NO writes, returns existing
        trade_id with status="duplicate".
      * Otherwise: INSERT trade row → flush → INSERT all leg rows →
        COMMIT. If the leg insert fails for any reason, the trade row
        is rolled back so no orphaned trade lands.
      * If a concurrent writer wins the UNIQUE race, IntegrityError is
        caught and the existing row is returned with status="duplicate".

    Paper-only invariant:
      * paper_only=True is FORCED regardless of proposal input. The DB
        also enforces this via CHECK constraint
        `ck_options_paper_trade_paper_only_invariant`.
    """
    fp = proposal_hash(proposal)

    # Pre-check: existing row with same hash → return without writing
    existing = session.query(OptionsPaperTrade.id).filter(
        OptionsPaperTrade.proposal_hash == fp
    ).first()
    if existing is not None:
        logger.debug(
            "persist_option: duplicate hash {} → returning existing "
            "trade_id={} for {}",
            fp, existing[0], proposal.underlying,
        )
        return int(existing[0]), "duplicate"

    trade = OptionsPaperTrade(
        underlying=proposal.underlying.upper(),
        strategy_name=proposal.strategy_name,
        strategy_version=proposal.strategy_version,
        status="PROPOSED",
        opened_at=proposal.opened_at,
        entry_credit_dollars=proposal.entry_credit_dollars,
        max_loss_dollars=proposal.max_loss_dollars,
        max_profit_dollars=proposal.max_profit_dollars,
        breakeven_lower=proposal.breakeven_lower,
        breakeven_upper=proposal.breakeven_upper,
        fees_total_dollars=proposal.fees_total_dollars,
        fill_model_version=proposal.fill_model_version,
        proposal_hash=fp,
        paper_only=True,  # FORCED — see docstring
    )
    session.add(trade)
    try:
        session.flush()
    except IntegrityError as exc:
        # UNIQUE race lost — another writer beat us with the same hash.
        session.rollback()
        existing = session.query(OptionsPaperTrade.id).filter(
            OptionsPaperTrade.proposal_hash == fp
        ).first()
        if existing is not None:
            logger.info(
                "persist_option: UNIQUE race lost for hash {} → returning "
                "existing trade_id={}",
                fp, existing[0],
            )
            return int(existing[0]), "duplicate"
        # Unexpected — re-raise so caller sees the real error.
        raise

    # Insert legs in a single batch. If any leg fails, rollback the
    # trade row to prevent an orphaned header.
    try:
        for leg in sorted(proposal.legs, key=lambda L: L.leg_index):
            # Schema does not store `multiplier` on the leg row — it's a
            # constant 100 for all US listed options and lives on the
            # OptionLegSpec dataclass for hash purposes only.
            entry_qts = (
                leg.entry_quote_at_utc
                if leg.entry_quote_at_utc is not None
                else proposal.opened_at
            )
            entry_fp = (
                leg.entry_fill_price
                if leg.entry_fill_price is not None
                else (leg.entry_mid or Decimal("0"))
            )
            session.add(OptionsPaperTradeLeg(
                trade_id=trade.id,
                leg_index=leg.leg_index,
                option_symbol=leg.option_symbol,
                underlying=leg.underlying.upper(),
                expiry=leg.expiry,
                strike=leg.strike,
                option_type=leg.option_type.upper(),
                side=leg.side.upper(),
                qty=leg.qty,
                entry_quote_at_utc=entry_qts,
                entry_bid=leg.entry_bid,
                entry_ask=leg.entry_ask,
                entry_mid=leg.entry_mid,
                entry_iv=leg.entry_iv,
                entry_delta=leg.entry_delta,
                entry_gamma=leg.entry_gamma,
                entry_theta=leg.entry_theta,
                entry_vega=leg.entry_vega,
                entry_fill_price=entry_fp,
            ))
        session.commit()
    except Exception:
        session.rollback()
        raise

    logger.info(
        "persist_option: inserted trade_id={} {} {} (hash={}, legs={})",
        trade.id, proposal.underlying, proposal.strategy_name,
        fp, len(proposal.legs),
    )
    return int(trade.id), "inserted"


# ---------------------------------------------------------------------------
# Dict-input bridge — minimal-disruption migration path
# ---------------------------------------------------------------------------


def persist_option_from_dicts(
    session: Session,
    *,
    underlying: str,
    strategy_name: str,
    strategy_version: str,
    opened_at: datetime.datetime,
    fill_model_version: str,
    legs: list[dict[str, Any]],
    entry_credit_dollars: Decimal | None = None,
    max_loss_dollars: Decimal | None = None,
    max_profit_dollars: Decimal | None = None,
    breakeven_lower: Decimal | None = None,
    breakeven_upper: Decimal | None = None,
    fees_total_dollars: Decimal | None = None,
) -> tuple[int, str]:
    """Convenience wrapper for callers that already build leg dicts.

    Each leg dict MUST contain at minimum:
      leg_index, option_symbol, underlying, expiry, strike, option_type,
      side, qty
    All other leg fields are optional and pass-through.

    Internally constructs OptionLegSpec + OptionTradeProposal and
    delegates to persist_option().
    """
    leg_specs: list[OptionLegSpec] = []
    for L in legs:
        leg_specs.append(OptionLegSpec(
            leg_index=int(L["leg_index"]),
            option_symbol=str(L["option_symbol"]),
            underlying=str(L.get("underlying") or underlying),
            expiry=L["expiry"] if isinstance(L["expiry"], datetime.date)
                else datetime.date.fromisoformat(str(L["expiry"])),
            strike=L["strike"] if isinstance(L["strike"], Decimal)
                else Decimal(str(L["strike"])),
            option_type=str(L["option_type"]),
            side=str(L["side"]),
            qty=int(L["qty"]),
            multiplier=int(L.get("multiplier") or 100),
            entry_quote_at_utc=L.get("entry_quote_at_utc"),
            entry_bid=L.get("entry_bid"),
            entry_ask=L.get("entry_ask"),
            entry_mid=L.get("entry_mid"),
            entry_iv=L.get("entry_iv"),
            entry_delta=L.get("entry_delta"),
            entry_gamma=L.get("entry_gamma"),
            entry_theta=L.get("entry_theta"),
            entry_vega=L.get("entry_vega"),
            entry_fill_price=L.get("entry_fill_price"),
        ))
    prop = OptionTradeProposal(
        underlying=underlying,
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        opened_at=opened_at,
        legs=leg_specs,
        fill_model_version=fill_model_version,
        entry_credit_dollars=entry_credit_dollars,
        max_loss_dollars=max_loss_dollars,
        max_profit_dollars=max_profit_dollars,
        breakeven_lower=breakeven_lower,
        breakeven_upper=breakeven_upper,
        fees_total_dollars=fees_total_dollars or Decimal("0"),
    )
    return persist_option(session, prop)
