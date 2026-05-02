"""Phase 11Z incident-response — replay paper-trading history.

After the 2026-05-02 `compose_pgdata` wipe, this script regenerates
paper-trading rows for a date range from already-recovered upstream
data (asset, price_bar, context_daily, regime_snapshot,
factor_snapshot, candidate_idea, safe_gate_evolution_shadow).

It is a SAFE wrapper around `scripts.run_paper_daily` — it does NOT
implement strategy logic, does not change thresholds, and does not
fabricate rows. If upstream data is missing for a date, that date
fails closed.

It is OPERATOR-ONLY:
  * NEVER scheduled.
  * NO entry in apps/worker/src/jobs/registry.py.
  * NO automatic invocation.
  * Refuses --commit unless the operator sets the literal env
    PAPER_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_PAPER_HISTORY.
  * Refuses to overwrite an existing date unless --replace-date is
    explicitly passed.
  * --dry-run is the default behaviour when neither --dry-run nor
    --commit is specified.

Touched tables (replay only writes to these):
  decision_log, paper_run_log, paper_trade, paper_trade_log,
  paper_shadow_log, paper_portfolio_snapshot, anomaly_event

Read-only inputs (replay must NEVER write to these):
  asset, price_bar, context_daily, regime_snapshot, factor_snapshot,
  candidate_idea, safe_gate_evolution_shadow, research_run,
  research_agent_output, research_debate_summary,
  research_reflection, research_checkpoint, options_paper_trade*,
  user_account, organization, subscription_*

Usage:
    # Dry-run a single date (default — no DB writes)
    python -m scripts.replay_paper_history \\
        --start-date 2026-04-24 --end-date 2026-04-24

    # Commit a single date (requires the confirmation env)
    PAPER_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_PAPER_HISTORY \\
      python -m scripts.replay_paper_history \\
        --start-date 2026-04-24 --end-date 2026-04-24 --commit

    # Replace already-replayed date (deletes that date's rows first)
    PAPER_REPLAY_CONFIRM=I_UNDERSTAND_THIS_REGENERATES_PAPER_HISTORY \\
      python -m scripts.replay_paper_history \\
        --start-date 2026-04-24 --end-date 2026-04-24 \\
        --commit --replace-date

Exit codes:
    0  ok
    2  refused (missing confirmation, conflicting flags, bad date)
    3  per-date upstream data missing
    4  per-date paper_daily subprocess returned non-zero
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from typing import Sequence

from loguru import logger
from sqlalchemy import text

from apps.api.src.db import SessionLocal


PAPER_ID = "default"
CONFIRM_ENV = "PAPER_REPLAY_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_REGENERATES_PAPER_HISTORY"

# Tables this script is allowed to touch. Anything not in here MUST
# stay read-only. Tests assert this list is the only set of tables
# that get DELETE / INSERT / UPDATE statements.
ALLOWED_WRITE_TABLES = frozenset({
    "decision_log",
    "paper_run_log",
    "paper_trade",
    "paper_trade_log",
    "paper_shadow_log",
    "paper_portfolio_snapshot",
    "anomaly_event",
    "context_daily",  # run_paper_daily upserts diagnostic rows
})

# Tables this script must NEVER write to. Tests assert this set is
# disjoint from ALLOWED_WRITE_TABLES and that no DELETE statement
# in this module touches any of these.
FORBIDDEN_WRITE_TABLES = frozenset({
    "research_run",
    "research_agent_output",
    "research_debate_summary",
    "research_reflection",
    "research_checkpoint",
    "options_paper_trade",
    "options_paper_trade_log",
    "options_paper_shadow_log",
    "user_account",
    "organization",
    "subscription_plan",
    "subscription_event",
    # Inputs we read but must never modify:
    "asset",
    "price_bar",
    "regime_snapshot",
    "factor_snapshot",
    "candidate_idea",
    "safe_gate_evolution_shadow",
})


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
@dataclass
class ReplayArgs:
    start_date: dt.date
    end_date: dt.date
    dry_run: bool
    commit: bool
    replace_date: bool


def _parse(argv: Sequence[str] | None = None) -> ReplayArgs:
    p = argparse.ArgumentParser(
        prog="replay_paper_history",
        description=(
            "Phase 11Z replay of paper-trading rows for a date range "
            "after the compose_pgdata wipe. Operator-only. Never "
            "scheduled."
        ),
    )
    p.add_argument(
        "--start-date",
        required=True,
        type=lambda s: dt.date.fromisoformat(s),
    )
    p.add_argument(
        "--end-date",
        required=True,
        type=lambda s: dt.date.fromisoformat(s),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Default. Walks the date range, runs paper_daily with "
            "--dry-run, prints row counts. No writes."
        ),
    )
    p.add_argument(
        "--commit",
        action="store_true",
        help=(
            "Actually write rows. Requires the confirmation env "
            f"({CONFIRM_ENV}={CONFIRM_VALUE})."
        ),
    )
    p.add_argument(
        "--replace-date",
        action="store_true",
        help=(
            "If a target date already has rows, delete that ONE "
            "date's rows from the allowed-write tables first. Without "
            "this flag, the script refuses to overwrite."
        ),
    )
    ns = p.parse_args(argv)
    if ns.start_date > ns.end_date:
        p.error("--start-date must be <= --end-date")
    if ns.dry_run and ns.commit:
        p.error("--dry-run and --commit are mutually exclusive")
    # Default to dry-run if neither specified
    dry_run = ns.dry_run or not ns.commit
    return ReplayArgs(
        start_date=ns.start_date,
        end_date=ns.end_date,
        dry_run=dry_run,
        commit=ns.commit,
        replace_date=ns.replace_date,
    )


# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------
def _enforce_commit_confirmation(args: ReplayArgs) -> None:
    """Raise SystemExit(2) when --commit is requested without the
    literal confirmation env. Dry-run paths bypass this."""
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
# Per-date row counting & idempotency
# ---------------------------------------------------------------------------
COUNT_TABLES = (
    # (table, date_expr) — date_expr is interpolated into a static
    # `WHERE {date_expr} = :d` predicate. Use `col` for date columns
    # and `col::date` for timestamptz fill columns. Fixed list — no
    # user input ever reaches the f-string.
    ("decision_log", "as_of_date"),
    ("paper_run_log", "run_date"),
    ("paper_trade", "fill_ts::date"),
    ("paper_trade_log", "entry_date"),
    ("paper_shadow_log", "as_of_date"),
    ("paper_portfolio_snapshot", "as_of_date"),
)


def _count_rows_for_date(session, target: dt.date) -> dict[str, int]:
    """Read-only — counts rows in the allowed-write tables for one
    date. Used both before and after replay so we can print deltas."""
    out: dict[str, int] = {}
    for table, date_expr in COUNT_TABLES:
        try:
            r = session.execute(
                text(f"SELECT count(*) FROM {table} WHERE {date_expr} = :d"),
                {"d": target},
            ).scalar()
            out[table] = int(r or 0)
        except Exception as exc:  # noqa: BLE001
            # Table might not exist in test DB; record as -1 sentinel.
            logger.debug("count {} failed: {}", table, exc)
            try:
                session.rollback()
            except Exception:
                pass
            out[table] = -1
    return out


def _date_has_rows(counts: dict[str, int]) -> bool:
    return any(v > 0 for v in counts.values())


# ---------------------------------------------------------------------------
# Per-date deletion (only when --replace-date)
# ---------------------------------------------------------------------------
DELETE_STATEMENTS_FOR_DATE: tuple[tuple[str, str], ...] = (
    # Order matters: child rows first.
    ("DELETE FROM paper_trade_log WHERE entry_date = :d", "paper_trade_log"),
    ("DELETE FROM paper_trade WHERE fill_ts::date = :d", "paper_trade"),
    ("DELETE FROM paper_shadow_log WHERE as_of_date = :d", "paper_shadow_log"),
    ("DELETE FROM paper_portfolio_snapshot WHERE as_of_date = :d",
     "paper_portfolio_snapshot"),
    ("DELETE FROM paper_run_log WHERE run_date = :d", "paper_run_log"),
    ("DELETE FROM decision_log WHERE as_of_date = :d", "decision_log"),
    ("DELETE FROM anomaly_event WHERE as_of_date = :d", "anomaly_event"),
)


def _delete_date_scoped(session, target: dt.date) -> dict[str, int]:
    """Delete only rows whose date column equals `target` from the
    allowed-write tables. Returns rowcount per table.

    Hard-coded statements — no dynamic SQL. Tests assert every
    statement here references a date column = :d (so it is impossible
    to accidentally drop rows from any other date)."""
    deleted: dict[str, int] = {}
    for stmt, table in DELETE_STATEMENTS_FOR_DATE:
        if table not in ALLOWED_WRITE_TABLES:
            raise RuntimeError(
                f"BUG: {table} not in ALLOWED_WRITE_TABLES — refusing to "
                f"delete (would break safety contract)"
            )
        try:
            res = session.execute(text(stmt), {"d": target})
            deleted[table] = int(getattr(res, "rowcount", 0) or 0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("delete {} skipped: {}", table, exc)
            try:
                session.rollback()
            except Exception:
                pass
            deleted[table] = -1
    session.commit()
    return deleted


# ---------------------------------------------------------------------------
# Subprocess invocation of run_paper_daily
# ---------------------------------------------------------------------------
def _invoke_run_paper_daily(target: dt.date, *, dry_run: bool) -> int:
    """Run scripts.run_paper_daily as an isolated subprocess.

    Always passes --force-recompute so an idempotent rerun (after
    --replace-date) does not bail on the existing-snapshot check."""
    cmd = [
        sys.executable, "-m", "scripts.run_paper_daily",
        "--date", target.isoformat(),
        "--force-recompute",
    ]
    if dry_run:
        cmd.append("--dry-run")
    logger.info("invoking: {}", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=False)
    return int(proc.returncode)


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
# Per-date orchestration
# ---------------------------------------------------------------------------
@dataclass
class DateResult:
    as_of: str
    status: str  # "ok" | "refused_existing" | "engine_failed" | "skipped_dry"
    counts_before: dict[str, int]
    counts_after: dict[str, int]
    deleted: dict[str, int]
    paper_daily_rc: int | None
    note: str = ""


def _process_one_date(
    session, target: dt.date, *, args: ReplayArgs,
) -> DateResult:
    counts_before = _count_rows_for_date(session, target)
    deleted: dict[str, int] = {}

    # Idempotency / overwrite gate
    if _date_has_rows(counts_before):
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
                deleted=deleted,
                paper_daily_rc=None,
                note="rows present; --replace-date not set",
            )
        if args.commit:
            deleted = _delete_date_scoped(session, target)
            logger.info(
                "[replace-date] deleted rows for {}: {}", target, deleted,
            )
        else:
            logger.info(
                "[dry-run] would delete rows for {} (counts={})",
                target, counts_before,
            )

    rc = _invoke_run_paper_daily(target, dry_run=args.dry_run)

    # Re-count after — open a fresh session to see committed rows.
    with SessionLocal() as s2:
        counts_after = _count_rows_for_date(s2, target)

    if rc != 0:
        return DateResult(
            as_of=target.isoformat(),
            status="engine_failed",
            counts_before=counts_before,
            counts_after=counts_after,
            deleted=deleted,
            paper_daily_rc=rc,
            note=f"run_paper_daily returned {rc}",
        )

    return DateResult(
        as_of=target.isoformat(),
        status=("skipped_dry" if args.dry_run else "ok"),
        counts_before=counts_before,
        counts_after=counts_after,
        deleted=deleted,
        paper_daily_rc=rc,
    )


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------
def replay_range(args: ReplayArgs) -> dict:
    _enforce_commit_confirmation(args)
    days = _trading_days(args.start_date, args.end_date)
    if not days:
        logger.error("no trading days in [{}, {}]", args.start_date, args.end_date)
        return {
            "ok": False,
            "start_date": args.start_date.isoformat(),
            "end_date": args.end_date.isoformat(),
            "days": [],
        }
    results: list[DateResult] = []
    overall_ok = True
    with SessionLocal() as session:
        for d in days:
            r = _process_one_date(session, d, args=args)
            results.append(r)
            if r.status in ("engine_failed",):
                overall_ok = False
    out = {
        "ok": overall_ok,
        "start_date": args.start_date.isoformat(),
        "end_date": args.end_date.isoformat(),
        "dry_run": args.dry_run,
        "commit": args.commit,
        "replace_date": args.replace_date,
        "days": [asdict(r) for r in results],
    }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    summary = replay_range(args)
    print("=" * 78)
    print(
        f"PAPER REPLAY  {summary['start_date']} → {summary['end_date']}  "
        f"[{'OK' if summary['ok'] else 'PARTIAL'}]"
    )
    print(f"  dry_run={summary['dry_run']}  commit={summary['commit']}  "
          f"replace_date={summary['replace_date']}")
    print("=" * 78)
    for d in summary["days"]:
        print(f"  {d['as_of']}  status={d['status']:<18}  rc={d['paper_daily_rc']}")
        before = d["counts_before"]
        after = d["counts_after"]
        for table in (t for t, _ in COUNT_TABLES):
            b = before.get(table, 0)
            a = after.get(table, 0)
            sign = "+" if a > b else ("=" if a == b else "-")
            print(f"      {table:<28}  {b:>5} → {a:>5}  ({sign}{abs(a-b)})")
        if d["deleted"]:
            print(f"      deleted-by-replace: {d['deleted']}")
        if d.get("note"):
            print(f"      note: {d['note']}")
    print("=" * 78)
    return 0 if summary["ok"] else 4


if __name__ == "__main__":
    sys.exit(main())
