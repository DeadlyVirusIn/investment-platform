"""Phase Opt-B2 — Options paper-trade lifecycle state machine.

This module is the SOLE gateway for status mutations on
options_paper_trade rows. Every transition is:

  * Validated (allowed FROM-state required)
  * Idempotent (calling twice with same evidence is safe)
  * Replay-safe (same event_at_utc + event_type is no-op-on-conflict)
  * Monotonic (no backward transitions; terminal states are sinks)
  * Transactional (single commit per call; rolls back on any failure)
  * Event-sourced (every transition emits options_trade_lifecycle_event
    + a typed event row when applicable)

Allowed transitions:

    PROPOSED ──FILL──> OPEN
                       │
                       ├──CLOSE────> CLOSED
                       ├──EXPIRE───> EXPIRED
                       └──ASSIGN───> ASSIGNED   (ITM short legs)

Terminal states (CLOSED, EXPIRED, ASSIGNED) accept NO further
transitions. Calling a transition function on a terminal row raises
TerminalStateError.

## Assignment precedence

When `transition_to_expired()` is called against a trade containing
SHORT legs that are ITM at settlement, the function REJECTS with
AssignmentPrecedenceError. The caller must call
`transition_to_assigned()` instead. This mirrors market reality
(ITM short options get assigned, not expired worthless).

## Discipline

This module does NOT:
  * trigger paper exec
  * activate scheduler jobs
  * mutate OPTIONS_ENABLED
  * read or write market chains
  * call any provider (ThetaData / Polygon / Tiingo)
  * do same-bar execution
  * touch any non-options table

It is a pure state machine. The caller (Phase Opt-B3 cron-driven
runner, or Phase Opt-A operator-triggered API endpoint) owns all
data fetching + evidence assembly.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.db.options_models import (
    OptionsPaperTrade,
    OptionsPaperTradeLeg,
)


# ---------------------------------------------------------------------------
# State constants
# ---------------------------------------------------------------------------

PROPOSED = "PROPOSED"
OPEN = "OPEN"
EXPIRING = "EXPIRING"
CLOSED = "CLOSED"
EXPIRED = "EXPIRED"
ASSIGNED = "ASSIGNED"

TERMINAL_STATES: frozenset[str] = frozenset({CLOSED, EXPIRED, ASSIGNED})

# Allowed (FROM, EVENT) → TO map. Every transition path is exhaustively
# enumerated here. Anything not in this dict is REJECTED loudly.
ALLOWED_TRANSITIONS: dict[tuple[str, str], str] = {
    (PROPOSED, "FILL"):     OPEN,
    (OPEN,     "CLOSE"):    CLOSED,
    (OPEN,     "EXPIRE"):   EXPIRED,
    (OPEN,     "ASSIGN"):   ASSIGNED,
    # Idempotent no-ops (caller may retry safely):
    (OPEN,     "FILL"):     OPEN,        # repeated open attempt
    (CLOSED,   "CLOSE"):    CLOSED,      # repeated close attempt
    (EXPIRED,  "EXPIRE"):   EXPIRED,     # repeated expire attempt
    (ASSIGNED, "ASSIGN"):   ASSIGNED,    # repeated assign attempt
}

# Reason codes (lifecycle event payload)
REASON_FILL = "fill"
REASON_TARGET_HIT = "target_hit"
REASON_STOP_HIT = "stop_hit"
REASON_OPERATOR_CLOSE = "operator_close"
REASON_FORCE_CLOSE = "force_close"
REASON_EXPIRY_OTM = "expired_otm"
REASON_EXPIRY_PIN_RISK = "expired_pin_risk"
REASON_ASSIGNED_ITM = "assigned_itm"
REASON_ASSIGNED_EARLY = "assigned_early"

# Triggered-by values (must match DB CHECK constraint)
TRIGGERED_BY_OPERATOR_API = "OPERATOR_API"
TRIGGERED_BY_SCHEDULED_JOB = "SCHEDULED_JOB"
TRIGGERED_BY_EXPIRATION_HANDLER = "EXPIRATION_HANDLER"
TRIGGERED_BY_ASSIGNMENT_HANDLER = "ASSIGNMENT_HANDLER"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LifecycleError(Exception):
    """Base class for all lifecycle errors. Caller MUST handle these
    explicitly; never silent-catch."""


class TradeNotFoundError(LifecycleError):
    """Trade ID does not exist in options_paper_trade."""


class InvalidTransitionError(LifecycleError):
    """Requested transition is not in ALLOWED_TRANSITIONS."""


class TerminalStateError(LifecycleError):
    """Trade is in a terminal state and accepts no further transitions."""


class MissingEvidenceError(LifecycleError):
    """Required evidence (fill / close / expiration / assignment) is
    missing or malformed."""


class AssignmentPrecedenceError(LifecycleError):
    """transition_to_expired() refused because the trade has SHORT legs
    that are ITM at settlement. Caller must use transition_to_assigned()
    instead."""


class InvariantViolationError(LifecycleError):
    """Catch-all for unexpected state — leg count mismatch, missing
    required column, etc. Should never fire in practice; if it does,
    the caller has built malformed evidence."""


# ---------------------------------------------------------------------------
# Evidence dataclasses (caller assembles + passes to transition fn)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LegFillEvidence:
    leg_index: int
    fill_price: Decimal


@dataclass(frozen=True)
class FillEvidence:
    """Required to transition PROPOSED → OPEN."""
    fill_at_utc: datetime.datetime
    chain_snapshot_id: int | None
    legs: list[LegFillEvidence]
    triggered_by: str = TRIGGERED_BY_OPERATOR_API


@dataclass(frozen=True)
class LegCloseEvidence:
    leg_index: int
    close_price: Decimal


@dataclass(frozen=True)
class CloseEvidence:
    """Required to transition OPEN → CLOSED."""
    close_at_utc: datetime.datetime
    reason: str  # one of REASON_TARGET_HIT, REASON_STOP_HIT, etc.
    chain_snapshot_id: int | None
    exit_debit_dollars: Decimal | None
    realized_pnl_dollars: Decimal | None
    legs: list[LegCloseEvidence]
    triggered_by: str = TRIGGERED_BY_OPERATOR_API


@dataclass(frozen=True)
class LegExpirationEvidence:
    leg_index: int
    # classification ∈ OTM | ITM | PIN_RISK | MISSING_DATA
    classification: str
    intrinsic_value_dollars: Decimal | None
    realized_pnl_dollars: Decimal | None


@dataclass(frozen=True)
class ExpirationEvidence:
    """Required to transition OPEN → EXPIRED."""
    expiry_date: datetime.date
    settlement_at_utc: datetime.datetime
    underlying_settlement: Decimal | None
    legs: list[LegExpirationEvidence]
    triggered_by: str = TRIGGERED_BY_EXPIRATION_HANDLER


@dataclass(frozen=True)
class LegAssignmentEvidence:
    leg_index: int
    # event_type ∈ ASSIGNED | EXERCISED
    event_type: str
    risk_level: str | None  # LOW | MEDIUM | HIGH
    intrinsic_value_dollars: Decimal | None
    realized_pnl_dollars: Decimal | None
    notes: str = ""


@dataclass(frozen=True)
class AssignmentEvidence:
    """Required to transition OPEN → ASSIGNED."""
    assigned_at_utc: datetime.datetime
    legs: list[LegAssignmentEvidence]
    triggered_by: str = TRIGGERED_BY_ASSIGNMENT_HANDLER


# ---------------------------------------------------------------------------
# TransitionResult — return value of every transition fn
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionResult:
    trade_id: int
    from_status: str
    to_status: str
    event_id: int | None       # None when idempotent no-op (no event written)
    is_idempotent: bool
    note: str                  # short human-readable reason


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _select_trade_for_update(session: Session, trade_id: int) -> OptionsPaperTrade:
    """Acquire a row-level lock on the trade for the transaction."""
    trade = session.execute(
        select(OptionsPaperTrade)
        .where(OptionsPaperTrade.id == trade_id)
        .with_for_update()
    ).scalar_one_or_none()
    if trade is None:
        raise TradeNotFoundError(f"trade_id={trade_id} not found")
    return trade


def _validate_transition(from_status: str, event: str) -> str:
    """Return the target state for (FROM, EVENT). Raise if not allowed."""
    key = (from_status, event)
    if key not in ALLOWED_TRANSITIONS:
        if from_status in TERMINAL_STATES:
            raise TerminalStateError(
                f"trade is in terminal state {from_status}; "
                f"event {event} rejected"
            )
        raise InvalidTransitionError(
            f"transition not allowed: from={from_status} event={event}. "
            f"Allowed events from {from_status}: "
            f"{[e for (f, e) in ALLOWED_TRANSITIONS if f == from_status]}"
        )
    return ALLOWED_TRANSITIONS[key]


def _emit_lifecycle_event(
    session: Session,
    *,
    trade_id: int,
    event_type: str,
    triggered_by: str,
    event_at_utc: datetime.datetime,
    payload: dict[str, Any],
) -> int | None:
    """Insert one options_trade_lifecycle_event row.

    Replay safety: pre-check for an existing row with the same
    (trade_id, event_type, event_at_utc) tuple. If found, returns
    None (caller treats as idempotent). If not, inserts and returns
    the new event id.
    """
    existing = session.execute(text(
        """
        SELECT id FROM options_trade_lifecycle_event
        WHERE trade_id = :tid
          AND event_type = :et
          AND event_at_utc = :tu
        LIMIT 1
        """
    ), {"tid": trade_id, "et": event_type, "tu": event_at_utc}).scalar_one_or_none()
    if existing is not None:
        return None  # replay no-op
    result = session.execute(text(
        """
        INSERT INTO options_trade_lifecycle_event
            (trade_id, event_type, event_at_utc, triggered_by, payload_json)
        VALUES
            (:tid, :et, :tu, :tb, CAST(:pj AS jsonb))
        RETURNING id
        """
    ), {
        "tid": trade_id, "et": event_type, "tu": event_at_utc,
        "tb": triggered_by,
        "pj": json.dumps(payload, default=str),
    })
    return int(result.scalar_one())


def _emit_expiration_event(
    session: Session, *, trade_id: int, leg_index: int,
    expiry_date: datetime.date,
    underlying_settlement: Decimal | None,
    classification: str,
    intrinsic_value_dollars: Decimal | None,
    realized_pnl_dollars: Decimal | None,
    event_at_utc: datetime.datetime,
) -> None:
    """Insert one options_expiration_event row. Natural-key UNIQUE
    (trade_id, leg_index, expiry_date) makes this idempotent at DB."""
    try:
        session.execute(text(
            """
            INSERT INTO options_expiration_event
                (trade_id, leg_index, expiry_date,
                 underlying_settlement, classification,
                 intrinsic_value_dollars, realized_pnl_dollars,
                 event_at_utc)
            VALUES
                (:tid, :li, :ed,
                 :us, :cl,
                 :iv, :rp,
                 :tu)
            """
        ), {
            "tid": trade_id, "li": leg_index, "ed": expiry_date,
            "us": underlying_settlement, "cl": classification,
            "iv": intrinsic_value_dollars, "rp": realized_pnl_dollars,
            "tu": event_at_utc,
        })
    except IntegrityError:
        # natural key collision → idempotent replay
        session.rollback()
        logger.debug(
            "expiration_event idempotent: (trade={}, leg={}, expiry={})",
            trade_id, leg_index, expiry_date,
        )


def _emit_assignment_event(
    session: Session, *, trade_id: int, leg_index: int,
    event_type: str, risk_level: str | None,
    intrinsic_value_dollars: Decimal | None,
    realized_pnl_dollars: Decimal | None,
    event_at_utc: datetime.datetime,
    notes: str = "",
) -> None:
    """Insert one options_assignment_event row. No natural-key UNIQUE,
    so we pre-check by (trade_id, leg_index, event_type, event_at_utc)."""
    existing = session.execute(text(
        """
        SELECT id FROM options_assignment_event
        WHERE trade_id = :tid AND leg_index = :li
          AND event_type = :et AND event_at_utc = :tu
        LIMIT 1
        """
    ), {"tid": trade_id, "li": leg_index,
        "et": event_type, "tu": event_at_utc}).scalar_one_or_none()
    if existing is not None:
        return
    session.execute(text(
        """
        INSERT INTO options_assignment_event
            (trade_id, leg_index, event_type, risk_level,
             intrinsic_value_dollars, realized_pnl_dollars,
             event_at_utc, notes)
        VALUES
            (:tid, :li, :et, :rl,
             :iv, :rp,
             :tu, :no)
        """
    ), {
        "tid": trade_id, "li": leg_index, "et": event_type,
        "rl": risk_level,
        "iv": intrinsic_value_dollars, "rp": realized_pnl_dollars,
        "tu": event_at_utc, "no": notes,
    })


def _load_legs(session: Session, trade_id: int) -> list[OptionsPaperTradeLeg]:
    return list(session.execute(
        select(OptionsPaperTradeLeg)
        .where(OptionsPaperTradeLeg.trade_id == trade_id)
        .order_by(OptionsPaperTradeLeg.leg_index)
    ).scalars())


# ---------------------------------------------------------------------------
# Public transition functions
# ---------------------------------------------------------------------------


def transition_to_open(
    session: Session,
    trade_id: int,
    evidence: FillEvidence,
) -> TransitionResult:
    """PROPOSED → OPEN.

    Idempotent: calling twice on an already-OPEN trade is a no-op
    (returns is_idempotent=True). Replay protection at the lifecycle
    event level via (trade_id, event_type, event_at_utc) pre-check.
    """
    trade = _select_trade_for_update(session, trade_id)
    target = _validate_transition(trade.status, "FILL")

    # Idempotent path
    if trade.status == OPEN:
        logger.debug(
            "transition_to_open: trade {} already OPEN — no-op", trade_id,
        )
        return TransitionResult(
            trade_id=trade_id, from_status=OPEN, to_status=OPEN,
            event_id=None, is_idempotent=True, note="already OPEN",
        )

    # Validate evidence
    if evidence is None or not evidence.legs:
        raise MissingEvidenceError(
            "transition_to_open requires FillEvidence with legs"
        )

    # Apply leg fills
    legs = _load_legs(session, trade_id)
    if len(legs) == 0:
        raise InvariantViolationError(
            f"trade {trade_id} has no legs in DB"
        )
    leg_fills_by_idx = {lf.leg_index: lf for lf in evidence.legs}
    for leg in legs:
        lf = leg_fills_by_idx.get(leg.leg_index)
        if lf is not None:
            leg.entry_fill_price = lf.fill_price

    # Update trade row
    trade.status = target
    if trade.opened_at is None:
        trade.opened_at = evidence.fill_at_utc

    event_id = _emit_lifecycle_event(
        session, trade_id=trade_id, event_type="FILLED",
        triggered_by=evidence.triggered_by,
        event_at_utc=evidence.fill_at_utc,
        payload={
            "from": PROPOSED, "to": OPEN, "reason": REASON_FILL,
            "chain_snapshot_id": evidence.chain_snapshot_id,
            "leg_fills": [
                {"leg_index": lf.leg_index,
                 "fill_price": str(lf.fill_price)}
                for lf in evidence.legs
            ],
        },
    )
    session.commit()
    logger.info(
        "transition_to_open: trade={} {} → {} event_id={}",
        trade_id, PROPOSED, OPEN, event_id,
    )
    return TransitionResult(
        trade_id=trade_id, from_status=PROPOSED, to_status=OPEN,
        event_id=event_id, is_idempotent=False, note=REASON_FILL,
    )


def transition_to_closed(
    session: Session,
    trade_id: int,
    evidence: CloseEvidence,
) -> TransitionResult:
    """OPEN → CLOSED. Reason ∈ {target_hit, stop_hit, operator_close, force_close}."""
    trade = _select_trade_for_update(session, trade_id)
    target = _validate_transition(trade.status, "CLOSE")

    if trade.status == CLOSED:
        return TransitionResult(
            trade_id=trade_id, from_status=CLOSED, to_status=CLOSED,
            event_id=None, is_idempotent=True, note="already CLOSED",
        )

    if evidence is None or not evidence.legs:
        raise MissingEvidenceError(
            "transition_to_closed requires CloseEvidence with per-leg close prices"
        )

    legs = _load_legs(session, trade_id)
    leg_closes_by_idx = {lc.leg_index: lc for lc in evidence.legs}
    for leg in legs:
        lc = leg_closes_by_idx.get(leg.leg_index)
        if lc is not None:
            # Per-leg close — store as exit_fill_price column if present,
            # else as a payload-only field. Schema check at insert time.
            if hasattr(leg, "exit_fill_price"):
                leg.exit_fill_price = lc.close_price

    # Update trade-level fields
    trade.status = target
    trade.closed_at = evidence.close_at_utc
    if evidence.exit_debit_dollars is not None:
        trade.exit_debit_dollars = evidence.exit_debit_dollars
    if evidence.realized_pnl_dollars is not None:
        trade.realized_pnl_dollars = evidence.realized_pnl_dollars
    trade.rollback_reason = evidence.reason if evidence.reason == REASON_FORCE_CLOSE else None

    event_id = _emit_lifecycle_event(
        session, trade_id=trade_id, event_type="CLOSED",
        triggered_by=evidence.triggered_by,
        event_at_utc=evidence.close_at_utc,
        payload={
            "from": OPEN, "to": CLOSED, "reason": evidence.reason,
            "chain_snapshot_id": evidence.chain_snapshot_id,
            "exit_debit_dollars": str(evidence.exit_debit_dollars)
                if evidence.exit_debit_dollars is not None else None,
            "realized_pnl_dollars": str(evidence.realized_pnl_dollars)
                if evidence.realized_pnl_dollars is not None else None,
            "leg_closes": [
                {"leg_index": lc.leg_index,
                 "close_price": str(lc.close_price)}
                for lc in evidence.legs
            ],
        },
    )
    session.commit()
    logger.info(
        "transition_to_closed: trade={} {} → {} reason={} event_id={}",
        trade_id, OPEN, CLOSED, evidence.reason, event_id,
    )
    return TransitionResult(
        trade_id=trade_id, from_status=OPEN, to_status=CLOSED,
        event_id=event_id, is_idempotent=False, note=evidence.reason,
    )


def _has_assignable_short_itm(
    legs: list[OptionsPaperTradeLeg],
    expiration_legs: list[LegExpirationEvidence],
) -> bool:
    """True if any SHORT leg is ITM at expiry. Drives assignment
    precedence over expiration."""
    legs_by_idx = {L.leg_index: L for L in legs}
    for ev in expiration_legs:
        leg = legs_by_idx.get(ev.leg_index)
        if leg is None:
            continue
        if str(leg.side).upper() == "SELL" and ev.classification == "ITM":
            return True
    return False


def transition_to_expired(
    session: Session,
    trade_id: int,
    evidence: ExpirationEvidence,
) -> TransitionResult:
    """OPEN → EXPIRED.

    Assignment precedence: if ANY short leg is ITM at settlement,
    raises AssignmentPrecedenceError. Caller must use
    transition_to_assigned() instead.

    Per-leg expiration_event rows are emitted with classification
    (OTM | ITM | PIN_RISK | MISSING_DATA). Natural key UNIQUE
    (trade_id, leg_index, expiry_date) makes per-leg writes idempotent.
    """
    trade = _select_trade_for_update(session, trade_id)
    target = _validate_transition(trade.status, "EXPIRE")

    if trade.status == EXPIRED:
        return TransitionResult(
            trade_id=trade_id, from_status=EXPIRED, to_status=EXPIRED,
            event_id=None, is_idempotent=True, note="already EXPIRED",
        )

    if evidence is None or not evidence.legs:
        raise MissingEvidenceError(
            "transition_to_expired requires ExpirationEvidence with per-leg classifications"
        )

    legs = _load_legs(session, trade_id)

    # Assignment precedence check
    if _has_assignable_short_itm(legs, evidence.legs):
        raise AssignmentPrecedenceError(
            f"trade {trade_id} has SHORT legs that are ITM at settlement; "
            f"call transition_to_assigned() instead of transition_to_expired()"
        )

    # Per-leg expiration events
    for leg_ev in evidence.legs:
        _emit_expiration_event(
            session, trade_id=trade_id,
            leg_index=leg_ev.leg_index,
            expiry_date=evidence.expiry_date,
            underlying_settlement=evidence.underlying_settlement,
            classification=leg_ev.classification,
            intrinsic_value_dollars=leg_ev.intrinsic_value_dollars,
            realized_pnl_dollars=leg_ev.realized_pnl_dollars,
            event_at_utc=evidence.settlement_at_utc,
        )

    # Aggregate realized P&L
    total_realized = Decimal("0")
    for leg_ev in evidence.legs:
        if leg_ev.realized_pnl_dollars is not None:
            total_realized += Decimal(str(leg_ev.realized_pnl_dollars))

    trade.status = target
    trade.closed_at = evidence.settlement_at_utc
    trade.realized_pnl_dollars = total_realized

    # Determine top-level reason
    has_pin = any(L.classification == "PIN_RISK" for L in evidence.legs)
    reason = REASON_EXPIRY_PIN_RISK if has_pin else REASON_EXPIRY_OTM

    event_id = _emit_lifecycle_event(
        session, trade_id=trade_id, event_type="EXPIRED",
        triggered_by=evidence.triggered_by,
        event_at_utc=evidence.settlement_at_utc,
        payload={
            "from": OPEN, "to": EXPIRED, "reason": reason,
            "expiry_date": str(evidence.expiry_date),
            "underlying_settlement": str(evidence.underlying_settlement)
                if evidence.underlying_settlement is not None else None,
            "leg_classifications": [
                {"leg_index": L.leg_index,
                 "classification": L.classification,
                 "intrinsic_value_dollars": str(L.intrinsic_value_dollars)
                     if L.intrinsic_value_dollars is not None else None,
                 "realized_pnl_dollars": str(L.realized_pnl_dollars)
                     if L.realized_pnl_dollars is not None else None}
                for L in evidence.legs
            ],
        },
    )
    session.commit()
    logger.info(
        "transition_to_expired: trade={} {} → {} reason={} event_id={}",
        trade_id, OPEN, EXPIRED, reason, event_id,
    )
    return TransitionResult(
        trade_id=trade_id, from_status=OPEN, to_status=EXPIRED,
        event_id=event_id, is_idempotent=False, note=reason,
    )


def transition_to_assigned(
    session: Session,
    trade_id: int,
    evidence: AssignmentEvidence,
) -> TransitionResult:
    """OPEN → ASSIGNED.

    Used when a SHORT leg gets assigned (early or at expiry). Writes
    per-leg options_assignment_event rows + a top-level lifecycle event.
    """
    trade = _select_trade_for_update(session, trade_id)
    target = _validate_transition(trade.status, "ASSIGN")

    if trade.status == ASSIGNED:
        return TransitionResult(
            trade_id=trade_id, from_status=ASSIGNED, to_status=ASSIGNED,
            event_id=None, is_idempotent=True, note="already ASSIGNED",
        )

    if evidence is None or not evidence.legs:
        raise MissingEvidenceError(
            "transition_to_assigned requires AssignmentEvidence with per-leg events"
        )

    # Per-leg assignment events
    for leg_ev in evidence.legs:
        _emit_assignment_event(
            session, trade_id=trade_id,
            leg_index=leg_ev.leg_index,
            event_type=leg_ev.event_type,
            risk_level=leg_ev.risk_level,
            intrinsic_value_dollars=leg_ev.intrinsic_value_dollars,
            realized_pnl_dollars=leg_ev.realized_pnl_dollars,
            event_at_utc=evidence.assigned_at_utc,
            notes=leg_ev.notes,
        )

    # Aggregate realized P&L
    total_realized = Decimal("0")
    for leg_ev in evidence.legs:
        if leg_ev.realized_pnl_dollars is not None:
            total_realized += Decimal(str(leg_ev.realized_pnl_dollars))

    trade.status = target
    trade.closed_at = evidence.assigned_at_utc
    trade.realized_pnl_dollars = total_realized

    is_early = any(
        L.event_type == "ASSIGNED" and L.risk_level == "HIGH"
        for L in evidence.legs
    )
    reason = REASON_ASSIGNED_EARLY if is_early else REASON_ASSIGNED_ITM

    event_id = _emit_lifecycle_event(
        session, trade_id=trade_id, event_type="ASSIGNED",
        triggered_by=evidence.triggered_by,
        event_at_utc=evidence.assigned_at_utc,
        payload={
            "from": OPEN, "to": ASSIGNED, "reason": reason,
            "leg_assignments": [
                {"leg_index": L.leg_index,
                 "event_type": L.event_type,
                 "risk_level": L.risk_level,
                 "intrinsic_value_dollars": str(L.intrinsic_value_dollars)
                     if L.intrinsic_value_dollars is not None else None,
                 "realized_pnl_dollars": str(L.realized_pnl_dollars)
                     if L.realized_pnl_dollars is not None else None,
                 "notes": L.notes}
                for L in evidence.legs
            ],
        },
    )
    session.commit()
    logger.info(
        "transition_to_assigned: trade={} {} → {} reason={} event_id={}",
        trade_id, OPEN, ASSIGNED, reason, event_id,
    )
    return TransitionResult(
        trade_id=trade_id, from_status=OPEN, to_status=ASSIGNED,
        event_id=event_id, is_idempotent=False, note=reason,
    )
