"""Phase 11P.5 - Manual paper observation labeller CLI.

Computes deterministic forward-return labels for both equity (strict +
exploratory) and options paper observations. Append-only. Default
mode is --dry-run; --commit requires --confirm-commit YES.

Re-runs are idempotent. `--reprocess-provisional` finalizes rows
whose horizon has now elapsed.

Exit codes:
  0  success
  2  precondition / safety / config failure
  4  zero pending observations
  9  internal error
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from decimal import Decimal
from typing import Sequence

from apps.api.src.labeling.forward_returns import (
    DEFAULT_THRESHOLD_PCT,
    LABEL_VERSION,
)
from apps.api.src.labeling.labeller_service import (
    LabellerConfig,
    run,
)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_paper_labeller",
        description=(
            "Manual paper-observation labeller. Default: dry-run. "
            "No live execution. No model. Pure-fn forward returns."
        ),
    )
    p.add_argument(
        "--domain", default="both",
        choices=("equity", "options", "both"),
    )
    p.add_argument(
        "--as-of-date", type=lambda s: dt.date.fromisoformat(s),
        default=dt.date.today(),
    )
    p.add_argument(
        "--horizon-days", type=int, default=20,
        help="frozen at 20 in v1",
    )
    p.add_argument(
        "--threshold-pct", type=lambda s: Decimal(s),
        default=DEFAULT_THRESHOLD_PCT,
    )
    p.add_argument(
        "--reprocess-provisional", action="store_true",
        help="finalize rows whose horizon has now elapsed",
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
        cfg = LabellerConfig(
            domain=args.domain,
            as_of_date=args.as_of_date,
            horizon_days=int(args.horizon_days),
            threshold_pct=args.threshold_pct,
            dry_run=dry_run, commit=commit,
            reprocess_provisional=bool(args.reprocess_provisional),
            label_version=LABEL_VERSION,
        )
    except ValueError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return 2

    try:
        summary = run(cfg)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[error] {exc}\n")
        return 9

    n_total = summary.n_equity_observations + summary.n_options_observations
    if n_total == 0 and summary.n_updated_provisional == 0:
        sys.stdout.write("no pending observations\n")
        return 4

    label = (
        "DRY-RUN -- no DB writes"
        if cfg.dry_run else
        "COMMIT -- labels persisted"
    )
    sys.stdout.write(
        f"[summary] domain={cfg.domain} "
        f"equity_obs={summary.n_equity_observations} "
        f"options_obs={summary.n_options_observations} "
        f"inserted={summary.n_inserted} "
        f"skipped={summary.n_skipped_existing} "
        f"updated_provisional={summary.n_updated_provisional} "
        f"label_version={cfg.label_version}\n"
        f"{label}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
