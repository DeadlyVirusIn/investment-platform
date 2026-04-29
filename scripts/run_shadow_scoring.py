"""Phase 11T - manual shadow scoring CLI.

Read-only. Default mode is --dry-run (zero file writes). --commit
writes a single JSON report under reports/. NEVER mutates DB.
NEVER mutates pickle / dataset / source tables.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Sequence

from apps.api.src.ml.shadow_report import (
    REPORTS_DIR,
    ShadowReportError,
    write_report,
)
from apps.api.src.ml.shadow_scorer import (
    BUCKET_EDGES_FROZEN,
    ScorerConfig,
    ShadowScorerError,
    run as run_scorer,
)


def _csv(s: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in s.split(",") if x.strip())


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_shadow_scoring",
        description=(
            "Read-only shadow scoring. Default: dry-run. No DB writes. "
            "No execution. No promotion. Reports under reports/ only."
        ),
    )
    p.add_argument("--model-id", required=True)
    p.add_argument(
        "--start", required=True,
        type=lambda s: dt.date.fromisoformat(s),
    )
    p.add_argument(
        "--end", required=True,
        type=lambda s: dt.date.fromisoformat(s),
    )
    p.add_argument(
        "--source", "--sources",
        dest="sources",
        type=_csv,
        default=("research_fast_fill",),
    )
    p.add_argument(
        "--domain", default="equity",
        choices=("equity", "options", "both"),
    )
    p.add_argument("--include-provisional", action="store_true")
    p.add_argument("--output-dir", default=str(REPORTS_DIR))
    p.add_argument(
        "--bucket-edges", type=_csv, default=None,
        help="frozen at 0.33,0.66; bumping requires registry-review",
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
    args = _parse(raw)

    commit = bool(args.commit)
    dry_run = not commit

    if commit and not _confirm(args):
        sys.stderr.write(
            "commit confirmation required: pass --confirm-commit "
            "YES or type YES at the interactive prompt\n",
        )
        return 2

    edges = BUCKET_EDGES_FROZEN
    if args.bucket_edges is not None:
        try:
            parts = [float(x) for x in args.bucket_edges]
            if len(parts) != 2:
                raise ValueError
            edges = (parts[0], parts[1])
        except (TypeError, ValueError):
            sys.stderr.write(
                "config error: --bucket-edges must be 'lo,hi' floats\n",
            )
            return 2

    try:
        cfg = ScorerConfig(
            model_id=str(args.model_id),
            start=args.start, end=args.end,
            sources=tuple(args.sources),
            domain=str(args.domain),
            include_provisional=bool(args.include_provisional),
            bucket_edges=edges,
            output_dir=str(args.output_dir),
            dry_run=dry_run, commit=commit,
        )
    except ValueError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return 2

    try:
        summary = run_scorer(cfg)
    except ShadowScorerError as exc:
        sys.stderr.write(f"[scorer] {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[error] {exc}\n")
        return 9

    if summary.rows_scored == 0:
        sys.stdout.write(
            "no rows scored in window\n",
        )
        return 4

    if commit:
        try:
            path = write_report(
                summary,
                sources_included=cfg.sources,
                domain=cfg.domain,
                output_dir=Path(cfg.output_dir),
            )
        except ShadowReportError as exc:
            sys.stderr.write(f"[report] {exc}\n")
            return 2
        sys.stdout.write(f"[report] {path}\n")
    label = (
        "DRY-RUN -- no report file written"
        if dry_run else
        "COMMIT -- report written"
    )
    sys.stdout.write(
        f"[summary] rows_input={summary.rows_input} "
        f"rows_scored={summary.rows_scored} "
        f"rows_with_realized_label={summary.rows_with_realized_label} "
        f"excluded={summary.rows_excluded_by_reason}\n"
        f"{label}\n",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
