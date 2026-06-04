"""Phase P6A — canary promotion / lifecycle orchestration (INFRASTRUCTURE).

Owns options_paper_position creation (TXN-OPEN) and release (TXN-RELEASE)
atomically, on top of the session-injected paper engine. Gated entirely by
the worker handlers on OPTIONS_CANARY_ENABLED — this module never flips a
flag and never opens a position on its own.

Concurrency model (red-team integrated):
  * per-portfolio xact advisory lock + FOR UPDATE = correctness anchor for
    slot-cap COUNT-then-INSERT (positions.lock_portfolio).
  * proposal_hash unique (open) handled via begin_nested() SAVEPOINT so a
    duplicate aborts only the savepoint and the single outer commit survives.
  * release credit is rowcount-guarded (positions.release_position) → at most
    once per position.
  * reserve = max_loss + round-trip fee buffer → cash_current stays >= 0.
  * funnel counters are absolute (recomputed per run; upsert overwrites).

The promotion POLICY (which candidate to promote) and the exit POLICY (when
to close) are P6B — left as explicit seams here. P6A keeps them inert:
_load_promotable_requests() returns [] and the lifecycle cycle only
reconciles. Strictly paper-only; touches only options_* tables.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.options.canary import positions as pos
from apps.api.src.options.canary import reconcile
from apps.api.src.options.canary.funnel import (
    FunnelCounts,
    FunnelSnapshot,
    upsert_funnel_row,
)
from apps.api.src.options.paper.engine import (
    close_trade,
    expire_trade,
    open_trade,
)
from apps.api.src.options.paper.fills import DEFAULT_FEE_PER_CONTRACT


@dataclass
class PromoteResult:
    status: str           # promoted | slot_full | over_capital_cap |
                          # proposal_duplicate | portfolio_inactive | rejected
    trade_id: int | None = None
    position_id: str | None = None
    reserved: Decimal | None = None
    detail: tuple = ()


@dataclass
class ReleaseResult:
    status: str           # released | already_released | engine_rejected
    credited: Decimal | None = None
    release_reason: str | None = None
    detail: dict = field(default_factory=dict)


class _Abort(Exception):
    """Internal: roll back the open SAVEPOINT with a reason tuple."""


# ===========================================================================
# TXN-OPEN — promote one proposal into an open position + capital reservation
# ===========================================================================

def promote_one(
    session: Session,
    *,
    portfolio_id: str,
    request,
    proposal_hash: str,
    now: dt.datetime,
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
) -> PromoteResult:
    """Atomic: open_trade + reserve_position + cash debit, in the caller's
    transaction. The caller commits exactly once. A duplicate proposal_hash
    or a cap/cash violation rolls back only the inner SAVEPOINT, leaving the
    outer transaction usable for the funnel write."""
    port = pos.lock_portfolio(session, portfolio_id)
    if port is None or not port["active"]:
        return PromoteResult("portfolio_inactive")
    if pos.count_open_positions(session, portfolio_id) >= int(port["max_open_trades"]):
        return PromoteResult("slot_full")
    cap = min(
        Decimal(str(port["max_capital_per_trade"])),
        Decimal(str(settings.OPTIONS_CANARY_MAX_CAPITAL_USD)),
    )
    try:
        with session.begin_nested():
            res = open_trade(
                request, proposal_hash=proposal_hash, session=session,
                fee_per_contract=fee_per_contract,
            )
            if not res.accepted:
                raise _Abort(tuple(res.rejected_reasons) or ("rejected",))
            reserved = pos.reserved_capital(
                max_loss_dollars=res.risk.max_loss_dollars,
                legs=request.legs, fee_per_contract=fee_per_contract,
            )
            if reserved > cap:
                raise _Abort(("over_capital_cap",))
            if pos.debit_cash(session, portfolio_id, reserved) != 1:
                raise _Abort(("over_capital_cap",))   # insufficient cash
            position_id = pos.reserve_position(
                session, portfolio_id=portfolio_id,
                trade_id=res.trade_id, reserved=reserved,
            )
    except IntegrityError:
        return PromoteResult("proposal_duplicate")
    except _Abort as a:
        reason = a.args[0] if a.args else ("rejected",)
        status = "over_capital_cap" if reason[0] == "over_capital_cap" else "rejected"
        return PromoteResult(status, detail=tuple(reason))
    return PromoteResult(
        "promoted", trade_id=res.trade_id,
        position_id=position_id, reserved=reserved,
    )


# ===========================================================================
# TXN-RELEASE — release a position on terminal transition + cash credit
# ===========================================================================

def _release_reason(terminal: str, out: dict, reason: str | None) -> str:
    if terminal == "expire":
        if out.get("status") == "ASSIGNED":
            return "ASSIGNED"
        return "EXPIRED_ITM" if out.get("has_assignment") else "EXPIRED_OTM"
    return reason or "CLOSED_OPERATOR"


def release_one(
    session: Session,
    *,
    portfolio_id: str,
    trade_id: int,
    terminal: str,                       # "close" | "expire"
    now: dt.datetime,
    settlement_price: Decimal | None = None,
    quotes: dict | None = None,
    reason: str | None = None,
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
) -> ReleaseResult:
    """Atomic: engine terminal transition + position release + cash credit, in
    the caller's transaction (one commit). Credit is rowcount-guarded: a
    duplicate/already-released position is a no-op (no double credit)."""
    pos.lock_portfolio(session, portfolio_id)
    if terminal == "expire":
        out = expire_trade(
            trade_id, settlement_price=settlement_price,
            session=session, fee_per_contract=fee_per_contract,
        )
    elif terminal == "close":
        out = close_trade(
            trade_id, quotes_by_symbol=quotes or {},
            reason=reason or "CLOSED_OPERATOR",
            session=session, fee_per_contract=fee_per_contract,
        )
    else:
        raise ValueError(f"terminal must be 'close' or 'expire', got {terminal!r}")

    if not out.get("accepted"):
        return ReleaseResult("engine_rejected", detail=out)

    rel_reason = _release_reason(terminal, out, reason)
    rc = pos.release_position(
        session, trade_id=trade_id, release_reason=rel_reason, now=now,
    )
    if rc != 1:
        return ReleaseResult("already_released")

    row = session.execute(text(
        "SELECT p.reserved_capital, t.realized_pnl_dollars "
        "FROM options_paper_position p "
        "JOIN options_paper_trade t ON t.id = p.trade_id "
        "WHERE p.trade_id = :tid"
    ), {"tid": trade_id}).mappings().first()
    credit = (Decimal(str(row["reserved_capital"]))
              + Decimal(str(row["realized_pnl_dollars"] or 0)))
    pos.credit_cash(session, portfolio_id, credit)
    return ReleaseResult("released", credited=credit, release_reason=rel_reason)


# ===========================================================================
# Cycles (called by worker handlers; gated upstream on OPTIONS_CANARY_ENABLED)
# ===========================================================================

def _load_promotable_requests(*, portfolio_id, run_date, session_factory):
    """P6B SEAM: select eligible candidates → build (TradeRequest,
    proposal_hash) pairs. P6A returns [] → no auto-open."""
    return []


def run_promotion_cycle(
    *,
    portfolio_id: str,
    run_date: dt.date,
    now: dt.datetime,
    session_factory=SessionLocal,
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
) -> FunnelCounts:
    """One promotion pass for a portfolio. Each candidate promoted in its own
    transaction (single commit). Funnel counts are ABSOLUTE for this run;
    upsert overwrites the (run_date, portfolio) row → idempotent."""
    requests = _load_promotable_requests(
        portfolio_id=portfolio_id, run_date=run_date,
        session_factory=session_factory,
    )
    counts = FunnelCounts(candidates_total=len(requests))

    with session_factory() as s:
        open_start = pos.count_open_positions(s, portfolio_id)
        cash_start = s.execute(text(
            "SELECT cash_current FROM options_paper_portfolio WHERE id = :pid"
        ), {"pid": portfolio_id}).scalar() or Decimal("0")

    for request, phash in requests:
        with session_factory() as s:
            try:
                r = promote_one(
                    s, portfolio_id=portfolio_id, request=request,
                    proposal_hash=phash, now=now, fee_per_contract=fee_per_contract,
                )
                if r.status == "promoted":
                    counts.promoted += 1
                    counts.filled += 1
                elif r.status == "slot_full":
                    counts.skip_slot_full += 1
                elif r.status == "over_capital_cap":
                    counts.skip_over_capital_cap += 1
                elif r.status == "proposal_duplicate":
                    counts.skip_proposal_duplicate += 1
                else:
                    counts.skip_other += 1
                s.commit()
            except Exception as exc:   # noqa: BLE001
                s.rollback()
                counts.skip_other += 1
                logger.error("promote_one failed pid={}: {}", portfolio_id, exc)

    with session_factory() as s:
        open_end = pos.count_open_positions(s, portfolio_id)
        cash_end = s.execute(text(
            "SELECT cash_current FROM options_paper_portfolio WHERE id = :pid"
        ), {"pid": portfolio_id}).scalar() or Decimal("0")
        upsert_funnel_row(
            s, run_date=run_date, portfolio_id=portfolio_id, counts=counts,
            snapshot=FunnelSnapshot(
                open_at_start=open_start, open_at_end=open_end,
                cash_at_start=Decimal(str(cash_start)),
                cash_at_end=Decimal(str(cash_end)),
            ),
        )
        s.commit()
    return counts


def run_lifecycle_cycle(
    *,
    portfolio_id: str,
    now: dt.datetime,
    heal: bool = True,
    session_factory=SessionLocal,
) -> reconcile.ReconcileReport:
    """One lifecycle pass: ordered reconciliation (heal orphan positions →
    drift/orphan-trade/reserved-mismatch alerts).

    P6B SEAM: MTM observation + exit-policy evaluation + release_one wiring
    plug in here (need a live quote source + exit thresholds). P6A reconciles
    only — no exit decisions."""
    with session_factory() as s:
        report = reconcile.run(s, now=now, heal=heal)
        s.commit()
    return report
