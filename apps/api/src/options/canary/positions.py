"""Phase P6A — canary position + cash primitives (session-injected, no commit).

Every function here operates inside the CALLER's transaction and never
commits. Correctness anchor for the slot-cap COUNT-then-INSERT race is the
per-portfolio advisory + row lock taken via :func:`lock_portfolio`.

This module does NO gating — the worker handlers enforce
OPTIONS_CANARY_ENABLED before any of this runs. Strictly paper-only; touches
only options_* tables.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.paper.fills import (
    DEFAULT_FEE_PER_CONTRACT,
    total_fees_for_legs,
)

# Dedicated advisory-lock namespace for options-canary mutations. Two-int
# form pg_advisory_xact_lock(ns, key) avoids collision with other systems.
ADVISORY_NS = 4242


# --- pure helpers -----------------------------------------------------------

def proposal_hash(
    *,
    portfolio_id: str,
    run_date: dt.date,
    underlying: str,
    strategy_name: str,
    strategy_version: str,
    legs: Sequence[Any],
) -> str:
    """Deterministic identity hash of a proposed spread.

    Scoped by portfolio + LOGICAL run_date (NOT wall-clock) + structure, so a
    same-day / lost-ACK retry of the same spread collides (dedup) while a
    next-day reopen is allowed. Strikes formatted to 4dp to match
    Numeric(12,4); legs sorted for order-independence. Price is NOT part of
    identity.
    """
    parts = [portfolio_id, run_date.isoformat(), underlying,
             strategy_name, strategy_version]
    for l in sorted(legs, key=lambda x: (
        x.option_type, str(x.strike), str(x.expiry), x.side,
    )):
        exp = l.expiry.isoformat() if hasattr(l.expiry, "isoformat") else str(l.expiry)
        parts.append(
            f"{l.side}:{l.option_type}:"
            f"{format(Decimal(str(l.strike)), '.4f')}:{exp}:{l.qty}"
        )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def fee_buffer(
    legs: Sequence[Any],
    *,
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
) -> Decimal:
    """Round-trip (open+close) fee estimate — the SAME fee_per_contract the
    close/expire paths charge, so reserve covers worst-case outflow exactly."""
    return total_fees_for_legs(
        [l.qty for l in legs], fee_per_contract=fee_per_contract,
    )


def reserved_capital(
    *,
    max_loss_dollars: Any,
    legs: Sequence[Any],
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
) -> Decimal:
    """reserve = structural max_loss + round-trip fee buffer. Guarantees the
    release credit (reserved + realized_pnl) >= 0 → cash_current never goes
    negative (defined-risk value is width-bounded, so realized loss <=
    max_loss + fees)."""
    return Decimal(str(max_loss_dollars)) + fee_buffer(
        legs, fee_per_contract=fee_per_contract,
    )


# --- DB primitives (no commit) ----------------------------------------------

def lock_portfolio(session: Session, portfolio_id: str) -> dict | None:
    """Take the per-portfolio xact advisory lock + row lock, return the
    portfolio row. Correctness anchor: serializes all promotion/release/cash
    mutations on a portfolio, making COUNT-then-INSERT slot enforcement
    race-free. Auto-released at commit/rollback."""
    session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, hashtext(:pid))"),
        {"ns": ADVISORY_NS, "pid": portfolio_id},
    )
    row = session.execute(
        text(
            "SELECT id, name, cash_initial, cash_current, max_open_trades, "
            "max_capital_per_trade, active "
            "FROM options_paper_portfolio WHERE id = :pid FOR UPDATE"
        ),
        {"pid": portfolio_id},
    ).mappings().first()
    return dict(row) if row else None


def count_open_positions(session: Session, portfolio_id: str) -> int:
    return int(session.execute(
        text(
            "SELECT COUNT(*) FROM options_paper_position "
            "WHERE portfolio_id = :pid AND released_at IS NULL"
        ),
        {"pid": portfolio_id},
    ).scalar() or 0)


def count_open_positions_for_underlying(
    session: Session, portfolio_id: str, underlying: str,
) -> int:
    """P6D.36D — OPEN canary positions on one underlying (per-underlying
    cap input). Read-only; race-free under lock_portfolio."""
    return int(session.execute(
        text(
            "SELECT COUNT(*) FROM options_paper_position p "
            "JOIN options_paper_trade t ON t.id = p.trade_id "
            "WHERE p.portfolio_id = :pid AND p.released_at IS NULL "
            "AND t.underlying = :u"
        ),
        {"pid": portfolio_id, "u": underlying},
    ).scalar() or 0)


def count_promotions_today(session: Session, portfolio_id: str) -> int:
    """P6D.36D — positions reserved during the DB server's CURRENT day
    (daily promotion cap input). Wall-clock by design: an operational
    rate limit, deliberately NOT the logical run_date (a backfill/replay
    of past run_dates still counts against today's budget)."""
    return int(session.execute(
        text(
            "SELECT COUNT(*) FROM options_paper_position "
            "WHERE portfolio_id = :pid "
            "AND opened_at >= date_trunc('day', NOW())"
        ),
        {"pid": portfolio_id},
    ).scalar() or 0)


def aggregate_open_max_loss(session: Session, portfolio_id: str) -> Decimal:
    """P6D.36D — SUM of structural max_loss_dollars across OPEN positions
    (aggregate loss-cap input). Read-only; race-free under lock_portfolio."""
    v = session.execute(
        text(
            "SELECT COALESCE(SUM(t.max_loss_dollars), 0) "
            "FROM options_paper_position p "
            "JOIN options_paper_trade t ON t.id = p.trade_id "
            "WHERE p.portfolio_id = :pid AND p.released_at IS NULL"
        ),
        {"pid": portfolio_id},
    ).scalar()
    return Decimal(str(v or 0))


def debit_cash(session: Session, portfolio_id: str, amount: Any) -> int:
    """Guarded debit. Returns rowcount (0 = insufficient cash → caller skips)."""
    return session.execute(
        text(
            "UPDATE options_paper_portfolio "
            "SET cash_current = cash_current - :amt, updated_at = NOW() "
            "WHERE id = :pid AND cash_current >= :amt"
        ),
        {"amt": Decimal(str(amount)), "pid": portfolio_id},
    ).rowcount


def credit_cash(session: Session, portfolio_id: str, amount: Any) -> int:
    return session.execute(
        text(
            "UPDATE options_paper_portfolio "
            "SET cash_current = cash_current + :amt, updated_at = NOW() "
            "WHERE id = :pid"
        ),
        {"amt": Decimal(str(amount)), "pid": portfolio_id},
    ).rowcount


def reserve_position(
    session: Session, *, portfolio_id: str, trade_id: int, reserved: Any,
) -> str:
    pos_id = str(uuid.uuid4())
    session.execute(
        text(
            "INSERT INTO options_paper_position "
            "(id, portfolio_id, trade_id, reserved_capital, opened_at) "
            "VALUES (:id, :pid, :tid, :rc, NOW())"
        ),
        {"id": pos_id, "pid": portfolio_id, "tid": trade_id,
         "rc": Decimal(str(reserved))},
    )
    return pos_id


def release_position(
    session: Session, *, trade_id: int, release_reason: str, now: dt.datetime,
) -> int:
    """Idempotent release. Returns rowcount: 1 = released now (caller credits
    cash), 0 = already released (caller skips → no double credit)."""
    return session.execute(
        text(
            "UPDATE options_paper_position "
            "SET released_at = :now, release_reason = :reason "
            "WHERE trade_id = :tid AND released_at IS NULL"
        ),
        {"now": now, "reason": release_reason, "tid": trade_id},
    ).rowcount
