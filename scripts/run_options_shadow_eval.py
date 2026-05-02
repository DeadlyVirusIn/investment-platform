"""Phase Options-1 — manual options shadow evaluator runner.

Read-only by default; persistence to options_shadow_decision_log
requires both --commit AND OPTIONS_SHADOW_EVAL_ENABLED=true. With
--dry-run (default), the runner evaluates and prints a summary
without writing.

NEVER opens options_paper_trade or paper_trade rows; the evaluator
only writes to options_shadow_decision_log.

Exit codes:
  0   evaluation completed
  2   precondition failure (config / arg parse)
  4   no chain data available for run_date
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Sequence

from loguru import logger

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.options.shadow_evaluator import evaluate


def _parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_options_shadow_eval",
        description=(
            "Run the options shadow evaluator for one date. "
            "Default --dry-run; use --commit + "
            "OPTIONS_SHADOW_EVAL_ENABLED=true to persist."
        ),
    )
    p.add_argument(
        "--date", type=lambda s: dt.date.fromisoformat(s), required=True,
    )
    p.add_argument(
        "--underlying", action="append", default=None,
        help="Restrict evaluation to one or more underlyings.",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    commit = bool(args.commit)
    if commit and not bool(settings.OPTIONS_SHADOW_EVAL_ENABLED):
        sys.stderr.write(
            "[options_shadow] OPTIONS_SHADOW_EVAL_ENABLED is False; "
            "refusing --commit. Set the env flag and retry.\n"
        )
        return 2

    persist = commit
    with SessionLocal() as session:
        summary, decisions = evaluate(
            session, run_date=args.date,
            underlyings=list(args.underlying) if args.underlying else None,
            persist=persist,
        )

    if summary.contracts_evaluated == 0:
        sys.stdout.write(
            f"[options_shadow] no contracts evaluated for {args.date}; "
            f"warnings={summary.freshness_warnings}\n"
        )
        return 4

    payload = {
        "run_date": summary.run_date.isoformat(),
        "underlying_count": summary.underlying_count,
        "contracts_evaluated": summary.contracts_evaluated,
        "would_trade_count": summary.would_trade_count,
        "blocked_reason_counts": summary.blocked_reason_counts,
        "freshness_warnings": summary.freshness_warnings,
        "inserted": summary.inserted,
        "commit": commit,
        "flag_enabled": bool(settings.OPTIONS_SHADOW_EVAL_ENABLED),
        "would_trade_top": [
            {
                "underlying": d.underlying_symbol,
                "option_symbol": d.option_symbol,
                "expiration": d.expiration.isoformat(),
                "strike": str(d.strike),
                "option_type": d.option_type,
                "score": str(d.score) if d.score is not None else None,
            }
            for d in decisions if d.would_trade
        ][:10],
    }
    sys.stdout.write(json.dumps(payload, default=str, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
