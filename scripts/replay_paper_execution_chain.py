"""Phase 11Z incident-response — replay the EXECUTION chain.

After the 2026-05-02 `compose_pgdata` wipe, the selector replay
(`scripts.replay_paper_history`) regenerated decision_log /
paper_run_log but produced 0 paper_trade rows because the lost
trades came from a different code path:

    account
      └── run_recommendations_for_all_accounts
            └── recommendation
                  └── run_paper_trading(as_of)
                        └── submit_trade
                              └── paper_trade + paper_position

This script rebuilds that chain HONESTLY for an operator-supplied
date range. No fabrication, no manual paper_trade INSERTs, no
threshold changes. All writes go through:

  * `apps.api.src.domain.recommendations.recommendation_engine`
    (run via `apps.worker.src.jobs.registry`
    `run_recommendations_for_all_accounts`)
  * `apps.worker.src.jobs.run_paper_trading.run_paper_trading(as_of)`
    which internally calls `auto_trade_portfolio` →
    `apps.api.src.domain.paper_trading.paper_execution.submit_trade`.

Replay vs live distinction (auto_trader convention):

    `run_paper_trading(as_of=date)` switches signal source from
    `recommendation` (live) to `candidate_idea.as_of_date`
    (historical). We have 504 candidate_idea rows across 8 dates,
    so historical replay is well-defined for those dates only.

Operator-only — NEVER scheduled, NO worker registry entry.

Usage:
    # Default — dry-run (no DB writes)
    python -m scripts.replay_paper_execution_chain \\
        --start-date 2026-04-24 --end-date 2026-05-01 \\
        --account-name "Replay Recovery Account" \\
        --initial-cash 100000

    # Commit (requires confirmation env)
    PAPER_EXEC_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_EXECUTION_HISTORY \\
      python -m scripts.replay_paper_execution_chain \\
        --start-date 2026-04-24 --end-date 2026-05-01 \\
        --account-name "Replay Recovery Account" \\
        --initial-cash 100000 --commit

    # Replace already-replayed date
    PAPER_EXEC_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_EXECUTION_HISTORY \\
      python -m scripts.replay_paper_execution_chain \\
        --start-date 2026-04-24 --end-date 2026-04-24 \\
        --account-name "Replay Recovery Account" --initial-cash 100000 \\
        --commit --replace-date

Exit codes:
  0  ok
  2  refused (missing confirmation, conflicting flags, bad date)
  3  prerequisites missing (e.g., no candidate_idea rows in window)
  4  per-date job returned non-zero
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys
from dataclasses import dataclass, asdict
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from loguru import logger
from sqlalchemy import select, text

from apps.api.src.db import SessionLocal


CONFIRM_ENV = "PAPER_EXEC_REPLAY_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_REGENERATES_EXECUTION_HISTORY"

# Tables this script is allowed to MUTATE. All writes happen through
# existing engine functions — we never INSERT into these directly,
# we only DELETE from them when --replace-date is set.
ALLOWED_WRITE_TABLES = frozenset({
    "account",                    # created once on first --commit
    "paper_portfolio",            # created once on first --commit
    "paper_trade",                # via submit_trade
    "paper_position",             # via submit_trade / position close
    "paper_equity_snapshot",      # via snapshot_equity_now
    "recommendation",             # via recommendation engine
    "recommendation_evidence",    # via recommendation engine
    "recommendation_outcome",     # via recommendation engine
})

# Tables this script must NEVER write to. Tests pin the disjointness.
FORBIDDEN_WRITE_TABLES = frozenset({
    # Selector path — handled by replay_paper_history, not us.
    "decision_log",
    "paper_run_log",
    "paper_trade_log",
    "paper_shadow_log",
    "paper_portfolio_snapshot",
    # Research / options / auth / org — entirely out of scope.
    "research_run",
    "research_agent_output",
    "research_debate_summary",
    "research_reflection",
    "research_checkpoint",
    "options_paper_trade",
    "options_paper_trade_leg",
    "options_paper_trade_log",
    "options_paper_shadow_log",
    "options_trade_lifecycle_event",
    "user_account",
    "organization",
    "subscription_plan",
    "subscription_event",
    # Read-only inputs — must never be modified.
    "asset",
    "price_bar",
    "context_daily",
    "regime_snapshot",
    "factor_snapshot",
    "candidate_idea",
    "safe_gate_evolution_shadow",
    "transaction",
    "lot",
    "lot_close",
})


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
@dataclass
class ReplayArgs:
    start_date: dt.date
    end_date: dt.date
    account_name: str
    initial_cash: Decimal
    dry_run: bool
    commit: bool
    replace_date: bool


def _parse(argv: Sequence[str] | None = None) -> ReplayArgs:
    p = argparse.ArgumentParser(
        prog="replay_paper_execution_chain",
        description=(
            "Phase 11Z replay of the paper execution chain "
            "(account → recs → paper_trading) for a date range. "
            "Operator-only. Never scheduled."
        ),
    )
    p.add_argument(
        "--start-date", required=True,
        type=lambda s: dt.date.fromisoformat(s),
    )
    p.add_argument(
        "--end-date", required=True,
        type=lambda s: dt.date.fromisoformat(s),
    )
    p.add_argument("--account-name", required=True)
    p.add_argument(
        "--initial-cash", required=True,
        type=lambda s: Decimal(str(s)),
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--replace-date", action="store_true")
    ns = p.parse_args(argv)
    if ns.start_date > ns.end_date:
        p.error("--start-date must be <= --end-date")
    if ns.dry_run and ns.commit:
        p.error("--dry-run and --commit are mutually exclusive")
    if ns.initial_cash <= 0:
        p.error("--initial-cash must be positive")
    return ReplayArgs(
        start_date=ns.start_date,
        end_date=ns.end_date,
        account_name=ns.account_name,
        initial_cash=ns.initial_cash,
        dry_run=ns.dry_run or not ns.commit,
        commit=ns.commit,
        replace_date=ns.replace_date,
    )


# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------
def _enforce_commit_confirmation(args: ReplayArgs) -> None:
    if not args.commit:
        return
    actual = os.environ.get(CONFIRM_ENV, "")
    if actual != CONFIRM_VALUE:
        logger.error(
            "REFUSED: --commit requires {}={} in env. Got {!r}.",
            CONFIRM_ENV, CONFIRM_VALUE, actual,
        )
        raise SystemExit(2)


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------
COUNT_TABLES_GLOBAL = (
    "account", "recommendation",
    "decision_log", "paper_trade", "paper_trade_log",
    "paper_position", "paper_run_log", "paper_shadow_log",
    "paper_portfolio", "paper_equity_snapshot",
)

# (table, where-expression-with-:d) — for per-date scoping.
COUNT_TABLES_PER_DATE: tuple[tuple[str, str], ...] = (
    ("paper_trade",            "fill_ts::date = :d"),
    ("paper_position",         "opened_at::date = :d"),
    ("paper_equity_snapshot",  "snapshot_date::date = :d"),
    ("recommendation",         "generated_at::date = :d"),
)


def _count_global(session) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in COUNT_TABLES_GLOBAL:
        try:
            out[t] = int(
                session.execute(text(f"SELECT count(*) FROM {t}")).scalar() or 0
            )
        except Exception:  # noqa: BLE001
            session.rollback()
            out[t] = -1
    return out


def _count_per_date(session, target: dt.date) -> dict[str, int]:
    out: dict[str, int] = {}
    for tbl, where in COUNT_TABLES_PER_DATE:
        try:
            out[tbl] = int(session.execute(
                text(f"SELECT count(*) FROM {tbl} WHERE {where}"),
                {"d": target},
            ).scalar() or 0)
        except Exception:  # noqa: BLE001
            session.rollback()
            out[tbl] = -1
    return out


# ---------------------------------------------------------------------------
# Account / portfolio bootstrap
# ---------------------------------------------------------------------------
def _ensure_account_and_portfolio(
    session, *, name: str, initial_cash: Decimal, commit: bool,
) -> tuple[str | None, str | None]:
    """Idempotent. Returns (account_id, portfolio_id) or (None, None)
    in dry-run if nothing exists yet (so the rest of the run can
    report what WOULD happen)."""
    from apps.api.src.db.models import Account, PaperPortfolio

    acct = session.scalars(
        select(Account).where(Account.name == name)
    ).first()
    portfolio = session.scalars(
        select(PaperPortfolio).where(PaperPortfolio.name == name)
    ).first()

    if acct and portfolio:
        return acct.id, portfolio.id

    if not commit:
        # Dry-run path: do not create. Surface the plan and continue.
        logger.info(
            "[dry-run] account+portfolio missing; would create "
            "name={!r} initial_cash={}",
            name, initial_cash,
        )
        return (acct.id if acct else None,
                portfolio.id if portfolio else None)

    if not acct:
        acct = Account(
            name=name,
            account_type="paper_replay",
            currency="USD",
            is_active=True,
        )
        session.add(acct)
        session.flush()
        logger.info("created account name={!r} id={}", name, acct.id)
    if not portfolio:
        portfolio = PaperPortfolio(
            name=name,
            starting_cash=initial_cash,
            cash=initial_cash,
            is_active=True,
        )
        session.add(portfolio)
        session.flush()
        logger.info(
            "created paper_portfolio name={!r} id={} starting_cash={}",
            name, portfolio.id, initial_cash,
        )
    session.commit()
    return acct.id, portfolio.id


# ---------------------------------------------------------------------------
# Per-date scoped delete (only when --replace-date)
# ---------------------------------------------------------------------------
DELETE_STATEMENTS_FOR_DATE: tuple[tuple[str, str], ...] = (
    # Order: child rows first.
    ("DELETE FROM paper_trade WHERE fill_ts::date = :d", "paper_trade"),
    ("DELETE FROM paper_position WHERE opened_at::date = :d AND is_open = false",
     "paper_position"),
    ("DELETE FROM paper_position WHERE opened_at::date = :d AND is_open = true",
     "paper_position"),
    ("DELETE FROM paper_equity_snapshot WHERE snapshot_date::date = :d",
     "paper_equity_snapshot"),
)


def _delete_date_scoped(session, target: dt.date) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for stmt, tbl in DELETE_STATEMENTS_FOR_DATE:
        if tbl not in ALLOWED_WRITE_TABLES:
            raise RuntimeError(
                f"BUG: {tbl} not in ALLOWED_WRITE_TABLES — refusing"
            )
        try:
            res = session.execute(text(stmt), {"d": target})
            n = int(getattr(res, "rowcount", 0) or 0)
            deleted[tbl] = deleted.get(tbl, 0) + n
        except Exception as exc:  # noqa: BLE001
            logger.debug("delete {} failed: {}", tbl, exc)
            session.rollback()
            deleted[tbl] = deleted.get(tbl, -1)
    session.commit()
    return deleted


def _has_downstream_dates(
    session, *, target: dt.date, end: dt.date,
) -> bool:
    """If --replace-date is used for `target`, warn when other
    in-window replay dates after `target` already have rows. Their
    cash/position state depends on `target`'s state, so deleting
    just `target` leaves them inconsistent."""
    if target >= end:
        return False
    n = session.execute(text("""
        SELECT count(*) FROM paper_trade
        WHERE fill_ts::date > :start AND fill_ts::date <= :end
    """), {"start": target, "end": end}).scalar() or 0
    return int(n) > 0


# ---------------------------------------------------------------------------
# Per-date orchestration
# ---------------------------------------------------------------------------
@dataclass
class DateResult:
    as_of: str
    status: str
    counts_before: dict[str, int]
    counts_after: dict[str, int]
    deleted: dict[str, int]
    note: str = ""


async def _run_paper_trading_for_date(target: dt.date) -> None:
    """Invoke the existing run_paper_trading worker job with as_of."""
    from apps.worker.src.jobs.run_paper_trading import run_paper_trading
    await run_paper_trading(as_of=target)


def _process_one_date(
    session, target: dt.date, *, args: ReplayArgs, end: dt.date,
) -> DateResult:
    counts_before = _count_per_date(session, target)
    deleted: dict[str, int] = {}
    has_existing = any(v > 0 for v in counts_before.values())

    if has_existing:
        if not args.replace_date:
            logger.warning(
                "refusing to replay {}: rows already exist (use "
                "--replace-date to override). counts={}",
                target, counts_before,
            )
            return DateResult(
                as_of=target.isoformat(),
                status="refused_existing",
                counts_before=counts_before,
                counts_after=counts_before,
                deleted={},
                note="rows present; --replace-date not set",
            )
        if _has_downstream_dates(session, target=target, end=end):
            logger.warning(
                "[{}] WARNING: trades exist on dates after {} but "
                "before/at {}. Cash + position chain may be "
                "inconsistent. Replay all later dates with "
                "--replace-date too.",
                target, target, end,
            )
        if args.commit:
            deleted = _delete_date_scoped(session, target)
            logger.info(
                "[replace-date] deleted rows for {}: {}", target, deleted,
            )
        else:
            logger.info(
                "[dry-run] would delete rows for {}: {}", target, counts_before,
            )

    if args.dry_run:
        logger.info(
            "[dry-run] would invoke run_paper_trading(as_of={})", target,
        )
        with SessionLocal() as s2:
            counts_after = _count_per_date(s2, target)
        return DateResult(
            as_of=target.isoformat(),
            status="skipped_dry",
            counts_before=counts_before,
            counts_after=counts_after,
            deleted=deleted,
        )

    try:
        asyncio.run(_run_paper_trading_for_date(target))
    except Exception as exc:  # noqa: BLE001
        logger.error("run_paper_trading({}) failed: {}", target, exc)
        with SessionLocal() as s2:
            counts_after = _count_per_date(s2, target)
        return DateResult(
            as_of=target.isoformat(),
            status="engine_failed",
            counts_before=counts_before,
            counts_after=counts_after,
            deleted=deleted,
            note=f"{type(exc).__name__}: {exc}",
        )

    with SessionLocal() as s2:
        counts_after = _count_per_date(s2, target)
    return DateResult(
        as_of=target.isoformat(),
        status="ok",
        counts_before=counts_before,
        counts_after=counts_after,
        deleted=deleted,
    )


# ---------------------------------------------------------------------------
# Recommendations bootstrap (runs once per script invocation)
# ---------------------------------------------------------------------------
async def _run_recommendations_once() -> None:
    from apps.worker.src.jobs.registry import (
        run_recommendations_for_all_accounts,
    )
    await run_recommendations_for_all_accounts()


# ---------------------------------------------------------------------------
# Trading-day enumeration
# ---------------------------------------------------------------------------
def _trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    out: list[dt.date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# Candidate_idea coverage check
# ---------------------------------------------------------------------------
def _candidate_idea_coverage(session, days: list[dt.date]) -> dict[str, int]:
    """For each business day, count candidate_idea rows. as_of replay
    consumes these directly — without rows we can't fill anything."""
    out: dict[str, int] = {}
    for d in days:
        try:
            n = session.execute(
                text("SELECT count(*) FROM candidate_idea WHERE as_of_date = :d"),
                {"d": d},
            ).scalar() or 0
            out[d.isoformat()] = int(n)
        except Exception:  # noqa: BLE001
            session.rollback()
            out[d.isoformat()] = -1
    return out


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------
def replay_chain(args: ReplayArgs) -> dict:
    _enforce_commit_confirmation(args)
    days = _trading_days(args.start_date, args.end_date)
    if not days:
        logger.error("no trading days in [{}, {}]", args.start_date, args.end_date)
        return {"ok": False, "days": []}

    with SessionLocal() as session:
        before_global = _count_global(session)
        coverage = _candidate_idea_coverage(session, days)
    missing = [d for d, n in coverage.items() if n <= 0]
    if missing:
        logger.warning(
            "candidate_idea missing or zero on {} date(s): {}. "
            "Auto-trader as_of replay needs candidate_idea — these "
            "dates will produce 0 trades.",
            len(missing), missing,
        )

    with SessionLocal() as session:
        acct_id, port_id = _ensure_account_and_portfolio(
            session,
            name=args.account_name,
            initial_cash=args.initial_cash,
            commit=args.commit,
        )

    # Run recs once (live mode). For historical as_of replay,
    # auto_trader uses candidate_idea — recs are run for spec
    # compliance; their output is not load-bearing for fills.
    if args.commit:
        try:
            asyncio.run(_run_recommendations_once())
        except Exception as exc:  # noqa: BLE001
            logger.warning("recommendation engine raised: {}", exc)
    else:
        logger.info("[dry-run] skipping recommendation engine call")

    results: list[DateResult] = []
    overall_ok = True
    with SessionLocal() as session:
        for d in days:
            r = _process_one_date(session, d, args=args, end=args.end_date)
            results.append(r)
            if r.status == "engine_failed":
                overall_ok = False

    with SessionLocal() as session:
        after_global = _count_global(session)

    return {
        "ok": overall_ok,
        "start_date": args.start_date.isoformat(),
        "end_date": args.end_date.isoformat(),
        "account_name": args.account_name,
        "account_id": acct_id,
        "portfolio_id": port_id,
        "dry_run": args.dry_run,
        "commit": args.commit,
        "replace_date": args.replace_date,
        "candidate_idea_coverage": coverage,
        "before_global": before_global,
        "after_global": after_global,
        "days": [asdict(r) for r in results],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    summary = replay_chain(args)
    print("=" * 78)
    print(
        f"PAPER EXECUTION REPLAY  {summary['start_date']} → {summary['end_date']}  "
        f"[{'OK' if summary['ok'] else 'PARTIAL'}]"
    )
    print(f"  account={summary['account_name']!r}  "
          f"acct_id={summary['account_id']}  port_id={summary['portfolio_id']}")
    print(f"  dry_run={summary['dry_run']}  commit={summary['commit']}  "
          f"replace_date={summary['replace_date']}")
    print("=" * 78)
    print("CANDIDATE_IDEA COVERAGE:")
    for d, n in summary["candidate_idea_coverage"].items():
        print(f"  {d}: {n} rows")
    print()
    print("GLOBAL ROW COUNT DELTAS:")
    for t in COUNT_TABLES_GLOBAL:
        b = summary["before_global"].get(t, 0)
        a = summary["after_global"].get(t, 0)
        sign = "+" if a > b else ("=" if a == b else "-")
        print(f"  {t:<28}  {b:>5} → {a:>5}  ({sign}{abs(a-b)})")
    print()
    print("PER-DATE RESULTS:")
    for d in summary["days"]:
        print(f"  {d['as_of']}  status={d['status']:<18}")
        for tbl, _w in COUNT_TABLES_PER_DATE:
            b = d["counts_before"].get(tbl, 0)
            a = d["counts_after"].get(tbl, 0)
            sign = "+" if a > b else ("=" if a == b else "-")
            print(f"      {tbl:<28}  {b:>5} → {a:>5}  ({sign}{abs(a-b)})")
        if d["deleted"]:
            print(f"      deleted-by-replace: {d['deleted']}")
        if d.get("note"):
            print(f"      note: {d['note']}")
    print("=" * 78)
    return 0 if summary["ok"] else 4


if __name__ == "__main__":
    sys.exit(main())
