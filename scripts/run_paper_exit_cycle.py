"""Operator-only paper exit-cycle runner.

Closes paper positions that meet a take-profit, stop-loss, or
max-hold rule. Uses the existing `submit_trade` sell path which
keeps the next-bar guard in place — fills only against a
price_bar with `ts > submitted_at`. Same-bar exits are forbidden.

Strict invariants:
  * Paper-only — `submit_trade` rejects with "no open position to
    sell" if the position is missing; the DB schema gates writes
    to paper-only structures.
  * No fabricated prices — exit price is the next-bar `find_next_open`
    fill on real `price_bar` rows.
  * No forced liquidations — without `--force-close-all`, only
    rule-driven closes happen.
  * Replay flags preserved — selling a replay-tagged trade does
    NOT remove the manifest entry; the new sell row simply isn't
    flagged.
  * Default off — `--commit` required for any DB write; bare
    invocation is a dry-run.

Exit rules (defaults, env-overridable):
  PAPER_TAKE_PROFIT_PCT=0.08     +8% on entry → sell
  PAPER_STOP_LOSS_PCT=0.04        -4% on entry → sell
  PAPER_MAX_HOLD_DAYS=10          held ≥10 trading days → sell

Existing logic this complements:
  auto_trader.generate_decisions already emits close_sell when:
    * holding age ≥ max_holding_days (default 30)
    * a Recommendation flips to Sell/Trim
  Neither rule fires on price moves, so without this runner
  positions never close on P&L. This runner adds the price-based
  rules without touching auto_trader.

Usage:
  python -m scripts.run_paper_exit_cycle
  python -m scripts.run_paper_exit_cycle --commit
  python -m scripts.run_paper_exit_cycle --commit --as-of 2026-05-06
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import text


CONFIRM_ENV = "PAPER_EXIT_CYCLE_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_CLOSES_PAPER_POSITIONS"

ARTIFACT_DIR = Path("artifacts/paper_exit_cycle")
ARTIFACT_NAME = "exit_cycle_{date}.json"


def _env_decimal(name: str, default: Decimal) -> Decimal:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = Decimal(raw)
    except Exception:  # noqa: BLE001
        return default
    return v


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _argparse() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_paper_exit_cycle",
        description=(
            "Close eligible paper positions on take-profit, "
            "stop-loss, or max-hold rules. Default dry-run."
        ),
    )
    p.add_argument(
        "--as-of", default=None,
        help="ISO date for submission timestamp anchor. "
             "Defaults to today UTC.",
    )
    p.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Default. No DB writes.",
    )
    p.add_argument(
        "--commit", action="store_true",
        help=f"Submit sells. Requires {CONFIRM_ENV}={CONFIRM_VALUE}.",
    )
    p.add_argument(
        "--force-close-all", action="store_true",
        help="Operator override — close every open position "
             "regardless of rule. Still requires --commit + env.",
    )
    return p


def _trading_days_between(a: dt.date, b: dt.date) -> int:
    """Inclusive Mon-Fri trading-day count."""
    if b < a:
        return 0
    n = 0
    cur = a
    while cur <= b:
        if cur.weekday() < 5:
            n += 1
        cur = cur + dt.timedelta(days=1)
    return n


def _latest_close(session, asset_id: str, as_of: dt.date) -> tuple[
    dt.date, Decimal,
] | None:
    row = session.execute(text("""
        SELECT ts::date AS d,
               coalesce(adjusted_close, close)::numeric AS px
        FROM price_bar
        WHERE asset_id = :a AND timeframe = '1d'
          AND ts::date <= :d
        ORDER BY ts DESC LIMIT 1
    """), {"a": asset_id, "d": as_of}).first()
    if row is None or row[1] is None:
        return None
    return row[0], Decimal(str(row[1]))


@dataclass
class ExitCycleResult:
    as_of: dt.date
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    max_hold_days: int
    force_close_all: bool
    scanned: int = 0
    closed: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    realized_pnl_total: Decimal = Decimal("0")


def run_exit_cycle(
    session,
    *,
    as_of: dt.date,
    portfolio_id: str | None = None,
    take_profit_pct: Decimal | None = None,
    stop_loss_pct: Decimal | None = None,
    max_hold_days: int | None = None,
    commit: bool = True,
    force_close_all: bool = False,
    snapshot_equity: bool = False,
) -> ExitCycleResult:
    """Evaluate take-profit / stop-loss / max-hold on open paper positions and
    (when ``commit``) close them via the submit_trade SELL path.

    Operates on the PASSED ``session``. ``portfolio_id=None`` scans every open
    position across all active portfolios (legacy CLI behaviour); a value
    scopes the scan to that one portfolio (replay). Rule params fall back to
    the PAPER_* env defaults when None. Each close runs in a SAVEPOINT so a
    rejected/duplicate sell never poisons the surrounding transaction (the
    P0-3B.3 isolation, preserved without per-position sub-sessions). The
    caller owns the outer commit. CONFIRM_ENV is NOT consulted here — that
    operator gate lives only in the CLI ``main``.
    """
    from sqlalchemy.exc import IntegrityError
    from apps.api.src.db.models import PaperPortfolio
    from apps.api.src.domain.paper_trading.paper_execution import (
        submit_trade, PaperTradeRejected,
    )
    from apps.api.src.domain.paper_trading.paper_service import (
        snapshot_equity_now,
    )

    take_profit = (
        take_profit_pct if take_profit_pct is not None
        else _env_decimal("PAPER_TAKE_PROFIT_PCT", Decimal("0.08"))
    )
    stop_loss = (
        stop_loss_pct if stop_loss_pct is not None
        else _env_decimal("PAPER_STOP_LOSS_PCT", Decimal("0.04"))
    )
    max_hold = (
        max_hold_days if max_hold_days is not None
        else _env_int("PAPER_MAX_HOLD_DAYS", 10)
    )

    submitted_at = dt.datetime.combine(
        as_of, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )

    res = ExitCycleResult(
        as_of=as_of, take_profit_pct=take_profit, stop_loss_pct=stop_loss,
        max_hold_days=max_hold, force_close_all=force_close_all,
    )

    sql = """
        SELECT pp.id, pp.portfolio_id, pp.asset_id,
               pp.quantity, pp.avg_cost, pp.opened_at,
               a.symbol, p.is_active, p.name
        FROM paper_position pp
        JOIN paper_portfolio p ON p.id = pp.portfolio_id
        JOIN asset a ON a.id = pp.asset_id
        WHERE pp.is_open = TRUE AND p.is_active = TRUE
          -- P1 2026-07-08: never exit-cycle per-user practice books;
          -- the engine's TP/SL/max-hold rules apply to ENGINE books only.
          AND p.name NOT LIKE 'user:%'
    """
    params: dict[str, Any] = {}
    if portfolio_id is not None:
        sql += " AND pp.portfolio_id = :pid"
        params["pid"] = portfolio_id
    rows = session.execute(text(sql), params).all()

    for r in rows:
        res.scanned += 1
        symbol = r.symbol
        pid = r.portfolio_id
        asset_id = r.asset_id
        qty = Decimal(str(r.quantity))
        basis = Decimal(str(r.avg_cost))
        opened_at = r.opened_at
        held_days = _trading_days_between(opened_at.date(), as_of)

        lc = _latest_close(session, asset_id, as_of)
        if lc is None:
            res.skipped.append({
                "portfolio_id": pid, "symbol": symbol,
                "reason": "no_price_bar_for_mark",
            })
            continue
        last_d, last_px = lc
        unrl_pct = (last_px - basis) / basis

        reason: str | None = None
        if force_close_all:
            reason = "force_close_all_operator_override"
        elif unrl_pct >= take_profit:
            reason = f"take_profit({unrl_pct:.4f} >= {take_profit})"
        elif unrl_pct <= -stop_loss:
            reason = f"stop_loss({unrl_pct:.4f} <= {-stop_loss})"
        elif held_days >= max_hold:
            reason = f"max_hold({held_days}d >= {max_hold}d)"

        if reason is None:
            res.skipped.append({
                "portfolio_id": pid, "symbol": symbol,
                "unrealized_pct": float(unrl_pct),
                "held_days": held_days,
                "reason": "no_rule_triggered",
            })
            continue

        if not commit:
            res.closed.append({
                "portfolio_id": pid, "symbol": symbol,
                "asset_id": asset_id, "qty": float(qty),
                "basis": float(basis), "last_close": float(last_px),
                "last_close_date": last_d.isoformat(),
                "unrealized_pct": float(unrl_pct),
                "held_days": held_days,
                "reason": reason,
                "result": "dry_run_planned",
            })
            continue

        try:
            with session.begin_nested():
                result = submit_trade(
                    session,
                    portfolio_id=pid, asset_id=asset_id,
                    side="sell", quantity=qty,
                    submitted_at=submitted_at,
                    reason=f"exit_cycle: {reason}",
                    # BP9a — close the EXACT scanned lot. Equivalent to the
                    # legacy lookup when there is one open position per asset
                    # (live); required for correct per-lot closes under no-merge.
                    position_id=r.id,
                )
                if snapshot_equity:
                    pf = session.get(PaperPortfolio, pid)
                    if pf is not None:
                        snapshot_equity_now(
                            session, pf,
                            as_of=submitted_at.replace(hour=22),
                            source="live",
                        )
            realized = Decimal(str(result.realized_pnl or 0))
            res.realized_pnl_total += realized
            res.closed.append({
                "portfolio_id": pid, "symbol": symbol,
                "trade_id": str(result.trade_id),
                "qty": float(qty), "basis": float(basis),
                "fill_price": float(result.fill_price),
                "fill_ts": result.fill_ts.isoformat(),
                "realized_pnl": float(realized),
                "reason": reason,
                "result": "submitted",
            })
            logger.info(
                "[exit-cycle.submitted] {} {} qty={} basis={} "
                "fill={} pnl={:.4f} reason={}",
                pid[:8], symbol, qty, basis,
                result.fill_price, realized, reason,
            )
        except PaperTradeRejected as exc:
            res.skipped.append({
                "portfolio_id": pid, "symbol": symbol,
                "reason": f"exec_rejected:{exc}",
                "rule": reason,
            })
        except IntegrityError as exc:
            # P0-3B.3 — duplicate engine sell blocked by
            # ux_paper_trade_engine_sell_day (migration 098). The SAVEPOINT
            # rolls back only this close; the loop continues.
            res.skipped.append({
                "portfolio_id": pid, "symbol": symbol,
                "reason": "idempotency_unique_violation (migration 098): "
                          "duplicate engine sell blocked",
                "rule": reason,
            })
            logger.error(
                "[exit-cycle] IDEMPOTENCY VIOLATION {} {} rule={}: {}",
                pid[:8], symbol, reason, exc,
            )

    return res


def main(argv: list[str] | None = None) -> int:
    args = _argparse().parse_args(argv)
    if args.as_of:
        try:
            as_of = dt.date.fromisoformat(args.as_of)
        except ValueError:
            sys.stderr.write(
                f"REFUSED: --as-of must be ISO date, got "
                f"{args.as_of!r}\n",
            )
            return 2
    else:
        as_of = dt.datetime.now(dt.timezone.utc).date()

    if args.commit:
        if os.environ.get(CONFIRM_ENV, "") != CONFIRM_VALUE:
            sys.stderr.write(
                f"REFUSED: --commit requires {CONFIRM_ENV}="
                f"{CONFIRM_VALUE}.\n"
            )
            return 2
    if args.force_close_all and not args.commit:
        sys.stderr.write(
            "REFUSED: --force-close-all requires --commit (and env).\n"
        )
        return 2

    take_profit = _env_decimal("PAPER_TAKE_PROFIT_PCT", Decimal("0.08"))
    stop_loss = _env_decimal("PAPER_STOP_LOSS_PCT", Decimal("0.04"))
    max_hold_days = _env_int("PAPER_MAX_HOLD_DAYS", 10)

    logger.info(
        "[exit-cycle] as_of={} mode={} take_profit={} "
        "stop_loss={} max_hold={} force_close_all={}",
        as_of, "commit" if args.commit else "dry-run",
        take_profit, stop_loss, max_hold_days,
        args.force_close_all,
    )

    from apps.api.src.db import SessionLocal

    with SessionLocal() as session:
        res = run_exit_cycle(
            session,
            as_of=as_of,
            portfolio_id=None,
            take_profit_pct=take_profit,
            stop_loss_pct=stop_loss,
            max_hold_days=max_hold_days,
            commit=args.commit,
            force_close_all=args.force_close_all,
            snapshot_equity=True,
        )
        if args.commit:
            session.commit()

    summary = {
        "schema_version": 1,
        "as_of": as_of.isoformat(),
        "mode": "commit" if args.commit else "dry-run",
        "rules": {
            "take_profit_pct": str(take_profit),
            "stop_loss_pct": str(stop_loss),
            "max_hold_days": max_hold_days,
            "force_close_all": args.force_close_all,
        },
        "scanned": res.scanned,
        "closed_count": len(res.closed),
        "skipped_count": len(res.skipped),
        "realized_pnl_total": float(res.realized_pnl_total),
        "closed": res.closed,
        "skipped": res.skipped[:50],
        "skipped_total": len(res.skipped),
        "safety": {
            "live_execution_enabled": False,
            "ml_can_affect_trades": False,
            "fabricated_prices": False,
            "replay_recovery_manifest_touched": False,
            "same_bar_exits_allowed": False,
        },
    }
    logger.info(
        "[exit-cycle.summary] scanned={} closed={} skipped={} "
        "realized_pnl={:.4f}",
        res.scanned, len(res.closed), len(res.skipped),
        res.realized_pnl_total,
    )
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACT_DIR / ARTIFACT_NAME.format(
        date=as_of.isoformat(),
    )
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    logger.info("[exit-cycle] wrote artifact: {}", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
