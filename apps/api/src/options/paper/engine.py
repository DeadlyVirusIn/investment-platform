"""Paper-trading lifecycle orchestrator (Phase 11E).

Open → Monitor (MTM) → Close OR Expire → Settle.

Writes only to options_paper_trade(_leg/_lifecycle/_expiration/_assignment).
NEVER writes to any non-`options_*` table.
NEVER reads from V2 / equity / governance tables.

Engine entry points:
  * open_trade(req)                  → creates trade + legs + FILLED event
  * record_mtm(trade_id, mtm_quotes) → emits MTM lifecycle event
  * close_trade(trade_id, close_quotes, reason) → fills exits, emits CLOSED
  * expire_trade(trade_id, settlement_price) → settlement payoff, ASSIGNED
                                              events for short ITM legs

All entry points are no-ops if `settings.OPTIONS_PAPER_ONLY` is False
or if the trade is in a terminal state. The kill-switch makes the
orchestrator inert for any non-paper environment.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.expiration import (
    ExpirationOutcome,
    LegExpirationOutcome,
    expire_legs,
)
from apps.api.src.options.paper.fills import (
    DEFAULT_FEE_PER_CONTRACT,
    FILL_MODEL_VERSION,
    FillResult,
    compute_entry_fill,
    compute_exit_fill,
    fees_for,
)
from apps.api.src.options.paper.pnl import (
    GreeksSnapshot,
    aggregate_greeks,
    trade_pnl_closed,
    trade_pnl_expired,
)
from apps.api.src.options.paper.strategies import (
    CONTRACT_MULTIPLIER,
    LegSpec,
    RiskMetrics,
    compute_risk,
    net_credit_dollars,
    validate_defined_risk,
)


# ---------------------------------------------------------------------------
# Domain dataclasses (engine-facing requests)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TradeRequest:
    underlying: str
    strategy_name: str
    strategy_version: str
    legs: tuple[LegSpec, ...]
    quotes_by_symbol: dict[str, OptionChainQuote]
    rationale_note: str | None = None


@dataclass(frozen=True)
class OpenResult:
    trade_id: int | None
    accepted: bool
    rejected_reasons: tuple[str, ...] = field(default_factory=tuple)
    entry_credit_dollars: Decimal | None = None
    fees_open_dollars: Decimal = Decimal("0")
    risk: RiskMetrics | None = None


# ---------------------------------------------------------------------------
# Status names mirror options_models.TRADE_STATUSES
# ---------------------------------------------------------------------------

STATUS_PROPOSED = "PROPOSED"
STATUS_OPEN     = "OPEN"
STATUS_EXPIRING = "EXPIRING"
STATUS_CLOSED   = "CLOSED"
STATUS_EXPIRED  = "EXPIRED"
STATUS_ASSIGNED = "ASSIGNED"

LIFECYCLE_FILLED          = "FILLED"
LIFECYCLE_MTM             = "MTM"
LIFECYCLE_EXPIRING_FLAG   = "EXPIRING_FLAGGED"
LIFECYCLE_PIN_RISK_FLAG   = "PIN_RISK_FLAGGED"
LIFECYCLE_EARLY_ASSIGN    = "EARLY_ASSIGN_RISK"
LIFECYCLE_CLOSED          = "CLOSED"
LIFECYCLE_EXPIRED         = "EXPIRED"
LIFECYCLE_ASSIGNED        = "ASSIGNED"

ASSIGN_EVT_ASSIGNED       = "ASSIGNED"


REJECT_KILL_SWITCH      = "OPTIONS_PAPER_ONLY_DISABLED"
REJECT_QUOTE_MISSING    = "QUOTE_MISSING"
REJECT_FILL_FAILED      = "FILL_REJECTED"
REJECT_NOT_DEFINED_RISK = "NOT_DEFINED_RISK"
REJECT_DUPLICATE        = "PROPOSAL_DUPLICATE"


def _kill_switch_blocks_writes() -> bool:
    """Engine is inert if either flag is False."""
    return not (
        getattr(settings, "OPTIONS_ENABLED", False)
        and getattr(settings, "OPTIONS_PAPER_ONLY", False)
    )


# ===========================================================================
# OPEN
# ===========================================================================

def open_trade(
    req: TradeRequest,
    *,
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
    session_factory=SessionLocal,
    now_utc: datetime.datetime | None = None,
    proposal_hash: str | None = None,
    session: Session | None = None,
) -> OpenResult:
    """Validate strategy shape → compute fills per leg → persist trade.

    When ``session`` is provided the inserts run inside the caller's
    transaction (the caller owns commit/rollback and any SAVEPOINT for
    duplicate handling); a unique ``proposal_hash`` violation surfaces via
    ``flush()`` so the caller's ``begin_nested()`` can catch it. When
    ``session`` is None the standalone path opens its own session, commits,
    and returns ``REJECT_DUPLICATE`` on a duplicate proposal_hash.
    """
    if _kill_switch_blocks_writes():
        return OpenResult(
            trade_id=None, accepted=False,
            rejected_reasons=(REJECT_KILL_SWITCH,),
        )

    try:
        validate_defined_risk(req.strategy_name, req.legs)
    except ValueError as exc:
        logger.warning("open_trade rejected — not defined risk: {}", exc)
        return OpenResult(
            trade_id=None, accepted=False,
            rejected_reasons=(REJECT_NOT_DEFINED_RISK, str(exc)),
        )

    fills: list[FillResult] = []
    rejects: list[str] = []
    for leg in req.legs:
        q = req.quotes_by_symbol.get(leg.option_symbol)
        if q is None:
            rejects.append(f"{REJECT_QUOTE_MISSING}:{leg.option_symbol}")
            continue
        # P6D.37C — role-aware entry OI floor: SELL (risk) legs keep the
        # strict 500; BUY (hedge wing) legs use the setting. Inert
        # default (500) reproduces the prior gate exactly. The selector
        # calls the SAME helper (P6D.12 parity).
        f = compute_entry_fill(
            q, side=leg.side,
            wing_min_oi=int(settings.OPTIONS_CANARY_WING_MIN_OI),
        )
        if not f.accepted:
            rejects.append(f"{REJECT_FILL_FAILED}:{leg.option_symbol}:{f.reason}")
        fills.append(f)
    if rejects:
        return OpenResult(
            trade_id=None, accepted=False,
            rejected_reasons=tuple(rejects),
        )

    entry_prices: list[Decimal] = [f.fill_price for f in fills]    # type: ignore[list-item]
    risk = compute_risk(req.strategy_name, req.legs, entry_prices)
    entry_credit = net_credit_dollars(req.legs, entry_prices)

    fees_open = sum(
        (fees_for(leg.qty, fee_per_contract=fee_per_contract)
         for leg in req.legs),
        start=Decimal("0"),
    )

    now = now_utc or datetime.datetime.now(datetime.timezone.utc)

    owns = session is None
    if owns:
        s = session_factory()
        try:
            trade_id = _open_trade_in_session(
                s, req=req, fills=fills, risk=risk,
                entry_credit=entry_credit, fees_open=fees_open,
                proposal_hash=proposal_hash, now=now,
            )
            s.commit()
        except IntegrityError:
            s.rollback()
            logger.warning(
                "open_trade rejected — duplicate proposal_hash={}", proposal_hash,
            )
            return OpenResult(
                trade_id=None, accepted=False,
                rejected_reasons=(REJECT_DUPLICATE,),
            )
        finally:
            s.close()
    else:
        # Injected session: caller owns the transaction. flush() inside
        # surfaces a unique proposal_hash violation NOW so the caller's
        # begin_nested() SAVEPOINT can roll it back. No commit here.
        trade_id = _open_trade_in_session(
            session, req=req, fills=fills, risk=risk,
            entry_credit=entry_credit, fees_open=fees_open,
            proposal_hash=proposal_hash, now=now,
        )

    logger.info(
        "open_trade: id={} strategy={} underlying={} legs={} credit={} max_loss={}",
        trade_id, req.strategy_name, req.underlying,
        len(req.legs), entry_credit, risk.max_loss_dollars,
    )
    return OpenResult(
        trade_id=trade_id, accepted=True,
        entry_credit_dollars=entry_credit,
        fees_open_dollars=fees_open,
        risk=risk,
    )


# ===========================================================================
# MTM
# ===========================================================================

def record_mtm(
    trade_id: int,
    *,
    quotes_by_symbol: dict[str, OptionChainQuote],
    leg_greeks: Sequence[GreeksSnapshot] | None = None,
    session_factory=SessionLocal,
    now_utc: datetime.datetime | None = None,
    session: Session | None = None,
) -> dict:
    """Append an MTM lifecycle event with current mids + aggregated Greeks.
    Pure observation — does NOT modify trade status or fills.

    When ``session`` is injected the event is written in the caller's
    transaction (no commit here); otherwise a standalone session is opened
    and committed.
    """
    if _kill_switch_blocks_writes():
        return {"accepted": False, "reason": REJECT_KILL_SWITCH}
    now = now_utc or datetime.datetime.now(datetime.timezone.utc)
    owns = session is None
    session = session if session is not None else session_factory()
    try:
        legs = _read_legs(session, trade_id)
        leg_specs = [_leg_to_spec(l) for l in legs]
        mtm_payload: dict = {"per_leg": []}
        for spec in leg_specs:
            q = quotes_by_symbol.get(spec.option_symbol)
            mid = q.mid if (q and q.mid is not None) else None
            mtm_payload["per_leg"].append({
                "option_symbol": spec.option_symbol,
                "mid": str(mid) if mid is not None else None,
            })
        if leg_greeks is not None:
            agg = aggregate_greeks(leg_specs, leg_greeks)
            mtm_payload["greeks"] = {
                "delta": str(agg.delta) if agg.delta is not None else None,
                "gamma": str(agg.gamma) if agg.gamma is not None else None,
                "theta": str(agg.theta) if agg.theta is not None else None,
                "vega":  str(agg.vega)  if agg.vega  is not None else None,
            }
        _insert_lifecycle_event(
            session, trade_id=trade_id, event_type=LIFECYCLE_MTM,
            triggered_by="SCHEDULED_JOB", payload=mtm_payload, now_utc=now,
        )
        if owns:
            session.commit()
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()
    return {"accepted": True, "trade_id": trade_id, "mtm": mtm_payload}


# ===========================================================================
# CLOSE (pre-expiry, manual or risk-driven)
# ===========================================================================

def close_trade(
    trade_id: int,
    *,
    quotes_by_symbol: dict[str, OptionChainQuote],
    reason: str = "OPERATOR_CLOSE",
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
    session_factory=SessionLocal,
    now_utc: datetime.datetime | None = None,
    session: Session | None = None,
) -> dict:
    if _kill_switch_blocks_writes():
        return {"accepted": False, "reason": REJECT_KILL_SWITCH}
    now = now_utc or datetime.datetime.now(datetime.timezone.utc)

    owns = session is None
    session = session if session is not None else session_factory()
    try:
        trade = _read_trade(session, trade_id)
        if trade.status in (STATUS_CLOSED, STATUS_EXPIRED, STATUS_ASSIGNED):
            return {"accepted": False, "reason": "TRADE_TERMINAL",
                    "status": trade.status}

        legs = _read_legs(session, trade_id)
        leg_specs = [_leg_to_spec(l) for l in legs]

        exit_fills: list[FillResult] = []
        for spec in leg_specs:
            q = quotes_by_symbol.get(spec.option_symbol)
            if q is None:
                return {"accepted": False, "reason": REJECT_QUOTE_MISSING,
                        "missing": spec.option_symbol}
            close_side = "BUY" if spec.side == "SELL" else "SELL"
            # P6D.37B — exits use the exit fillability profile (sanity
            # gates kept; OI + spread caps settings-parameterized).
            # Inert defaults reproduce the entry gate exactly. The
            # expiry settlement path (expire_trade) is quote-ungated
            # and untouched.
            f = compute_exit_fill(
                q, side=close_side,
                min_open_interest=int(settings.OPTIONS_EXIT_MIN_OI),
                max_spread_pct=Decimal(
                    str(settings.OPTIONS_EXIT_MAX_SPREAD_PCT)),
                max_spread_floor=Decimal(
                    str(settings.OPTIONS_EXIT_MAX_SPREAD_FLOOR_DOLLARS)),
            )
            if not f.accepted:
                return {"accepted": False, "reason": REJECT_FILL_FAILED,
                        "leg": spec.option_symbol, "fill_reason": f.reason}
            exit_fills.append(f)

        # PnL math
        entry_fills = [Decimal(str(l.entry_fill_price)) for l in legs]
        fees_close = sum(
            (fees_for(spec.qty, fee_per_contract=fee_per_contract)
             for spec in leg_specs),
            start=Decimal("0"),
        )
        fees_total = Decimal(str(trade.fees_total_dollars or 0)) + fees_close
        pnl = trade_pnl_closed(
            leg_specs, entry_fills,
            [f.fill_price for f in exit_fills],     # type: ignore[arg-type]
            fees_total_dollars=fees_total,
        )

        # Persist exit fills + updated trade row
        for spec_idx, (db_leg, f) in enumerate(zip(legs, exit_fills)):
            _update_leg_exit(
                session, leg_id=db_leg.id,
                exit_fill_price=f.fill_price,         # type: ignore[arg-type]
                exit_quote_at_utc=now, exit_reason=reason,
                quote=quotes_by_symbol[db_leg.option_symbol],
            )
        _update_trade_close(
            session, trade_id=trade_id,
            exit_debit_dollars=pnl.exit_debit_dollars,
            realized_pnl_dollars=pnl.realized_pnl_dollars,
            fees_total_dollars=fees_total,
            closed_at=now, status=STATUS_CLOSED,
        )
        _insert_lifecycle_event(
            session, trade_id=trade_id, event_type=LIFECYCLE_CLOSED,
            triggered_by="OPERATOR_API",
            payload={
                "reason": reason,
                "exit_debit_dollars": str(pnl.exit_debit_dollars),
                "realized_pnl_dollars": str(pnl.realized_pnl_dollars),
                "fees_total_dollars": str(fees_total),
            }, now_utc=now,
        )
        if owns:
            session.commit()
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()

    logger.info(
        "close_trade: id={} reason={} realized={}",
        trade_id, reason, pnl.realized_pnl_dollars,
    )
    return {
        "accepted": True, "trade_id": trade_id,
        "realized_pnl_dollars": str(pnl.realized_pnl_dollars),
        "exit_debit_dollars": str(pnl.exit_debit_dollars),
    }


# ===========================================================================
# EXPIRE (held to expiry settlement; v1 records assignment events but does
# NOT create synthetic equity positions)
# ===========================================================================

def expire_trade(
    trade_id: int,
    *,
    settlement_price: Decimal | None,
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
    session_factory=SessionLocal,
    now_utc: datetime.datetime | None = None,
    session: Session | None = None,
) -> dict:
    if _kill_switch_blocks_writes():
        return {"accepted": False, "reason": REJECT_KILL_SWITCH}
    now = now_utc or datetime.datetime.now(datetime.timezone.utc)

    owns = session is None
    session = session if session is not None else session_factory()
    try:
        trade = _read_trade(session, trade_id)
        if trade.status in (STATUS_CLOSED, STATUS_EXPIRED, STATUS_ASSIGNED):
            return {"accepted": False, "reason": "TRADE_TERMINAL",
                    "status": trade.status}

        legs = _read_legs(session, trade_id)
        leg_specs = [_leg_to_spec(l) for l in legs]

        outcome: ExpirationOutcome = expire_legs(
            leg_specs, settlement_price=settlement_price,
        )
        entry_fills = [Decimal(str(l.entry_fill_price)) for l in legs]
        # Fees: charge round-trip — opening fees already in trade.fees_total_dollars,
        # add the same per-contract fee per leg again at expiry to remove the
        # optimistic-expiry advantage (no zero-cost exit at expiration).
        fees_open = Decimal(str(trade.fees_total_dollars or 0))
        fees_close = sum(
            (fees_for(spec.qty, fee_per_contract=fee_per_contract)
             for spec in leg_specs),
            start=Decimal("0"),
        )
        fees_total = fees_open + fees_close
        payoffs = [
            (lo.payoff_dollars if lo.payoff_dollars is not None else Decimal("0"))
            for lo in outcome.legs
        ]
        pnl = trade_pnl_expired(
            leg_specs, entry_fills,
            settlement_payoffs_per_leg=payoffs,
            fees_total_dollars=fees_total,
        )

        for db_leg, lo in zip(legs, outcome.legs):
            _insert_expiration_event(
                session, trade_id=trade_id, leg_index=lo.leg_index,
                expiry_date=db_leg.expiry,
                underlying_settlement=settlement_price,
                classification=lo.classification,
                intrinsic_value_dollars=(
                    None if lo.intrinsic_value_per_contract is None else
                    lo.intrinsic_value_per_contract
                    * CONTRACT_MULTIPLIER * Decimal(db_leg.qty)
                ),
                realized_pnl_dollars=lo.payoff_dollars, now_utc=now,
            )

        # Assignment events for short ITM legs — v1 paper-only is a
        # SIMPLIFIED EXIT: assignment is treated as a TERMINAL event,
        # final payoff = intrinsic, no synthetic equity position is
        # created. This is recorded explicitly so audit + downstream
        # research can see the simplification was applied.
        any_assignment = False
        for db_leg, lo in zip(legs, outcome.legs):
            if lo.assigned:
                any_assignment = True
                _insert_assignment_event(
                    session, trade_id=trade_id, leg_index=lo.leg_index,
                    event_type=ASSIGN_EVT_ASSIGNED,
                    risk_level=("HIGH" if lo.classification == "PIN_RISK"
                                 else "MEDIUM"),
                    intrinsic_value_dollars=(
                        lo.intrinsic_value_per_contract
                        * CONTRACT_MULTIPLIER * Decimal(db_leg.qty)
                        if lo.intrinsic_value_per_contract else None
                    ),
                    realized_pnl_dollars=lo.payoff_dollars,
                    notes=(
                        "ASSIGNMENT_SIMPLIFIED_EXIT — v1 paper-only: "
                        "assignment treated as terminal; final payoff "
                        "taken at intrinsic; no synthetic equity "
                        "position created"
                    ),
                    now_utc=now,
                )

        # Final lifecycle event + status flip. Assignment is terminal.
        terminal_status = STATUS_ASSIGNED if any_assignment else STATUS_EXPIRED
        terminal_event  = LIFECYCLE_ASSIGNED if any_assignment else LIFECYCLE_EXPIRED
        _update_trade_close(
            session, trade_id=trade_id,
            exit_debit_dollars=None,
            realized_pnl_dollars=pnl.realized_pnl_dollars,
            fees_total_dollars=fees_total,
            closed_at=now, status=terminal_status,
        )
        _insert_lifecycle_event(
            session, trade_id=trade_id, event_type=terminal_event,
            triggered_by="EXPIRATION_HANDLER",
            payload={
                "settlement_price": (
                    str(settlement_price) if settlement_price is not None else None
                ),
                "realized_pnl_dollars": str(pnl.realized_pnl_dollars),
                "fees_total_dollars": str(fees_total),
                "fees_close_dollars": str(fees_close),
                "has_pin_risk": outcome.has_pin_risk,
                "has_assignment": outcome.has_assignment,
                "has_missing_data": outcome.has_missing_data,
                "flags": list(outcome.flags),
            }, now_utc=now,
        )
        if owns:
            session.commit()
    except Exception:
        if owns:
            session.rollback()
        raise
    finally:
        if owns:
            session.close()

    logger.info(
        "expire_trade: id={} status={} settlement={} realized={} flags={}",
        trade_id, terminal_status, settlement_price,
        pnl.realized_pnl_dollars, list(outcome.flags),
    )
    return {
        "accepted": True, "trade_id": trade_id,
        "status": terminal_status,
        "realized_pnl_dollars": str(pnl.realized_pnl_dollars),
        "fees_total_dollars": str(fees_total),
        "has_pin_risk": outcome.has_pin_risk,
        "has_assignment": outcome.has_assignment,
        "has_missing_data": outcome.has_missing_data,
        "flags": list(outcome.flags),
    }


# ===========================================================================
# Internal — DB helpers
# ===========================================================================

def _open_trade_in_session(
    session: Session,
    *,
    req: TradeRequest,
    fills: list[FillResult],
    risk: RiskMetrics,
    entry_credit: Decimal,
    fees_open: Decimal,
    proposal_hash: str | None,
    now: datetime.datetime,
) -> int:
    """Insert trade + legs + FILLED event in the given session, then flush
    so a unique proposal_hash violation raises IntegrityError immediately.
    No commit — caller owns the transaction boundary."""
    trade_id = _insert_trade_row(
        session,
        underlying=req.underlying,
        strategy_name=req.strategy_name,
        strategy_version=req.strategy_version,
        entry_credit_dollars=entry_credit,
        fees_open_dollars=fees_open,
        risk=risk,
        now_utc=now,
        proposal_hash=proposal_hash,
    )
    for idx, (leg, f, q) in enumerate(zip(req.legs, fills, [
        req.quotes_by_symbol[leg.option_symbol] for leg in req.legs
    ])):
        _insert_leg_row(
            session,
            trade_id=trade_id, leg_index=idx, leg=leg, quote=q,
            entry_fill_price=f.fill_price, now_utc=now,    # type: ignore[arg-type]
        )
    _insert_lifecycle_event(
        session, trade_id=trade_id, event_type=LIFECYCLE_FILLED,
        triggered_by="OPERATOR_API", payload={
            "entry_credit_dollars": str(entry_credit),
            "fees_open_dollars": str(fees_open),
            "fill_model_version": FILL_MODEL_VERSION,
            "rationale_note": req.rationale_note,
        }, now_utc=now,
    )
    session.flush()
    return trade_id


def _insert_trade_row(
    session: Session,
    *,
    underlying: str,
    strategy_name: str,
    strategy_version: str,
    entry_credit_dollars: Decimal,
    fees_open_dollars: Decimal,
    risk: RiskMetrics,
    now_utc: datetime.datetime,
    proposal_hash: str | None = None,
) -> int:
    row = session.execute(text(
        """
        INSERT INTO options_paper_trade (
            underlying, strategy_name, strategy_version,
            status, opened_at, entry_credit_dollars,
            fees_total_dollars, max_loss_dollars, max_profit_dollars,
            breakeven_lower, breakeven_upper,
            fill_model_version, paper_only, proposal_hash
        ) VALUES (
            :underlying, :strategy_name, :strategy_version,
            :status, :opened_at, :entry_credit_dollars,
            :fees_total_dollars, :max_loss_dollars, :max_profit_dollars,
            :breakeven_lower, :breakeven_upper,
            :fill_model_version, TRUE, :proposal_hash
        )
        RETURNING id
        """
    ), {
        "underlying": underlying,
        "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "status": STATUS_OPEN,
        "opened_at": now_utc,
        "entry_credit_dollars": entry_credit_dollars,
        "fees_total_dollars": fees_open_dollars,
        "max_loss_dollars": risk.max_loss_dollars,
        "max_profit_dollars": risk.max_profit_dollars,
        "breakeven_lower": risk.breakeven_lower,
        "breakeven_upper": risk.breakeven_upper,
        "fill_model_version": FILL_MODEL_VERSION,
        "proposal_hash": proposal_hash,
    }).one()
    return int(row.id)


def _insert_leg_row(
    session: Session,
    *,
    trade_id: int, leg_index: int, leg: LegSpec,
    quote: OptionChainQuote, entry_fill_price: Decimal,
    now_utc: datetime.datetime,
) -> None:
    session.execute(text(
        """
        INSERT INTO options_paper_trade_leg (
            trade_id, leg_index, option_symbol, underlying,
            expiry, strike, option_type, side, qty,
            entry_quote_at_utc, entry_bid, entry_ask, entry_mid,
            entry_iv, entry_delta, entry_gamma, entry_theta, entry_vega,
            entry_fill_price
        ) VALUES (
            :trade_id, :leg_index, :option_symbol, :underlying,
            :expiry, :strike, :option_type, :side, :qty,
            :entry_quote_at_utc, :entry_bid, :entry_ask, :entry_mid,
            :entry_iv, :entry_delta, :entry_gamma, :entry_theta, :entry_vega,
            :entry_fill_price
        )
        """
    ), {
        "trade_id": trade_id, "leg_index": leg_index,
        "option_symbol": leg.option_symbol,
        "underlying": quote.underlying,
        "expiry": leg.expiry,
        "strike": leg.strike,
        "option_type": leg.option_type,
        "side": leg.side, "qty": leg.qty,
        "entry_quote_at_utc": quote.snapshot_at_utc,
        "entry_bid": quote.bid, "entry_ask": quote.ask, "entry_mid": quote.mid,
        "entry_iv": quote.iv,
        "entry_delta": quote.delta, "entry_gamma": quote.gamma,
        "entry_theta": quote.theta, "entry_vega": quote.vega,
        "entry_fill_price": entry_fill_price,
    })


def _update_leg_exit(
    session: Session,
    *,
    leg_id: int, exit_fill_price: Decimal,
    exit_quote_at_utc: datetime.datetime,
    exit_reason: str, quote: OptionChainQuote,
) -> None:
    session.execute(text(
        """
        UPDATE options_paper_trade_leg
        SET exit_fill_price    = :exit_fill_price,
            exit_quote_at_utc  = :exit_quote_at_utc,
            exit_bid = :exit_bid, exit_ask = :exit_ask, exit_mid = :exit_mid,
            exit_iv  = :exit_iv,
            exit_delta = :exit_delta, exit_gamma = :exit_gamma,
            exit_theta = :exit_theta, exit_vega  = :exit_vega,
            exit_reason = :exit_reason
        WHERE id = :id
        """
    ), {
        "id": leg_id,
        "exit_fill_price": exit_fill_price,
        "exit_quote_at_utc": exit_quote_at_utc,
        "exit_bid": quote.bid, "exit_ask": quote.ask, "exit_mid": quote.mid,
        "exit_iv": quote.iv,
        "exit_delta": quote.delta, "exit_gamma": quote.gamma,
        "exit_theta": quote.theta, "exit_vega": quote.vega,
        "exit_reason": exit_reason,
    })


def _update_trade_close(
    session: Session,
    *,
    trade_id: int,
    exit_debit_dollars: Decimal | None,
    realized_pnl_dollars: Decimal | None,
    fees_total_dollars: Decimal,
    closed_at: datetime.datetime,
    status: str,
) -> None:
    session.execute(text(
        """
        UPDATE options_paper_trade
        SET status = :status,
            closed_at = :closed_at,
            exit_debit_dollars = :exit_debit_dollars,
            realized_pnl_dollars = :realized_pnl_dollars,
            fees_total_dollars = :fees_total_dollars
        WHERE id = :id
        """
    ), {
        "id": trade_id, "status": status, "closed_at": closed_at,
        "exit_debit_dollars": exit_debit_dollars,
        "realized_pnl_dollars": realized_pnl_dollars,
        "fees_total_dollars": fees_total_dollars,
    })


def _insert_lifecycle_event(
    session: Session, *, trade_id: int, event_type: str,
    triggered_by: str, payload: dict,
    now_utc: datetime.datetime,
) -> None:
    session.execute(text(
        """
        INSERT INTO options_trade_lifecycle_event
            (trade_id, event_type, event_at_utc, triggered_by, payload_json)
        VALUES
            (:trade_id, :event_type, :event_at_utc, :triggered_by,
             CAST(:payload_json AS jsonb))
        """
    ), {
        "trade_id": trade_id, "event_type": event_type,
        "event_at_utc": now_utc, "triggered_by": triggered_by,
        "payload_json": json.dumps(payload, default=str),
    })


def _insert_expiration_event(
    session: Session, *, trade_id: int, leg_index: int,
    expiry_date: datetime.date,
    underlying_settlement: Decimal | None,
    classification: str,
    intrinsic_value_dollars: Decimal | None,
    realized_pnl_dollars: Decimal | None,
    now_utc: datetime.datetime,
) -> None:
    session.execute(text(
        """
        INSERT INTO options_expiration_event
            (trade_id, leg_index, expiry_date,
             underlying_settlement, classification,
             intrinsic_value_dollars, realized_pnl_dollars,
             event_at_utc)
        VALUES
            (:trade_id, :leg_index, :expiry_date,
             :underlying_settlement, :classification,
             :intrinsic_value_dollars, :realized_pnl_dollars,
             :event_at_utc)
        """
    ), {
        "trade_id": trade_id, "leg_index": leg_index,
        "expiry_date": expiry_date,
        "underlying_settlement": underlying_settlement,
        "classification": classification,
        "intrinsic_value_dollars": intrinsic_value_dollars,
        "realized_pnl_dollars": realized_pnl_dollars,
        "event_at_utc": now_utc,
    })


def _insert_assignment_event(
    session: Session, *, trade_id: int, leg_index: int,
    event_type: str, risk_level: str | None,
    intrinsic_value_dollars: Decimal | None,
    realized_pnl_dollars: Decimal | None,
    notes: str, now_utc: datetime.datetime,
) -> None:
    session.execute(text(
        """
        INSERT INTO options_assignment_event
            (trade_id, leg_index, event_type, risk_level,
             intrinsic_value_dollars, realized_pnl_dollars,
             event_at_utc, notes)
        VALUES
            (:trade_id, :leg_index, :event_type, :risk_level,
             :intrinsic_value_dollars, :realized_pnl_dollars,
             :event_at_utc, :notes)
        """
    ), {
        "trade_id": trade_id, "leg_index": leg_index,
        "event_type": event_type, "risk_level": risk_level,
        "intrinsic_value_dollars": intrinsic_value_dollars,
        "realized_pnl_dollars": realized_pnl_dollars,
        "event_at_utc": now_utc, "notes": notes,
    })


def _read_trade(session: Session, trade_id: int):
    return session.execute(text(
        "SELECT id, status, fees_total_dollars FROM options_paper_trade "
        "WHERE id = :id"
    ), {"id": trade_id}).one()


def _read_legs(session: Session, trade_id: int):
    return session.execute(text(
        "SELECT id, trade_id, leg_index, option_symbol, underlying, "
        "       expiry, strike, option_type, side, qty, entry_fill_price "
        "FROM options_paper_trade_leg "
        "WHERE trade_id = :id "
        "ORDER BY leg_index"
    ), {"id": trade_id}).all()


def _leg_to_spec(db_leg) -> LegSpec:
    return LegSpec(
        side=db_leg.side, option_type=db_leg.option_type,
        strike=Decimal(str(db_leg.strike)), expiry=db_leg.expiry,
        qty=int(db_leg.qty), option_symbol=db_leg.option_symbol,
    )
