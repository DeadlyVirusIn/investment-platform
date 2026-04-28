"""Phase 11P.3 - Manual exploratory paper-only runner CLI.

Writes append-only rows to `decision_log` tagged
source='exploratory_paper'. NEVER writes to `paper_position` or
`paper_trade`. NEVER alters strict engine behaviour.

Default mode is --dry-run. --commit requires --confirm-commit YES
AND settings.EQUITY_EXPLORATORY_ENABLED must be True.

Exit codes:
  0  success
  2  precondition / safety / config failure
  4  zero days in window
  9  internal error
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Sequence

from apps.api.src.data.strategy.exploratory_runner import (
    ExploratoryConfig,
    ExploratorySafetyError,
    run,
)


DEFAULT_UNDERLYINGS = ("SPY", "QQQ", "IWM")


def _csv_upper(s: str) -> tuple[str, ...]:
    return tuple(x.strip().upper() for x in s.split(",") if x.strip())


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_exploratory_paper",
        description=(
            "Manual exploratory paper-only runner. Default: dry-run. "
            "No live trading. No scheduler. No automation."
        ),
    )
    p.add_argument(
        "--date", type=lambda s: dt.date.fromisoformat(s),
        default=dt.date.today(),
    )
    p.add_argument(
        "--underlyings", type=_csv_upper,
        default=DEFAULT_UNDERLYINGS,
    )
    p.add_argument(
        "--backfill-from", type=lambda s: dt.date.fromisoformat(s),
        default=None,
        help="historical start date for sweep; default = same as --date",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    p.add_argument("--confirm-commit", default=None)
    return p.parse_args(argv)


def _confirm(args: argparse.Namespace) -> bool:
    if not args.commit:
        return True
    if args.confirm_commit == "YES":
        return True
    if sys.stdin.isatty():
        sys.stdout.write("Type YES to confirm commit: ")
        sys.stdout.flush()
        return sys.stdin.readline().strip() == "YES"
    return False


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
        cfg = ExploratoryConfig(
            date=args.date,
            underlyings=tuple(args.underlyings),
            backfill_from=args.backfill_from,
            dry_run=dry_run, commit=commit,
        )
    except ValueError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return 2

    try:
        summary = run(cfg)
    except ExploratorySafetyError as exc:
        sys.stderr.write(f"[safety] {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[error] {exc}\n")
        return 9

    if summary.n_days == 0:
        sys.stdout.write("no business days in window\n")
        return 4

    label = (
        "DRY-RUN -- no DB writes"
        if cfg.dry_run else
        "COMMIT -- exploratory observations recorded"
    )
    sys.stdout.write(
        f"[summary] days={summary.n_days} "
        f"decisions={summary.n_decisions} "
        f"fires={summary.n_fires} "
        f"committed={summary.n_committed} "
        f"rule={summary.rule_version}\n"
        f"{label}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
