"""Phase 11O - Manual options paper evaluation runner CLI.

Usage:
    python -m scripts.run_options_paper_eval --date YYYY-MM-DD ...

Default mode is --dry-run (no DB writes). The --commit flag requires
either --confirm-commit YES on the command line OR an interactive TTY
prompt typed YES.

Hard guarantees enforced by apps.api.src.options.paper.eval_runner:
  * OPTIONS_ENABLED must be True
  * OPTIONS_PAPER_ONLY must be True
  * OPTIONS_ML_CAN_AFFECT_TRADES must be False
  * No broker / live / execution module may be loaded
  * The worker job registry must not contain any options job

Exit codes (per spec):
  0  success (dry-run or commit)
  2  precondition / safety failure
  3  chain ingest failure
  4  zero qualified observations
  5  open_trade rejection during commit
  9  internal error
"""

from __future__ import annotations

import argparse
import datetime
import sys
from decimal import Decimal
from typing import Sequence

from apps.api.src.options.data.chain_ingest import DEFAULT_UNIVERSE
from apps.api.src.options.paper.eval_runner import (
    EvalRunnerCommitError,
    EvalRunnerIngestError,
    EvalRunnerSafetyError,
    run,
)
from apps.api.src.options.paper.eval_runner_models import (
    RunnerConfig,
    RunnerSummary,
)


def _csv_upper(s: str) -> tuple[str, ...]:
    return tuple(x.strip().upper() for x in s.split(",") if x.strip())


def _csv(s: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in s.split(",") if x.strip())


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_options_paper_eval",
        description=(
            "Manual options paper evaluation runner. Default: dry-run. "
            "No live trading. No scheduler. No automation."
        ),
    )
    p.add_argument(
        "--date",
        type=lambda s: datetime.date.fromisoformat(s),
        default=datetime.date.today(),
        help="evaluation date (UTC); default = today",
    )
    p.add_argument(
        "--underlyings",
        type=_csv_upper,
        default=tuple(DEFAULT_UNIVERSE),
        help="comma-separated underlyings; default = SPY,QQQ,IWM,GLD,TLT",
    )
    p.add_argument(
        "--strategies",
        type=_csv,
        default=None,
        help="optional comma-separated rule_id filter",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="default; no DB writes")
    mode.add_argument("--commit", action="store_true",
                      help="open paper trades; requires --confirm-commit YES")
    p.add_argument("--max-open", type=int, default=5,
                   help="hard cap on planned trades (1..25); default=5")
    p.add_argument("--explain", action="store_true",
                   help="verbose per-observation log")
    p.add_argument("--skip-ingest", action="store_true",
                   help="skip the chain snapshot step")
    p.add_argument("--confirm-commit", default=None,
                   help='must be the literal string "YES" to commit')
    return p.parse_args(argv)


def _confirm(args: argparse.Namespace) -> bool:
    if not args.commit:
        return True
    if args.confirm_commit == "YES":
        return True
    if sys.stdin.isatty():
        sys.stdout.write("Type YES to confirm commit: ")
        sys.stdout.flush()
        line = sys.stdin.readline().strip()
        return line == "YES"
    return False


def _fmt_money(d: Decimal | None) -> str:
    if d is None:
        return "n/a"
    return f"${d:.2f}"


def _render(summary: RunnerSummary) -> str:
    cfg = summary.config
    lines: list[str] = []
    lines.append(
        f"[ingest] inserted={summary.n_chain_inserted}"
    )
    lines.append(
        "[collect] observations total="
        f"{summary.n_observations_total} qualified={summary.n_qualified}"
    )
    lines.append(
        f"[plan] planned={summary.n_planned} "
        f"rejected={summary.n_planned_rejected}"
    )
    lines.append(
        "[dedupe] duplicate_open_today="
        f"{summary.n_existing_open_trade_dedup}"
    )
    lines.append(f"[cap] max_open={cfg.max_open}")
    lines.append("")

    label = (
        "DRY-RUN -- no DB writes"
        if cfg.dry_run else
        "COMMIT -- opening paper trades"
    )
    lines.append(label)
    lines.append("-" * 76)

    if cfg.commit:
        lines.append(
            " # | underlying | rule_id                       "
            "| trade_id | net_credit | max_loss"
        )
    else:
        lines.append(
            " # | underlying | rule_id                       "
            "| legs | net_credit | max_loss | qual"
        )
    lines.append("-" * 76)

    for i, p in enumerate(summary.planned_trades, start=1):
        credit = _fmt_money(p.entry_credit_dollars)
        max_loss = _fmt_money(
            p.risk.max_loss_dollars if p.risk is not None else None
        )
        if cfg.commit:
            tid = (
                str(summary.committed_trade_ids[i - 1])
                if i - 1 < len(summary.committed_trade_ids)
                else "--"
            )
            lines.append(
                f"{i:2d} | {p.underlying:<10} | {p.rule_id:<28} "
                f"| {tid:>8} | {credit:>10} | {max_loss:>8}"
            )
        else:
            lines.append(
                f"{i:2d} | {p.underlying:<10} | {p.rule_id:<28} "
                f"| {len(p.legs):>4} | {credit:>10} | {max_loss:>8} "
                f"| {'yes' if p.qualified else 'no'}"
            )

    if cfg.dry_run:
        lines.append("")
        lines.append(
            "next step: re-run with --commit --confirm-commit YES"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    args = _parse_args(raw)

    commit = bool(args.commit)
    dry_run = not commit

    if commit and not _confirm(args):
        sys.stderr.write(
            "commit confirmation required: pass --confirm-commit YES "
            "or type YES at the interactive prompt\n"
        )
        return 2

    try:
        config = RunnerConfig(
            date=args.date,
            underlyings=tuple(args.underlyings),
            strategy_filter=args.strategies,
            dry_run=dry_run,
            commit=commit,
            max_open=int(args.max_open),
            explain=bool(args.explain),
            skip_ingest=bool(args.skip_ingest),
        )
    except ValueError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return 2

    try:
        summary = run(config)
    except EvalRunnerSafetyError as exc:
        sys.stderr.write(f"[safety] {exc}\n")
        return 2
    except EvalRunnerIngestError as exc:
        sys.stderr.write(f"[ingest] {exc}\n")
        return 3
    except EvalRunnerCommitError as exc:
        sys.stderr.write(f"[commit] {exc}\n")
        return 5
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[error] {exc}\n")
        return 9

    if summary.n_qualified == 0:
        sys.stdout.write(
            "no qualified observations for date "
            f"{config.date.isoformat()}\n"
        )
        return 4

    sys.stdout.write(_render(summary) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
