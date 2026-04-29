"""Phase 11U.4 - manual drift-report CLI.

Read-only. Default mode is --dry-run. --commit writes a single JSON
report under reports/. NEVER mutates DB. NEVER edits the model
registry. NEVER mutates baseline / shadow / dataset files.

Exit codes:
  0  success
  2  precondition / safety / config / model not in registry
  3  required input file missing or unreadable
  4  insufficient_recent_data
  9  internal error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from apps.api.src.ml.drift_monitor import (
    DriftConfig,
    DriftInputError,
    DriftMonitorError,
    REPORTS_DIR,
    STATUS_INSUFFICIENT,
    run as run_drift,
    write_report,
)


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_model_drift_report",
        description=(
            "Read-only drift report. Default: dry-run. No DB writes. "
            "No registry mutation. No execution. Reports under reports/."
        ),
    )
    p.add_argument("--model-id", required=True)
    p.add_argument(
        "--baseline-report", required=True,
        type=lambda s: Path(s),
    )
    p.add_argument(
        "--shadow-report", required=True,
        type=lambda s: Path(s),
    )
    p.add_argument(
        "--baseline-dataset", default=None,
        type=lambda s: Path(s) if s else None,
    )
    p.add_argument(
        "--recent-dataset", default=None,
        type=lambda s: Path(s) if s else None,
    )
    p.add_argument(
        "--output-dir", default=str(REPORTS_DIR),
        type=lambda s: Path(s),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    p.add_argument("--confirm-commit", default=None)
    p.add_argument("--explain", action="store_true")
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
    args = _parse(raw)
    commit = bool(args.commit)
    dry_run = not commit

    if commit and not _confirm(args):
        sys.stderr.write(
            "commit confirmation required: pass --confirm-commit YES "
            "or type YES at the interactive prompt\n",
        )
        return 2

    try:
        cfg = DriftConfig(
            model_id=str(args.model_id),
            baseline_report_path=args.baseline_report,
            shadow_report_path=args.shadow_report,
            baseline_dataset_path=args.baseline_dataset,
            recent_dataset_path=args.recent_dataset,
            output_dir=args.output_dir,
            dry_run=dry_run, commit=commit,
            explain=bool(args.explain),
        )
    except ValueError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return 2

    try:
        body = run_drift(cfg)
    except DriftInputError as exc:
        sys.stderr.write(f"[input] {exc}\n")
        return 3
    except DriftMonitorError as exc:
        sys.stderr.write(f"[drift] {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[error] {exc}\n")
        return 9

    overall = body.get("overall_monitoring_status")
    if overall == STATUS_INSUFFICIENT:
        sys.stdout.write(
            f"overall_monitoring_status: {overall}\n"
        )
        if commit:
            try:
                path = write_report(cfg, body)
                sys.stdout.write(f"[report] {path}\n")
            except DriftMonitorError as exc:
                sys.stderr.write(f"[report] {exc}\n")
                return 2
        return 4

    sys.stdout.write(
        f"overall_monitoring_status: {overall}\n"
    )

    if commit:
        try:
            path = write_report(cfg, body)
        except DriftMonitorError as exc:
            sys.stderr.write(f"[report] {exc}\n")
            return 2
        sys.stdout.write(f"[report] {path}\n")
    label = (
        "DRY-RUN -- no report file written"
        if dry_run else
        "COMMIT -- report written"
    )
    sys.stdout.write(f"{label}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
