"""Phase P6A — canary reconciliation (read-mostly, ordered).

Detectors for the lifecycle invariants. Ordering matters: orphan-position
heal MUST run before the cash-drift check, else terminal-but-unreleased
trades raise false drift alerts (X7).

P6A policy: orphan-position heal is the only auto-mutation, and it is
idempotent (release rowcount guard → credit once). Orphan trades and cash
drift are ALERT-ONLY (never fabricate / auto-correct capital). All heal
mutations are session-injected (caller owns commit). Strictly options_*.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.canary import positions as pos

_TERMINAL = ("CLOSED", "EXPIRED", "ASSIGNED")


@dataclass
class ReconcileReport:
    orphan_trades: list[int] = field(default_factory=list)
    orphan_positions_healed: list[int] = field(default_factory=list)
    cash_drift: list[dict] = field(default_factory=list)
    reserved_mismatch: list[dict] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.orphan_trades or self.cash_drift
                    or self.reserved_mismatch)


def find_orphan_trades(session: Session) -> list[int]:
    """OPEN trades with no unreleased position. Alert + quarantine only —
    never auto-create a reservation (capital implication needs a human)."""
    rows = session.execute(text(
        """
        SELECT t.id
        FROM options_paper_trade t
        LEFT JOIN options_paper_position p
          ON p.trade_id = t.id AND p.released_at IS NULL
        WHERE t.status = 'OPEN' AND p.id IS NULL
        """
    )).all()
    return [int(r[0]) for r in rows]


def heal_orphan_positions(
    session: Session, *, now: dt.datetime,
) -> list[int]:
    """Positions still unreleased whose trade is terminal → release + credit.
    Idempotent: release rowcount guard ensures credit happens exactly once."""
    rows = session.execute(text(
        f"""
        SELECT p.trade_id, p.portfolio_id, p.reserved_capital,
               t.status, t.realized_pnl_dollars
        FROM options_paper_position p
        JOIN options_paper_trade t ON t.id = p.trade_id
        WHERE p.released_at IS NULL AND t.status IN {_TERMINAL}
        """
    )).mappings().all()
    healed: list[int] = []
    for r in rows:
        reason = f"HEAL_{r['status']}"
        rc = pos.release_position(
            session, trade_id=r["trade_id"], release_reason=reason, now=now,
        )
        if rc == 1:
            credit = (Decimal(str(r["reserved_capital"]))
                      + Decimal(str(r["realized_pnl_dollars"] or 0)))
            pos.credit_cash(session, r["portfolio_id"], credit)
            healed.append(int(r["trade_id"]))
    return healed


def check_cash_drift(
    session: Session, *, tolerance: Decimal = Decimal("0.01"),
) -> list[dict]:
    """Recompute cash identity per portfolio; alert on drift. Read-only,
    never auto-corrects. Run AFTER heal_orphan_positions."""
    rows = session.execute(text(
        """
        SELECT pp.id, pp.cash_initial, pp.cash_current,
               COALESCE(res.reserved, 0)  AS reserved_open,
               COALESCE(rel.realized, 0)  AS realized_released
        FROM options_paper_portfolio pp
        LEFT JOIN (
          SELECT portfolio_id, SUM(reserved_capital) AS reserved
          FROM options_paper_position WHERE released_at IS NULL
          GROUP BY portfolio_id
        ) res ON res.portfolio_id = pp.id
        LEFT JOIN (
          SELECT p.portfolio_id, SUM(t.realized_pnl_dollars) AS realized
          FROM options_paper_position p
          JOIN options_paper_trade t ON t.id = p.trade_id
          WHERE p.released_at IS NOT NULL
          GROUP BY p.portfolio_id
        ) rel ON rel.portfolio_id = pp.id
        """
    )).mappings().all()
    drift: list[dict] = []
    for r in rows:
        expected = (Decimal(str(r["cash_initial"]))
                    - Decimal(str(r["reserved_open"]))
                    + Decimal(str(r["realized_released"])))
        actual = Decimal(str(r["cash_current"]))
        delta = actual - expected
        if abs(delta) > tolerance:
            drift.append({"portfolio_id": r["id"], "expected": str(expected),
                          "actual": str(actual), "delta": str(delta)})
    return drift


def check_reserved_mismatch(session: Session) -> list[dict]:
    """Open positions whose reserved_capital < trade.max_loss_dollars (reserve
    should be >= max_loss + fees). Alert only."""
    rows = session.execute(text(
        """
        SELECT p.trade_id, p.reserved_capital, t.max_loss_dollars
        FROM options_paper_position p
        JOIN options_paper_trade t ON t.id = p.trade_id
        WHERE p.released_at IS NULL
          AND p.reserved_capital < t.max_loss_dollars
        """
    )).mappings().all()
    return [{"trade_id": int(r["trade_id"]),
             "reserved": str(r["reserved_capital"]),
             "max_loss": str(r["max_loss_dollars"])} for r in rows]


def run(
    session: Session, *, now: dt.datetime, heal: bool = True,
) -> ReconcileReport:
    """Ordered reconciliation. heal=False = detect-only (P6A dry-run posture);
    heal=True arms orphan-position auto-heal (P6B runtime)."""
    report = ReconcileReport()
    if heal:
        report.orphan_positions_healed = heal_orphan_positions(session, now=now)
    report.orphan_trades = find_orphan_trades(session)
    report.cash_drift = check_cash_drift(session)        # AFTER heal (X7)
    report.reserved_mismatch = check_reserved_mismatch(session)
    return report
