"""Phase 11V - turnover and data-collection health report runner.

Read-only CLI. Combines turnover_diagnostic + data_collection_health
into a single JSON report under reports/. NEVER writes to DB. NEVER
mutates source files. Refuses to overwrite existing report files.

Usage:
    python -m scripts.run_turnover_report \\
        --as-of-date 2026-04-29 \\
        --lookback-days 30 \\
        --dry-run \\
        --explain

Modes:
    --dry-run   prints the report to stdout, does NOT write to disk
    (default)   writes <reports/>/turnover_<as_of>_<lookback>d.json

The report bundles:
  - per-portfolio turnover diagnostic
  - data-collection health summary
  - next-cycle prediction (close_count, free_slots_after, ...)
  - the neutral-language pledge

NEVER changes strategy / thresholds / fill SQL / scheduler /
DEFAULT_MAX_OPEN_POSITIONS / cron / API / UI.

Frozen constants:
  REPORT_VERSION = "turnover-report-v1.0.0"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from apps.api.src.db import SessionLocal
from apps.api.src.ml.data_collection_health import health_summary
from apps.api.src.ml.turnover_diagnostic import (
    diagnose_all_portfolios,
    predict_next_cycle,
)


REPORT_VERSION = "turnover-report-v1.0.0"
REPORTS_DIR = Path("reports")
NEUTRAL_PLEDGE = (
    "This report is offline diagnostic analysis only. Numbers are "
    "intended to surface stale data and stuck portfolios; they are "
    "not advice and do not direct execution."
)


class TurnoverReportError(RuntimeError):
    """Base error for the turnover report runner."""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_turnover_report",
        description=(
            "Phase 11V turnover + data-health diagnostic. "
            "Read-only. NEVER writes to DB."
        ),
    )
    p.add_argument(
        "--as-of-date",
        type=lambda s: dt.date.fromisoformat(s),
        default=dt.datetime.now(dt.timezone.utc).date(),
        help="ISO date (YYYY-MM-DD); defaults to today UTC.",
    )
    p.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Window for turnover and throughput stats.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report to stdout instead of writing to disk.",
    )
    p.add_argument(
        "--explain",
        action="store_true",
        help="Print a human-readable summary alongside the JSON.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=REPORTS_DIR,
        help="Directory to write the JSON report to.",
    )
    return p.parse_args(argv)


def report_path(
    *, as_of: dt.date, lookback_days: int, output_dir: Path,
) -> Path:
    """Frozen filename format. Pure function."""
    return output_dir / (
        f"turnover_{as_of.isoformat()}_{lookback_days}d.json"
    )


def build_report(
    session,
    *,
    as_of: dt.datetime,
    lookback_days: int,
) -> dict[str, Any]:
    """Pure read-only aggregation. Bundles diagnostic + health into
    a single JSON-serializable dict."""
    portfolios = diagnose_all_portfolios(
        session, as_of=as_of, lookback_days=lookback_days,
    )
    next_cycle = [
        {
            "portfolio_id": p["portfolio_id"],
            "portfolio_name": p["portfolio_name"],
            **predict_next_cycle(p),
        }
        for p in portfolios
    ]
    return {
        "report_version": REPORT_VERSION,
        "generated_at": dt.datetime.now(
            dt.timezone.utc,
        ).isoformat(),
        "as_of": as_of.isoformat(),
        "lookback_days": lookback_days,
        "portfolios": portfolios,
        "next_cycle_prediction": next_cycle,
        "data_collection_health": health_summary(
            session,
            as_of=as_of,
            lookback_days=lookback_days,
        ),
        "neutral_language_pledge": NEUTRAL_PLEDGE,
    }


def write_report(
    report: dict[str, Any],
    *,
    as_of: dt.date,
    lookback_days: int,
    output_dir: Path,
) -> Path:
    """Write the report to disk. Refuses to overwrite. Creates the
    output directory if missing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = report_path(
        as_of=as_of, lookback_days=lookback_days,
        output_dir=output_dir,
    )
    if path.exists():
        raise TurnoverReportError(
            f"refusing to overwrite existing report: {path}"
        )
    path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def explain(report: dict[str, Any]) -> str:
    """Render a short human-readable summary. Pure-fn."""
    lines: list[str] = []
    lines.append(
        f"=== Turnover Report (as_of={report['as_of']}, "
        f"lookback={report['lookback_days']}d) ==="
    )
    if not report["portfolios"]:
        lines.append("(no active portfolios)")
    for p in report["portfolios"]:
        lines.append(
            f"\nPortfolio: {p['portfolio_name']} "
            f"({p['portfolio_id']})"
        )
        lines.append(
            f"  open={p['open_positions_count']}/"
            f"{p['max_open_positions']}, "
            f"free_slots={p['free_slots']}, "
            f"pending_exits={p['pending_exits_count']}, "
            f"expected_after_next_run="
            f"{p['expected_slots_after_next_run']}"
        )
        if p.get("blocked_buys_reason"):
            lines.append(
                f"  blocked_buys: {p['blocked_buys_reason']}"
            )
        lw = p["lookback_window"]
        lines.append(
            f"  window: buys={lw['buys_count']}, "
            f"sells={lw['sells_count']}, "
            f"turnover_ratio={lw['turnover_ratio']}, "
            f"realized_pnl={lw['realized_pnl_total']}"
        )
        for ex in p["pending_exits"][:5]:
            lines.append(
                f"    pending_exit: {ex.get('symbol') or ex['asset_id']} "
                f"age={ex['age_days']}d "
                f"latest_action={ex['latest_action']} "
                f"reason={ex['reason']}"
            )
    h = report["data_collection_health"]
    pb = h["price_bar"]
    lines.append(
        f"\nData health: price_bar fresh={pb['fresh_count']}, "
        f"stale={pb['stale_count']}, missing={pb['missing_count']}"
    )
    cd = h["context_daily"]
    lines.append(
        f"  context_daily: all_present={cd['all_present']}"
    )
    if cd["missing_gates"]:
        lines.append(
            f"    missing_gates: {cd['missing_gates']}"
        )
    rec = h["recommendations"]
    lines.append(
        f"  recommendations: total={rec['total']} "
        f"by_action={rec['by_action']}"
    )
    ci = h["candidate_ideas"]
    lines.append(
        f"  candidate_ideas: total={ci['total']} "
        f"days_with_data={ci['days_with_data']}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    as_of_dt = dt.datetime.combine(
        args.as_of_date, dt.time(15, 0), tzinfo=dt.timezone.utc,
    )
    with SessionLocal() as session:
        report = build_report(
            session,
            as_of=as_of_dt,
            lookback_days=args.lookback_days,
        )
    if args.explain:
        print(explain(report))
        print()
    if args.dry_run:
        print(json.dumps(report, indent=2, default=str))
        return 0
    path = write_report(
        report,
        as_of=args.as_of_date,
        lookback_days=args.lookback_days,
        output_dir=args.output_dir,
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
