"""Phase 11R - Manual fast-fill research-mode CLI.

Generates same-day simulated paper fills tagged
`source='research_fast_fill'` for ML label generation. NEVER touches
strict paper tables. NEVER changes the strict T+1 fill model.

Usage:
    python -m scripts.run_research_fast_fill [OPTIONS]

Default mode is --dry-run. --commit requires --confirm-commit YES
or interactive TTY confirmation.

Exit codes:
  0  success
  2  precondition / safety / config failure
  4  zero days / zero candidates
  9  internal error
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Sequence

from apps.api.src.data.research.fast_fill_runner import (
    DEFAULT_MAX_PER_DAY,
    DEFAULT_UNDERLYINGS,
    HARD_MAX_PER_DAY,
    LABEL_VERSION,
    RunnerConfig,
    run,
)


def _csv_upper(s: str) -> tuple[str, ...]:
    return tuple(x.strip().upper() for x in s.split(",") if x.strip())


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_research_fast_fill",
        description=(
            "Manual fast-fill research-mode runner. Default: dry-run. "
            "No live trading. No scheduler. No automation."
        ),
    )
    p.add_argument(
        "--date", type=lambda s: dt.date.fromisoformat(s),
        default=dt.date.today(),
    )
    p.add_argument(
        "--backfill-from", type=lambda s: dt.date.fromisoformat(s),
        default=None,
    )
    p.add_argument(
        "--underlyings", type=_csv_upper,
        default=DEFAULT_UNDERLYINGS,
    )
    p.add_argument(
        "--max-per-day", type=int, default=DEFAULT_MAX_PER_DAY,
    )
    p.add_argument(
        "--label-version", default=LABEL_VERSION,
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    p.add_argument("--confirm-commit", default=None)
    p.add_argument("--explain", action="store_true")
    p.add_argument("--skip-context", action="store_true")
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
        cfg = RunnerConfig(
            date=args.date,
            backfill_from=args.backfill_from,
            underlyings=tuple(args.underlyings),
            max_per_day=int(args.max_per_day),
            label_version=str(args.label_version),
            dry_run=dry_run, commit=commit,
            explain=bool(args.explain),
            skip_context=bool(args.skip_context),
        )
    except ValueError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return 2

    try:
        summary = run(cfg)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[error] {exc}\n")
        return 9

    if summary.n_days == 0:
        sys.stdout.write("no business days in window\n")
        return 4

    label = (
        "DRY-RUN -- no DB writes"
        if cfg.dry_run else
        "COMMIT -- research fills persisted"
    )
    sys.stdout.write(
        f"[summary] days={summary.n_days} "
        f"candidates={summary.n_candidates} "
        f"filled={summary.n_filled} "
        f"skipped_no_bar={summary.n_skipped_no_bar} "
        f"committed={summary.n_committed} "
        f"skipped_existing={summary.n_skipped_existing} "
        f"label_version={cfg.label_version}\n"
        f"{label}\n"
    )
    if summary.audit_log_path:
        sys.stdout.write(
            f"audit log: {summary.audit_log_path}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
